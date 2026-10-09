#!/usr/bin/env python3
"""Native smoke test for the migrated Python facade, using disposable local fixtures.

Independent memcheck/stat readers verify the shared writer's results. No ROM builds
or downloads. Set EMU_HARNESS_DATA and MELONDS_SHIM to existing local resources.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools'))
import emu_harness as E
import emu_guide0107 as G
import memcheck

spec = importlib.util.spec_from_file_location('independent_runtime', ROOT / 'work/save-editor/scripts/verify-runtime.py')
independent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(independent)


def identity(path):
    return {'path':str(path.resolve()), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--seed', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--emulator', choices=('melonds', 'desmume'), default='melonds')
    parser.add_argument('--party-count', type=int, choices=(3, 6), default=6,
                        help='Three exercises a shrunken party and last-active slot; six retains the original scenario')
    parser.add_argument('--expect-generator-invalid', action='store_true',
                        help='Require safe rejection of the independently reproduced native generator defect')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / 'work/build'):
        parser.error('--out must be under work/build')
    out.mkdir(parents=True, exist_ok=False)
    before = [identity(args.rom), identity(args.seed)]
    sf = E.SaveFile(args.seed)
    operations = [
        {'type':'setVar','var':E.SENTINEL_VAR,'value':17123},
        {'type':'editPartyMon','slot':0,'changes':{'moves':[53,85,0,0],'pp':[15,15,0,0]},'tailPolicy':'preserve'},
        {'type':'setPocket','name':'medicine','items':[[50,99]]},
    ]
    if args.party_count == 3:
        operations.extend([
            {'type':'setPartyCount','count':3},
            {'type':'editPartyMon','slot':2,'changes':{'moves':[33,0,0,0],'pp':[35,0,0,0]},'tailPolicy':'preserve'},
        ])
    sf.transaction(operations)
    fixture = out / 'fixture.sav'
    sf.write(fixture)
    with E.Harness(args.rom, fixture, out=out, emulator=args.emulator, verbose=False) as h:
        h.boot_to_menu()
        h.continue_game()
        assert h.get_var(E.SENTINEL_VAR) == 17123
        assert h.u16(h.array(E.ARR_BAG) + E.POCKETS['medicine'][0]) == 50
        party = h.array(E.ARR_PARTY)
        assert h.u32(party + 4) == args.party_count
        if args.party_count == 3:
            assert h.u32(party + 4) == 3, 'Native load did not preserve shrunken party count'
            last_active = party + 8 + 2 * 236
            assert memcheck.decode_stored_moves(h.read(last_active, 136))['moves'] == [33,0,0,0]
            last_stats = independent.decode_party_stats(h.read(last_active, 236))
            h.edit_party_mon(2, moves=[85], pp=[15])
            assert memcheck.decode_stored_moves(h.read(last_active, 136))['moves'] == [85,0,0,0]
            assert independent.decode_party_stats(h.read(last_active, 236)) == last_stats
        raw = h.read(party + 8, 236)
        assert memcheck.decode_stored_moves(raw[:136])['moves'] == [53,85,0,0]
        original_stats = independent.decode_party_stats(raw)
        h.edit_party_mon(0, moves=[33], pp=[35], ability=311, item=7)
        after_partial = h.read(party + 8, 236)
        assert memcheck.decode_stored_moves(after_partial[:136])['moves'] == [33,85,0,0]
        assert independent.decode_party_stats(after_partial) == original_stats
        G.set_party_hp(h, 0, 1)
        assert independent.decode_party_stats(h.read(party + 8, 236))['party']['currentHp'] == 1
        snapshot = h.read(party, 8 + 6 * 236)
        try:
            h.edit_party_mon(args.party_count, moves=[33])
        except ValueError:
            pass
        else:
            raise AssertionError('Inactive party slot accepted')
        assert h.read(party, 8 + 6 * 236) == snapshot
        # Run ordinary emulator frames after synchronous worker edits.
        h.step(120)
        assert memcheck.decode_stored_moves(h.read(party + 8, 136))['moves'] == [33,85,0,0]
        if args.party_count == 3:
            assert memcheck.decode_stored_moves(h.read(last_active, 136))['moves'] == [85,0,0,0]
        try:
            generated = h.generate_pokemon(1, level=5)
        except RuntimeError as exc:
            if not args.expect_generator_invalid or 'invalid closed Pokemon' not in str(exc):
                raise
            slot = h.u32(h.array(E.ARR_PARTY) + 4) - 1
            raw_generated = h.read(h.array(E.ARR_PARTY) + 8 + slot * 236, 236)
            try:
                memcheck.decode_stored_moves(raw_generated[:136])
            except ValueError as independent_error:
                assert 'checksum mismatch' in str(independent_error)
            else:
                raise AssertionError('Independent reader accepted the rejected native record')
            generator_result = {'status':'invalid native output safely rejected', 'error':str(exc)}
        else:
            assert not args.expect_generator_invalid, 'Expected the known native generator defect'
            generated_fields = {key:generated[key] for key in ('species','level','checksum_ok','flags','form')}
            assert generated['species'] == 1 and generated['level'] == 5 and generated['checksum_ok'], generated_fields
            raw_generated = h.read(party + 8 + 236 * h.generated_slot, 236)
            oracle = memcheck.decode_stored_moves(raw_generated[:136])
            assert oracle['moves'] == [33,45,22,0]
            assert independent.decode_party_stats(raw_generated)['party']['level'] == 5
            assert h.party()[h.generated_slot]['species'] == 1
            generator_result = {'status':'valid', 'species':generated['species'], 'level':generated['level']}
        h.screenshot('shared-core-field')
        result = {'status':'passed','emulator':args.emulator,'initial_party_count':args.party_count,'location':h.location(),
                  'native_generator':generator_result,
                  'fixture_report':sf.report,'checks':['battery transaction native load','saved variable','bag pocket',
                    'independent move decode','partial moves retain unused slots','boxed edits preserve native stats',
                    'HP edit independent decode','inactive slot no mutation','native frames after edit','native generator']}
        if args.party_count == 3:
            result['checks'].extend(['three-member party native load','last-active-slot battery/live edits',
                                     'successful native generation checked by independent readers'])
    after = [identity(args.rom), identity(args.seed)]
    assert before == after
    result.update(inputs=before, inputs_unchanged=True)
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
