"""Native Options music/text cross-product and neighboring-row regression.

Changes settings through the real menu only, on a private imported battery copy.
Hooks observe the original narrowed music getter and heap; no Options RAM writes.
"""
import argparse
import json
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, start_game, add_arguments, attach_probe, identity, inputs_unchanged, itcm_errors,
                         load_expected_payload, memory_errors, memory_summary, require, resolve)


def main():
    from emu_harness import Harness
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    args = resolve(parser, parser.parse_args())
    payload = load_expected_payload(args)
    report = {'status': 'failed', **identity(args, payload),
              'cross_product': [], 'neighbor_rows': [], 'getter_checks': 0, 'errors': []}
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start = itcm_errors(h, payload)
            require(not start, repr(start))
            probe = attach_probe(h)
            menus = []; exits = []; getter = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            h.on_exec(payload['symbols']['exit_free'] & ~1, lambda h: exits.append(h.frame))
            def getter_entry(h):
                getter.append(h.u16(h.reg.r0) & 3)
            def getter_return(h):
                require(getter, 'Music getter returned without entry')
                expected = getter.pop()
                require(h.reg.r0 == expected and h.reg.r0 < 3, repr((h.reg.r0, expected)))
                report['getter_checks'] += 1
            h.on_exec(0x0202b1c4, getter_entry)
            h.on_exec(0x0202b1ce, getter_return)
            counts = (3, 2, 2, 2, 3, 20, 2)       # TEXT SPEED: NORMAL, FAST
            def rows(d):
                return [h.u16(d + 0x86 + row * 0x54) for row in range(7)]
            def open_menu():
                n = len(menus)
                h.press('X', after=90); h.touch(124, 115, after=300)
                require(len(menus) == n + 1, 'check failed: len(menus) == n + 1')
                d = menus[-1]
                require((h.u32(d + 16) >> 2) & 7 == 0, 'check failed: (h.u32(d + 16) >> 2) & 7 == 0')
                require(all(0 <= value < count for value, count in zip(rows(d), counts)), 'check failed: all(0 <= value < count for value, count in zip(rows(d), counts))')
                return d
            def leave(confirm):
                n = len(exits)
                if confirm:
                    h.touch(149, 180, after=300)
                else:
                    h.press('B', after=300)
                require(len(exits) == n + 1, 'check failed: len(exits) == n + 1')
                h.press('B', after=90)
            def select_music(d, target):
                current = rows(d)[0]
                for _ in range((target - current) % 3):
                    h.press('RIGHT', after=30)
                require(rows(d)[0] == target, 'check failed: rows(d)[0] == target')
            original = h.u16(h.array(1))
            d = open_menu(); initial_rows = rows(d); leave(False)
            for mode in (0, 1):                  # NORMAL, FAST
                for music in range(3):
                    d = open_menu()
                    before = h.u16(h.array(1))
                    select_music(d, music)
                    h.touch((130, 210)[mode], 152, after=30)
                    require(rows(d) == [music, *initial_rows[1:6], mode], 'check failed: rows(d) == [music, *initial_rows[1:6], mode]')
                    require(h.u16(h.array(1)) == before, 'Menu edits changed saved Options before Confirm')
                    leave(True)
                    expected = (original & ~15) | music | (mode << 2)
                    require(h.u16(h.array(1)) == expected, f'Confirm did not store the chosen text speed and music '
                            f'(Options {h.u16(h.array(1)):#x}, expected {expected:#x})')
                    d = open_menu(); committed = rows(d)
                    require(committed == [music, *initial_rows[1:6], mode], 'check failed: committed == [music, *initial_rows[1:6], mode]')
                    # Every setting row can be changed, then canceled atomically.
                    for row, count in enumerate(counts):
                        h.press('RIGHT', after=30)
                        require(rows(d)[row] == (committed[row] + 1) % count, 'check failed: rows(d)[row] == (committed[row] + 1) % count')
                        if row < 6:
                            h.press('DOWN', after=30)
                            require((h.u32(d + 16) >> 2) & 7 == row + 1, 'check failed: (h.u32(d + 16) >> 2) & 7 == row + 1')
                    leave(False)
                    require(h.u16(h.array(1)) == expected, 'check failed: h.u16(h.array(1)) == expected')
                    d = open_menu(); require(rows(d) == committed, 'check failed: rows(d) == committed'); leave(False)
                    report['cross_product'].append({'text_speed': mode, 'music_speed': music,
                                                    'options': expected, 'cancel_all_rows': True})
            # The original rows must still commit/reopen after the metadata shift.
            for row in range(1, 6):
                d = open_menu(); before = rows(d)
                for _ in range(row): h.press('DOWN', after=30)
                h.press('RIGHT', after=30)
                wanted = list(before); wanted[row] = (before[row] + 1) % counts[row]
                require(rows(d) == wanted, 'check failed: rows(d) == wanted')
                leave(True)
                require(h.u16(h.array(1)) & 15 == 6, 'check failed: h.u16(h.array(1)) & 15 == 6')  # FAST and music 1/4
                d = open_menu(); require(rows(d) == wanted, 'check failed: rows(d) == wanted')
                for _ in range(row): h.press('DOWN', after=30)
                h.press('LEFT', after=30); require(rows(d) == before, 'check failed: rows(d) == before')
                leave(True)
                require(h.u16(h.array(1)) == (original & ~15) | 6, 'check failed: h.u16(h.array(1)) == (original & ~15) | 6')
                report['neighbor_rows'].append({'row': row, 'before': before[row], 'committed': wanted[row],
                                                'restored': True})
            h.screenshot('completed-field')
            require(not getter and report['getter_checks'] >= 9, "check failed: not getter and report['getter_checks'] >= 9")
            report['memory'] = memory_summary(probe)
            problems = memory_errors(report['memory']) + itcm_errors(h, payload)
            require(not problems, repr(problems))
        require(inputs_unchanged(report), 'input modified')
        report['status'] = 'passed'
    except BaseException as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))


if __name__ == '__main__':
    main()
