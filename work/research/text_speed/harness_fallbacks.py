"""Controlled runtime regressions for fallback paths on an exact-ROM checkpoint.

Uses the shared emulator harness. Deliberate RAM changes are limited to Options,
cartridge-save flag, a transient null runtime pointer, and requested printer delay.
These are branch tests, not natural gameplay claims. Inputs are never modified.

Every case prints the trainer's first page (54 glyphs) from the same checkpoint.
Native tasks are judged per task (text_speed_checks.task_errors, with the frame
model). Invalid mode, an unpublished runtime pointer and explicit delays must
delegate every task to the original printer; legacy music values must behave
exactly like SLOW. The invalid-mode original printer is the baseline of the
product rules (text_speed_checks.order_errors): ORIGINAL > SLOW > MEDIUM > FAST in
printing frames (a tie only at the physical cap), no speed with more dropped frames
than the original, none dropped only because of extra glyphs, SLOW within its floor.
"""
import argparse
import json

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, PRINTER_START, PrinterTrace, start_game, add_arguments, code_bytes, identity,
                         inputs_unchanged, itcm_errors, judge_message, load_expected_payload, require, resolve)
import text_speed_checks as checks

RUNTIME = 0x021106C8   # main runtime SaveData pointer (null before publication)
CASES = [('slow', 0, 0, False, 0), ('medium', 1, 0, False, 0), ('fast', 2, 0, False, 0),
         ('invalid', 3, 0, False, 0), ('null', 2, 0, True, 0),
         ('old-music-1', 0, 1, False, 0), ('old-music-2', 0, 2, False, 0),
         ('delay-slow', 0, 0, False, 3), ('delay-medium', 1, 0, False, 3), ('delay-fast', 2, 0, False, 3)]


def main():
    from emu_harness import Harness
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    a = resolve(p, p.parse_args())
    payload = load_expected_payload(a)
    report = {'status': 'failed', **identity(a, payload), 'cases': {}, 'errors': []}
    errors = report['errors']
    try:
        with Harness(a.rom, a.save, out=a.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            checkpoint = a.out / 'fresh-candidate.dst'
            h.save_state(checkpoint)
            code = code_bytes(payload)
            state = {'null': False, 'hidden': False, 'save': 0, 'delay': 0, 'delayed': 0}

            def restore(h, *_):
                if state['hidden']:
                    h.w32(RUNTIME, state['save'])
                    state['hidden'] = False

            def native(h, ptr):
                if state['null']:
                    h.w32(RUNTIME, 0)
                    state['hidden'] = True

            def constructor(h):
                if state['delay']:
                    h.reg.r1 = state['delay']
                    state['delayed'] += 1
            tracer = PrinterTrace(h, payload, font=1, on_task=native, on_original=restore, on_render=restore)
            h.on_exec(PRINTER_START, constructor)
            for name, mode, music, null, delay in CASES:
                h.load_state(checkpoint)
                tracer.reset()
                require(h.read(payload['base'], len(code)) == code, 'stale checkpoint executable')
                save = h.u32(RUNTIME)
                opts = h.array(1)
                value = (h.u16(opts) & ~15) | (mode << 2) | music
                h.w16(opts, value)
                h.w32(save + 4, 0)  # initialized new-game state before the first cartridge save
                state.update(null=null, hidden=False, save=save, delay=delay, delayed=0)
                # Natural A interaction from the trainer fixture; only test fields above are changed.
                h.press('A', after=400)
                state['null'] = False
                require(not state['hidden'] and h.u32(RUNTIME) == save, f'{name}: runtime pointer not restored')
                require(h.u16(opts) == value and h.u32(save + 4) == 0, f'{name}: test fields changed')
                rows = list(tracer.glyphs)
                require(len(rows) == 54, f'{name}: expected 54 glyphs, observed {len(rows)}')
                tasks = list(tracer.tasks)
                native_n, original_n = len(tasks), sum(1 for t in tasks if t['delegated'])
                fallback = mode == 3 or null or delay
                require(native_n > 0, f'{name}: no native task')
                if fallback:
                    require(original_n == native_n, f'{name}: fallback skipped the original task '
                            f'({original_n} of {native_n} tasks delegated)')
                else:
                    require(original_n == 0, f'{name}: {original_n} tasks delegated to the original printer')
                if delay:
                    require(state['delayed'], f'{name}: delay injection not exercised')
                judged = checks.ORIGINAL if (mode == 3 or null) else mode
                record, stops, stop_errors = judge_message(tracer, judged, 0, 0)
                errors.extend(f'{name}: {e}' for e in stop_errors + tracer.state_errors)
                first = rows[0][3]
                report['cases'][name] = {'glyphs': [r[3] - first for r in rows],
                                         'glyph_tasks': [r[1] for r in rows], 'record': record,
                                         'span': rows[-1][3] - first, 'lag_frames': record['drops'],
                                         'native': native_n, 'original': original_n, 'stops': stops,
                                         'per_task': checks.cadence(judged, [(r[1], r[2], r[3]) for r in rows])[0]
                                         .get('per_task')}
            cases = report['cases']
            for name in ('old-music-1', 'old-music-2'):
                if cases[name]['glyphs'] != cases['slow']['glyphs']:
                    errors.append(f'{name}: glyph timing differs from SLOW')
            # The null injection adds instructions before the same original task:
            # task cadence must be identical, display frames may differ by one.
            invalid_tasks = [t - cases['invalid']['glyph_tasks'][0] for t in cases['invalid']['glyph_tasks']]
            null_tasks = [t - cases['null']['glyph_tasks'][0] for t in cases['null']['glyph_tasks']]
            if invalid_tasks != null_tasks:
                errors.append('null: task cadence differs from the invalid-mode original printer')
            if max(abs(x - y) for x, y in zip(cases['invalid']['glyphs'], cases['null']['glyphs'])) > 1:
                errors.append('null: glyph frames differ from the invalid-mode original printer by more than 1')
            names = {3: 'invalid', 0: 'slow', 1: 'medium', 2: 'fast'}
            order, notes = checks.order_errors({m: cases[n]['record'] for m, n in names.items()})
            errors.extend(f'frame order: {e}' for e in order)
            report['capped_ties'] = notes
            if not cases['delay-slow']['glyphs'] == cases['delay-medium']['glyphs'] == cases['delay-fast']['glyphs']:
                errors.append('explicit delay: glyph timing differs between speeds')
            if not cases['delay-slow']['span'] > cases['slow']['span']:
                errors.append('explicit delay: not slower than SLOW (delay not applied)')
            errors.extend(itcm_errors(h, payload))
        if not inputs_unchanged(report):
            errors.append('input modified')
        if not errors:
            report['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (a.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(errors))


if __name__ == '__main__':
    main()
