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
  first page's wait; after release ONE new press must start page 2 (no lost or
  latched input) with the original's glyph positions.
- tap: A tapped (4 frames down, 4 up) from the start. Page 2 must start only after a
  tap that began after page 1 was complete; page 1 and the start of page 2 keep the
  original layout.
- Latency (held and tap cases), counted in the printer's own tasks and judged from
  the page prompt's observed input polls (D-2175), not from fixed frames: the first
  poll comes exactly as many printer tasks after page 1's last glyph as with the
  original, the prompt polls in every printer task until it accepts, it accepts a
  press that began after page 1 was complete (held: the press after the release) and
  no later than the first tap that began after the first poll (no lost input), and
  page 2's first glyph comes exactly as many printer tasks after the accepting poll
  as with the original. Frames would depend on the game's pass length (30 or 60 fps)
  and on where the fixed input frames fall in a two-frame pass (the input phase).
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
# RenderText's page waits (0x02002AEC with the arrow, 0x02002B10) call this key check
# with r0 = the printer unless auto-scroll is set; at ACCEPT the check saw a new A/B press
# (or a touch) and the wait returns 1 (pressed: sound effect, then the page advances).
PAGE_POLL = 0x02002A84
PAGE_ACCEPT = 0x02002A8E
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
            start_game(h, args.phase)
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
                    polls = []      # [frame, printer task id, accepted] of the font-1 printer's page waits

                    def poll(h):
                        if h.u8(h.reg.r0 + 9) == 1:
                            polls.append([h.frame, tracer.current.get(h.reg.r0), False])

                    def accept(h):
                        if polls and polls[-1][0] == h.frame:
                            polls[-1][2] = True

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
                    h.on_exec(PAGE_POLL, poll)
                    h.on_exec(PAGE_ACCEPT, accept)
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
                    # a task still running when the case stopped recording is not judged: its
                    # reading after the render falls after the recording (phase 1, tap-1)
                    cut = tracer.unfinished()
                    tasks = [t for t in tracer.tasks if t['font'] == 1 and t['id'] not in cut]
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
                            printer = page1[-1][0]
                            waits = [x for x in polls if x[1] is not None and page1[-1][1] <= x[1] <= later[0][1]]
                            require(waits, f'{tag}: the page prompt never polled input')
                            accepted = [x for x in waits if x[2]]
                            require(accepted, f'{tag}: page 2 started without an accepting page-prompt poll')
                            first, took = waits[0], accepted[0]
                            trace['polls'] = {'first': first[:2], 'accept': took[:2], 'count': len(waits)}
                            # Printer tasks: from the last glyph's task to the first poll, and from the
                            # accepting poll to page 2's first glyph (compared with the original below).
                            trace['prompt_tasks'] = tracer.tasks_between(page1[-1][1], first[1], printer)
                            trace['accept_tasks'] = tracer.tasks_between(took[1], later[0][1], printer)
                            polled = tracer.tasks_between(first[1], took[1], printer) + 1
                            if len([x for x in waits if x[1] <= took[1]]) != polled:
                                errors.append(f'{tag}: the page prompt skipped polls before accepting '
                                              f'({len([x for x in waits if x[1] <= took[1]])} polls in {polled} '
                                              'printer tasks)')
                            if took[0] < press:
                                errors.append(f'{tag}: the page prompt accepted at frame {took[0]}, before the '
                                              f'fresh press at {press} (latched input)')
                            if kind == 'tap':
                                due = min((t for t in trace['taps'] if t > first[0]), default=None)
                                after = min((t for t in trace['taps'] if due is not None and t > due), default=None)
                                if after is not None and took[0] >= after:
                                    errors.append(f'{tag}: the tap at frame {due}, after the first poll at '
                                                  f'{first[0]}, was not accepted (accepted at {took[0]}: lost input)')
                            trace['page2_raw_latency'] = later[0][2] - press
                            trace['page2_accept_frames'] = later[0][2] - took[0]
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
                        for key, what in (('prompt_tasks', 'printer tasks from the last glyph to the first '
                                                           'page-prompt poll'),
                                          ('accept_tasks', 'printer tasks from the accepting poll to page 2')):
                            got, want = case.get(key), base.get(key)
                            if got is None or want is None or got != want:
                                errors.append(f'{kind}-{mode}: page 2 latency: {got} {what}, original {want} '
                                              '(must be equal)')
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
