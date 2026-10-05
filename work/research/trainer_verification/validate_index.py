"""Validate regenerated research data against freshly read Chinese archive bytes.

Also compares raw provenance and semantic changes with the optional old v2 dump.
No cached parsed roster is accepted as the source of truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools/docs'))
import ndspy.narc
import ndspy.rom
import romdata as R


def check(data_dir, old_dir=None):
    def read(name):
        return json.loads((data_dir / (name + '.json')).read_text())
    roster, summary = read('roster'), read('summary')
    source = Path(R.ROM_PATH)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == summary['provenance']['rom_sha256']
    assert summary['schema_version'] == 3
    for name, digest in summary['provenance']['inputs'].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    for name, digest in summary['provenance']['modules'].items():
        assert hashlib.sha256((ROOT / 'work/tools/docs' / name).read_bytes()).hexdigest() == digest, name
    assert hashlib.sha256((Path(__file__).parent / 'export_index.py').read_bytes()).hexdigest() == summary['provenance']['exporter_sha256']
    rom = ndspy.rom.NintendoDSRom.fromFile(str(source))
    headers = ndspy.narc.NARC(rom.getFileByName('a/0/5/5')).files
    parties = ndspy.narc.NARC(rom.getFileByName('a/0/5/6')).files
    scripts = ndspy.narc.NARC(rom.getFileByName('a/0/1/2')).files
    assert len(roster) == len(headers) == len(parties) == 1024
    slots = 0
    for tid, row in enumerate(roster):
        header, raw = headers[tid], parties[tid]
        assert row['id'] == tid
        assert row['raw_party_sha256'] == hashlib.sha256(raw).hexdigest()
        assert row['raw_metadata_sha256'] == hashlib.sha256(header).hexdigest()
        flags, cls, count, *item_slots, ai, battle_type = struct.unpack('<BHB4HII', header)
        assert row['metadata'] == dict(flags=flags, cls=cls, count=count, items=[i for i in item_slots if i],
                                       ai=ai, double=battle_type != 0)
        assert len(raw) == 28 * count == 28 * len(row['party'])
        for slot, mon in enumerate(row['party']):
            p = raw[slot * 28:(slot + 1) * 28]
            ability, level, species, item = struct.unpack_from('<4H', p, 4)
            assert mon == dict(iv=p[0], ivs=p[0] * 31 // 255, hp_ivs=10 if level <= 40 else 20 if level <= 79 else 31,
                abil_slot=p[1], nature=None if p[3] == 255 else p[3], ability=ability, level=level,
                species=species, form=p[2], item=item, moves=[m for m in struct.unpack_from('<4H', p, 12) if m],
                evs=[p[20], p[21], p[22], p[24], p[25], p[23]])
            slots += 1
    assert slots == 3891
    encounters = read('encounters')
    assert len(encounters) == len({e['key'] for e in encounters}) == 941
    for e in encounters:
        op = struct.unpack_from('<H', scripts[e['script']], e['pc'])[0]
        assert R.cmds()[op][0] == ('TrainerBattle' if e['kind'] == 'trainer' else 'MultiBattle')
        n = 3 if e['kind'] == 'multi_battle' else 2
        expected = [dict(role='partner' if e['kind'] == 'multi_battle' and i == 0 else 'opponent',
                         slot=i, trainer_id=t) for i, t in enumerate(e['resolved_args'][:n]) if t != 0]
        assert e['participants'] == expected
        for role, field in [('partner', 'partner_party_max'), ('opponent', 'opponent_party_max')]:
            ids = {p['trainer_id'] for p in expected if p['role'] == role and p['trainer_id']}
            assert e[field] == max((m['level'] for i in ids for m in roster[i]['party']), default=None)
        assert not e['conditions_complete'] and e['reachability'] == 'static-reference-only'
    assert next(e for e in encounters if e['key'] == 'script:741:151')['curated_dead_scene']
    assert not next(e for e in encounters if e['key'] == 'script:741:2311')['curated_dead_scene']
    assert {b['award']['args'][0] for b in read('badge_candidates')} == set(range(16))
    assert len(read('badge_candidates')) == 18
    assert {m['trainer_id'] for m in read('menu78_assignments')} == {287,288,479,487,498,503,544,557,558,700,733,734,863,864,865,866,867}
    assert {u['trainer_id'] for u in read('unreferenced')} == {86,89,260,440,488,492,609,706,707,708,709,710,711,760,947}
    for u in read('unreferenced'):
        assert u['party'] == roster[u['trainer_id']]['party']
    old_comparison = None
    if old_dir and (old_dir / 'roster.json').exists():
        old = json.loads((old_dir / 'roster.json').read_text())
        assert len(old) == len(roster)
        changes = dict(form=0, evs=0, hp_ivs=0)
        for before, after in zip(old, roster):
            assert before['id'] == after['id']
            assert before['raw_party_sha256'] == after['raw_party_sha256']
            assert before['metadata'] == after['metadata']
            assert len(before['party']) == len(after['party'])
            for a, b in zip(before['party'], after['party']):
                for key in a:
                    if key in ('form', 'evs'):
                        changes[key] += a[key] != b[key]
                    else:
                        assert a[key] == b[key], (after['id'], key)
                changes['hp_ivs'] += a['ivs'] != b['hp_ivs']
        assert changes == dict(form=21, evs=1129, hp_ivs=3891)
        old_comparison = dict(raw_hashes_unchanged=True, corrected_slots=changes)
    return dict(status='passed', trainer_records=len(roster), party_slots=slots, callsites=len(encounters),
                old_comparison=old_comparison, scope='raw extraction, reviewed party semantics, provenance and structural references; not global reachability')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--data', type=Path, default=ROOT / 'work/build/difficulty-trainers-v3')
    ap.add_argument('--old', type=Path, default=Path('/private/tmp/poke-difficulty-research/work/build/difficulty-trainers-v2'))
    args = ap.parse_args()
    result = check(args.data, args.old)
    out = args.data.resolve()
    if not out.is_relative_to(ROOT / 'work/build'):
        ap.error('validation output must stay under ignored work/build/')
    (out / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
