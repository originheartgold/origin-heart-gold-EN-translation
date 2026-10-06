"""Cold-boot text-speed corpus regression using emu_harness.

Script injection selects messages only; SLOW/MEDIUM/FAST are chosen through the
native Options UI. Each mode runs in its own process with a private battery
directory. No old savestates.

Mode 3 is the controlled baseline: Options are confirmed through the UI, then the
reserved value 3 is written to the two text-speed bits, which makes the native
task delegate every call to the original printer task. All three choices must
reproduce that baseline's completed pages, glyph count and glyph layout exactly.

Per message and speed the child also records the glyph cadence (glyphs per native
task and per frame, judged by text_speed_checks.cadence against the design
budgets), per-page printing spans, printer allocation/free pairing and per-heap
usage before and after the corpus, and the ITCM payload/arena state at the start
and end of the session.
"""
import argparse
from datetime import datetime
import hashlib
import json
import re
import subprocess
import sys

from gate_common import (CLOCK, ROOT, PRINTER_START, PrinterTrace, add_arguments, attach_probe,
                         digest, heap_usage, identity, inputs_unchanged, itcm_errors, load_expected_payload,
                         memory_errors, memory_summary, resolve)
import text_speed_checks as checks

CORPUS = ((48, 20), (48, 26), (48, 60), (457, 123), (718, 160), (718, 1093))
MODES = (3, 0, 1, 2)          # baseline first
CROP = (8, 145, 236, 184)     # message window text area; excludes the animated continuation arrow


def child(args):
    from emu_harness import Harness, SENTINEL_VAR, message_script
    payload = load_expected_payload(args)
    result = {'status': 'failed', 'rom_sha256': digest(args.rom), 'mode': args.mode, 'messages': [], 'errors': []}
    errors = result['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            h.set_clock(datetime(2026, 10, 9, 12))
            h.boot_to_menu()
            h.continue_game()
            start_itcm = itcm_errors(h, payload)
            assert not start_itcm, start_itcm
            probe = attach_probe(h)
            menus = []
            exits = []
            h.on_exec(payload['symbols']['exit_free'] & ~1, lambda h: exits.append(h.frame))
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            trace = printers = PrinterTrace(h, payload, font=1, probe=probe)
            starts = []
            h.on_exec(PRINTER_START, lambda h: starts.append({'speed': h.reg.r1, 'callback': h.reg.r2}))

            def open_options():
                before = len(menus)
                h.press('X', after=90)
                h.touch(124, 115, after=300)
                assert len(menus) == before + 1, 'Options failed to open'
                d = menus[-1]
                assert h.u16(d + 0x27c) == 3, 'text row missing'
                return d
            d = open_options()
            opts = h.u32(d + 0x24)
            original = h.u16(opts)
            assert (original >> 2) & 3 == 0, 'fixture is not an old SLOW save'
            # First exercise cancel after touch, then reopen and commit via buttons.
            h.touch(227, 152, after=60)
            assert h.u16(d + 0x27e) == 2 and h.u16(opts) == original
            h.touch(220, 180, after=300)
            assert h.u16(opts) == original, 'Cancel committed text speed'
            d = open_options()
            assert h.u16(d + 0x27e) == 0
            # Touch locates the row; d-pad moves the value and A confirms native UI.
            ui_mode = 1 if args.mode == 3 else args.mode
            h.touch(130, 152, after=40)
            for _ in range(ui_mode):
                h.press('RIGHT', after=30)
            assert h.u16(d + 0x27e) == ui_mode, 'button selection failed'
            h.press('DOWN', after=30)
            assert (h.u32(d + 16) >> 2) & 7 == 7
            h.press('LEFT', after=30)  # Native CN row defaults to Quit (0); Confirm is 1.
            assert h.u16(d + 0x2d2) == 1, 'Confirm button not selected'
            prior_exits = len(exits)
            h.press('A', after=300)
            assert len(exits) == prior_exits + 1, 'A did not leave Options'
            h.press('B', after=90)  # Options returns to the field menu; close it before scripts.
            h.screenshot('after-confirm')
            expected = (original & ~12) | (ui_mode << 2)
            assert h.u16(opts) == expected, ('Confirm changed unrelated options', h.u16(opts), expected)
            if args.mode == 3:
                expected = original | 12          # controlled: reserved value -> original printer task
                h.w16(opts, expected)
            result['options'] = {'before': original, 'after': expected, 'cancel': 'passed', 'buttons': 'passed'}
            idle_heaps = heap_usage(h)
            for bank, msg in (((718, 160),) if args.controls else CORPUS):
                mark = trace.mark()
                sentinel = h.get_var(SENTINEL_VAR)
                h.set_var(SENTINEL_VAR, 0)
                program = message_script(bank, msg)
                try:
                    h.run_script(file=3, index=0, msg_bank=bank, program=program, settle=480)
                    pages, page_marks, live_during = [], [], None
                    for page in range(16):
                        if h.get_var(SENTINEL_VAR) == 0x5A5A:
                            break
                        crop = h.emu.screenshot().crop(CROP)
                        assert checks.nonblank(crop.tobytes()), f'blank message window on page {page}'
                        pages.append(hashlib.sha256(crop.tobytes()).hexdigest())
                        page_marks.append(trace.mark())
                        if live_during is None:
                            live_during = len(printers.live())
                        h.screenshot(f'{bank}_{msg}_{page}')
                        n = trace.mark()
                        h.step(120)
                        assert trace.mark() == n, 'page progressed without input'
                        assert crop.tobytes() == h.emu.screenshot().crop(CROP).tobytes(), 'text changed while waiting'
                        h.press('A', after=480)
                    assert h.get_var(SENTINEL_VAR) == 0x5A5A, 'message did not complete within page budget'
                    glyphs = trace.since(mark)
                    assert glyphs and pages, 'empty/vacuous message test'
                    if args.controls:
                        from control_fixture import TEXT
                        source = TEXT
                        before = len(re.sub(r'\{[^}]*\}', '', TEXT.split('{VAR:0201:60}')[0]))
                        pause_gap = glyphs[before][2] - glyphs[before - 1][2]
                        assert pause_gap >= 60, ('explicit pause shortened', pause_gap)
                        result['explicit_pause_frames'] = pause_gap
                    else:
                        bank_source = json.loads((ROOT / f'work/translate/banks/a027/{bank:04d}.json').read_text())
                        source = next(s['en'] for s in bank_source['strings'] if s['id'] == msg)
                    expected_glyphs = len(re.sub(r'\{[^}]*\}', '', source))
                    assert len(glyphs) == expected_glyphs, ('wrong message or incomplete rendering', bank, msg,
                                                            len(glyphs), expected_glyphs)
                    # Printing time per page: first to last glyph, excluding page waits and input.
                    bounds = [m - mark for m in page_marks]
                    assert bounds[-1] == len(glyphs), 'glyphs drawn after the last page was captured'
                    page_spans = [glyphs[b - 1][2] - glyphs[a][2]
                                  for a, b in zip([0] + bounds[:-1], bounds) if b > a]
                    # Frames inside a page's printing in which no glyph was drawn (game lag or
                    # explicit pauses; the same pauses occur at every speed).
                    lag_frames = sum(glyphs[b - 1][2] - glyphs[a][2] + 1 - len({g[2] for g in glyphs[a:b]})
                                     for a, b in zip([0] + bounds[:-1], bounds) if b > a)
                    summary, cadence_errors = checks.cadence(args.mode, glyphs)
                    errors.extend(f'{bank}#{msg}: {e}' for e in cadence_errors)
                    assert live_during, 'no live printer observed while the message was displayed'
                    result['messages'].append({'bank': bank, 'id': msg, 'pages': pages, 'glyphs': len(glyphs),
                                               'layout': trace.layout(mark), 'page_spans': page_spans,
                                               'print_frames': sum(page_spans), 'lag_frames': lag_frames,
                                               'cadence': summary})
                finally:
                    h.set_var(SENTINEL_VAR, sentinel)
                assert h.u16(opts) == expected, 'dialogue changed Options'
            h.step(60)
            result['printers'] = {'starts': len(starts), 'allocations': len(printers.allocations),
                                  'live_after': printers.live()}
            if result['printers']['live_after']:
                errors.append(f"printer allocations never freed: {result['printers']['live_after']}")
            after_heaps = heap_usage(h)
            result['heaps'] = {'idle_before': idle_heaps, 'idle_after': after_heaps}
            errors.extend(checks.heap_growth_errors([idle_heaps, after_heaps]))
            result['memory'] = memory_summary(probe)
            errors.extend(memory_errors(result['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
            assert not errors, errors
            result['status'] = 'passed'
    except BaseException as exc:
        if not errors or str(exc) != str(errors):
            errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(result, indent=2, default=str))


def compare(report):
    """Cross-mode assertions; returns errors."""
    modes = {r['mode']: r for r in report['modes']}
    baseline = modes[3]['messages']
    errors = []
    for mode in (0, 1, 2):
        errors += [f'{checks.NAMES[mode]}: {e}' for e in checks.compare_messages(baseline, modes[mode]['messages'])]
    orders = []
    for i, base in enumerate(baseline):
        spans = {m: modes[m]['messages'][i]['print_frames'] for m in MODES}
        lag = {m: modes[m]['messages'][i]['lag_frames'] for m in MODES}
        order, warnings = checks.speed_order_with_lag(spans, lag)
        orders.append({'message': f"{base['bank']}#{base['id']}", 'print_frames': spans, 'lag_frames': lag,
                       'errors': order, 'warnings': warnings})
        errors += [f"{base['bank']}#{base['id']}: {e}" for e in order]
        report.setdefault('warnings', []).extend(f"{base['bank']}#{base['id']}: {w}" for w in warnings)
    report['speed_order'] = orders
    per_frame = {m: max(x['cadence']['max_tasks_per_frame'] for x in modes[m]['messages']) for m in MODES}
    report['max_tasks_per_frame'] = per_frame
    errors += [f'{checks.NAMES[m]}: {per_frame[m]} printer tasks in one frame, original {per_frame[3]}'
               for m in (0, 1, 2) if per_frame[m] > per_frame[3]]
    if 'explicit_pause_frames' in modes[3]:
        pause = {m: modes[m]['explicit_pause_frames'] for m in MODES}
        report['explicit_pause_frames'] = pause
        errors += [f'{checks.NAMES[m]}: explicit pause {pause[m]} frames != original {pause[3]}'
                   for m in (0, 1, 2) if abs(pause[m] - pause[3]) > 1]
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    p.add_argument('--mode', type=int, choices=MODES)
    p.add_argument('--controls', action='store_true', help='Use the separately generated authored control fixture ROM')
    args = resolve(p, p.parse_args())
    if args.mode is not None:
        child(args)
        return
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload), 'modes': [], 'errors': []}
    try:
        for mode in MODES:
            out = args.out / str(mode)
            command = [sys.executable, __file__, '--rom', str(args.rom), '--save', str(args.save),
                       '--out', str(out), '--mode', str(mode)]
            command += ['--controls'] if args.controls else []
            command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
            with (args.out / f'{mode}.log').open('w') as log:
                code = subprocess.run(command, timeout=900, stdout=log, stderr=subprocess.STDOUT,
                                      cwd=ROOT).returncode
            r = json.loads((out / 'report.json').read_text())
            assert r['rom_sha256'] == report['inputs'][str(args.rom)], 'wrong candidate executed'
            report['modes'].append(r)
            if code or r['status'] != 'passed':
                report['errors'].append(f"mode {mode} child failed: {r.get('errors') or 'see ' + str(out)}")
        if not report['errors']:
            report['errors'] = compare(report)
        assert inputs_unchanged(report), 'input modified'
        if not report['errors']:
            report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, report['errors'])) or 'failed')


if __name__ == '__main__':
    main()
