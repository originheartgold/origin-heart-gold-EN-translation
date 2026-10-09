#!/usr/bin/env python3
"""Read-only comparison of existing and migrated harness native generation."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[3]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--tools', type=Path, required=True)
p.add_argument('--rom', type=Path, required=True)
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--mutate', action='store_true')
p.add_argument('--clear-target-slot', action='store_true',
               help='On this disposable run only, clear the inactive target like native ZeroMonData before generation')
p.add_argument('--trace-party-writes', action='store_true',
               help='Capture native bus writes to the newly generated party record without changing it')
a = p.parse_args()
sys.path.insert(0, str(a.tools.resolve()))
import emu_harness as E
import emu_guide0107 as G
import memcheck
out = a.out.resolve()
if not out.is_relative_to(ROOT / 'work/build'):
    p.error('output must be under work/build')
out.mkdir(parents=True, exist_ok=False)
identities = {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.rom,a.fixture)}
rows=[]
with E.Harness(a.rom, a.fixture, out=out, emulator='melonds', verbose=False) as h:
    h.boot_to_menu()
    h.continue_game()
    party=h.array(E.ARR_PARTY)
    if a.mutate:
        h.edit_party_mon(0,moves=[33],pp=[35],ability=311,item=7)
        G.set_party_hp(h,0,1)
        h.step(120)
    watched_slot = min(h.u32(party + 4), 5)
    if a.clear_target_slot:
        import save_core
        h.w32(party + 4, watched_slot)
        h.write(party + 8 + 236 * watched_slot, save_core.result_bytes(save_core.request('emptyPokemon')))
    if a.trace_party_writes:
        h.watch(party + 8 + 236 * watched_slot, 236, read=False, write=True)
    generator_error = None
    try:
        generated=h.generate_pokemon(1,level=5)
        slot=h.generated_slot
    except RuntimeError as error:
        if not str(error).startswith('Native generator produced an invalid closed Pokemon'):
            raise
        generator_error=str(error)
        slot=h.u32(party+4)-1
    trace = h.watch_hits() if a.trace_party_writes else []
    trace_report = {'hits':list(trace),'dropped':getattr(trace,'dropped',0)}
    if a.trace_party_writes:
        h.clear_watches()
        (out / 'native-party-writes.json').write_text(json.dumps(trace_report,indent=2)+'\n')
    address=party+8+236*slot
    for frames in (0,1,10,120):
        h.step(frames)
        raw=h.read(address,236)
        (out / f'generated-{frames}.bin').write_bytes(raw)
        decoded=E.decode_party_pokemon(raw)
        # A diagnostic copy only: never repair or write the native record. This
        # distinguishes a bad ciphertext checksum from a plaintext payload whose
        # closed flag is inconsistent with the actual representation.
        opened=bytearray(raw)
        struct.pack_into('<H',opened,4,struct.unpack_from('<H',raw,4)[0] | 2)
        as_open=E.decode_party_pokemon(opened)
        try:
            oracle=memcheck.decode_stored_moves(raw[:136])
        except ValueError as error:
            oracle={'error':str(error)}
        rows.append({'frames':frames,'address':hex(address),'header':struct.unpack_from('<IHH',raw),
                     'decoded':{key:decoded[key] for key in ('species','level','checksum_ok','form')},
                     'oracle':oracle,'rawSha256':hashlib.sha256(raw).hexdigest(),
                     'payloadPlaintextSum':sum(struct.unpack_from('<64H',raw,8)) & 65535,
                     'asBoxOpenDiagnosticOnly':{key:as_open[key] for key in ('species','level','checksum_ok','form')}})
    h.screenshot('after-generator')
assert identities == {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (a.rom,a.fixture)}
result={'tools':str(a.tools.resolve()),'mutate':a.mutate,'clearTargetSlot':a.clear_target_slot,'inputs':identities,'generatorError':generator_error,'rows':rows,
        'nativePartyWrites': {'hits':len(trace),'dropped':getattr(trace,'dropped',0)} if a.trace_party_writes else None}
(out / 'report.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
