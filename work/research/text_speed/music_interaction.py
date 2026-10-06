"""Native Options music/text cross-product and neighboring-row regression.

Changes settings through the real menu only, on a private imported battery copy.
Hooks observe the original narrowed music getter and heap; no Options RAM writes.
"""
import argparse
import json
import sys
from pathlib import Path
from harness_regression import ROOT, digest
sys.path.insert(0, str(ROOT / 'work/tools'))


def main():
    from emu_harness import Harness
    from text_speed_patch import load_payload
    from memcheck import Probe
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'save', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    args.rom, args.save, args.out = (x.resolve() for x in (args.rom, args.save, args.out))
    if not args.out.is_relative_to(ROOT / 'work/build') or args.out == ROOT / 'work/build':
        parser.error('Output must be a separate directory under this worktree work/build')
    args.out.mkdir(parents=True, exist_ok=True)
    report = {'status': 'failed', 'inputs': {str(x): digest(x) for x in (args.rom, args.save)},
              'cross_product': [], 'neighbor_rows': [], 'getter_checks': 0}
    payload = load_payload()
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False) as h:
            h.boot_to_menu(); h.continue_game()
            code = bytes.fromhex(payload['code'])
            assert h.read(payload['base'], len(code)) == code
            probe = Probe(h.emu); probe.armed = True
            def frame(h):
                if h.frame % 10 == 0 and probe.corrupt is None:
                    probe.frame = h.frame
                    bad = probe.heap_walk()
                    if bad:
                        probe.corrupt = (h.frame, bad)
            h.on_frame(frame)
            menus = []; exits = []; getter = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            h.on_exec(payload['symbols']['exit_free'] & ~1, lambda h: exits.append(h.frame))
            def getter_entry(h):
                getter.append(h.u16(h.reg.r0) & 3)
            def getter_return(h):
                assert getter, 'Music getter returned without entry'
                expected = getter.pop()
                assert h.reg.r0 == expected and h.reg.r0 < 3, (h.reg.r0, expected)
                report['getter_checks'] += 1
            h.on_exec(0x0202b1c4, getter_entry)
            h.on_exec(0x0202b1ce, getter_return)
            counts = (3, 2, 2, 2, 3, 20, 3)
            def rows(d):
                return [h.u16(d + 0x86 + row * 0x54) for row in range(7)]
            def open_menu():
                n = len(menus)
                h.press('X', after=90); h.touch(124, 115, after=300)
                assert len(menus) == n + 1
                d = menus[-1]
                assert (h.u32(d + 16) >> 2) & 7 == 0
                assert all(0 <= value < count for value, count in zip(rows(d), counts))
                return d
            def leave(confirm):
                n = len(exits)
                if confirm:
                    h.touch(149, 180, after=300)
                else:
                    h.press('B', after=300)
                assert len(exits) == n + 1
                h.press('B', after=90)
            def select_music(d, target):
                current = rows(d)[0]
                for _ in range((target - current) % 3):
                    h.press('RIGHT', after=30)
                assert rows(d)[0] == target
            original = h.u16(h.array(1))
            d = open_menu(); initial_rows = rows(d); leave(False)
            for mode in range(3):
                for music in range(3):
                    d = open_menu()
                    before = h.u16(h.array(1))
                    select_music(d, music)
                    h.touch((130, 177, 227)[mode], 152, after=30)
                    assert rows(d) == [music, *initial_rows[1:6], mode]
                    assert h.u16(h.array(1)) == before, 'Menu edits changed saved Options before Confirm'
                    leave(True)
                    expected = (original & ~15) | music | (mode << 2)
                    assert h.u16(h.array(1)) == expected
                    d = open_menu(); committed = rows(d)
                    assert committed == [music, *initial_rows[1:6], mode]
                    # Every setting row can be changed, then canceled atomically.
                    for row, count in enumerate(counts):
                        h.press('RIGHT', after=30)
                        assert rows(d)[row] == (committed[row] + 1) % count
                        if row < 6:
                            h.press('DOWN', after=30)
                            assert (h.u32(d + 16) >> 2) & 7 == row + 1
                    leave(False)
                    assert h.u16(h.array(1)) == expected
                    d = open_menu(); assert rows(d) == committed; leave(False)
                    report['cross_product'].append({'text_speed': mode, 'music_speed': music,
                                                    'options': expected, 'cancel_all_rows': True})
            # The original rows must still commit/reopen after the metadata shift.
            for row in range(1, 6):
                d = open_menu(); before = rows(d)
                for _ in range(row): h.press('DOWN', after=30)
                h.press('RIGHT', after=30)
                wanted = list(before); wanted[row] = (before[row] + 1) % counts[row]
                assert rows(d) == wanted
                leave(True)
                assert h.u16(h.array(1)) & 15 == 10  # FAST and music 1/4
                d = open_menu(); assert rows(d) == wanted
                for _ in range(row): h.press('DOWN', after=30)
                h.press('LEFT', after=30); assert rows(d) == before
                leave(True)
                assert h.u16(h.array(1)) == (original & ~15) | 10
                report['neighbor_rows'].append({'row': row, 'before': before[row], 'committed': wanted[row],
                                                'restored': True})
            h.screenshot('completed-field')
            assert not getter and report['getter_checks'] >= 9
            report['memory'] = {key: getattr(probe, key) for key in
                                ('heap_checks', 'corrupt', 'fails', 'nullw', 'text_rejections',
                                 'heap_table_errors', 'text_probe_errors')}
            assert probe.heap_checks and not any(value for key, value in report['memory'].items()
                                                 if key != 'heap_checks')
        assert all(digest(Path(path)) == sha for path, sha in report['inputs'].items())
        report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
