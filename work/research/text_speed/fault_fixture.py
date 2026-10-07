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
GEAR = 92               # Pokégear overlay: an edit marked with it addresses this overlay's RAM range


def bl(src, dst):
    from text_speed_patch import bl as encode
    return encode(src, dst)


def units(text):
    """Label text in the English font codes used by labels.h (A=0x12B .. Z=0x144)."""
    return b''.join((0x12B + ord(c) - ord('A')).to_bytes(2, 'little') for c in text) + b'\xff\xff'


def nop(address, original):
    return (address, bytes.fromhex(original), bytes.fromhex('c046'))


# name: {description, edits [(address, original bytes, broken bytes[, GEAR])], gates}.
# 'gates' maps every gate that must FAIL on the fault to a substring its errors
# must contain: text from the gate's own checks (validate_release.fault_verdict never
# accepts an unexpected Python exception as detection). A fault with 'dead' instead
# of gates is proven unreachable (see text_speed_release_checks.md) and has no gate.
# 'checker' (optional): text_speed_checks constants the gates use for this fault, so
# that the gates' frame model matches the broken payload: such a fault can only be
# caught by the product checks (frames, drops, frame stops), not by the model check.
B = bytes.fromhex
# Addresses are those of the reviewed D-1604 payload (NORMAL / FAST, with the phone-call
# wrapper call_print at 0x01FF8B40: 1466 bytes; code before it unchanged from 1406 bytes).
# Removed with SLOW (D-1604): 'slow-flat' (SLOW's phase: there is no SLOW and no phase)
# and 'no-phase-reset' (init_printer and the private +0x34 phase byte no longer exist).
FAULTS = {
    'fast-budget': {
        'description': 'FAST budget 9 instead of 3 glyphs per task',
        'edits': [(0x01FF871E, B('0320'), B('0920'))],
        'gates': {'corpus': 'design budget', 'battle': 'design budget', 'callbacks': 'design budget',
                  'fallbacks': 'budget', 'natural-dialogue': 'design budget', 'scenes': 'budget'}},
    'normal-batches': {
        'description': 'NORMAL (stored 0) batches like FAST: fast() tests value <= 1 instead of == 1',
        # cmp r1,#4 (bits 2..3 masked); bne original -> bhi original
        'edits': [(0x01FF86E4, B('07d1'), B('07d8'))],
        'gates': {'corpus': 'did not delegate', 'scenes': 'did not delegate', 'natural-dialogue': 'did not delegate',
                  'fallbacks': 'fallback skipped the original task', 'field-rate': 'did not delegate'}},
    'unknown-value-fast': {
        'description': 'unknown values 2 and 3 are treated as FAST (printer and Options row)',
        # fast(): bne original -> blo original (only value 0 delegates); load_rows: shows
        # FAST for every nonzero value (subs r0,r1,#1; movs r1,#0; adcs r1,r1)
        'edits': [(0x01FF86E4, B('07d1'), B('07d3')), (0x01FF88DE, B('081f'), B('481e')),
                  (0x01FF88E0, B('4142'), B('0021')), (0x01FF88E2, B('4141'), B('4941'))],
        'gates': {'options': 'is not shown as NORMAL', 'fallbacks': 'fallback skipped the original task',
                  'corpus': 'did not delegate'}},
    # exit_free has commit_speed inlined; the standalone commit_speed copy is not called.
    'commit-noop': {
        'description': 'Options Confirm no longer stores the text-speed bits',
        'edits': [nop(0x01FF89BA, '0180')],
        'gates': {'options': 'did not store the chosen text speed', 'save': 'did not store the chosen text speed',
                  'music': 'did not store the chosen text speed', 'corpus': 'did not store the chosen text speed'}},
    'label-overflow': {
        'description': 'FAST label replaced by a ten-letter label',
        # labels[2] is u16[11]: FAST, terminator, six zero units.
        'edits': [(0x01FF8BA8, units('FAST') + bytes(12), units('FASTFASTFA'))],
        'gates': {'options': 'label', 'save': 'label'}},
    'new-game-normal': {
        'description': 'new-game Options initialiser sets NORMAL instead of FAST (main ARM9)',
        'edits': [(0x0202B176, B('0420'), B('0020'))],
        'gates': {'new-game': 'does not start at FAST'}},
    'arena-overlap': {
        'description': 'SDK ITCM arena lower bound put back over the payload (main ARM9 data)',
        'edits': [(0x020D1A28, B('e08bff01'), B('2086ff01'))],
        'gates': {'lifecycle': 'ITCM arena', 'options': 'ITCM arena'}},
    # Phone-call wait (D-1600, bug D-1599).
    'no-call-redirect': {
        'description': 'Pokégear call printer calls AddTextPrinterParameterized directly again (overlay 92)',
        'edits': [(0x021F1228, bl(0x021F1228, 0x01FF8B41), bl(0x021F1228, 0x02020834), GEAR)],
        'gates': {'phone-call': 'advanced without input'}},
    'call-clear-noop': {
        'description': 'call_print no longer clears auto-scroll (blx SetAutoScrollParam -> nop)',
        'edits': [nop(0x01FF8B50, '8847')],
        'gates': {'phone-call': 'advanced without input'}},
    'no-control-stop': {
        'description': 'batching no longer stops before control codes',
        'edits': [nop(0x01FF878E, '27d3'), nop(0x01FF8796, '23d3'), nop(0x01FF879C, '20d0')],
        'gates': {'corpus': 'without a frame decision', 'controls': 'without a frame decision',
                  'battle': 'to_free'}},
    'eos-only-no-stop': {
        'description': 'batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls)',
        'edits': [nop(0x01FF8796, '23d3')],
        'gates': {'corpus': 'without a frame decision', 'battle': 'without a frame decision'}},
    'no-newline-peek': {
        'description': 'batching no longer looks past a newline: a newline before the end of the text is '
                       'rendered with the batch',
        'edits': [(0x01FF8782, B('01d1'), B('01e0'))],
        'gates': {'battle': 'end-of-text step moved'}},
    'space-stop': {
        'description': 'batching stops before every space (0x01DE) instead of 0xF0FD',
        'edits': [(0x01FF8824, B('fdf00000'), B('de010000'))],
        'gates': {'corpus': 'allowed another glyph', 'natural-dialogue': 'allowed another glyph',
                  'fallbacks': 'allowed another glyph', 'callbacks': 'allowed another glyph'}},
    'no-color-setup': {
        'description': 'native task no longer sets the glyph colour table before rendering',
        'edits': [nop(0x01FF871C, '9847')],
        'gates': {'corpus': 'pages differs', 'controls': 'pages differs', 'callbacks': 'pixels differ'}},
    'no-state-stop': {
        'description': 'batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph',
        'edits': [nop(0x01FF8770, '36d1'), nop(0x01FF8776, '33d1')],
        'dead': 'after a glyph (result 0) RenderText is always in state 0 with +0x2a = 0; '
                'see text_speed_release_checks.md'},
    'zero-glyph': {
        'description': 'the batching task returns before its first render (draws nothing)',
        'edits': [(0x01FF8710, B('e27d'), B('f5e7'))],
        'gates': {'corpus': 'did not complete', 'natural-dialogue': 'expected the 54-glyph trainer page',
                  'fallbacks': 'expected 54 glyphs', 'callbacks': '(0 glyphs)',
                  'scenes': 'no native tasks observed', 'battle': 'stuck without A/B input'}},
    'frame-rule-ignored': {
        'description': 'the frame decision always draws (the batch always uses its whole budget)',
        'edits': [(0x01FF87A8, B('00f03ef8'), B('0120c046'))],
        'gates': {'natural-dialogue': 'after a frame stop', 'fallbacks': 'after a frame stop',
                  'callbacks': 'after a frame stop', 'scenes': 'after a frame stop'}},
    'rest-not-stored': {
        'description': 'frame_end no longer stores the measured rest (the decision runs on the seed)',
        'edits': [nop(0x01FF8678, '0a72')],
        'gates': {'natural-dialogue': 'payload state', 'scenes': 'payload state', 'corpus': 'payload state',
                  'fallbacks': 'payload state', 'callbacks': 'payload state'}},
    # The next faults keep the gates' frame model equal to the broken payload ('checker'),
    # so only the product checks can catch them.
    'fixed-model': {
        'description': 'the cf50a23 rule: draw when 20 or more lines are left, lost below 7, no measured costs',
        # fit when left > 19 (movs r1,#19 for glyph + rest); low = 7 (movs r3,#7); 'a rest was
        # measured' = 1 (movs r0,#1)
        'edits': [(0x01FF8892, B('5118'), B('1321')), (0x01FF88B0, B('461e'), B('0723')),
                  (0x01FF88B2, B('b041'), B('0120'))],
        'checker': {'FIXED_MODEL': [20, 7]},
        'gates': {'scenes': 'would have fitted'}},
    'tail-ignored': {
        'description': 'the decision leaves out the rest of the pass (predicts only the glyph)',
        # adds r1,r2,r1 (glyph + rest) -> movs r1,r2 (glyph)
        'edits': [(0x01FF8892, B('5118'), B('1100'))],
        'checker': {'IGNORE_REST': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    'glyph-ignored': {
        'description': 'the decision leaves out the glyph cost (predicts only the rest of the pass)',
        # adds r1,r2,r1 (glyph + rest) -> movs r1,r1 (rest)
        'edits': [(0x01FF8892, B('5118'), B('0900'))],
        'checker': {'IGNORE_GLYPH': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    'short-history-unguarded': {
        'description': 'no rest floor while fewer than 3 rests are measured (the Route 1 promoter drop of 2026-10-07)',
        # rest = max(rest, 7) while samples < 3  ->  max(rest, 0)
        'edits': [(0x01FF8882, B('0721'), B('0021'))],
        'checker': {'SHORT_REST': 0},
        'gates': {'scenes': 'dropped only because'}},
    'no-catch-up': {
        'description': 'pass_end never catches up (a late pass needs 255 VBlanks): the hack\'s half rate in 30 fps maps',
        # cmp r2,#2 (VBlanks since the previous pass end) -> cmp r2,#255
        'edits': [(0x01FF8A6A, B('022a'), B('ff2a'))],
        'checker': {'NO_CATCH_UP': True},
        'gates': {'field-rate': 'frames per glyph'}},
    # Too conservative: every stored glyph cost is larger (both the plain and the line-wrap
    # branch of lines_between: catch-up batches cross line 0), so an extra glyph needs that
    # many more lines once a glyph cost is measured. (The SLOW-era variants biased the rest
    # instead and were caught by the SLOW floor; without SLOW the 'would have fitted' rule
    # must catch them.)
    'too-conservative-24': {
        'description': 'needs 4 more lines for an extra glyph (the review\'s threshold 24 against 20)',
        'edits': [(0x01FF874A, B('2900'), B('291d')), (0x01FF8750, B('0831'), B('0c31'))],
        'checker': {'GLYPH_COST_BIAS': 4},
        'gates': {'scenes': 'would have fitted', 'natural-dialogue': 'would have fitted'}},
    'too-conservative-27': {
        'description': 'needs 7 more lines for an extra glyph (the largest bias one Thumb instruction encodes)',
        'edits': [(0x01FF874A, B('2900'), B('e91d')), (0x01FF8750, B('0831'), B('0f31'))],
        'checker': {'GLYPH_COST_BIAS': 7},
        'gates': {'scenes': 'would have fitted', 'natural-dialogue': 'would have fitted'}},
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
    gear = rom.loadArm9Overlays()[GEAR]
    gear_data = bytearray(gear.data)
    if gear.compressed:
        raise SystemExit('unexpected compressed Pokégear overlay')
    for address, before, after, *where in edits:
        if len(after) > len(before):
            raise SystemExit(f'{a.fault}: edit at {address:#x} grows')
        after = after + before[len(after):]
        if where == [GEAR]:
            start, section = gear.ramAddress, gear_data
            if not start <= address < start + len(gear_data):
                raise SystemExit(f'{a.fault}: {address:#x} is outside overlay {GEAR}')
        elif where:
            raise SystemExit(f'{a.fault}: unknown edit target {where}')
        else:
            start = ITCM if address < 0x02000000 else main.ramAddress
            section = data[start]
        off = address - start
        if bytes(section[off:off + len(before)]) != before:
            raise SystemExit(f'{a.fault}: candidate bytes at {address:#x} are not the reviewed ones')
        if section is data[ITCM]:
            rel = address - payload['base']
            if bytes(code[rel:rel + len(before)]) != before:
                raise SystemExit(f'{a.fault}: payload bytes at {address:#x} are not the reviewed payload')
            code[rel:rel + len(before)] = after
        section[off:off + len(before)] = after
    itcm.data, main.data = bytes(data[ITCM]), bytes(data[main.ramAddress])
    rom.arm9 = arm9.save(compress=False)
    rom.files[gear.fileID] = bytes(gear_data)
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
