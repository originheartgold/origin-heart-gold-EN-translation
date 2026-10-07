#!/usr/bin/env python3
"""Read-only, bounded consumer checks; a checked consumer is not exhaustive coverage."""
import json
from pathlib import Path
import struct
import msgtool
import text_buffer_check
from text_expansion_check import measure_contract_expansion
from text_capacity_proofs import inspect_proofs, inspect_field_proofs

HERE = Path(__file__).resolve().parent
ARM_GUARDS = {
    'copy': (0x02026F38, '6888421ca24206d80835301c291c5200bdf064ec70bd'),
    'trainer_load': (0x0207254A, '294a00900c1c019b01201b2199f79ffa'),
    'trainer_bank': (0x020725F0, 'cf020000'),
    'trainer_copy': (0x020725A6, '0498a16999f7c9fa061c291c0822b4f7b2fc'),
    'frontier_load': (0x0204ACF4, '01201b211a22331cc0f7ccfe'),
    'frontier_copy': (0x0204AD2A, '381cc0f708ff0835041c291c0822dcf7f0f8'),
}


def validate_guards(data, base, names):
    for name in names:
        address, expected = ARM_GUARDS[name]
        offset = address - base
        raw = bytes.fromhex(expected)
        if offset < 0 or bytes(data[offset:offset + len(raw)]) != raw:
            raise ValueError(f'Unrecognized consumer guard {name} at {address:08X}')


def measure_units(units, stage):
    if not units or units[-1] != msgtool.CODE_END:
        raise ValueError('Missing terminal unit')
    if stage == 'stored':
        return len(units)
    if stage != 'decompressed':
        raise ValueError('Unsupported capacity stage')
    codes = msgtool.decompress_units(units)[0] if units[0] == msgtool.CODE_COMPRESSED else units[:-1]
    # Expansion bounds belong to the formatter checker, never count a command as a glyph.
    if any(code in (msgtool.CODE_CMD, msgtool.CODE_COMPRESSED) for code in codes):
        raise ValueError('Dynamic/control-bearing name needs an expansion contract')
    return len(codes) + 1


def check_entries(strings, contract):
    checks = []
    ids = range(len(strings)) if contract['ids'] is None else contract['ids']
    for entry in ids:
        row = {'ref': f"{contract['bank']}#{entry}", 'contract': contract['id'],
               'stage': contract['stage'], 'capacity_units': contract['capacity_units'],
               'evidence_level': contract['evidence_level']}
        try:
            if entry < 0 or entry >= len(strings):
                raise ValueError('Required message ID missing')
            if contract['stage'] == 'expanded':
                measurement = measure_contract_expansion(strings[entry], contract)
                if measurement['status'] != 'passed':
                    row.update(status='incomplete', reason='Expansion bound unresolved', expansion=measurement)
                    checks.append(row)
                    continue
                count = measurement['expanded_units']
            else:
                count = measure_units(strings[entry], contract['stage'])
            row.update(measured_units=count, status='failed' if count > contract['capacity_units'] else 'passed')
        except ValueError as exc:
            row.update(status='incomplete', reason=str(exc))
        checks.append(row)
    return checks


def inspect_consumers(rom_path):
    import ndspy.rom
    import ndspy.narc
    rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
    arm = rom.loadArm9().sections[0]
    narc = ndspy.narc.NARC(rom.getFileByName('a/0/2/7'))
    contracts, checks, gaps = [], [], []

    def add(cid, bank, capacity, stage='stored', ids=None, evidence='policy_only', note='', guards=()):
        contract = dict(id=cid, bank=bank, ids=ids, capacity_units=capacity, stage=stage,
                        evidence_level=evidence, evidence=note, includes_terminator=True,
                        exhaustive_consumers=False, status='passed' if evidence == 'rom_guarded' else 'incomplete')
        try:
            validate_guards(arm.data, arm.ramAddress, guards)
        except ValueError as exc:
            contract['evidence_level'] = 'unverified'
            contract['status'] = 'incomplete'
            gaps.append({'contract': cid, 'reason': str(exc)})
        contracts.append(contract)
        if contract['evidence_level'] == 'unverified':
            return
        _, strings, _ = msgtool.decrypt_bank(narc.files[int(bank.split('/')[1])])
        checks.extend(check_entries(strings, contract))

    add('trainer-name-copy', 'a027/0719', 8, evidence='rom_guarded',
        note='ARM9 bank literal 0x020725F0; load 0x02072556; bounded u16 copy 0x020725B4.',
        guards=('copy', 'trainer_load', 'trainer_bank', 'trainer_copy'))
    add('frontier-name-copy', 'a027/0026', 8, evidence='rom_guarded',
        note='ARM9 bank load 0x0204ACFC; bounded u16 copy 0x0204AD38.',
        guards=('copy', 'frontier_load', 'frontier_copy'))
    try:
        report = text_buffer_check.inspect_rom(rom_path)
        for index, consumer in enumerate(report['consumers']):
            add(f'item-description-{index}', 'a027/0218', consumer['capacity'],
                evidence='rom_guarded', note=f"text_buffer_check: {consumer['context']}, allocation {consumer['allocation_site']}")
    except (ValueError, KeyError, IndexError) as exc:
        gaps.append({'contract': 'item-descriptions', 'reason': str(exc)})
    overlays = rom.loadArm9Overlays()
    scripts = msgtool.Narc.parse(rom.getFileByName('a/0/1/2')).files
    for contract in inspect_proofs(arm, overlays) + inspect_field_proofs(arm, overlays, scripts):
        contracts.append(contract)
        if contract['status'] != 'passed':
            gaps.append({'contract': contract['id'], 'reason': contract['reason']})
            continue
        _, strings, _ = msgtool.decrypt_bank(narc.files[int(contract['bank'].split('/')[1])])
        checks.extend(check_entries(strings, contract))
    cfg = json.loads((HERE / 'qa_config.json').read_text())
    for bank, category in cfg['banks'].items():
        if bank.startswith('a027/') and isinstance(category, str):
            spec = cfg['categories'][category]
            if 'max_chars' in spec:
                add(f'configured-{bank}', bank, spec['max_chars'] + 1, stage='decompressed',
                    note=f'qa_config category {category}; character policy, not proven receiving capacity.')
    add('default-player-rival-save', 'a027/0247', 8, stage='decompressed', ids=list(range(36)) + [84],
        note='work/notes/hardcoded_text.md: default names copied into 8-unit save field; code path not guarded here.')
    for bank, spec in cfg['compressed_banks'].items():
        if not bank.startswith('_'):
            add(f'raw-name-{bank}', bank, spec['raw_max_chars'] + 1, ids=spec['raw_ids'],
                stage='decompressed', note='qa_config raw trainer names consumed without formatter; consumer remains unguarded.')
    # Hardcoded strings: follow actual pointers, so relocated labels are checked as shipped.
    import hardcoded
    hc = hardcoded.load()  # [[string]] entries of the enabled fixes in work/patches
    for entry in hc['strings']:
        contract = dict(id=entry['id'], bank='hardcoded', ids=[entry['id']], stage='decompressed',
                        capacity_units=entry.get('reloc_max_units', entry['max_units']) + 1,
                        evidence_level='policy_only', evidence='hardcoded_text.md and work/patches/outfit-chooser-strings/fix.toml; receiving code not guarded',
                        includes_terminator=True, exhaustive_consumers=False, status='incomplete')
        contracts.append(contract)
        try:
            overlay = overlays[int(entry['file'].removeprefix('overlay'))]
            targets = [struct.unpack_from('<I', overlay.data, int(p, 0))[0] - overlay.ramAddress for p in entry.get('pointers', [])]
            if not targets:
                targets = [int(entry['offset'], 0)]
            for target in set(targets):
                if target < 0 or target % 2 or target >= len(overlay.data):
                    raise ValueError('Pointer target outside overlay or unaligned')
                units = []
                for offset in range(target, len(overlay.data) - 1, 2):
                    unit = struct.unpack_from('<H', overlay.data, offset)[0]
                    units.append(unit)
                    if unit == msgtool.CODE_END:
                        break
                count = measure_units(units, 'decompressed')
                checks.append(dict(ref=entry['id'], contract=entry['id'], stage='decompressed',
                                   measured_units=count, capacity_units=contract['capacity_units'], evidence_level='policy_only',
                                   status='failed' if count > contract['capacity_units'] else 'passed'))
        except (ValueError, KeyError, struct.error) as exc:
            gaps.append({'contract': entry['id'], 'reason': str(exc)})
    gaps.append({'reason': 'Consumer discovery is not exhaustive; all other contexts and dynamic expansion require explicit contracts.'})
    findings = [row for row in checks if row['status'] == 'failed']
    gaps.extend(row for row in checks if row['status'] == 'incomplete')
    return dict(schema_version=1, status='failed' if findings else 'incomplete', contracts=contracts,
                checks=checks, findings=findings, gaps=gaps, exhaustive=False)
