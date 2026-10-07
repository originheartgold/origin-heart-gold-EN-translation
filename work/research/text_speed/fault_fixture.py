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


def nop(address, original):
    return (address, bytes.fromhex(original), bytes.fromhex('c046'))


# name: {description, edits [(address, original bytes, broken bytes)], gates}.
# 'gates' maps every gate that must FAIL on the fault to a substring its errors
# must contain (None: any failure). validate_release.py --fault-payload reports
# 'fault-detected' only if every declared gate failed that way. A fault with
# 'dead' instead of gates is proven unreachable (see text_speed_release_checks.md)
# and has no gate to declare.
FAULTS = {
    'fast-budget': {
        'description': 'MEDIUM/FAST budget m+7 instead of m+1 (8 and 9 glyphs per task)',
        'edits': [(0x01FF867E, bytes.fromhex('781c'), bytes.fromhex('f81d'))],
        'gates': {'corpus': 'design budget', 'battle': 'design budget', 'callbacks': 'design budget',
                  'fallbacks': 'budget', 'natural-dialogue': 'design budget'}},
    'slow-flat': {
        'description': 'SLOW ignores its phase: always one glyph per task',
        'edits': [(0x01FF8684, bytes.fromhex('0121'), bytes.fromhex('0021'))],
        'gates': {'corpus': 'without a reason', 'callbacks': 'without a reason',
                  'fallbacks': 'without a reason', 'natural-dialogue': 'without a reason',
                  'battle': 'without a reason'}},
    'no-phase-reset': {
        'description': 'init_printer no longer clears the private phase byte (+0x34)',
        'edits': [nop(0x01FF862C, '2154')],
        'gates': {'lifecycle': 'phase'}},
    # exit_free has commit_speed inlined; the standalone commit_speed copy is not called.
    'commit-noop': {
        'description': 'Options Confirm no longer stores the text-speed bits',
        'edits': [nop(0x01FF886A, '0280')],
        'gates': {'options': None, 'save': None, 'music': None, 'corpus': None}},
    'label-overflow': {
        'description': 'MEDIUM label replaced by a ten-letter label',
        # labels[2] is u16[11]: MEDIUM, terminator, four zero units.
        'edits': [(0x01FF8920, units('MEDIUM') + bytes(8), units('MEDIUMMEDI'))],
        'gates': {'options': 'label', 'save': 'label'}},
    'default-slow': {
        'description': 'new-game Options initialiser sets SLOW instead of MEDIUM (main ARM9)',
        'edits': [(0x0202B176, bytes.fromhex('0420'), bytes.fromhex('0020'))],
        'gates': {'new-game': None}},
    'arena-overlap': {
        'description': 'SDK ITCM arena lower bound put back over the payload (main ARM9 data)',
        'edits': [(0x020D1A28, bytes.fromhex('6089ff01'), bytes.fromhex('2086ff01'))],
        'gates': {'lifecycle': 'ITCM arena', 'options': 'ITCM arena'}},
    'no-control-stop': {
        'description': 'batching no longer stops before control codes',
        'edits': [nop(0x01FF86D4, '2fd3'), nop(0x01FF86DC, '2bd3'), nop(0x01FF86E2, '28d0')],
        'gates': {'corpus': 'control step', 'controls': 'control step', 'battle': 'to_free'}},
    'eos-only-no-stop': {
        'description': 'batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls)',
        'edits': [nop(0x01FF86DC, '2bd3')],
        'gates': {'corpus': 'control step', 'battle': 'to_free'}},
    'space-stop': {
        'description': 'batching stops before every space (0x01DE) instead of 0xF0FD',
        'edits': [(0x01FF8768, bytes.fromhex('fdf00000'), bytes.fromhex('de010000'))],
        'gates': {'corpus': 'without a reason', 'natural-dialogue': 'without a reason',
                  'fallbacks': 'without a reason', 'callbacks': 'without a reason'}},
    'no-color-setup': {
        'description': 'native task no longer sets the glyph colour table before rendering',
        'edits': [nop(0x01FF8698, '9847')],
        'gates': {'corpus': 'pages differs', 'controls': 'pages differs', 'callbacks': 'pixels differ'}},
    'no-state-stop': {
        'description': 'batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph',
        'edits': [nop(0x01FF86C2, '38d1'), nop(0x01FF86C8, '35d1')],
        'dead': 'after a glyph (result 0) RenderText is always in state 0 with +0x2a = 0; '
                'see text_speed_release_checks.md'},
    'reserved-fast': {
        'description': 'Options shows reserved/legacy value 3 as FAST instead of MEDIUM',
        'edits': [(0x01FF8792, bytes.fromhex('0120'), bytes.fromhex('0220'))],
        'gates': {'options': None}},
    'vcount-ignored': {
        'description': 'batch ignores the VCOUNT frame check (always draws its whole budget)',
        'edits': [nop(0x01FF870A, '10d2'), (0x01FF8716, bytes.fromhex('c7d3'), bytes.fromhex('c7e7'))],
        'gates': {'natural-dialogue': 'after a frame stop', 'fallbacks': 'after a frame stop',
                  'callbacks': 'after a frame stop'}},
    'vcount-zero-glyph': {
        'description': 'frame check runs before the first glyph (a late task draws nothing)',
        'edits': [(0x01FF86A6, bytes.fromhex('0500'), bytes.fromhex('21e0'))],
        # In the corpus scene every task starts late, so the printer never draws: the
        # message cannot complete (a stuck message), before any per-task check runs.
        'gates': {'corpus': 'did not complete', 'natural-dialogue': 'before the first glyph',
                  'fallbacks': 'before the first glyph', 'callbacks': 'before the first glyph',
                  'battle': 'before the first glyph'}},
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
    fault = FAULTS[a.fault]
    description, edits = fault['description'], fault['edits']
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
