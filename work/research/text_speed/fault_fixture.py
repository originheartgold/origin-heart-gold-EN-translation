"""Derive a deliberately broken ROM to prove a runtime gate check is not vacuous.

    python fault_fixture.py CANDIDATE.nds work/build/<dir> --fault fast-budget

Writes <dir>/FAULT-<name>.nds and <dir>/FAULT-<name>.payload.json (the payload
with the same edit, plus a "fault" key). Run a gate on that ROM with
--fault-payload <dir>/FAULT-<name>.payload.json: the gate must FAIL. Reports of
such runs carry "fault_fixture" and are never release evidence. Each edit checks
the candidate's exact original bytes first; the candidate file is never changed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools'))

ITCM = 0x01FF8000


def units(text):
    """Label text in the English font codes used by labels.h (A=0x12B .. Z=0x144)."""
    return b''.join((0x12B + ord(c) - ord('A')).to_bytes(2, 'little') for c in text) + b'\xff\xff'


# name: (description, [(address, original bytes, broken bytes)])
FAULTS = {
    'fast-budget': ('MEDIUM/FAST budget m+7 instead of m+1 (8 and 9 glyphs per task)',
                    [(0x01FF867E, bytes.fromhex('781c'), bytes.fromhex('f81d'))]),
    'slow-flat': ('SLOW ignores its phase: always one glyph per task',
                  [(0x01FF8684, bytes.fromhex('0121'), bytes.fromhex('0021'))]),
    'no-phase-reset': ('init_printer no longer clears the private phase byte (+0x34)',
                       [(0x01FF862C, bytes.fromhex('2154'), bytes.fromhex('c046'))]),
    # exit_free has commit_speed inlined; the standalone commit_speed copy is not called.
    'commit-noop': ('Options Confirm no longer stores the text-speed bits',
                    [(0x01FF8836, bytes.fromhex('0280'), bytes.fromhex('c046'))]),
    'label-overflow': ('MEDIUM label replaced by a ten-letter label',
                       # labels[2] is u16[11]: MEDIUM, terminator, four zero units.
                       [(0x01FF88EC, units('MEDIUM') + bytes(8), units('MEDIUMMEDI'))]),
    'default-slow': ('new-game Options initialiser sets SLOW instead of MEDIUM (main ARM9)',
                     [(0x0202B176, bytes.fromhex('0420'), bytes.fromhex('0020'))]),
    'arena-overlap': ('SDK ITCM arena lower bound put back over the payload (main ARM9 data)',
                      [(0x020D1A28, bytes.fromhex('2089ff01'), bytes.fromhex('2086ff01'))]),
    'no-control-stop': ('batching no longer stops before control codes',
                        [(0x01FF86D4, bytes.fromhex('17d3'), bytes.fromhex('c046')),
                         (0x01FF86DC, bytes.fromhex('13d3'), bytes.fromhex('c046')),
                         (0x01FF86E2, bytes.fromhex('10d0'), bytes.fromhex('c046'))]),
}


def main():
    import ndspy.rom
    from text_speed_patch import load_payload
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('candidate', type=Path)
    p.add_argument('out_dir', type=Path)
    p.add_argument('--fault', required=True, choices=sorted(FAULTS))
    a = p.parse_args()
    out = a.out_dir.resolve()
    if not out.is_relative_to(ROOT / 'work/build') or out == ROOT / 'work/build':
        p.error('output must be a separate directory under this worktree work/build')
    out.mkdir(parents=True, exist_ok=True)
    description, edits = FAULTS[a.fault]
    payload = load_payload()
    code = bytearray.fromhex(payload['code'])
    rom = ndspy.rom.NintendoDSRom.fromFile(str(a.candidate))
    arm9 = rom.loadArm9()
    itcm = arm9.sections[1]
    if itcm.ramAddress != ITCM:
        raise SystemExit('unexpected ITCM section')
    main = arm9.sections[0]
    if main.ramAddress != 0x02000000:
        raise SystemExit('unexpected ARM9 main section')
    data = {ITCM: bytearray(itcm.data), main.ramAddress: bytearray(main.data)}
    for address, before, after in edits:
        if len(after) > len(before):
            raise SystemExit(f'{a.fault}: edit at {address:#x} grows')
        after = after + before[len(after):]
        start = ITCM if address < 0x02000000 else main.ramAddress
        section, off = data[start], address - start
        if bytes(section[off:off + len(before)]) != before:
            raise SystemExit(f'{a.fault}: candidate bytes at {address:#x} are not the reviewed ones')
        if start == ITCM:
            rel = address - payload['base']
            if bytes(code[rel:rel + len(before)]) != before:
                raise SystemExit(f'{a.fault}: payload bytes at {address:#x} are not the reviewed payload')
            code[rel:rel + len(before)] = after
        section[off:off + len(before)] = after
    itcm.data, main.data = bytes(data[ITCM]), bytes(data[main.ramAddress])
    rom.arm9 = arm9.save(compress=False)
    target = out / f'FAULT-{a.fault}.nds'
    rom.saveToFile(str(target))
    derived = dict(payload, code=code.hex(), fault={'name': a.fault, 'description': description,
                                                   'candidate_sha256': hashlib.sha256(a.candidate.read_bytes()).hexdigest()})
    (out / f'FAULT-{a.fault}.payload.json').write_text(json.dumps(derived, indent=1))
    print(json.dumps({'fault': a.fault, 'rom': str(target),
                      'rom_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
