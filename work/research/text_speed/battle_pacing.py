"""Battle text pacing at every speed against the original printer, without A/B input.

Several battles, each in its own process (own DeSmuME battery directory): a cold
boot, FAST chosen through the native Options UI, then a field checkpoint in front
of the battle. Every segment (battle start up to the first command menu, then three
turns using move 1) is played from the SAME checkpoint once per mode: the original
printer (unknown value 3, controlled RAM write of the two text-speed bits) first,
then NORMAL and FAST. The original run's end state is the next segment's
checkpoint, so all three modes see the same battle and print the same messages.

Per message the gate requires: identical text sequence, glyph counts and completed
text pixels; the per-task model checks (text_speed_checks.task_errors) and the
payload's frame state equal to the measured costs; the product rules per segment
(text_speed_checks.order_errors). The battle's own waits are compared in game-loop
passes, not display frames:
- the end-of-text step: passes from the final glyph to the printer's removal must
  equal the original's exactly. (In display frames it can differ by one: a battle
  loop pass runs from one VBlank to the next, so when a pass ends after line 0 the
  emulator frame holds two printer task runs; whether the final glyph falls in the
  first or the second decides whether the removal shares its frame.)
- the pause after a completed message (final glyph to the next printer, or to the
  command menu) and the completed text's on-screen dwell: equal to the original's
  (pause in passes, dwell in frames), or a value that the original printer itself
  shows when replayed from the same checkpoint with its start delayed by
  1..JITTER_DELAYS frames (seen: up to two passes apart). Mechanism: the battle
  waits for its sound (move/cry sound effects) to end, and the sound engine runs on
  the ARM7's own sound-frame clock (about 5.2 ms), not on video frames, so the pass
  in which the battle sees the sound end depends on the absolute timing; in those
  replays RAM differs only in the sound engine's work area and two timer words
  until the pass where the battle moves on (work/notes/text_speed_vcount.md).
- the lead-in before the first message is identical, and each segment is shorter by
  exactly the printing frames saved plus the pause differences.

Battle RNG pin (coordinator decision, 2026-10-07): which moves hit, crit or faint the
fixture's Pokémon depends on the battle RNG, whose seed the game derives at battle start
from timing; any payload change (a few cycles per loop pass) gave other battles (with the
1406-byte payload trainers 1 and 30 blacked out even with the original printer). In every
segment-0 run the gate therefore writes BATTLE_RNG_SEED into the battle RNG state at the
battle RNG's first use (the state lives in the battle's own data, created at battle start,
so it cannot be written at the field checkpoint), reads it back and records both in the
report ('rng_pins'); text_speed_checks.rng_pin_errors fails the gate when a pin is missing
or did not hold. Later segments start from savestates and carry the pinned sequence.
--no-rng-pin (diagnosis only, never used by validate_release) shows the fixture problem
the pin removes: the gate fails with 'stuck without A/B input' instead of passing.

Trainers: see TRAINERS. EXCLUDED lists battles that cannot run without input.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLOCK, ROOT, PrinterTrace, add_arguments, attach_probe, digest, identity,  # noqa: E402
                         inputs_unchanged, itcm_errors, load_expected_payload, memory_errors, memory_summary,
                         require, resolve)
import text_speed_checks as checks  # noqa: E402

MODES = checks.MODES
SPEEDS = (checks.NORMAL, checks.FAST)
TEXT_BOX = (8, 153, 248, 184)
TURNS = 3
JITTER_DELAYS = 12
# Battle RNG (CN/EN ARM9 overlay 14, also loaded in battle): the routine at BATTLE_RNG_ROUTINE
# advances the u32 at [BATTLE_RNG_HOLDER] + BATTLE_RNG_OFFSET (x * 0x41C64E6D + 0x6073) and
# returns (x >> 16) % r0. Found by hooking it during battle turns (the main LCRNG and the
# Mersenne twister are not called during a turn). The routine's first bytes are checked
# before every pin because other overlays share the address range.
BATTLE_RNG_ROUTINE = 0x0222646C
BATTLE_RNG_CODE = bytes.fromhex('70b50c4c011c932320689b00c5580a4a')
BATTLE_RNG_HOLDER = 0x02255BAC
BATTLE_RNG_OFFSET = 0x24C
BATTLE_RNG_SEED = 0x5EED1604
# Trainer ids (a/0/5/5) started with the game's TrainerBattle command. 1: the
# fixture's default; 2: Steven; 5: Picnicker Amelia (won in turn 2: victory and prize
# messages); 15: Bug Catcher Dylan; 8: Rival Blue (a switch-in); 40 and 50: two more
# battles whose three turns run without input from this checkpoint with the pinned
# battle RNG (BATTLE_RNG_SEED). 15 replaced 30 (Leader Whitney) on 2026-10-07.
TRAINERS = (1, 2, 5, 15, 8, 40, 50)
# Not runnable without input, with the original printer as well (checked
# 2026-10-07): the fixture's only Pokémon (Charmander, Lv 9) faints and the game
# blacks out, which waits for a button press.
EXCLUDED = {100: 'Fisherman Noah: his Poliwrath (Lv 64) faints the fixture\'s only Pokémon (Lv 9) in turn 1; '
                 'the black-out messages wait for a button press',
            3: 'Sinnoh Trainer Cynthia: the fixture\'s Pokémon faints in turn 2 (black-out waits for a button)',
            6: 'Youngster Sol: the fixture\'s Pokémon faints in turn 3 (black-out waits for a button)',
            10: 'Rich Boy Howard: the fixture\'s Pokémon faints in turn 1 (black-out waits for a button)',
            30: 'Leader Whitney: with the pinned battle RNG the fixture\'s Pokémon faints in turn 2 with the '
                'original printer (black-out waits for a button); in the gate until the pin (2026-10-07)'}


def play_segment(h, segment, trainer, delay=0):
    """Play one segment from the loaded checkpoint; True when it reached the command menu or the field."""
    from emu_harness import BATTLE_BUTTONS, MOVE_BUTTONS
    h.step(delay)
    if segment == 0:
        h.trainer_battle(trainer)
        return (h.run_until(lambda h: not h.in_field(), 600)
                and h.run_until(lambda h: h.on_screen('battle_menu'), 1800))
    h.touch(*BATTLE_BUTTONS['fight'], frames=10, after=40)
    h.touch(*MOVE_BUTTONS[0], frames=10, after=90)
    return h.run_until(lambda h: h.on_screen('battle_menu') or h.in_field(), 3000)


def child(args, trainer):
    from emu_harness import Harness
    import msgtool
    payload = load_expected_payload(args)
    cm = msgtool.Charmap.load([str(ROOT / 'work/tools/charmap_en.tsv')])
    report = {'status': 'failed', 'trainer': trainer, 'rom_sha256': digest(args.rom), 'segments': [], 'errors': []}
    errors = report['errors']
    state = {'rows': None}
    active = {}
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            h.set_clock(datetime(2026, 10, 9, 12))
            h.boot_to_menu()
            h.continue_game()
            start = itcm_errors(h, payload)
            require(not start, repr(start))
            probe = attach_probe(h)
            screens = {}

            def passes():
                return len(tracer.frame_ends)

            def frame(h):
                rows = state['rows']
                if rows is None:
                    return
                for i, row in enumerate(rows):
                    if not row['glyphs'] or 'dwell' in row:
                        continue
                    last = row['glyphs'][-1][1]
                    if h.frame == last + 3:   # allow the display transfer after the final glyph
                        screens[i] = (last, h.emu.screenshot().crop(TEXT_BOX).tobytes())
                        row['pixels'] = hashlib.sha256(screens[i][1]).hexdigest()
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
                row = {'start': h.frame, 'start_pass': passes(), 'text': msgtool.decode_units(units, cm),
                       'callback': h.u32(ptr + 0x1C), 'delay': h.u8(ptr + 0x29) & 127, 'id': h.u8(ptr + 0x2C),
                       'glyphs': [], 'glyph_passes': [], 'printer': ptr,
                       'task_mark': len(tracer.tasks) - 1, 'glyph_mark': tracer.mark()}
                active[ptr] = row
                state['rows'].append(row)

            def glyph(h, ptr, event):
                row = active.get(ptr)
                if row is not None:
                    row['glyphs'].append(event)
                    row['glyph_passes'].append(passes())
                    row.pop('dwell', None)

            def destroy(h):
                for ptr, row in list(active.items()):
                    if row['id'] == h.reg.r0:
                        row['end'], row['end_pass'] = h.frame, passes()
                        del active[ptr]
            tracer = PrinterTrace(h, payload, probe=probe, on_task=task, on_glyph=glyph, on_destroy=destroy)
            pin = {'armed': False, 'record': None}
            report['rng_pins'] = []
            report['rng_seed'] = None if args.no_rng_pin else BATTLE_RNG_SEED

            def battle_rng(h):
                """First battle RNG use of a segment-0 run: write the pinned seed, read it back."""
                if not pin['armed'] or h.read(BATTLE_RNG_ROUTINE, len(BATTLE_RNG_CODE)) != BATTLE_RNG_CODE:
                    return
                holder = h.u32(BATTLE_RNG_HOLDER)
                if not holder:
                    return
                address = holder + BATTLE_RNG_OFFSET
                before = h.u32(address)
                h.w32(address, BATTLE_RNG_SEED)
                pin['armed'] = False
                pin['record'].update(applied=True, frame=h.frame, address=address, before=before,
                                     readback=h.u32(address))
            if not args.no_rng_pin:
                h.on_exec(BATTLE_RNG_ROUTINE, battle_rng)

            menus = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            h.press('X', after=90)
            h.touch(124, 115, after=300)
            require(menus, 'Options did not open')
            opts = h.u32(menus[-1] + 0x24)
            before = h.u16(opts)
            h.touch(210, 152, after=40)
            h.touch(149, 180, after=300)
            h.press('B', after=90)
            require(h.u16(opts) == (before & ~12) | (checks.FAST << 2), 'native UI did not select FAST')
            checkpoint = args.out / 'segment-0.dst'
            h.save_state(checkpoint)

            def run(segment, mode, delay=0):
                h.load_state(checkpoint)
                tracer.resync()
                active.clear()
                screens.clear()
                opts_now = h.array(1)
                h.w16(opts_now, (h.u16(opts_now) & ~12) | (mode << 2))
                rows = state['rows'] = []
                if segment == 0 and not args.no_rng_pin:
                    pin['record'] = {'segment': 0, 'mode': checks.NAMES[mode], 'delay': delay, 'applied': False}
                    report['rng_pins'].append(pin['record'])
                    pin['armed'] = True
                began, began_pass = h.frame, passes()
                reached = play_segment(h, segment, trainer, delay)
                pin['armed'] = False
                ended, ended_pass = h.frame, passes()
                h.step(4)
                state['rows'] = None
                printed = [r for r in rows if r['glyphs']]
                for i, row in enumerate(printed):
                    nxt = printed[i + 1] if i + 1 < len(printed) else None
                    last, last_pass = row['glyphs'][-1][1], row['glyph_passes'][-1]
                    row['after_last'] = (nxt['start'] if nxt else ended) - last
                    row['after_last_passes'] = (nxt['start_pass'] if nxt else ended_pass) - last_pass
                    row['print_frames'] = last - row['glyphs'][0][1]
                    row['to_first'] = row['glyphs'][0][1] - row['start']
                    row['to_first_passes'] = row['glyph_passes'][0] - row['start_pass']
                    row['glyph_count'] = len(row['glyphs'])
                    row['to_free'] = row['end'] - last if row.get('end') is not None else None
                    row['to_free_passes'] = row['end_pass'] - last_pass if row.get('end') is not None else None
                lead = (printed[0]['start'] - began - delay) if printed else None
                return reached, ended - began - delay, lead, printed

            for segment in range(TURNS + 1):
                runs = {}
                for mode in MODES:
                    reached, frames, lead, printed = run(segment, mode)
                    h.screenshot(f'segment-{segment}-{checks.NAMES[mode]}')
                    if segment == 0 and not args.no_rng_pin:
                        problems = checks.rng_pin_errors(report['rng_pins'][-1:], BATTLE_RNG_SEED)
                        require(not problems, f'segment 0 {checks.NAMES[mode]}: {problems}')
                    require(reached, f'segment {segment} {checks.NAMES[mode]}: stuck without A/B input'
                            + ('' if mode != checks.ORIGINAL else ' (the original printer itself: a fixture '
                               'problem, e.g. the battle blacks out)'))
                    for row in printed:
                        tasks = [t for t in tracer.tasks[row['task_mark']:] if t['printer'] == row['printer']
                                 and t['frame'] <= row.get('end', h.frame)]
                        last = row['glyphs'][-1][1]
                        row['lag_frames'] = sum(1 for f in range(row['glyphs'][0][1], last + 1)
                                                if f not in {t['frame'] for t in tasks})
                        summary, cadence_errors = checks.cadence(mode, row['glyphs'])
                        row['cadence'] = summary
                        row['stops'], stop_errors = checks.task_errors(mode, tasks)
                        warm = checks.warm_costs(tasks)
                        row['record'] = checks.speed_record(
                            tasks, [(row['glyphs'][0][1], last)],
                            sorted(warm)[len(warm) // 2] if warm else checks.GLYPH_SEED)
                        tag = f"segment {segment} {checks.NAMES[mode]} {row['text'][:30]!r}"
                        errors.extend(f'{tag}: {e}' for e in cadence_errors + stop_errors)
                        if row.get('pixels') is None:
                            errors.append(f'{tag}: completed text pixels not captured')
                    errors.extend(f'segment {segment} {checks.NAMES[mode]}: {e}' for e in tracer.state_errors)
                    tracer.state_errors.clear()
                    runs[mode] = {'frames': frames, 'lead_in': lead, 'field': h.in_field(), 'messages': [
                        {k: r.get(k) for k in ('text', 'glyph_count', 'print_frames', 'to_first', 'to_first_passes',
                                               'after_last',
                                               'after_last_passes', 'dwell', 'end', 'to_free', 'to_free_passes',
                                               'lag_frames', 'pixels', 'callback', 'delay', 'cadence', 'stops',
                                               'record')} | {'glyphs': r['glyph_count']}
                        for r in printed]}
                    if mode == 3:
                        following = args.out / f'segment-{segment + 1}.dst'
                        h.save_state(following)
                base = runs[3]['messages']
                if not base:
                    errors.append(f'segment {segment}: original printer printed nothing (vacuous)')
                # The original printer's own pauses with its start delayed by 1..JITTER_DELAYS frames:
                # needed only where a speed's pause differs from the original's by one pass.
                jitter = None
                if any((a['after_last_passes'], a.get('dwell')) != (b['after_last_passes'], b.get('dwell'))
                       for m in SPEEDS for a, b in zip(base, runs[m]['messages'])
                       if [x['text'] for x in base] == [x['text'] for x in runs[m]['messages']]):
                    jitter = [{'pause': {r['after_last_passes']}, 'dwell': {r.get('dwell')}} for r in base]
                    replays = []
                    for delay in range(1, JITTER_DELAYS + 1):
                        reached, _, _, printed = run(segment, 3, delay)
                        texts = [r['text'] for r in printed]
                        same = reached and texts == [r['text'] for r in base]
                        replays.append({'delay': delay, 'reached': reached, 'same_battle': same,
                                        'pauses': [r['after_last_passes'] for r in printed],
                                        'dwell': [r.get('dwell') for r in printed]})
                        if same:
                            for i, r in enumerate(printed):
                                jitter[i]['pause'].add(r['after_last_passes'])
                                jitter[i]['dwell'].add(r.get('dwell'))
                    tracer.state_errors.clear()
                    runs[3]['jitter_replays'] = replays
                for mode in SPEEDS:
                    errors.extend(f'segment {segment} {checks.NAMES[mode]}: {e}'
                                  for e in checks.battle_pacing_errors(base, runs[mode]['messages'], jitter))
                    if runs[mode]['lead_in'] != runs[3]['lead_in']:
                        errors.append(f"segment {segment} {checks.NAMES[mode]}: lead-in {runs[mode]['lead_in']} "
                                      f"frames != original {runs[3]['lead_in']}")
                    saved = sum(r['print_frames'] for r in base) - sum(r['print_frames'] for r in runs[mode]['messages'])
                    paused = sum(a['after_last'] - b['after_last'] + a['to_first'] - b['to_first']
                                 for a, b in zip(base, runs[mode]['messages']))
                    runs[mode]['frames_saved_vs_original'] = runs[3]['frames'] - runs[mode]['frames']
                    runs[mode]['print_frames_saved'] = saved
                    runs[mode]['pause_frames_saved'] = paused
                    if runs[mode]['frames_saved_vs_original'] != saved + paused:
                        errors.append(f'segment {segment} {checks.NAMES[mode]}: segment shortened by '
                                      f"{runs[mode]['frames_saved_vs_original']} frames, printing by {saved}, "
                                      f'pauses by {paused}')
                spans = {m: sum(r['print_frames'] for r in runs[m]['messages']) for m in MODES}
                records = {m: checks.merge_records([r['record'] for r in runs[m]['messages']]) for m in MODES}
                order, notes = checks.order_errors(records)
                errors.extend(f'segment {segment}: {e}' for e in order)
                report['segments'].append({'segment': segment, 'runs': runs,
                                           'jitter': [{k: sorted(v, key=str) for k, v in x.items()} for x in jitter]
                                           if jitter else None,
                                           'order': {'print_frames': spans, 'records': records,
                                                     'capped_ties': notes}})
                checkpoint = args.out / f'segment-{segment + 1}.dst'
                if runs[3]['field']:
                    break
            if not args.no_rng_pin:
                errors.extend(checks.rng_pin_errors(report['rng_pins'], BATTLE_RNG_SEED))
            texts = [m['text'] for s in report['segments'] for m in s['runs'][3]['messages']]
            if len(texts) < 4 or not any('used' in t for t in texts):
                errors.append(f'too few battle messages for a pacing check: {texts}')
            report['memory'] = memory_summary(probe)
            errors.extend(memory_errors(report['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        if not errors:
            report['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(p)
    p.add_argument('--trainer', type=int, help='child mode: one battle')
    p.add_argument('--trainers', help='diagnosis only: comma-separated subset (validate_release runs all)')
    p.add_argument('--no-rng-pin', action='store_true',
                   help='diagnosis only: do not pin the battle RNG (shows the fixture problem; never release evidence)')
    p.add_argument('--jobs', type=int, default=3)
    args = resolve(p, p.parse_args())
    if args.trainer is not None:
        child(args, args.trainer)
        return
    payload = load_expected_payload(args)
    trainers = [int(x) for x in args.trainers.split(',')] if args.trainers else list(TRAINERS)
    report = {'status': 'failed', **identity(args, payload), 'battles': {}, 'excluded': EXCLUDED, 'errors': []}
    errors = report['errors']

    def run(trainer):
        out = args.out / f'trainer-{trainer}'
        command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                   '--out', str(out), '--trainer', str(trainer)]
        command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
        command += ['--no-rng-pin'] if args.no_rng_pin else []
        with (args.out / f'trainer-{trainer}.log').open('w') as log:
            code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        return trainer, code, out / 'report.json'

    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(run, trainers))
        for trainer, code, path in results:
            if not path.exists():
                errors.append(f'trainer {trainer}: child wrote no report (exit {code})')
                continue
            r = json.loads(path.read_text())
            if r.get('rom_sha256') != digest(args.rom):
                errors.append(f'trainer {trainer}: wrong candidate executed')
            report['battles'][trainer] = {'segments': r['segments'], 'memory': r.get('memory'),
                                          'rng_seed': r.get('rng_seed'), 'rng_pins': r.get('rng_pins')}
            if args.no_rng_pin:
                errors.append(f'trainer {trainer}: run without the battle RNG pin (diagnosis only, never evidence)')
            if code or r['status'] != 'passed':
                errors.extend(f'trainer {trainer}: {e}' for e in (r['errors'] or [f'exit {code}']))
        per_frame = {m: max((x['cadence'].get('max_tasks_per_frame', 0) for b in report['battles'].values()
                             for s in b['segments'] for x in s['runs'][str(m)]['messages']), default=0)
                     for m in MODES}
        report['max_tasks_per_frame'] = per_frame
        report['jitter'] = {t: [(s['segment'], s['jitter']) for s in b['segments'] if s['jitter']]
                            for t, b in report['battles'].items()}
        if not inputs_unchanged(report):
            errors.append('input modified')
        if not errors and len(report['battles']) == len(trainers):
            report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, errors)))


if __name__ == '__main__':
    main()
