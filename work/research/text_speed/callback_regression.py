"""Controlled callback fallback, busy callback retries and A/B input comparisons.

Uses a same-candidate checkpoint in front of the trainer fixture (a two-page
conversation). Mode 3 (reserved value, controlled RAM write) is the original
printer task and the baseline for every case.

- callback / busy: an existing, byte-verified return-zero code sequence is
  injected as the printer callback; only its return value is overridden to
  simulate four busy retries. No executable code is injected. Callback events,
  task cadence, layout and completed pixels must equal the original.
- held-A / held-B: holding A (or B while pressing A) must not advance past the
  first page's wait; after release ONE new press must start page 2 with the same
  latency (within 2 frames) and glyph positions as the original (no lost or
  latched input).
- tap: A tapped (4 frames down, 4 up) from the start. Page 2 must start only after a
  tap that began after page 1 was complete, with the original's latency from
  that tap; page 1 and the start of page 2 keep the original layout.
Plain/held/tap cases are judged against the design glyph budget per task.
These are renderer/input tests on one natural conversation, not a scene audit.
"""
import argparse
import hashlib
import json

from gate_common import (CLOCK, start_game, add_arguments, attach_probe, identity, inputs_unchanged, itcm_errors,
                         load_expected_payload, memory_errors, memory_summary, resolve)
import text_speed_checks as checks

STUB = 0x0200107A
CALLBACK_SITES = (0x02020A67, 0x02020A7F)
ORIGINAL_TASK = 0x02020A1C
PRINTER_START = 0x020208D4
GLYPH = 0x02002680
PAGE1 = 54
KINDS = ('callback', 'busy', 'held-A', 'held-B', 'tap')


def main():
    from emu_harness import Harness
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload), 'cases': {}, 'errors': []}
    errors = report['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start = itcm_errors(h, payload)
            assert not start, start
            checkpoint = args.out / 'candidate.dst'
            h.save_state(checkpoint)
            code = bytes.fromhex(payload['code'])
            for kind in KINDS:
                for mode in (3, 0, 1, 2):
                    h.load_state(checkpoint)
                    assert h.read(payload['base'], len(code)) == code
                    assert h.read(STUB, 4) == bytes.fromhex('00207047')
                    opts = h.array(1)
                    value = (h.u16(opts) & ~12) | (mode << 2)
                    h.w16(opts, value)
                    trace = {'glyphs': [], 'callbacks': [], 'native': 0, 'original': 0, 'injected': 0,
                             'phase': {}, 'taps': []}

                    def native(h):
                        if h.u8(h.reg.r1 + 9) == 1:
                            trace['native'] += 1
                            trace['phase'][trace['native']] = h.u8(h.reg.r1 + 0x34)

                    def original(h):
                        if h.u8(h.reg.r1 + 9) == 1:
                            trace['original'] += 1

                    def constructor(h):
                        if kind in ('callback', 'busy') and h.u8(h.reg.r0 + 9) == 1:
                            assert h.reg.r2 == 0, 'fixture already has a callback'
                            h.reg.r2 = STUB | 1
                            trace['injected'] += 1

                    def callback(h):
                        if h.reg.lr not in CALLBACK_SITES:
                            return
                        assert h.u8(h.reg.r0 + 9) == 1
                        trace['callbacks'].append({'event': h.reg.r1, 'glyphs': len(trace['glyphs'])})

                    def callback_return(h):
                        if h.reg.lr in CALLBACK_SITES:
                            h.reg.r0 = int(kind == 'busy' and len(trace['callbacks']) <= 4)

                    def glyph(h):
                        ptr = h.reg.r4
                        if h.u8(ptr + 9) == 1:
                            trace['glyphs'].append((trace['native'], h.u16(ptr + 12), h.u16(ptr + 14), h.frame))
                    h.on_exec(payload['symbols']['print_task'] & ~1, native)
                    h.on_exec(ORIGINAL_TASK, original)
                    h.on_exec(PRINTER_START, constructor)
                    h.on_exec(STUB, callback)
                    h.on_exec(STUB + 2, callback_return)
                    h.on_exec(GLYPH, glyph)
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
                    page1 = trace['glyphs'][:PAGE1]
                    if kind in ('held-A', 'held-B'):
                        assert len(trace['glyphs']) == PAGE1, (kind, mode, 'held input moved past page 1',
                                                               len(trace['glyphs']))
                        trace['pixels'] = hashlib.sha256(
                            h.emu.screenshot().crop((8, 153, 236, 182)).tobytes()).hexdigest()
                        press = h.frame
                        h.press('A', after=120)
                    assert trace['native'] > 0 and len(page1) == PAGE1, (kind, mode, len(trace['glyphs']))
                    assert h.u16(opts) == value
                    if kind in ('callback', 'busy'):
                        assert len(trace['glyphs']) == PAGE1, 'callback case left page 1'
                        assert trace['injected'] > 0 and trace['original'] == trace['native']
                        assert len(trace['callbacks']) >= PAGE1
                        if kind == 'busy':
                            assert [x['glyphs'] for x in trace['callbacks'][:5]] == [1] * 5
                    else:
                        assert not trace['callbacks'] and not trace['injected']
                        assert bool(trace['original']) == (mode == 3)
                        later = trace['glyphs'][PAGE1:]
                        if kind in ('held-A', 'held-B', 'tap'):
                            assert later, (kind, mode, 'page 2 never started: input lost')
                            done = page1[-1][3]
                            if kind == 'tap':
                                press = min((t for t in trace['taps'] if t > done), default=None)
                                early = [t for t in trace['taps'] if t <= done]
                                assert early, 'tap case did not tap during printing (vacuous)'
                            assert press is not None and press > done, (kind, mode, 'no press after page 1')
                            trace['page2_latency'] = later[0][3] - press
                        glyph_events = [(task, trace['phase'].get(task), frame) for task, _, _, frame in page1]
                        summary, cadence_errors = checks.cadence(mode, glyph_events)
                        trace['cadence'] = summary
                        errors.extend(f'{kind}-{mode}: {e}' for e in cadence_errors)
                    first = page1[0][0]
                    trace['layout'] = [[x, y] for _, x, y, _ in trace['glyphs']]
                    trace['task_offsets'] = [task - first for task, _, _, _ in page1]
                    if kind in ('callback', 'busy'):
                        trace['pixels'] = hashlib.sha256(
                            h.emu.screenshot().crop((8, 153, 236, 182)).tobytes()).hexdigest()
                    bad = probe.heap_walk()
                    trace['memory'] = memory_summary(probe)
                    errors.extend(f'{kind}-{mode}: {e}' for e in memory_errors(trace['memory']))
                    if bad:
                        errors.append(f'{kind}-{mode}: heap {bad}')
                    h._per_frame.clear()
                    trace['glyph_count'] = len(trace['glyphs'])
                    del trace['glyphs'], trace['phase']
                    report['cases'][f'{kind}-{mode}'] = trace
                base = report['cases'][f'{kind}-3']
                for mode in range(3):
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
                        if lat is None or want is None or abs(lat - want) > 2:
                            errors.append(f'{kind}-{mode}: page 2 latency {lat} frames after the press, '
                                          f'original {want}')
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        assert inputs_unchanged(report), 'input modified'
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
