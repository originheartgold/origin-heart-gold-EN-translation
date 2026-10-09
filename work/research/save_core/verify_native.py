#!/usr/bin/env python3
"""Reproduce local save-core native evidence; never download inputs or build a ROM.

All four binary inputs require explicit SHA-256 pins in a local JSON manifest.
Run --plan first to inspect the exact subprocesses. Reports/fixtures stay ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
INPUTS = ('cn', 'en', 'seed', 'shim')
GROUPS = ('loader', 'harness', 'persistence')


def identity(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path), 'sha256': digest.hexdigest(), 'size': path.stat().st_size}


def load_manifest(path):
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or set(raw) != {'repo', 'inputs'}:
        raise ValueError('Manifest requires exactly repo and inputs')
    repo = Path(raw['repo']).expanduser().resolve()
    python = repo / '.venv/bin/python'
    if not python.is_file():
        raise ValueError(f'Existing project interpreter missing: {python}')
    if not isinstance(raw['inputs'], dict) or set(raw['inputs']) != set(INPUTS):
        raise ValueError('Manifest inputs must be exactly cn, en, seed, shim')
    checked = {}
    for name in INPUTS:
        item = raw['inputs'][name]
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise ValueError(f'{name} requires exactly path and sha256')
        if not isinstance(item['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
            raise ValueError(f'{name}: expected lowercase SHA-256 pin')
        actual = identity(Path(item['path']).expanduser().resolve())
        if actual['sha256'] != item['sha256']:
            raise ValueError(f'{name}: SHA-256 mismatch; expected {item["sha256"]}, got {actual["sha256"]}')
        checked[name] = actual
    if len({row['path'] for row in checked.values()}) != len(INPUTS):
        raise ValueError('Binary inputs must have distinct paths')
    if checked['seed']['size'] != 524288:
        raise ValueError('Seed must be a raw 512 KiB save')
    return {'repo': str(repo), 'python': str(python), 'inputs': checked}


def check_inputs(manifest):
    for name, old in manifest['inputs'].items():
        if identity(Path(old['path'])) != old:
            raise ValueError(f'{name}: source input changed during verification')


def make_plan(manifest, run_id, groups=GROUPS, timeout=600):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}', run_id):
        raise ValueError('Run ID must be 1–80 letters, digits, underscores or hyphens')
    if not groups or set(groups) - set(GROUPS):
        raise ValueError('Select at least one known verification group')
    if type(timeout) is not int or timeout <= 0:
        raise ValueError('Timeout must be a positive integer')
    build = ROOT / 'work/build' / ('save-core-native-' + run_id)
    local = ROOT / 'work/save-editor/local' / ('shared-core-native-' + run_id)
    fixture = local / 'fixture'
    python = manifest['python']
    seed = manifest['inputs']['seed']['path']
    scripts = ROOT / 'work/research/save_core'
    stages = []

    def stage(name, group, command, report=None, validator='passed', depends=()):
        stages.append({'name': name, 'group': group, 'command': list(map(str, command)),
                       'report': str(report) if report else None, 'validator': validator,
                       'depends': ([] if group == 'preflight' else ['core-preflight']) + list(depends), 'timeout': timeout,
                       'selected': group == 'preflight' or group in groups})

    stage('core-preflight', 'preflight', [python, '-c',
          'import sys,json; sys.path.insert(0,"work/tools"); import save_core; '
          'print(json.dumps(save_core.request("handshake")))'], validator='exit')
    stages[-1]['timeout'] = min(timeout, 30)
    for language in ('cn', 'en'):
        out = build / ('loader-' + language)
        stage('loader-' + language, 'loader', [python, scripts / 'native_loader_probe.py',
              '--rom', manifest['inputs'][language]['path'], '--seed', seed, '--out', out],
              out / 'report.json', 'loader')
        stage('parity-' + language, 'loader', [python, scripts / 'native_parity.py', out / 'report.json'],
              validator='exit', depends=('loader-' + language,))
        out = build / ('harness-' + language)
        stage('harness-' + language, 'harness', [python, scripts / 'harness_runtime.py',
              '--rom', manifest['inputs'][language]['path'], '--seed', seed, '--out', out,
              '--expect-generator-invalid'], out / 'report.json', 'harness')
        out = build / ('harness-short-' + language)
        stage('harness-short-' + language, 'harness', [python, scripts / 'harness_runtime.py',
              '--rom', manifest['inputs'][language]['path'], '--seed', seed, '--out', out,
              '--party-count', '3'], out / 'report.json', 'harness-valid')
    stage('combined-fixture', 'persistence', ['node', scripts / 'runtime_fixture.mjs', seed, fixture],
          fixture / 'report.json', 'fixture')
    for language in ('cn', 'en'):
        out = local / ('persistence-' + language)
        command = [python, ROOT / 'work/save-editor/scripts/verify-runtime.py',
                   '--repo', manifest['repo'], '--rom', manifest['inputs'][language]['path'],
                   '--save', fixture / 'edited.sav', '--out', out, '--observe-traits', '--persistence',
                   '--timeout', str(max(1, timeout - 15))]
        for option, filename in (('--expect', 'moves'), ('--expect-stats', 'stats'),
                                 ('--expect-traits', 'traits'), ('--expect-inventory', 'inventory')):
            command.extend([option, fixture / (filename + '.json')])
        stage('persistence-' + language, 'persistence', command, out / 'report.json',
              'persistence', ('combined-fixture',))
    return {'build': str(build), 'local': str(local), 'stages': stages}


def validate_report(stage):
    kind = stage['validator']
    if kind == 'exit':
        return
    data = json.loads(Path(stage['report']).read_text())
    if not isinstance(data, dict):
        raise ValueError('Evidence report must be a JSON object')
    if kind == 'loader':
        # The following parity stage checks the native observations themselves.
        from native_loader_probe import CASES
        if (data.get('inputs_unchanged') is not True or not isinstance(data.get('rows'), list)
                or any(not isinstance(row, dict) or not isinstance(row.get('case'), str) for row in data['rows'])
                or sorted(row['case'] for row in data['rows']) != sorted(CASES)):
            raise ValueError('Loader report is incomplete or contains duplicate cases')
    elif kind == 'fixture':
        if data.get('sourceUnchanged') is not True or data.get('changedBytes', 0) <= 0:
            raise ValueError('Fixture report lacks source integrity/change evidence')
    elif kind == 'persistence':
        if (data.get('status') != 'passed' or data.get('gaps') != []
                or data.get('in_game_save_reload') != 'passed'):
            raise ValueError('Persistence report is incomplete or has evidence gaps')
    elif kind in ('harness', 'harness-valid'):
        expected_generator = 'valid' if kind == 'harness-valid' else 'invalid native output safely rejected'
        if (data.get('status') != 'passed' or data.get('inputs_unchanged') is not True
                or not isinstance(data.get('native_generator'), dict)
                or data['native_generator'].get('status') != expected_generator):
            raise ValueError('Harness report lacks expected native-generator evidence')
    else:
        raise ValueError('Unknown report validator')


def run_process(command, *, cwd, env, timeout, stdout, stderr):
    """Bound a whole subprocess tree, including native verifier worker children."""
    with Path(stdout).open('xb') as out, Path(stderr).open('xb') as err:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=out, stderr=err,
                                   start_new_session=True)
        try:
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise


def reference_provenance(manifest):
    """Record the optional provenance gate separately from named native scenarios."""
    source = ROOT / 'work/save-editor/src/generated-reference.ts'
    try:
        match = re.search(r'"romSha256"\s*:\s*"([0-9a-f]{64})"', source.read_text())
        expected = match.group(1) if match else None
    except OSError:
        expected = None
    actual = manifest['inputs']['en']['sha256']
    return {'status': 'skipped', 'bundled_rom_sha256': expected, 'native_en_sha256': actual,
            'rom_hash_matches': expected == actual if expected else None,
            'reason': 'This command verifies named native scenarios, not the separate bundled-reference provenance gate; '
                      + ('the pinned English ROM differs from the bundle' if expected and expected != actual
                         else 'run the optional reference-data provenance test with its pinned ROM')}


def execute(manifest, plan, run=run_process, validator=validate_report):
    build, local = Path(plan['build']), Path(plan['local'])
    # Refuse reuse, including symlinks. Never delete or overwrite an earlier run.
    if build.exists() or build.is_symlink() or local.exists() or local.is_symlink():
        raise ValueError('Run output already exists; choose a new run ID')
    build.mkdir(parents=True)
    local.mkdir(parents=True)
    env = dict(os.environ, EMU_HARNESS_DATA=str(Path(manifest['repo']) / 'work'),
               MELONDS_SHIM=manifest['inputs']['shim']['path'], PYTHONDONTWRITEBYTECODE='1')
    env.pop('PYTHONOPTIMIZE', None)  # Probe assertions are evidence gates, never optional.
    report = {'status': 'running', 'scope': 'named native scenarios only',
              'reference_provenance': reference_provenance(manifest),
              'inputs': manifest['inputs'], 'stages': [],
              'inputs_unchanged': False,
              'generator_policy': 'Six-member scenario must safely reject its pre-existing invalid output; three-member scenario must produce an independently valid record; never repair native records'}
    report_path = build / 'report.json'

    def publish():
        temp = report_path.with_suffix('.json.tmp')
        temp.write_text(json.dumps(report, indent=2) + '\n')
        temp.replace(report_path)

    publish()
    for stage in plan['stages']:
        row = dict(stage, status='skipped')
        report['stages'].append(row)
        if not stage['selected']:
            row['reason'] = 'Group not selected explicitly'
        elif any(not any(r['name'] == dep and r['status'] == 'passed' for r in report['stages'])
                 for dep in stage['depends']):
            row['reason'] = 'Required earlier stage did not pass'
        else:
            start = time.monotonic()
            row['status'] = 'running'
            publish()
            row['stdout'] = str(build / (stage['name'] + '.stdout.log'))
            row['stderr'] = str(build / (stage['name'] + '.stderr.log'))
            try:
                check_inputs(manifest)
                code = run(stage['command'], cwd=ROOT, env=env, timeout=stage['timeout'],
                           stdout=row['stdout'], stderr=row['stderr'])
                row['returncode'] = code
                if code != 0:
                    raise ValueError(f'Subprocess exited {code}')
                validator(stage)
                check_inputs(manifest)
                row['status'] = 'passed'
            except subprocess.TimeoutExpired:
                row.update(status='failed', reason=f'Stage exceeded {stage["timeout"]} seconds')
            except (OSError, ValueError, TypeError, KeyError) as error:
                row.update(status='failed', reason=str(error))
            row['seconds'] = round(time.monotonic() - start, 3)
        print(f'{row["name"]}: {row["status"]}' + (': ' + row['reason'] if 'reason' in row else ''), flush=True)
        publish()
    try:
        check_inputs(manifest)
        report['inputs_unchanged'] = True
    except (OSError, ValueError) as error:
        report['input_error'] = str(error)
    statuses = [row['status'] for row in report['stages']]
    report['status'] = ('failed' if 'failed' in statuses or not report['inputs_unchanged']
                        else 'incomplete' if 'skipped' in statuses else 'passed')
    report['counts'] = {status: statuses.count(status) for status in ('passed', 'failed', 'skipped')}
    publish()
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', required=True, type=Path, help='Local manifest containing repo and four path/SHA-256 pairs')
    parser.add_argument('--run-id', required=True, help='Unique output suffix; existing runs are never overwritten')
    parser.add_argument('--only', choices=GROUPS, nargs='+', help='Selected groups; omitted groups remain explicitly skipped')
    parser.add_argument('--timeout', type=int, default=600, help='Per-stage wall-clock limit, including child processes')
    parser.add_argument('--plan', action='store_true', help='Verify input pins and show commands without starting emulation')
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest(args.inputs)
        plan = make_plan(manifest, args.run_id, args.only or GROUPS, args.timeout)
        if args.plan:
            print(json.dumps({'status': 'planned', 'inputs': manifest['inputs'], **plan}, indent=2))
            return 0
        result = execute(manifest, plan)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'Native verification preflight failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps({'status': result['status'], 'counts': result['counts'],
                      'report': str(Path(plan['build']) / 'report.json')}))
    return 0 if result['status'] == 'passed' else 2 if result['status'] == 'incomplete' else 1


if __name__ == '__main__':
    sys.exit(main())
