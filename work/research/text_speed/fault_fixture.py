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
# Addresses are those of the reviewed payload of D-2269/D-2271/D-2279 (tick-timer timing, estimates once per
# batch: 2460 bytes, print_task 0x01FF874C, pass_end 0x01FF8B88, call_print 0x01FF8E2C, frame state 0x01FF8F88).
# Removed with SLOW (D-1604): 'slow-flat' (SLOW's phase: there is no SLOW and no phase)
# and 'no-phase-reset' (init_printer and the private +0x34 phase byte no longer exist).
FAULTS = {
    'fast-budget': {
        'description': 'FAST budget 9 instead of 3 glyphs per task',
        'edits': [(0x01FF87B2, B('0320'), B('0920'))],
        'gates': {'corpus': 'design budget', 'battle': 'design budget', 'callbacks': 'design budget',
                  'fallbacks': 'budget', 'natural-dialogue': 'design budget', 'scenes': 'budget'}},
    'normal-batches': {
        'description': 'NORMAL (stored 0) batches like FAST: fast() tests value <= 1 instead of == 1',
        # cmp r1,#4 (bits 2..3 masked); bne original -> bhi original
        'edits': [(0x01FF876C, B('07d1'), B('07d8'))],
        'gates': {'corpus': 'did not delegate', 'scenes': 'did not delegate', 'natural-dialogue': 'did not delegate',
                  'fallbacks': 'fallback skipped the original task', 'field-rate': 'did not delegate'}},
    'unknown-value-fast': {
        'description': 'unknown values 2 and 3 are treated as FAST (printer and Options row)',
        # fast(): bne original -> blo original (only value 0 delegates); load_rows: shows
        # FAST for every nonzero value (subs r0,r1,#1; movs r1,#0; adcs r1,r1)
        'edits': [(0x01FF876C, B('07d1'), B('07d3')), (0x01FF8A22, B('081f'), B('481e')),
                  (0x01FF8A24, B('4142'), B('0021')), (0x01FF8A26, B('4141'), B('4941'))],
        'gates': {'options': 'is not shown as NORMAL', 'fallbacks': 'fallback skipped the original task',
                  'corpus': 'did not delegate'}},
    # exit_free has commit_speed inlined; the standalone commit_speed copy is not called.
    'commit-noop': {
        'description': 'Options Confirm no longer stores the text-speed bits',
        'edits': [nop(0x01FF8AFE, '0180')],
        'gates': {'options': 'did not store the chosen text speed', 'save': 'did not store the chosen text speed',
                  'music': 'did not store the chosen text speed', 'corpus': 'did not store the chosen text speed'}},
    'label-overflow': {
        'description': 'FAST label replaced by a ten-letter label',
        # labels[2] is u16[11]: FAST, terminator, six zero units.
        'edits': [(0x01FF8F70, units('FAST') + bytes(12), units('FASTFASTFA'))],
        'gates': {'options': 'label', 'save': 'label'}},
    'new-game-normal': {
        'description': 'new-game Options initialiser sets NORMAL instead of FAST (main ARM9)',
        'edits': [(0x0202B176, B('0420'), B('0020'))],
        'gates': {'new-game': 'does not start at FAST'}},
    'arena-overlap': {
        'description': 'SDK ITCM arena lower bound put back over the payload (main ARM9 data)',
        'edits': [(0x020D1A28, B('c08fff01'), B('2086ff01'))],
        'gates': {'lifecycle': 'ITCM arena', 'options': 'ITCM arena'}},
    # Phone-call wait (D-1600, bug D-1599).
    'no-call-redirect': {
        'description': 'Pokégear call printer calls AddTextPrinterParameterized directly again (overlay 92)',
        'edits': [(0x021F1228, bl(0x021F1228, 0x01FF8E2D), bl(0x021F1228, 0x02020834), GEAR)],
        'gates': {'phone-call': 'advanced without input'}},
    'call-clear-noop': {
        'description': 'call_print no longer clears auto-scroll (blx SetAutoScrollParam -> nop)',
        'edits': [nop(0x01FF8E3C, '8847')],
        'gates': {'phone-call': 'advanced without input'}},
    'no-control-stop': {
        'description': 'batching no longer stops before control codes',
        'edits': [nop(0x01FF88A4, '6bd3'), nop(0x01FF88AC, '67d3'), nop(0x01FF88B2, '64d0')],
        # Not callbacks (2026-10-09, D-2279 payload): its page-2 latencies were identical with and without the
        # fault at both input phases (rc5 matrix): its batches never reach the page prompt with budget left.
        'gates': {'corpus': 'without a frame decision', 'controls': 'without a frame decision',
                  'battle': 'to_free'}},
    'eos-only-no-stop': {
        'description': 'batching no longer stops before 0xFFFF/0xFFFE (end of text, extended controls)',
        'edits': [nop(0x01FF88AC, '67d3')],
        'gates': {'corpus': 'without a frame decision', 'battle': 'without a frame decision'}},
    'no-newline-peek': {
        'description': 'batching no longer looks past a newline: a newline before the end of the text is '
                       'rendered with the batch',
        'edits': [(0x01FF8898, B('01d1'), B('01e0'))],
        'gates': {'battle': 'end-of-text step moved'}},
    'budget-batch-no-copy': {
        'description': 'a FAST batch that ends on its glyph budget skips its window copy (and mark): the drawn '
                       'glyphs appear with the next copy, so the box changes later at the start of the next '
                       'message; the glyph draws and the completed text are unchanged',
        # beq (budget exhausted) to the window copy -> beq to the return
        'edits': [(0x01FF88BA, B('60d0'), B('5fd0'))],
        'gates': {'battle': 'the speed\'s code changes the pause'}},
    'space-stop': {
        'description': 'batching stops before every space (0x01DE) instead of 0xF0FD',
        'edits': [(0x01FF8A08, B('fdf00000'), B('de010000'))],
        'gates': {'corpus': 'allowed another glyph', 'natural-dialogue': 'allowed another glyph',
                  'fallbacks': 'allowed another glyph', 'callbacks': 'allowed another glyph'}},
    'no-color-setup': {
        'description': 'native task no longer sets the glyph colour table before rendering',
        'edits': [nop(0x01FF87A6, '9847')],
        'gates': {'corpus': 'pages differs', 'controls': 'pages differs', 'callbacks': 'pixels differ'}},
    'no-state-stop': {
        'description': 'batch ignores RenderText state +0x28 / delay counter +0x2a after a glyph',
        'edits': [nop(0x01FF8886, '7ad1'), nop(0x01FF888C, '77d1')],
        'dead': 'after a glyph (result 0) RenderText is always in state 0 with +0x2a = 0; '
                'see text_speed_release_checks.md'},
    'zero-glyph': {
        'description': 'the batching task returns before its first render (draws nothing)',
        'edits': [(0x01FF879C, B('e27d'), B('f3e7'))],
        'gates': {'corpus': 'did not complete', 'natural-dialogue': 'expected the 54-glyph trainer page',
                  'fallbacks': 'expected 54 glyphs', 'callbacks': '(0 glyphs)',
                  'scenes': 'no native tasks observed', 'battle': 'stuck without A/B input'}},
    'frame-rule-ignored': {
        'description': 'the frame decision always draws (the batch always uses its whole budget)',
        'edits': [(0x01FF88F6, B('00f065fa'), B('01200004'))],
        'gates': {'natural-dialogue': 'after a frame stop', 'fallbacks': 'after a frame stop',
                  'callbacks': 'after a frame stop', 'scenes': 'after a frame stop'}},
    'rest-not-stored': {
        'description': 'frame_end no longer stores the measured rest (the decision runs on the seed)',
        'edits': [nop(0x01FF86EA, '0a82')],
        'gates': {'natural-dialogue': 'payload state', 'scenes': 'payload state', 'corpus': 'payload state',
                  'fallbacks': 'payload state', 'callbacks': 'payload state'}},
    # The next faults keep the gates' frame model equal to the broken payload ('checker'),
    # so only the product checks can catch them.
    'fixed-model': {
        'description': 'a fixed rule that ignores the measured costs: an extra glyph needs 664 ticks (about 20 '
                       'lines, the cf50a23 threshold) whatever the glyph and the rest cost',
        # need = glyph + rest + MARGIN (adds r1,r1,r2; adds r1,#0x40) -> movs r1,#0xa6; lsls r1,r1,#2
        'edits': [(0x01FF8900, B('89184031'), B('a6218900'))],
        'checker': {'FIXED_NEED': 664},
        'gates': {'scenes': 'would have fitted'}},
    'tail-ignored': {
        'description': 'the decision leaves out the rest of the pass (predicts only the glyph)',
        # adds r1,r1,r2 (glyph + rest) -> nop (glyph)
        'edits': [nop(0x01FF8900, '8918')],
        'checker': {'IGNORE_REST': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    'glyph-ignored': {
        'description': 'the decision leaves out the glyph cost (predicts only the rest of the pass)',
        # adds r1,r1,r2 (glyph + rest) -> movs r1,r2 (rest)
        'edits': [(0x01FF8900, B('8918'), B('1100'))],
        'checker': {'IGNORE_GLYPH': True},
        'gates': {'scenes': 'dropped only because', 'natural-dialogue': 'dropped only because'}},
    # The floor's code path is proven by the model check (user decision 2026-10-08): no gate
    # shows the floor value 7 saving a frame in the current 17 scenes (with the floor removed,
    # movs r1,r0, and the gates' model matched, all decisions equal the candidate's). This edit
    # forces the short-history rest to 0; the gates keep the real floor in their model.
    'short-history-unguarded': {
        'description': 'the short-history branch forces the rest to 0 instead of the floor 7 (code path of the '
                       'floor added after the Route 1 promoter drop of 2026-10-07)',
        # compiled floor: rest; if rest <= 232 ticks (7 lines): the floor 232 (movs r1,#232 -> movs r1,#0); with 3 or more rests the rest
        'edits': [(0x01FF88D6, B('e821'), B('0021'))],
        'gates': {'scenes': 'drew on after a frame stop'}},
    'no-catch-up': {
        'description': 'pass_end never catches up (a late pass needs 255 VBlanks): the hack\'s half rate in 30 fps maps',
        # cmp r2,#2 (VBlanks since the previous pass end) -> cmp r2,#255
        'edits': [(0x01FF8BD2, B('022a'), B('ff2a'))],
        'checker': {'NO_CATCH_UP': True},
        'gates': {'field-rate': 'frames per glyph'}},
    # D-2175: the field-rate gate bounds what pass_end costs without text (its reading to its return, in
    # timer ticks) instead of comparing idle pass counts with the catch-up off, which depend on the
    # input phase. This fault proves the bound: pass_end's estimate loop runs 255 times instead of 8
    # (it reads past the frame state; the maxima it finds also suppress catch-ups).
    'catch-up-idle-cost': {
        'description': 'pass_end\'s catch-up walks 64 printer slots instead of 8 in every late pass that fits, '
                       'with or without text',
        # cmp r5,#8 (the printer slot loop) -> cmp r5,#64. Each extra slot costs about 0.17 ticks (rc5: 15 ticks
        # idle without the fault, 19 with 32 slots, under IDLE_TICKS 20); 255 slots (until 2026-10-09) made every
        # idle pass_end so slow that an interrupt always fell inside it, so the gate stopped at its vacuity guard
        # ('no pass_end without an interrupt') and never reached the cost bound this fault exists to prove.
        'edits': [(0x01FF8C72, B('082d'), B('402d'))],
        'gates': {'field-rate': 'idle: pass_end took'}},
    # Too conservative: every decision needs more time than the margin covers (the margin's
    # immediate adds r1,#0x40 raised: +133 ticks, about 4 display lines, and +191, the
    # largest one Thumb instruction encodes); the gates' model is set to match, so only the
    # 'would have fitted' rule can catch them.
    'too-conservative-24': {
        'description': 'needs 4 more lines (133 ticks) for an extra glyph',
        'edits': [(0x01FF8902, B('4031'), B('c531'))],
        'checker': {'MARGIN': 197},
        'gates': {'scenes': 'would have fitted', 'natural-dialogue': 'would have fitted'}},
    'too-conservative-27': {
        'description': 'needs 191 more ticks (about 5.7 lines) for an extra glyph: the largest margin one Thumb '
                       'instruction encodes',
        'edits': [(0x01FF8902, B('4031'), B('ff31'))],
        'checker': {'MARGIN': 255},
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
