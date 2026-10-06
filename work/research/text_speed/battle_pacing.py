"""Battle text pacing at every speed against the original printer, without A/B input.

One emulator session. FAST is first chosen through the native Options UI. Then a
field checkpoint is taken in front of the battle, and every segment (battle start
up to the first command menu, then three turns using move 1) is played from the
SAME checkpoint once per mode: the original printer (reserved value 3, controlled
RAM write of the two text-speed bits) first, then SLOW, MEDIUM and FAST. The
original run's end state is the next segment's checkpoint, so all four modes see
the same battle and print the same messages.

Per message the gate requires: identical text sequence and glyph counts, the
design glyph budget per task (text_speed_checks.cadence), and the pause after
the completed message (final glyph -> next printer, or -> command menu) and the
unchanged-text dwell on screen equal to the original within 2 frames. Faster
text may only shorten printing, never the battle's own waits. Heap integrity and
the ITCM payload/arena are checked through the session.
"""
import argparse
import json
from datetime import datetime

from gate_common import (CLOCK, ROOT, PRINTER_DESTROY, PrinterTrace, add_arguments, attach_probe, identity, inputs_unchanged,
                         itcm_errors, load_expected_payload, memory_errors, memory_summary, resolve)
import text_speed_checks as checks

MODES = (3, 0, 1, 2)
TEXT_BOX = (8, 153, 248, 184)
TURNS = 3


def main():
    from emu_harness import Harness, BATTLE_BUTTONS, MOVE_BUTTONS
    import msgtool
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    cm = msgtool.Charmap.load([str(ROOT / 'work/tools/charmap_en.tsv')])
    report = {'status': 'failed', **identity(args, payload), 'segments': [], 'errors': []}
    errors = report['errors']
    state = {'rows': None}
    active = {}
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            h.set_clock(datetime(2026, 10, 9, 12))
            h.boot_to_menu()
            h.continue_game()
            start = itcm_errors(h, payload)
            assert not start, start
            probe = attach_probe(h)
            screens = {}

            def frame(h):
                rows = state['rows']
                if rows is None:
                    return
                for i, row in enumerate(rows):
                    if not row['glyphs'] or 'dwell' in row:
                        continue
                    last = row['glyphs'][-1][2]
                    if h.frame == last + 3:   # allow the display transfer after the final glyph
                        screens[i] = (last, h.emu.screenshot().crop(TEXT_BOX).tobytes())
                    elif i in screens and screens[i][0] == last and h.frame > last + 3:
                        if h.emu.screenshot().crop(TEXT_BOX).tobytes() != screens[i][1]:
                            row['dwell'] = h.frame - last - 3
            h.on_frame(frame)

            def task(h, ptr):
                if state['rows'] is None or ptr in active:
                    return
                addr, units = h.u32(ptr), []
                for n in range(1024):
                    unit = h.u16(addr + 2 * n)
                    if unit == 0xFFFF:
                        break
                    units.append(unit)
                row = {'start': h.frame, 'text': msgtool.decode_units(units, cm), 'callback': h.u32(ptr + 0x1C),
                       'delay': h.u8(ptr + 0x29) & 127, 'id': h.u8(ptr + 0x2C), 'glyphs': []}
                active[ptr] = row
                state['rows'].append(row)

            def glyph(h, ptr, event):
                row = active.get(ptr)
                if row is not None:
                    row['glyphs'].append(event)
                    row.pop('dwell', None)

            def destroy(h):
                for ptr, row in list(active.items()):
                    if row['id'] == h.reg.r0:
                        row['end'] = h.frame
                        del active[ptr]
            PrinterTrace(h, payload, probe=probe, on_task=task, on_glyph=glyph)
            h.on_exec(PRINTER_DESTROY, destroy)

            menus = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            h.press('X', after=90)
            h.touch(124, 115, after=300)
            assert menus, 'Options did not open'
            opts = h.u32(menus[-1] + 0x24)
            before = h.u16(opts)
            h.touch(227, 152, after=40)
            h.touch(149, 180, after=300)
            h.press('B', after=90)
            assert h.u16(opts) == (before & ~12) | 8, 'native UI did not select FAST'
            checkpoint = args.out / 'segment-0.dst'
            h.save_state(checkpoint)

            def at_menu(h):
                return h.on_screen('battle_menu') or h.in_field()

            for segment in range(TURNS + 1):
                runs = {}
                for mode in MODES:
                    h.load_state(checkpoint)
                    active.clear()
                    screens.clear()
                    opts_now = h.array(1)
                    h.w16(opts_now, (h.u16(opts_now) & ~12) | (mode << 2))
                    rows = state['rows'] = []
                    began = h.frame
                    if segment == 0:
                        h.trainer_battle(1)
                        reached = (h.run_until(lambda h: not h.in_field(), 600)
                                   and h.run_until(lambda h: h.on_screen('battle_menu'), 1800))
                    else:
                        h.touch(*BATTLE_BUTTONS['fight'], frames=10, after=40)
                        h.touch(*MOVE_BUTTONS[0], frames=10, after=90)
                        reached = h.run_until(at_menu, 3000)
                    ended = h.frame
                    h.step(4)
                    state['rows'] = None
                    h.screenshot(f'segment-{segment}-{checks.NAMES[mode]}')
                    assert reached, f'segment {segment} {checks.NAMES[mode]}: stuck without A/B input'
                    printed = [r for r in rows if r['glyphs']]
                    for i, row in enumerate(printed):
                        nxt = printed[i + 1]['start'] if i + 1 < len(printed) else ended
                        row['after_last'] = nxt - row['glyphs'][-1][2]
                        row['print_frames'] = row['glyphs'][-1][2] - row['glyphs'][0][2]
                        row['glyph_count'] = len(row['glyphs'])
                        summary, cadence_errors = checks.cadence(mode, row['glyphs'])
                        row['cadence'] = summary
                        errors.extend(f"segment {segment} {checks.NAMES[mode]} {row['text'][:30]!r}: {e}"
                                      for e in cadence_errors)
                    runs[mode] = {'frames': ended - began, 'field': h.in_field(), 'messages': [
                        {k: r.get(k) for k in ('text', 'glyph_count', 'print_frames', 'after_last', 'dwell',
                                               'end', 'callback', 'delay', 'cadence')} | {'glyphs': r['glyph_count']}
                        for r in printed]}
                    if mode == 3:
                        following = args.out / f'segment-{segment + 1}.dst'
                        h.save_state(following)
                base = runs[3]['messages']
                if not base:
                    errors.append(f'segment {segment}: original printer printed nothing (vacuous)')
                for mode in (0, 1, 2):
                    errors.extend(f'segment {segment} {checks.NAMES[mode]}: {e}'
                                  for e in checks.battle_pacing_errors(base, runs[mode]['messages']))
                    saved = sum(r['print_frames'] for r in base) - sum(r['print_frames'] for r in runs[mode]['messages'])
                    runs[mode]['frames_saved_vs_original'] = runs[3]['frames'] - runs[mode]['frames']
                    runs[mode]['print_frames_saved'] = saved
                    if abs(runs[mode]['frames_saved_vs_original'] - saved) > 2 * len(base) + 2:
                        errors.append(f'segment {segment} {checks.NAMES[mode]}: segment shortened by '
                                      f"{runs[mode]['frames_saved_vs_original']} frames but printing only by {saved}")
                spans = {m: sum(r['print_frames'] for r in runs[m]['messages']) for m in MODES}
                errors.extend(f'segment {segment}: {e}' for e in checks.speed_order(spans, strict=True))
                report['segments'].append({'segment': segment, 'runs': runs})
                checkpoint = args.out / f'segment-{segment + 1}.dst'
                if runs[3]['field']:
                    break
            # The game may run a printer task twice in one frame (the original task too);
            # no speed may be scheduled more often than the original printer was.
            per_frame = {m: max((r['cadence'].get('max_tasks_per_frame', 0) for s in report['segments']
                                 for r in s['runs'][m]['messages']), default=0) for m in MODES}
            report['max_tasks_per_frame'] = per_frame
            errors.extend(f'{checks.NAMES[m]}: {per_frame[m]} printer tasks in one frame, original {per_frame[3]}'
                          for m in (0, 1, 2) if per_frame[m] > per_frame[3])
            texts = [m['text'] for s in report['segments'] for m in s['runs'][3]['messages']]
            if len(texts) < 6 or not any('used' in t for t in texts):
                errors.append(f'too few battle messages for a pacing check: {texts}')
            report['memory'] = memory_summary(probe)
            errors.extend(memory_errors(report['memory']))
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
