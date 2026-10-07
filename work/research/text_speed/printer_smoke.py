"""Smoke gate for text printers outside ordinary field dialogue.

Each screen is played from the same checkpoint once per mode: the original printer
(reserved value 3) and SLOW / MEDIUM / FAST. Every AddTextPrinter call is logged
(speed, callback, caller). Per screen the gate requires:
- the batched path is used exactly as declared: 'batched' screens print through
  native batching tasks at every speed (and only through the original task with
  value 3); 'synchronous' screens start no asynchronous printer at all;
- every native task passes text_speed_checks.task_errors (budget, frame rule,
  stop reasons);
- the captured screens equal the original printer's, after the text completed
  (top screen rows TEXT_ROWS, which exclude the page arrow and animated field).

Screens: save prompt, Route 1 sign, Pokémon Center PC (two messages) and a
Pokégear phone call to Mom (three pages, each captured). Not covered: the Pokégear radio (the fixture has no radio
card), mail (no mail item), the credits (end of the game) and the new-game
introduction: it is reachable from a blank battery (about 32 A presses), but its
pages are drawn synchronously; the one asynchronous printer it starts renders a
single control step before the scene removes it, and New Game re-initialises
Options (MEDIUM), so a mode cannot be chosen there. No batched glyphs to compare.
"""
import argparse
import hashlib
import json
import subprocess
import sys

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, PRINTER_START, ROOT, PrinterTrace, add_arguments, identity, inputs_unchanged,
                         itcm_errors, load_expected_payload, require, resolve, start_game)
import text_speed_checks as checks

MODES = (3, 0, 1, 2)
PC_CENTER = (69, 11, 13)          # Cherrygrove Pokémon Center 1F: tile below the PC (behaviour 0x83), facing up
SIGN_SCRIPT = 3                   # Route 1 bg event 0: the direction sign


def crop_hash(h, box):
    return hashlib.sha256(h.emu.screenshot().crop(box).tobytes()).hexdigest()


# Capture boxes in the 256x384 screenshot (top screen y 0..191, bottom 192..383).
MESSAGE_BOX = (8, 145, 236, 184)      # field message window text, without the page arrow
SCREENS = {
    'save': {'path': 'batched', 'shots': {'prompt': MESSAGE_BOX}},
    'sign': {'path': 'synchronous', 'shots': {'sign': MESSAGE_BOX}},
    'pc': {'path': 'batched', 'shots': {'booted': MESSAGE_BOX, 'which-pc': (8, 145, 200, 184)}},
    'phone': {'path': 'batched', 'shots': {'call': (8, 120, 248, 176), 'call-2': (8, 120, 248, 176),
                                           'call-3': (8, 120, 248, 176)}},
}


def play(h, name, shot):
    """Drive one screen from the checkpoint; shot(label) captures."""
    if name == 'save':
        h.field_menu('save')
        h.step(200)
        shot('prompt')
        h.press('B', after=120)
    elif name == 'sign':
        h.run_script(script_id=SIGN_SCRIPT, settle=30)
        h.step(150)
        shot('sign')
    elif name == 'pc':
        h.warp(*PC_CENTER, 0)
        h.press('A', after=200)
        shot('booted')
        h.press('A', after=200)
        shot('which-pc')
    elif name == 'phone':
        h.field_menu('pokegear')
        h.step(60)
        h.press('A', after=90)
        h.press('A', after=90)
        h.press('A', after=300)
        shot('call')                  # Mom: three pages, A between them
        h.press('A', after=200)
        shot('call-2')
        h.press('A', after=200)
        shot('call-3')


def child(args, payload, battery):
    """One emulator process per battery (DeSmuME keeps per-process state)."""
    from emu_harness import Harness
    report = {'status': 'failed', 'battery': battery, 'screens': [], 'errors': []}
    errors = report['errors']
    try:
        names = list(SCREENS)
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start = itcm_errors(h, payload)
            require(not start, f'ITCM at start: {start}')
            tracer = PrinterTrace(h, payload)
            starts = []
            h.on_exec(PRINTER_START, lambda h: starts.append((h.frame, h.reg.r1, h.reg.r2, h.reg.lr)))
            checkpoint = args.out / 'checkpoint.dst'
            h.save_state(checkpoint)
            for name in names:
                for mode in MODES:
                    h.load_state(checkpoint)
                    tracer.reset()
                    del starts[:]
                    opts = h.array(1)
                    h.w16(opts, (h.u16(opts) & ~12) | (mode << 2))
                    shots = {}

                    def shot(label):
                        shots[label] = crop_hash(h, SCREENS[name]['shots'][label])
                        h.screenshot(f'{name}-{label}-{checks.NAMES[mode]}')
                    first = h.frame
                    play(h, name, shot)
                    tag = f'{name} {checks.NAMES[mode]}'
                    require(set(shots) == set(SCREENS[name]['shots']), f'{tag}: captures missing')
                    asynchronous = [(f - first, s, hex(c), hex(lr)) for f, s, c, lr in starts if s not in (0, 0xFF)]
                    drew = [t for t in tracer.tasks if t['delegated'] or any(e[0] == 'glyph' for e in t['events'])]
                    batched = sum(1 for t in drew if not t['delegated'])
                    delegated = sum(1 for t in drew if t['delegated'])
                    stops, stop_errors = checks.task_errors(mode, drew) if drew else ({}, [])
                    errors.extend(f'{tag}: {e}' for e in stop_errors + tracer.state_errors)
                    row = {'screen': name, 'mode': mode, 'path': SCREENS[name]['path'], 'shots': shots,
                           'async_starts': asynchronous, 'sync_starts': len(starts) - len(asynchronous),
                           'glyphs': len(tracer.glyphs), 'batched': batched, 'delegated': delegated,
                           'tasks': len(tracer.tasks),
                           'stops': stops}
                    if SCREENS[name]['path'] == 'synchronous':
                        if asynchronous:
                            errors.append(f'{tag}: declared synchronous, but started async printers {asynchronous}')
                    elif not asynchronous:
                        errors.append(f'{tag}: declared batched, but no async printer started')
                    elif mode == 3 and batched:
                        errors.append(f'{tag}: {batched} batched tasks with the original printer selected')
                    elif mode != 3 and not batched:
                        errors.append(f'{tag}: async printer did not go through the batched path')
                    if not tracer.glyphs:
                        errors.append(f'{tag}: no glyphs drawn (vacuous)')
                    report['screens'].append(row)
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
        if not errors:
            report['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    p.add_argument('--battery', choices=('fixture',))
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    if args.battery:
        child(args, payload, args.battery)
        return
    report = {'status': 'failed', **identity(args, payload), 'screens': [], 'errors': []}
    errors = report['errors']
    try:
        for battery in ('fixture',):
            out = args.out / battery
            command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                       '--out', str(out), '--battery', battery]
            command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
            with (args.out / f'{battery}.log').open('w') as log:
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
            if not (out / 'report.json').exists():
                errors.append(f'{battery}: child wrote no report (exit {code})')
                continue
            r = json.loads((out / 'report.json').read_text())
            report['screens'] += r['screens']
            if code or r['status'] != 'passed':
                errors.extend(f'{battery}: {e}' for e in (r['errors'] or [f'exit {code}']))
        results = {(r['screen'], r['mode']): r for r in report['screens']}
        for name in SCREENS:
            base = results.get((name, 3))
            if base is None:
                errors.append(f'{name}: original printer run missing')
                continue
            for mode in (0, 1, 2):
                other = results.get((name, mode))
                if other is None:
                    errors.append(f'{name} {checks.NAMES[mode]}: run missing')
                    continue
                other['identical'] = other['shots'] == base['shots']
                for label, digest in base['shots'].items():
                    if other['shots'].get(label) != digest:
                        errors.append(f'{name} {checks.NAMES[mode]}: {label} pixels differ from the original printer')
        if not inputs_unchanged(report):
            errors.append('input modified')
        if not errors:
            report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(errors))


if __name__ == '__main__':
    main()
