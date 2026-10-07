"""Private printer state, allocation pairing and heap steadiness over many messages.

Poison only the new private byte (+0x34) before the native initializer runs and
require the game's constructor return to see both the phase and the original
focus pointer (+0x30) reset, for every printer including reused heap slots.

The same two-page message is then shown REPEATS times (one per text-speed value,
cycling SLOW/MEDIUM/FAST). Every printer allocation must be freed, and every
heap's used blocks/bytes may not grow from the first to the last idle point by
more than text_speed_checks.heap_growth_errors' tolerance (2 blocks / 1 KiB; the
field itself allocates and frees a few unrelated blocks while time passes), so a
leak of even one block per two messages fails. Sensitivity is shown in the report: heap usage while a message
is open must differ from idle (the printer and window allocations are visible to
the same measurement). Heap integrity runs every 10 frames; the ITCM payload and
arena are checked at the start and the end.
"""
import argparse
from datetime import datetime
import json

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, FREE_TO_HEAP, add_arguments, attach_probe, heap_usage, identity, inputs_unchanged,
                         itcm_errors, load_expected_payload, memory_errors, memory_summary, require, resolve)
from text_speed_checks import heap_growth_errors, unfreed

CONSTRUCTOR_RETURN = 0x02020966
REPEATS = 24


def main():
    from emu_harness import Harness, SENTINEL_VAR, message_script
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload), 'constructors': 0, 'errors': []}
    errors = report['errors']
    pending, seen, reused = [], set(), set()
    events = {'n': 0, 'allocations': [], 'frees': []}
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            h.set_clock(datetime(2026, 10, 9, 12))   # clock-driven field allocations otherwise vary
            h.boot_to_menu()
            h.continue_game()
            start = itcm_errors(h, payload)
            require(not start, repr(start))
            probe = attach_probe(h)

            def begin(h):
                ptr = h.reg.r0
                pending.append(ptr)
                if ptr in seen:
                    reused.add(ptr)
                seen.add(ptr)
                events['n'] += 1
                events['allocations'].append((events['n'], ptr))
                h.w8(ptr + 0x34, 255)

            def end(h):
                ptr = h.reg.r4
                if not pending or pending.pop() != ptr:
                    errors.append('constructor pairing mismatch')
                if h.u8(ptr + 0x34) != 0 or h.u32(ptr + 0x30) != 0:
                    errors.append(f'printer {ptr:#x}: initializer did not reset private phase/focus pointer')
                report['constructors'] += 1

            def free(h):
                events['n'] += 1
                events['frees'].append((events['n'], h.reg.r0))
                probe._on_summary_free(FREE_TO_HEAP, 2)
            h.on_exec(payload['symbols']['init_printer'] & ~1, begin)
            h.on_exec(CONSTRUCTOR_RETURN, end)
            h.on_exec(FREE_TO_HEAP, free)
            opts = h.array(1)
            idle, open_usage = [], []
            for i in range(REPEATS):
                mode = i % 3
                h.w16(opts, (h.u16(opts) & ~12) | (mode << 2))
                idle.append(heap_usage(h))
                saved = h.get_var(SENTINEL_VAR)
                h.set_var(SENTINEL_VAR, 0)
                try:
                    h.run_script(file=3, index=0, msg_bank=48, program=message_script(48, 20), settle=240)
                    open_usage.append(heap_usage(h))
                    for _ in range(8):
                        if h.get_var(SENTINEL_VAR) == 0x5A5A:
                            break
                        h.press('A', after=240)
                    require(h.get_var(SENTINEL_VAR) == 0x5A5A, f'message {i} did not complete')
                finally:
                    h.set_var(SENTINEL_VAR, saved)
                h.step(30)
            idle.append(heap_usage(h))
            report['messages'] = REPEATS
            report['reused_allocations'] = len(reused)
            report['live_after'] = unfreed(events['allocations'], events['frees'])
            report['heap_idle_first'], report['heap_idle_last'] = idle[0], idle[-1]
            report['heap_open_first'] = open_usage[0]
            errors.extend(heap_growth_errors(idle))
            report['heap_idle_spread'] = {hid: [min(u[hid][0] for u in idle), max(u[hid][0] for u in idle)]
                                          for hid in idle[0]}
            if report['live_after']:
                errors.append(f"printer allocations never freed: {report['live_after']}")
            if open_usage[0] == idle[0]:
                errors.append('heap usage does not see an open message (insensitive leak measurement)')
            if report['constructors'] < REPEATS or not reused or pending:
                errors.append(f"constructors {report['constructors']}, reused {len(reused)}, pending {pending}")
            report['memory'] = memory_summary(probe)
            errors.extend(memory_errors(report['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        require(inputs_unchanged(report), 'input modified')
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
