"""Controlled callback fallback, busy callback retries and A/B input comparisons.

Uses a same-candidate checkpoint in front of the trainer fixture (a two-page
conversation). Mode 3 (unknown value, controlled RAM write) is the original
printer task and the baseline for every case; NORMAL must delegate exactly like it.

- callback / busy: an existing, byte-verified return-zero code sequence is
  injected as the printer callback; only its return value is overridden to
  simulate four busy retries. No executable code is injected. Callback events,
  task cadence, layout and completed pixels must equal the original, and every
  native task must delegate to the original task.
- held-A / held-B: holding A (or B while pressing A) must not advance past the
  first page's wait; after release ONE new press must start page 2 with exactly
  the original's latency and glyph positions (no lost or latched input).
- tap: A tapped (4 frames down, 4 up) from the start. Page 2 must start only after a
  tap that began after page 1 was complete, with exactly the original's latency from
  that tap; page 1 and the start of page 2 keep the original layout.
Plain/held/tap cases are judged per native task (text_speed_checks.task_errors:
NORMAL delegates; FAST budget, frame decisions against the payload's frame model,
stop reason).
These are renderer/input tests on one natural conversation, not a scene audit.
"""
import argparse
import hashlib
import json

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, PRINTER_START, PrinterTrace, start_game, add_arguments, attach_probe, code_bytes, identity,
                         inputs_unchanged, itcm_errors, load_expected_payload, memory_errors, memory_summary, require,
                         resolve)
import text_speed_checks as checks

STUB = 0x0200107A
CALLBACK_SITES = (0x02020A67, 0x02020A7F)
PAGE1 = 54
PROMPT_READY = 2   # frames from the last glyph until the page prompt accepts input
KINDS = ('callback', 'busy', 'held-A', 'held-B', 'tap')
CROP = (8, 153, 236, 182)


def main():
    from emu_harness import Harness
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    p.add_argument('--kinds', default=','.join(KINDS), help='comma-separated subset (diagnosis only; '
                   'validate_release always runs all)')
    args = resolve(p, p.parse_args())
    kinds = args.kinds.split(',')
    if not set(kinds) <= set(KINDS):
        p.error(f'unknown kinds {kinds}')
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload), 'cases': {}, 'errors': []}
    errors = report['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start = itcm_errors(h, payload)
            require(not start, f'ITCM at start: {start}')
            checkpoint = args.out / 'candidate.dst'
            h.save_state(checkpoint)
            code = code_bytes(payload)
            tracer = PrinterTrace(h, payload, font=1)
            for kind in kinds:
                for mode in checks.MODES:
                    h.load_state(checkpoint)
                    tracer.reset()
                    require(h.read(payload['base'], len(code)) == code, 'stale checkpoint executable')
                    require(h.read(STUB, 4) == bytes.fromhex('00207047'), 'callback stub bytes changed')
                    opts = h.array(1)
                    value = (h.u16(opts) & ~12) | (mode << 2)
                    h.w16(opts, value)
                    trace = {'callbacks': [], 'injected': 0, 'taps': []}

                    def constructor(h):
                        if kind in ('callback', 'busy') and h.u8(h.reg.r0 + 9) == 1:
                            require(h.reg.r2 == 0, 'fixture already has a callback')
                            h.reg.r2 = STUB | 1
                            trace['injected'] += 1

                    def callback(h):
                        if h.reg.lr not in CALLBACK_SITES:
                            return
                        require(h.u8(h.reg.r0 + 9) == 1, 'callback for an unexpected printer')
                        trace['callbacks'].append({'event': h.reg.r1, 'glyphs': len(tracer.glyphs)})

                    def callback_return(h):
                        if h.reg.lr in CALLBACK_SITES:
                            h.reg.r0 = int(kind == 'busy' and len(trace['callbacks']) <= 4)
                    h.on_exec(PRINTER_START, constructor)
                    h.on_exec(STUB, callback)
                    h.on_exec(STUB + 2, callback_return)
                    probe = attach_probe(h)
                    probe.frame = h.frame
                    press = None
                    if kind == 'held-A':
                        h.hold('A'); h.step(406); h.release(); h.step(10)
                    elif kind == 'held-B':
                        h.hold('B'); h.press('A', after=400); h.release(); h.step(10)
                    elif kind == 'tap':
                        for _ in range(30):
                            trace['taps'].append(h.frame)
                            h.press('A', frames=4, after=4)
                        h.step(60)
                    else:
                        h.press('A', after=400)
                    tag = f'{kind}-{mode}'
                    rows = list(tracer.glyphs)
                    page1 = rows[:PAGE1]
                    if kind in ('held-A', 'held-B'):
                        require(len(rows) == PAGE1, f'{tag}: held input moved past page 1 ({len(rows)} glyphs)')
                        trace['pixels'] = hashlib.sha256(h.emu.screenshot().crop(CROP).tobytes()).hexdigest()
                        press = h.frame
                        h.press('A', after=120)
                        rows = list(tracer.glyphs)
                    tasks = [t for t in tracer.tasks if t['font'] == 1]
                    native, original = len(tasks), sum(1 for t in tasks if t['delegated'])
                    require(native > 0 and len(page1) == PAGE1, f'{tag}: page 1 incomplete ({len(rows)} glyphs)')
                    require(h.u16(opts) == value, f'{tag}: Options changed')
                    if kind in ('callback', 'busy'):
                        require(len(rows) == PAGE1, f'{tag}: callback case left page 1')
                        require(trace['injected'] > 0, f'{tag}: callback injection not exercised')
                        require(original == native, f'{tag}: {native - original} callback tasks not delegated')
                        require(len(trace['callbacks']) >= PAGE1, f'{tag}: too few callback events')
                        if kind == 'busy':
                            require([x['glyphs'] for x in trace['callbacks'][:5]] == [1] * 5,
                                    f'{tag}: busy callback retries not observed')
                        trace['pixels'] = hashlib.sha256(h.emu.screenshot().crop(CROP).tobytes()).hexdigest()
                    else:
                        require(not trace['callbacks'] and not trace['injected'], f'{tag}: unexpected callback')
                        require(original == (native if mode in checks.DELEGATING else 0),
                                f'{tag}: delegation does not match the mode ({original} of {native} tasks delegated)')
                        later = rows[PAGE1:]
                        if kind in ('held-A', 'held-B', 'tap'):
                            require(later, f'{tag}: page 2 never started: input lost')
                            done = page1[-1][2]
                            if kind == 'tap':
                                press = min((t for t in trace['taps'] if t > done), default=None)
                                require([t for t in trace['taps'] if t <= done],
                                        'tap case did not tap during printing (vacuous)')
                            require(press is not None and press > done, f'{tag}: no press after page 1')
                            # The page prompt control is rendered by the task after the last
                            # glyph and polls input from the task after that (last glyph + 2);
                            # a tap that starts earlier is seen then. Latency counts from the
                            # later of the press and that frame, for every mode alike.
                            trace['page2_latency'] = later[0][2] - max(press, done + PROMPT_READY)
                            trace['page2_raw_latency'] = later[0][2] - press
                            trace['page1_done'], trace['page2_press'] = done, press
                        summary, cadence_errors = checks.cadence(mode, [(r[1], r[2]) for r in page1])
                        trace['cadence'] = summary
                        trace['stops'], stop_errors = checks.task_errors(mode, tasks)
                        errors.extend(f'{tag}: {e}' for e in cadence_errors + stop_errors + tracer.state_errors)
                    first = page1[0][1]
                    trace['layout'] = [[r[3], r[4]] for r in rows]
                    trace['task_offsets'] = [r[1] - first for r in page1]
                    trace['native'], trace['original'] = native, original
                    bad = probe.heap_walk()
                    trace['memory'] = memory_summary(probe)
                    errors.extend(f'{tag}: {e}' for e in memory_errors(trace['memory']))
                    if bad:
                        errors.append(f'{tag}: heap {bad}')
                    h._per_frame.clear()
                    trace['glyph_count'] = len(rows)
                    report['cases'][tag] = trace
                base = report['cases'][f'{kind}-{checks.ORIGINAL}']
                for mode in (checks.NORMAL, checks.FAST):
                    case = report['cases'][f'{kind}-{mode}']
                    n = min(len(case['layout']), len(base['layout']))
                    if case['layout'][:n] != base['layout'][:n] or n < PAGE1 + (kind in ('held-A', 'held-B', 'tap')):
                        errors.append(f'{kind}-{mode}: glyph layout differs from the original')
                    if case.get('pixels') != base.get('pixels'):
                        errors.append(f'{kind}-{mode}: completed page 1 pixels differ')
                    if kind in ('callback', 'busy'):
                        if case['callbacks'] != base['callbacks']:
                            errors.append(f'{kind}-{mode}: callback events differ')
                        if case['task_offsets'] != base['task_offsets']:
                            errors.append(f'{kind}-{mode}: callback task cadence changed')
                    else:
                        lat, want = case.get('page2_latency'), base.get('page2_latency')
                        if lat is None or want is None or lat != want:
                            errors.append(f'{kind}-{mode}: page 2 latency {lat} frames after the press, '
                                          f'original {want} (must be equal)')
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        if not inputs_unchanged(report):
            errors.append('input modified')
        if not errors:
            report['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(errors))


if __name__ == '__main__':
    main()
