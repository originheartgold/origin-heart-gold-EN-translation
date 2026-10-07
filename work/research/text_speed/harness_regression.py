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
budgets), the model checks per native task (text_speed_checks.task_errors with the
payload's frame model), the product record (gate_common.judge_message: frames,
dropped frames, frame stops), printer allocation/free pairing and per-heap usage
before and after the corpus, and the ITCM payload/arena state at the start and end
of the session. The parent compares the speeds with the original printer
(text_speed_checks.order_errors) and requires the printer tasks from each page's
last glyph to its control step to equal the original's.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLOCK, ROOT, PRINTER_START, PrinterTrace, add_arguments, attach_probe,  # noqa: E402
                         digest, heap_usage, identity, inputs_unchanged, itcm_errors, judge_message,
                         load_expected_payload, memory_errors, memory_summary, require, resolve)
import text_speed_checks as checks  # noqa: E402

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
            require(not start_itcm, repr(start_itcm))
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
                require(len(menus) == before + 1, 'Options failed to open')
                d = menus[-1]
                require(h.u16(d + 0x27c) == 3, 'text row missing')
                return d
            d = open_options()
            opts = h.u32(d + 0x24)
            original = h.u16(opts)
            require((original >> 2) & 3 == 0, 'fixture is not an old SLOW save')
            # First exercise cancel after touch, then reopen and commit via buttons.
            h.touch(227, 152, after=60)
            require(h.u16(d + 0x27e) == 2 and h.u16(opts) == original, 'check failed: h.u16(d + 0x27e) == 2 and h.u16(opts) == original')
            h.touch(220, 180, after=300)
            require(h.u16(opts) == original, 'Cancel committed text speed')
            d = open_options()
            require(h.u16(d + 0x27e) == 0, 'check failed: h.u16(d + 0x27e) == 0')
            # Touch locates the row; d-pad moves the value and A confirms native UI.
            ui_mode = 1 if args.mode == 3 else args.mode
            h.touch(130, 152, after=40)
            for _ in range(ui_mode):
                h.press('RIGHT', after=30)
            require(h.u16(d + 0x27e) == ui_mode, 'button selection failed')
            h.press('DOWN', after=30)
            require((h.u32(d + 16) >> 2) & 7 == 7, 'check failed: (h.u32(d + 16) >> 2) & 7 == 7')
            h.press('LEFT', after=30)  # Native CN row defaults to Quit (0); Confirm is 1.
            require(h.u16(d + 0x2d2) == 1, 'Confirm button not selected')
            prior_exits = len(exits)
            h.press('A', after=300)
            require(len(exits) == prior_exits + 1, 'A did not leave Options')
            h.press('B', after=90)  # Options returns to the field menu; close it before scripts.
            h.screenshot('after-confirm')
            expected = (original & ~12) | (ui_mode << 2)
            stored = h.u16(opts)
            require((stored >> 2) & 3 == (expected >> 2) & 3,
                    f'Confirm did not store the chosen text speed (Options {stored:#x}, expected {expected:#x})')
            require(stored == expected, repr(('Confirm changed unrelated options', stored, expected)))
            if args.mode == 3:
                expected = original | 12          # controlled: reserved value -> original printer task
                h.w16(opts, expected)
            result['options'] = {'before': original, 'after': expected, 'cancel': 'passed', 'buttons': 'passed'}
            idle_heaps = heap_usage(h)
            corpus = ((718, 160),) if args.controls else CORPUS
            if args.only_message:
                corpus = (tuple(int(x) for x in args.only_message.split('#')),)
            for bank, msg in corpus:
                mark, task_mark = trace.mark(), trace.task_mark()
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
                        require(checks.nonblank(crop.tobytes()), f'blank message window on page {page}')
                        pages.append(hashlib.sha256(crop.tobytes()).hexdigest())
                        page_marks.append(trace.mark())
                        if live_during is None:
                            live_during = len(printers.live())
                        h.screenshot(f'{bank}_{msg}_{page}')
                        n = trace.mark()
                        h.step(120)
                        require(trace.mark() == n, 'page progressed without input')
                        require(crop.tobytes() == h.emu.screenshot().crop(CROP).tobytes(), 'text changed while waiting')
                        h.press('A', after=480)
                    require(h.get_var(SENTINEL_VAR) == 0x5A5A, 'message did not complete within page budget')
                    glyphs = trace.since(mark)
                    require(glyphs and pages, 'empty/vacuous message test')
                    if args.controls:
                        from control_fixture import TEXT
                        source = TEXT
                        before = len(re.sub(r'\{[^}]*\}', '', TEXT.split('{VAR:0201:60}')[0]))
                        pause_gap = glyphs[before][2] - glyphs[before - 1][2]
                        require(pause_gap >= 60, repr(('explicit pause shortened', pause_gap)))
                        result['explicit_pause_frames'] = pause_gap
                        printer = trace.glyphs[mark + before][0]
                        result['explicit_pause_tasks'] = trace.tasks_between(glyphs[before - 1][0], glyphs[before][0],
                                                                             printer)
                    else:
                        bank_source = json.loads((ROOT / f'work/translate/banks/a027/{bank:04d}.json').read_text())
                        source = next(s['en'] for s in bank_source['strings'] if s['id'] == msg)
                    expected_glyphs = len(re.sub(r'\{[^}]*\}', '', source))
                    require(len(glyphs) == expected_glyphs, repr(('wrong message or incomplete rendering', bank, msg,
                                                            len(glyphs), expected_glyphs)))
                    # Printing time per page: first to last glyph, excluding page waits and input.
                    bounds = [m - mark for m in page_marks]
                    require(bounds[-1] == len(glyphs), 'glyphs drawn after the last page was captured')
                    page_frames = [(glyphs[a][2], glyphs[b - 1][2])
                                   for a, b in zip([0] + bounds[:-1], bounds) if b > a]
                    page_spans = [b - a for a, b in page_frames]
                    summary, cadence_errors = checks.cadence(args.mode, glyphs)
                    errors.extend(f'{bank}#{msg}: {e}' for e in cadence_errors)
                    # Model (budgets, frame decisions, stop reasons, phase) and product record:
                    # frames, dropped frames (frames inside a page's printing in which the
                    # printer's task did not run), frame stops.
                    record, stops, stop_errors = judge_message(trace, args.mode, mark, task_mark, page_frames)
                    errors.extend(f'{bank}#{msg}: {e}' for e in stop_errors + trace.state_errors)
                    lag_frames = record['drops']
                    require(live_during, 'no live printer observed while the message was displayed')
                    result['messages'].append({'bank': bank, 'id': msg, 'pages': pages, 'glyphs': len(glyphs),
                                               'layout': trace.layout(mark), 'page_spans': page_spans,
                                               'print_frames': sum(page_spans), 'lag_frames': lag_frames,
                                               'record': record,
                                               'control_latency': trace.control_latencies(
                                                   task_mark, set(trace.printers_since(mark))),
                                               'cadence': summary, 'stops': stops})
                finally:
                    h.set_var(SENTINEL_VAR, sentinel)
                require(h.u16(opts) == expected, 'dialogue changed Options')
            if args.dump_tasks:
                (args.out / 'tasks.json').write_text(json.dumps(trace.tasks, default=str))
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
            if not errors:
                result['status'] = 'passed'
    except BaseException as exc:
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
        limited = {m: modes[m]['messages'][i]['stops'].get('frame', 0) for m in MODES}
        free = {m: modes[m]['messages'][i]['control_latency'] for m in MODES}
        name = f"{base['bank']}#{base['id']}"
        order, notes = checks.order_errors({m: modes[m]['messages'][i]['record'] for m in MODES})
        order += checks.exact_errors('printer tasks from each page\'s last glyph to its control step', free[3],
                                     {m: free[m] for m in (0, 1, 2)})
        if not free[3]:
            order.append('no control step observed after a glyph (vacuous control-latency check)')
        orders.append({'message': name, 'print_frames': spans, 'lag_frames': lag, 'frame_stops': limited,
                       'control_latency': free, 'errors': order, 'capped_ties': notes})
        errors += [f'{name}: {e}' for e in order]
        report.setdefault('capped_ties', []).extend(f'{name}: {n}' for n in notes)
    report['speed_order'] = orders
    per_frame = {m: max(x['cadence']['max_tasks_per_frame'] for x in modes[m]['messages']) for m in MODES}
    report['max_tasks_per_frame'] = per_frame
    errors += [f'{checks.NAMES[m]}: {per_frame[m]} printer tasks in one frame, original {per_frame[3]}'
               for m in (0, 1, 2) if per_frame[m] > per_frame[3]]
    if 'explicit_pause_tasks' in modes[3]:
        # The 60-tick pause counts printer tasks; frames are an observation (a dropped
        # frame inside the pause lengthens it by one frame at any speed, original included).
        report['explicit_pause_frames'] = {m: modes[m]['explicit_pause_frames'] for m in MODES}
        pause = {m: modes[m]['explicit_pause_tasks'] for m in MODES}
        report['explicit_pause_tasks'] = pause
        errors += [f'{checks.NAMES[m]}: explicit pause {pause[m]} printer tasks != original {pause[3]}'
                   for m in (0, 1, 2) if pause[m] != pause[3]]
    return errors


def main():
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    p.add_argument('--mode', type=int, choices=MODES)
    p.add_argument('--controls', action='store_true', help='Use the separately generated authored control fixture ROM')
    p.add_argument('--only-message', help='diagnosis only: BANK#ID of one corpus message (child mode)')
    p.add_argument('--dump-tasks', action='store_true', help='diagnosis only: write every task record (child mode)')
    args = resolve(p, p.parse_args())
    if args.mode is not None:
        child(args)
        return
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload), 'modes': [], 'errors': []}
    try:
        for mode in MODES:
            out = args.out / str(mode)
            command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                       '--out', str(out), '--mode', str(mode)]
            command += ['--controls'] if args.controls else []
            command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
            with (args.out / f'{mode}.log').open('w') as log:
                code = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                      cwd=ROOT).returncode
            if not (out / 'report.json').exists():
                report['errors'].append(f'mode {mode} child wrote no report (exit {code})')
                continue
            r = json.loads((out / 'report.json').read_text())
            require(r['rom_sha256'] == report['inputs'][str(args.rom)], 'wrong candidate executed')
            report['modes'].append(r)
            if code or r['status'] != 'passed':
                report['errors'].append(f"mode {mode} child failed: {r.get('errors') or 'see ' + str(out)}")
        if not report['errors']:
            report['errors'] = compare(report)
        if not inputs_unchanged(report):
            report['errors'].append('input modified')
        if not report['errors'] and len(report['modes']) == len(MODES):
            report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, report['errors'])) or 'failed')


if __name__ == '__main__':
    main()
