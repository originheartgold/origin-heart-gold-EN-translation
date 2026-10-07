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
# must contain: text from the gate's own checks (validate_release.fault_verdict never
# accepts an unexpected Python exception as detection). A fault with 'dead' instead
# of gates is proven unreachable (see text_speed_release_checks.md) and has no gate.
# 'checker' (optional): text_speed_checks constants the gates use for this fault, so
# that the gates' frame model matches the broken payload: such a fault can only be
# caught by the product checks (frames, drops, frame stops), not by the model check.
B = bytes.fromhex
FAULTS = {
    'fast-budget': {
        'description': 'MEDIUM/FAST budget m+7 instead of m+1 (8 and 9 glyphs per task)',
        'edits': [(0x01FF872A, B('781c'), B('f81d'))],
        'gates': {'corpus': 'design budget', 'battle': 'design budget', 'callbacks': 'design budget',
                  'fallbacks': 'budget', 'natural-dialogue': 'design budget', 'scenes': 'budget'}},
    'slow-flat': {
        'description': 'SLOW ignores its phase: always one glyph per task',
        'edits': [(0x01FF8730, B('0121'), B('0021'))],
        'gates': {'corpus': 'allowed another glyph', 'callbacks': 'allowed another glyph',
                  'fallbacks': 'allowed another glyph', 'natural-dialogue': 'allowed another glyph',
                  'battle': 'allowed another glyph', 'scenes': 'allowed another glyph'}},
    'no-phase-reset': {
        'description': 'init_printer no longer clears the private phase byte (+0x34)',
        'edits': [nop(0x01FF862C, '2154')],
        'gates': {'lifecycle': 'phase'}},
    # exit_free has commit_speed inlined; the standalone commit_speed copy is not called.
    'commit-noop': {
        'description': 'Options Confirm no longer stores the text-speed bits',
        'edits': [nop(0x01FF89FE, '0280')],
        'gates': {'options': 'did not store the chosen text speed', 'save': 'did not store the chosen text speed',
                  'music': 'did not store the chosen text speed', 'corpus': 'did not store the chosen text speed'}},
    'label-overflow': {
        'description': 'MEDIUM label replaced by a ten-letter label',
        # labels[2] is u16[11]: MEDIUM, terminator, four zero units.
        'edits': [(0x01FF8AB4, units('MEDIUM') + bytes(8), units('MEDIUMMEDI'))],
        'gates': {'options': 'label', 'save': 'label'}},
    'default-slow': {
        'description': 'new-game Options initialiser sets SLOW instead of MEDIUM (main ARM9)',
        'edits': [(0x0202B176, B('0420'), B('0020'))],
        'gates': {'new-game': 'does not start at MEDIUM'}},
    'arena-overlap': {
        'description': 'SDK ITCM arena lower bound put back over the payload (main ARM9 data)',
        'edits': [(0x020D1A28, B('008bff01'), B('2086ff01'))],
        'gates': {'lifecycle': 'ITCM arena', 'options': 'ITCM arena'}},
    'no-control-stop': {
        'description': 'batching no longer stops before control codes',
        'edits': [nop(0x01FF87B2, '39d3'), nop(0x01FF87BA, '35d3'), nop(0x01FF87C0, '32d0')],
        'gates': {'corpus': 'without a frame decision', 'controls': 'without a frame decision',
                  'battle': 'to_free'}},
    'eos-only-no-stop': {
        'description': 'batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls)',
        'edits': [nop(0x01FF87BA, '35d3')],
        'gates': {'corpus': 'without a frame decision', 'battle': 'without a frame decision'}},
    'no-newline-peek': {
        'description': 'batching no longer looks past a newline: a newline before the end of the text is '
                       'rendered with the batch',
        'edits': [(0x01FF87A6, B('01d1'), B('01e0'))],
        'gates': {'battle': 'end-of-text step moved'}},
    'space-stop': {
        'description': 'batching stops before every space (0x01DE) instead of 0xF0FD',
        'edits': [(0x01FF8890, B('fdf00000'), B('de010000'))],
        'gates': {'corpus': 'allowed another glyph', 'natural-dialogue': 'allowed another glyph',
                  'fallbacks': 'allowed another glyph', 'callbacks': 'allowed another glyph'}},
    'no-color-setup': {
        'description': 'native task no longer sets the glyph colour table before rendering',
        'edits': [nop(0x01FF8744, '9847')],
        'gates': {'corpus': 'pages differs', 'controls': 'pages differs', 'callbacks': 'pixels differ'}},
    'no-state-stop': {
        'description': 'batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph',
        'edits': [nop(0x01FF8794, '48d1'), nop(0x01FF879A, '45d1')],
        'dead': 'after a glyph (result 0) RenderText is always in state 0 with +0x2a = 0; '
                'see text_speed_release_checks.md'},
    'reserved-fast': {
        'description': 'Options shows reserved/legacy value 3 as FAST instead of MEDIUM',
        'edits': [(0x01FF8926, B('0120'), B('0220'))],
        'gates': {'options': 'reserved value 3 is not shown as MEDIUM'}},
    'zero-glyph': {
        'description': 'the batching task returns before its first render (draws nothing)',
        'edits': [(0x01FF8738, B('e27d'), B('ebe7'))],
        'gates': {'corpus': 'did not complete', 'natural-dialogue': 'expected the 54-glyph trainer page',
                  'fallbacks': 'expected 54 glyphs', 'callbacks': '(0 glyphs)',
                  'scenes': 'no native tasks observed', 'battle': 'stuck without A/B input'}},
    'frame-rule-ignored': {
        'description': 'the frame decision always draws (the batch always uses its whole budget)',
        'edits': [(0x01FF87CC, B('00f062f8'), B('0120c046'))],
        'gates': {'natural-dialogue': 'after a frame stop', 'fallbacks': 'after a frame stop',
                  'callbacks': 'after a frame stop', 'scenes': 'after a frame stop'}},
    'rest-not-stored': {
        'description': 'frame_end no longer stores the measured rest (the decision runs on the seed)',
        'edits': [nop(0x01FF868C, '0a72')],
        'gates': {'natural-dialogue': 'payload state', 'scenes': 'payload state', 'corpus': 'payload state',
                  'fallbacks': 'payload state', 'callbacks': 'payload state'}},
    # The next four keep the gates' frame model equal to the broken payload ('checker'),
    # so only the product checks can catch them.
    'fixed-model': {
        'description': 'the cf50a23 rule: draw when 20 or more lines are left, lost below 7, no measured costs',
        'edits': [(0x01FF88D8, B('1c19'), B('1324')), (0x01FF88F6, B('4c1e'), B('0121')),
                  (0x01FF88F8, B('a141'), B('0722'))],
        'checker': {'FIXED_MODEL': [20, 7]},
        'gates': {'scenes': 'would have fitted'}},
    'tail-ignored': {
        'description': 'the decision leaves out the rest of the pass (predicts only the glyph)',
        'edits': [(0x01FF88D8, B('1c19'), B('1c1c'))],
        'checker': {'IGNORE_REST': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    'glyph-ignored': {
        'description': 'the decision leaves out the glyph cost (predicts only the rest of the pass)',
        'edits': [(0x01FF88D8, B('1c19'), B('241c'))],
        'checker': {'IGNORE_GLYPH': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    'too-conservative-24': {
        'description': 'needs 4 more lines for an extra glyph (the review\'s threshold 24 against 20)',
        # cmp r1,#0; adds r4,r1,#4; cmp r1,#0; bne: a measured rest counts 4 lines more.
        'edits': [(0x01FF88CA, B('8c46'), B('0c1d')), (0x01FF88CC, B('6446'), B('0029'))],
        'checker': {'MARGIN': 5, 'REST_SEED': 16},
        'gates': {'scenes': 'SLOW floor', 'natural-dialogue': 'SLOW floor'}},
    'too-conservative-30': {
        'description': 'needs 10 more lines for an extra glyph (the review\'s threshold 30 against 20)',
        # a measured rest counts 7 lines more, every stored glyph cost 3 more
        'edits': [(0x01FF88CA, B('8c46'), B('cc1d')), (0x01FF88CC, B('6446'), B('0029')),
                  (0x01FF8770, B('2900'), B('e91c'))],
        'checker': {'MARGIN': 8, 'REST_SEED': 13, 'GLYPH_COST_BIAS': 3},
        'gates': {'scenes': 'SLOW floor', 'natural-dialogue': 'SLOW floor'}},
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
    if fault.get('checker'):
        derived['checker'] = fault['checker']
    (out / f'FAULT-{a.fault}.payload.json').write_text(json.dumps(derived, indent=1))
    print(json.dumps({'fault': a.fault, 'rom': str(target),
                      'rom_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
