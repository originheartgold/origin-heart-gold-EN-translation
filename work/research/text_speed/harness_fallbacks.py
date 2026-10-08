"""Controlled runtime regressions for fallback paths on an exact-ROM checkpoint.

Uses the shared emulator harness. Deliberate RAM changes are limited to Options,
cartridge-save flag, a transient null runtime pointer, and requested printer delay.
These are branch tests, not natural gameplay claims. Inputs are never modified.

Every case prints the trainer's first page (54 glyphs) from the same checkpoint.
Native tasks are judged per task (text_speed_checks.task_errors, with the frame
model). NORMAL, the unknown values 2 and 3, an unpublished runtime pointer (with
FAST stored) and explicit delays must delegate every task to the original printer
(D-1604); the unknown value 2 must print exactly like value 3; legacy music values
next to FAST must behave exactly like FAST. The value-3 original printer is the
baseline of the product rules (text_speed_checks.order_errors): NORMAL identical to
it, FAST at most NORMAL's printing frames (strictly fewer where a NORMAL frame had
room for one more glyph), no more dropped frames than NORMAL, at most one dropped
only because of extra glyphs (D-2276). The unpublished-pointer case's display frames
are reported against value 3, not judged (D-2280); its task cadence must be identical.
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
# (name, stored text-speed value, music bits, unpublished runtime pointer, explicit delay)
CASES = [('normal', 0, 0, False, 0), ('fast', 1, 0, False, 0),
         ('invalid', 3, 0, False, 0), ('invalid-2', 2, 0, False, 0), ('null', 1, 0, True, 0),
         ('old-music-1', 1, 1, False, 0), ('old-music-2', 1, 2, False, 0),
         ('delay-normal', 0, 0, False, 3), ('delay-fast', 1, 0, False, 3)]


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
            start_game(h, a.phase)
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
                fallback = mode != checks.FAST or null or delay
                require(native_n > 0, f'{name}: no native task')
                if fallback:
                    require(original_n == native_n, f'{name}: fallback skipped the original task '
                            f'({original_n} of {native_n} tasks delegated)')
                else:
                    require(original_n == 0, f'{name}: {original_n} tasks delegated to the original printer')
                if delay:
                    require(state['delayed'], f'{name}: delay injection not exercised')
                judged = checks.ORIGINAL if (mode in (2, 3) or null) else mode
                record, stops, stop_errors = judge_message(tracer, judged, 0, 0)
                errors.extend(f'{name}: {e}' for e in stop_errors + tracer.state_errors)
                first = rows[0][2]
                report['cases'][name] = {'glyphs': [r[2] - first for r in rows],
                                         'glyph_tasks': [r[1] for r in rows], 'record': record,
                                         'span': rows[-1][2] - first, 'lag_frames': record['drops'],
                                         'native': native_n, 'original': original_n, 'stops': stops,
                                         'per_task': checks.cadence(judged, [(r[1], r[2]) for r in rows])[0]
                                         .get('per_task')}
            cases = report['cases']
            for name in ('old-music-1', 'old-music-2'):
                if cases[name]['glyphs'] != cases['fast']['glyphs']:
                    errors.append(f'{name}: glyph timing differs from FAST')
            # Unknown value 2 is NORMAL exactly like value 3 (D-1604).
            for key in ('glyphs', 'span', 'lag_frames', 'record'):
                if cases['invalid-2'][key] != cases['invalid'][key]:
                    errors.append(f'invalid-2: {key} differs from the unknown value 3 (both must print as NORMAL)')
            # The null injection adds instructions before the same original task: the task
            # cadence must be identical (the printer's behaviour). Display frames follow the game's
            # own lag frames, which a few instructions can tip near a frame edge (phase 1: 2 more
            # lag frames), so their difference is reported, not judged (D-2280).
            invalid_tasks = [t - cases['invalid']['glyph_tasks'][0] for t in cases['invalid']['glyph_tasks']]
            null_tasks = [t - cases['null']['glyph_tasks'][0] for t in cases['null']['glyph_tasks']]
            if invalid_tasks != null_tasks:
                errors.append('null: task cadence differs from the invalid-mode original printer')
            shift = max(abs(x - y) for x, y in zip(cases['invalid']['glyphs'], cases['null']['glyphs']))
            report['null_glyph_frame_shift'] = shift
            if shift > 1:
                report.setdefault('warnings', []).append(
                    f'null: glyph frames up to {shift} from the invalid-mode original printer '
                    f"(lag frames {cases['null']['lag_frames']} vs {cases['invalid']['lag_frames']}; "
                    'task cadence identical)')
            names = {checks.ORIGINAL: 'invalid', checks.NORMAL: 'normal', checks.FAST: 'fast'}
            records = {m: cases[n]['record'] for m, n in names.items()}
            order, notes = checks.order_errors(records)
            checks.tally_overruns(report, records)
            errors.extend(f'frame order: {e}' for e in order)
            report['capped_ties'] = notes
            if not cases['delay-normal']['glyphs'] == cases['delay-fast']['glyphs']:
                errors.append('explicit delay: glyph timing differs between speeds')
            if not cases['delay-normal']['span'] > cases['normal']['span']:
                errors.append('explicit delay: not slower than NORMAL (delay not applied)')
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
