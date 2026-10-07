"""Account for every message's controls, expansion and evidenced consumer limits.

Unknown consumers remain gaps. This ledger deliberately does not equate a
structurally valid message, or a known consumer passing, with universal safety.

Approved exceptions live in text_static_exceptions.json beside this file. An
entry waives one control finding on one string only when ref, code and the
source/candidate command lists match exactly, and must cite decisions. Waived
findings stay in the ledger under 'waived'; an entry that matches nothing is an
error, so stale exceptions cannot hide later changes.
"""
from collections import Counter
import json
from pathlib import Path

import msgtool as m
from text_control_check import check_controls
from text_expansion_check import measure_expansion, inspect_formatter_engine, measure_contract_expansion
from text_reference_check import inspect_references

NARCS = {'a027': 'a/0/2/7', 'battle_string': 'battle/string/battle_string.narc'}
EXCEPTIONS = Path(__file__).with_name('text_static_exceptions.json')


def _norm(value):
    return json.loads(json.dumps(value))


def load_exceptions(path=EXCEPTIONS):
    """Return {ref: [entry, ...]}; reject malformed entries rather than ignore them."""
    document = json.loads(Path(path).read_text())
    if document.get('schema') != 1 or not isinstance(document.get('exceptions'), list):
        raise ValueError('text_static exceptions: unsupported schema')
    result = {}
    for entry in document['exceptions']:
        if (not isinstance(entry, dict) or entry.get('check') != 'controls' or not isinstance(entry.get('ref'), str)
                or not entry.get('code') or 'source' not in entry or 'candidate' not in entry
                or not isinstance(entry.get('decisions'), list) or not entry['decisions'] or not entry.get('reason')):
            raise ValueError(f'text_static exceptions: invalid entry {entry!r}')
        result.setdefault(entry['ref'], []).append(entry)
    return result


def waive_controls(controls, entries):
    """Move exactly matching findings to 'waived' and recompute the control status."""
    if not entries or not controls.get('findings'):
        return controls
    kept, waived = [], []
    for finding in controls['findings']:
        normal = _norm(finding)
        match = next((e for e in entries if e['code'] == normal.get('code') and e['source'] == normal.get('source')
                      and e['candidate'] == normal.get('candidate')), None)
        if match is None:
            kept.append(finding)
        else:
            match['_used'] = True
            waived.append({'finding': finding, 'decisions': match['decisions'], 'reason': match['reason']})
    if waived:
        controls = dict(controls, findings=kept, waived=waived)
        controls['status'] = 'failed' if kept else 'incomplete' if controls['gaps'] or controls['baseline_findings'] else 'passed'
    return controls


def status_of(errors, gaps):
    return 'failed' if errors else 'incomplete' if gaps else 'passed'


def apply_capacities(units, expansion, contracts, bank, sid):
    results = []
    for contract in contracts:
        if contract.get('bank') != bank or (contract.get('ids') is not None and sid not in contract['ids']):
            continue
        stage = contract.get('stage')
        capacity = contract.get('capacity_units')
        context_expansion = measure_contract_expansion(units, contract) if stage == 'expanded' else expansion
        measured = len(units) if stage == 'stored' else context_expansion.get('expanded_units') if stage == 'expanded' else expansion.get('decoded_units') if stage in ('decoded', 'decompressed') else None
        reason = None
        if contract.get('status', 'incomplete') != 'passed' and contract.get('evidence_level') != 'policy_only':
            reason = 'consumer_guard_unproven'
        elif type(capacity) is not int or capacity <= 0:
            reason = 'invalid_capacity_contract'
        elif stage in ('decoded', 'decompressed') and expansion.get('commands'):
            reason = 'decoded_name_contains_commands'
        elif type(measured) is not int:
            reason = 'expansion_or_stage_unresolved'
        overflow = reason is None and measured > capacity
        proven = contract.get('evidence_level') == 'rom_guarded'
        results.append({'contract': contract.get('id', contract.get('evidence', bank)), 'stage': stage,
                        'capacity_units': capacity, 'measured_units': measured,
                        'status': 'incomplete' if reason else 'failed' if overflow else 'passed' if proven else 'incomplete',
                        'reason': reason or ('capacity_exceeded' if overflow else None if proven else 'policy_only_capacity')})
    return results


def assess_record(original, units, ref, contracts, bounds=None, exceptions=None):
    bank, sid = ref.split('#')
    controls = waive_controls(check_controls(original, units, ref), (exceptions or {}).get(ref))
    expansion = measure_expansion(units, bounds)
    capacity = apply_capacities(units, expansion, contracts, bank, int(sid))
    baseline = {c['contract']: c for c in apply_capacities(original, measure_expansion(original, bounds), contracts, bank, int(sid))}
    for result in capacity:
        result['source_status'] = baseline.get(result['contract'], {}).get('status', 'incomplete')
        result['inherited'] = result['status'] == 'failed' and result['source_status'] == 'failed'
    errors = []
    gaps = ['consumer_discovery_incomplete']
    for name, result in (('controls', controls), ('expansion', expansion)):
        if result.get('status') == 'failed':
            errors.append(name)
        elif result.get('status') != 'passed':
            gaps.append(name)
    if any(c['status'] == 'failed' and not c['inherited'] for c in capacity):
        errors.append('capacity')
    if not capacity:
        gaps.append('no_capacity_contract')
    elif any(c['status'] != 'passed' for c in capacity):
        gaps.append('capacity')
    return {'status': status_of(errors, gaps), 'controls': controls['status'],
            'stored_units': len(units), 'decoded_units': expansion.get('decoded_units'),
            'expanded_units': expansion.get('expanded_units'), 'capacity': capacity,
            'errors': errors, 'gaps': gaps, 'waived': controls.get('waived', []),
            'control_details': controls if controls['status'] != 'passed' or controls.get('waived') else None,
            'expansion_details': expansion if expansion['status'] != 'passed' else None}



def inspect_hardcoded_workspace(cm, contracts):
    import hardcoded
    document = hardcoded.load()  # [[string]] entries of the enabled fixes in work/patches
    rows, errors = [], []
    expected = {c['id']: c for c in contracts if c.get('bank') == 'hardcoded'}
    ids = [e.get('id') for e in document['strings']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        errors.append({'code': 'hardcoded_inventory_mismatch'})
    for entry in document['strings']:
        ref = entry['id']
        try:
            before, after = m.encode_text(entry['zh'], cm), m.encode_text(entry['en'], cm)
            controls = check_controls(before, after, ref)
            expansion = measure_expansion(after)
            contract = expected.get(ref, {})
            cap = contract.get('capacity_units')
            length = expansion.get('expanded_units')
            overflow = type(cap) is int and type(length) is int and length > cap
            rows.append({'ref': ref, 'status': 'failed' if overflow or controls['status'] == 'failed' or expansion['status'] == 'failed' else 'incomplete',
                         'capacity_units': cap, 'expanded_units': length, 'controls': controls,
                         'reason': 'capacity_exceeded' if overflow else 'consumer_capacity_policy_only'})
        except Exception as exc:
            errors.append({'ref': ref, 'code': 'hardcoded_unreadable', 'reason': str(exc)})
    return {'status': 'failed' if errors or any(r['status'] == 'failed' for r in rows) else 'incomplete',
            'counts': {'strings': len(rows)}, 'records': rows, 'errors': errors}


def inspect_safety(source_path, candidate_path, export_dir, output_dir):
    from text_consumer_check import inspect_consumers
    source, candidate = m.load_rom(source_path), m.load_rom(candidate_path)
    cm = m.Charmap.load([Path(__file__).with_name('charmap_en.tsv'), Path(__file__).parent/'charmaps/charmap_zh_xzonn_gen4.tsv'])
    def capture(call):
        try:
            return call()
        except (Exception, SystemExit) as exc:
            return {'status': 'incomplete', 'contracts': [], 'gaps': [{'code': 'consumer_evidence_unavailable', 'reason': str(exc)}]}
    engines = {}
    for label, rom in (('source', source), ('candidate', candidate)):
        def engine(rom=rom):
            section = rom.loadArm9().sections[0]
            return inspect_formatter_engine(section.data, section.ramAddress)
        engines[label] = capture(engine)
    consumers = {'source': capture(lambda: inspect_consumers(source_path)), 'candidate': capture(lambda: inspect_consumers(candidate_path))}
    source_failures = {(r['ref'], r['contract']) for r in consumers['source'].get('findings', [])}
    for finding in consumers['candidate'].get('findings', []):
        finding['inherited'] = (finding['ref'], finding['contract']) in source_failures
    contracts = consumers['candidate'].get('contracts', [])
    hardcoded_workspace = inspect_hardcoded_workspace(cm, contracts)
    ledger, errors, counts, banks = [], [], Counter(), {}
    exception_errors = []
    try:
        exceptions = load_exceptions()
    except (OSError, ValueError) as exc:
        exceptions = {}
        exception_errors.append({'ref': str(EXCEPTIONS.name), 'code': 'exceptions_unreadable', 'reason': str(exc)})
    source_counts, candidate_counts = [], []
    for archive, path in NARCS.items():
        originals = m.Narc.parse(m.get_file(source, path)).files
        candidates = m.Narc.parse(m.get_file(candidate, path)).files
        if len(originals) != len(candidates):
            errors.append({'ref': archive, 'code': 'bank_count_changed'})
        for bi in range(max(len(originals), len(candidates))):
            bank = f'{archive}/{bi:04d}'
            counts['banks'] += 1
            if bi >= len(originals) or bi >= len(candidates):
                errors.append({'ref': bank, 'code': 'bank_missing_on_one_side'})
                continue
            try:
                _, before, _ = m.decrypt_bank(originals[bi])
                _, after, _ = m.decrypt_bank(candidates[bi])
                if archive == 'a027':
                    source_counts.append(len(before)); candidate_counts.append(len(after))
                exported = json.loads((Path(export_dir)/archive/f'{bi:04d}.json').read_text())
                _, pending, _ = m.decrypt_bank(m.json_to_bank(exported, cm))
            except Exception as exc:
                errors.append({'ref': bank, 'code': 'bank_unreadable', 'reason': str(exc)})
                continue
            summary = Counter(strings=len(before))
            for sid in range(max(len(before), len(after), len(pending))):
                ref = f'{bank}#{sid}'
                counts['strings'] += 1
                if any(sid >= len(seq) for seq in (before, after, pending)):
                    errors.append({'ref': ref, 'code': 'string_missing_on_one_side'})
                    ledger.append({'ref': ref, 'status': 'failed', 'reason': 'string_missing_on_one_side'})
                    continue
                row = {'ref': ref}
                for label, units in (('candidate', after[sid]), ('workspace', pending[sid])):
                    result = assess_record(before[sid], units, ref, contracts, exceptions=exceptions)
                    if result['waived']:
                        counts[f'{label}_waived'] += 1
                    row[label] = result
                    summary[f'{label}_{result["status"]}'] += 1
                    counts[f'{label}_{result["status"]}'] += 1
                    counts[f'{label}_controls_{result["controls"]}'] += 1
                    if result['expanded_units'] is not None:
                        counts[f'{label}_expansion_bounded'] += 1
                    if result['capacity']:
                        counts[f'{label}_with_capacity_contract'] += 1
                    if any(c['status'] == 'failed' for c in result['capacity']):
                        counts[f'{label}_capacity_failures'] += 1
                ledger.append(row)
            banks[bank] = dict(summary)
    applied = []
    for ref, entries in sorted(exceptions.items()):
        for entry in entries:
            if entry.pop('_used', False):
                applied.append({'ref': ref, 'code': entry['code'], 'decisions': entry['decisions']})
            else:
                exception_errors.append({'ref': ref, 'code': 'unused_exception', 'reason': 'exception matches no finding; remove or update it'})
    try:
        if errors:
            raise ValueError('Message inventory incomplete; bank indices cannot be trusted for reference analysis')
        references = inspect_references(source, candidate, source_counts, candidate_counts)
    except (Exception, SystemExit) as exc:
        references = {'status': 'incomplete', 'gaps': [{'code': 'reference_scan_unavailable', 'reason': str(exc)}]}
    errors.extend(exception_errors)
    path = Path(output_dir)/'text-safety-ledger.json'
    path.write_text(json.dumps({'records': ledger, 'banks': banks}, separators=(',', ':'))+'\n')
    failed = bool(errors or counts['candidate_failed'] or counts['workspace_failed'] or references['status'] == 'failed'
                  or any(not f['inherited'] for f in consumers['candidate'].get('findings', [])) or hardcoded_workspace['status'] == 'failed')
    return {'status': 'failed' if failed else 'incomplete', 'counts': dict(counts), 'errors': errors,
            'gaps': [{'code': 'consumer_discovery_incomplete', 'reason': 'Every message is inventoried; complete consumer and dynamic target coverage is not yet established.'},
                     {'code': 'graphics_text_outside_message_pipeline', 'reason': 'Baked-in text requires existing graphics artifact/layout checks.'}],
            'exceptions': applied, 'formatter_engines': engines, 'consumers': consumers, 'hardcoded_workspace': hardcoded_workspace, 'references': references, 'ledger': str(path),
            'scope': 'All source/candidate message records and fresh workspace export; known hardcoded strings in consumer report; static safety is not universal gameplay certification.'}
