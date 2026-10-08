#!/usr/bin/env python3
"""Read-only static text safety gate for an existing English ROM; never builds one."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import msgtool as m
import text_binary_check as binary
from text_inventory_check import check_inventory
import ws

WORK = Path(__file__).resolve().parent.parent
NARCS = {'a027': 'a/0/2/7', 'battle_string': 'battle/string/battle_string.narc'}


def aggregate(checks):
    if not checks:
        return 'incomplete'
    statuses = [value.get('status') for value in checks.values()]
    if 'failed' in statuses:
        return 'failed'
    return 'passed' if all(s == 'passed' for s in statuses) else 'incomplete'


def aggregate_report(report):
    """Fail closed on absent proof even if a supplied summary says passed."""
    checks = report.get('checks', {})
    required = {'inventory', 'binary', 'boundary', 'safety', 'input_stability'}
    if not isinstance(checks, dict):
        return 'incomplete'
    if any(isinstance(v, dict) and v.get('status') == 'failed' for v in checks.values()):
        return 'failed'
    if not required.issubset(checks) or any(not isinstance(v, dict) for v in checks.values()):
        return 'incomplete'
    if aggregate(checks) != 'passed':
        return 'incomplete'
    required_counts = {'safety': ('banks', 'strings'), 'inventory': ('banks', 'strings'), 'binary': ('banks', 'records'), 'boundary': ('files_compared', 'attributes_compared')}
    for key, names in required_counts.items():
        counts = checks[key].get('counts', {})
        if not isinstance(counts, dict) or any(type(counts.get(n)) is not int or counts[n] <= 0 for n in names):
            return 'incomplete'
        if checks[key].get('errors') or checks[key].get('gaps'):
            return 'incomplete'
    if any(checks['safety']['counts'].get(k) != checks['inventory']['counts'].get(k) for k in ('banks', 'strings')):
        return 'incomplete'
    if checks['boundary']['counts'].get('message_payloads_deferred') != len(NARCS):
        return 'incomplete'
    findings = checks['binary'].get('findings')
    if not isinstance(findings, dict) or not findings:
        return 'incomplete'
    if any(not isinstance(v, dict) for v in findings.values()):
        return 'incomplete'
    if any(v.get('status') == 'failed' or v.get('errors') for v in findings.values()):
        return 'failed'
    if any(v.get('status') != 'passed' or v.get('gaps') for v in findings.values()):
        return 'incomplete'
    if checks['input_stability'].get('unchanged') is not True:
        return 'incomplete'
    before, after = report.get('inputs_before'), report.get('inputs_after')
    labels = {'source', 'candidate', 'us', 'workspace', 'extract', 'tools', 'graphics', 'patches', 'reference_mapping'}
    if not isinstance(before, dict) or set(before) != labels or before != after:
        return 'incomplete'
    for snapshot in before.values():
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get('files'), dict) or not snapshot['files']:
            return 'incomplete'
        for entry in snapshot['files'].values():
            if not isinstance(entry, dict) or type(entry.get('size')) is not int or entry['size'] < 0 or not isinstance(entry.get('sha256'), str) or len(entry['sha256']) != 64 or any(c not in '0123456789abcdef' for c in entry['sha256']):
                return 'incomplete'
    return 'passed'


def capture_inputs(paths):
    result = {}
    for label, path in paths.items():
        path = Path(path)
        files = sorted(p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc') if path.is_dir() else [path]
        result[label] = {'path': str(path.resolve()), 'files': {}}
        for item in files:
            key = str(item.relative_to(path)) if path.is_dir() else '.'
            digest = hashlib.sha256()
            with item.open('rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024), b''):
                    digest.update(chunk)
            result[label]['files'][key] = {'size': item.stat().st_size, 'sha256': digest.hexdigest()}
    return result


def guarded(call):
    try:
        value = call()
        if not isinstance(value, dict) or value.get('status') not in ('passed', 'failed', 'incomplete'):
            return {'status': 'incomplete', 'errors': ['checker returned no valid status']}
        return value
    except Exception as exc:
        return {'status': 'failed', 'errors': [f'{type(exc).__name__}: {exc}']}


def load_members(path):
    rom = m.load_rom(path)
    return {key: m.Narc.parse(m.get_file(rom, name)).files for key, name in NARCS.items()}


def binary_check(paths):
    findings, counts = {}, {'banks': 0, 'records': 0}
    for label, path in paths.items():
        try:
            rom = m.load_rom(path)
        except Exception as exc:
            findings[label] = {'status': 'failed', 'errors': [str(exc)]}
            continue
        for key, name in NARCS.items():
            ref = f'{label}/{key}'
            try:
                narc = binary.inspect_narc(m.get_file(rom, name))
                findings[ref] = {k: v for k, v in narc.items() if k != 'members'}
                for member in narc['members']:
                    result = binary.inspect_bank(member['data'])
                    counts['banks'] += 1
                    counts['records'] += result['count'] or 0
                    findings[f'{ref}/{member["id"]:04d}'] = {k: v for k, v in result.items() if k != 'records'}
            except Exception as exc:
                findings[ref] = {'status': 'failed', 'errors': [str(exc)]}
    return {'status': aggregate(findings), 'counts': counts, 'findings': findings}


def run(source, candidate, us, workspace, extract, output, statuses=('tm', 'draft', 'reviewed')):
    output = Path(output).resolve()
    build = (WORK / 'build').resolve()
    if not output.is_relative_to(build) or output == build:
        raise ValueError('output must be a new directory beneath work/build')
    output.mkdir(parents=True, exist_ok=False)
    inputs = dict(source=source, candidate=candidate, us=us, workspace=workspace, extract=extract, tools=WORK/'tools', graphics=WORK/'graphics', patches=WORK/'patches', reference_mapping=WORK/'translate/scripts/build_bank_maps.py')
    report = {'schema': 1, 'statuses': list(statuses), 'checks': {}, 'scope': 'existing artifacts; no ROM built or repaired'}
    try:
        report['inputs_before'] = capture_inputs(inputs)
        if not __debug__:
            report['checks']['environment'] = {'status': 'failed', 'errors': ['Python -O disables production helper assertions']}
        else:
            def inventory():
                counts, problems = ws.export(Path(workspace), Path(extract), output / 'export', statuses, False, list(NARCS))
                cm = m.Charmap.load([str(WORK / 'tools/charmap_en.tsv'), str(WORK / 'tools/charmaps/charmap_zh_xzonn_gen4.tsv')])
                result = check_inventory(load_members(source), load_members(candidate), output / 'export', cm, workspace)
                result['export_counts'] = dict(counts)
                result['export_problems'] = problems
                if problems:
                    result['status'] = 'failed'
                return result
            report['checks']['inventory'] = guarded(inventory)
            report['checks']['binary'] = guarded(lambda: binary_check({'source': source, 'candidate': candidate}))
            def boundary():
                from text_boundary_check import check_boundary
                return check_boundary(source, candidate, us)
            report['checks']['boundary'] = guarded(boundary)
            def safety():
                from text_safety_check import inspect_safety
                return inspect_safety(source, candidate, output / 'export', output)
            report['checks']['safety'] = guarded(safety)
    except Exception as exc:
        report['checks']['inputs'] = {'status': 'failed', 'errors': [f'{type(exc).__name__}: {exc}']}
    finally:
        try:
            report['inputs_after'] = capture_inputs(inputs)
            unchanged = report.get('inputs_before') == report['inputs_after']
            report['checks']['input_stability'] = {'status': 'passed' if unchanged else 'failed', 'unchanged': unchanged}
        except Exception as exc:
            report['checks']['input_stability'] = {'status': 'failed', 'errors': [str(exc)]}
        report['status'] = aggregate_report(report)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=WORK/'rom/origin_v4.0.3_cn.nds')
    parser.add_argument('--candidate', '--rom', type=Path, default=WORK/'build/origin_hg_v4.0.3_en_wip.nds')
    parser.add_argument('--us', type=Path, default=WORK/'rom/Pokemon - HeartGold Version (USA).nds')
    parser.add_argument('--ws', type=Path, default=ws.DEFAULT_WS)
    parser.add_argument('--extract', type=Path, default=ws.DEFAULT_EXTRACT)
    parser.add_argument('--statuses', default='tm,draft,reviewed')
    parser.add_argument('--output', type=Path, default=WORK/'build/static-text'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ'))
    parser.add_argument('--json', type=Path, help='additional report path beneath work/build')
    args = parser.parse_args(argv)
    if args.json is not None and (not args.json.resolve().is_relative_to((WORK/'build').resolve()) or args.json.exists()):
        parser.error('--json must be a new file beneath work/build')
    report = run(args.source, args.candidate, args.us, args.ws, args.extract, args.output, tuple(args.statuses.split(',')))
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'checks': {k: v['status'] for k,v in report['checks'].items()}, 'report': str(args.output/'report.json')}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
