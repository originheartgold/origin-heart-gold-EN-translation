"""Text speed in busy and light field scenes, judged by the product (frames and dropped frames).

Each scene is a fresh cold boot (own process, private battery directory, pinned clock)
into the trainer fixture's Route 1 spot, then the scene's setup (an Options visit, a long
idle, or a scripted warp and 600 frames to settle), then a checkpoint. From that
checkpoint the same text is printed once per mode: the original printer (reserved value
3, controlled RAM write of the two text-speed bits) first, then SLOW, MEDIUM and FAST.
The text is either the 54-glyph trainer page (A on the trainer), message 718#160 (two
pages, injected with the game's own message command, A between pages), or a real NPC
talk (A until no new glyph appears).

Per mode the gate requires the model checks (text_speed_checks.task_errors: budgets,
every frame decision equal to the payload's frame model, stop reasons, SLOW phase; the
payload's frame state equal to the costs the gate measured itself), the same glyph count
and layout as the original printer, and the product rules of
text_speed_checks.order_errors: ORIGINAL > SLOW > MEDIUM > FAST in printing frames, a tie
or inversion only at the physical cap (no unnecessary frame stop, judged from the
observed frame ends; the remaining difference only drops that the mandatory first glyph
forced), no speed with more dropped frames than the original printer, and SLOW within
its design floor (2/3 of the original's printing tasks plus one per page).

The scene set is the independent review's (2026-10-07): busy 60 fps scenes where even
one glyph per frame sometimes overruns, light 60 fps scenes, and 30 fps scenes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLOCK, ROOT, PrinterTrace, add_arguments, attach_probe, digest, identity,  # noqa: E402
                         inputs_unchanged, itcm_errors, judge_message, load_expected_payload, memory_errors,
                         memory_summary, require, resolve)
import text_speed_checks as checks  # noqa: E402

MODES = (3, 0, 1, 2)
# name: (setup, text). setup: ('trainer', condition) stays on the fixture's Route 1 spot;
# (map, x, y) warps there with the game's Warp command; None stays where the save starts.
SCENES = {
    'trainer-fresh': (('trainer', 'plain'), 'trainer'),
    'trainer-after-options': (('trainer', 'options'), 'trainer'),
    'route1-idle': (('trainer', 'idle'), 'trainer'),
    'pallet-house-2f': ((64, 6, 4), '718#160'),
    'ecruteak-theater': ((86, 8, 10), '718#160'),
    'pokeathlon-gatehouse': ((150, 5, 11), '718#160'),
    'mt-moon': ((448, 5, 15), '718#160'),
    'celadon-gym': ((395, 7, 8), '718#160'),
    'goldenrod-dept-6f': ((196, 4, 8), '718#160'),
    'route1': (None, '718#160'),
    'route1-30fps': ((9, 1041, 335), '718#160'),
    'viridian-city': ((50, 1033, 248), '718#160'),
    'viridian-forest': ((147, 90, 73), '718#160'),
    'ss-anne': ((307, 8, 15), '718#160'),
    'route1-promoter': (None, 'talk'),
    'route1-promoter-30fps': ((9, 1041, 335), 'talk'),
    'seven-island-tourist': ((163, 245, 104), 'talk'),
}
# Scenes where even the original printer drops frames or the speeds reach the frame
# limit; the review found the fixed frame rule failing here. At least these must run.
BUSY = ('goldenrod-dept-6f', 'celadon-gym', 'route1-idle', 'trainer-after-options')


def setup(h, spec):
    h.set_clock(CLOCK)
    h.step(2400)
    h.press('START', after=400)
    for _ in range(2):
        h.press('A', after=300)
    require(h.run_until(lambda h: h.in_field(), 600, every=10), 'did not reach the field')
    if spec and spec[0] == 'trainer':
        if spec[1] == 'plain':
            h.step(60)
        elif spec[1] == 'options':     # open Options and confirm without a change
            h.press('X', after=90)
            for key in ('RIGHT', 'DOWN', 'DOWN'):
                h.press(key, after=30)
            h.press('A', after=300)
            h.touch(149, 180, frames=6, after=300)
        elif spec[1] == 'idle':
            h.step(2100)
    elif spec:
        h.warp(*spec, 0)
        h.step(600)
    else:
        h.step(600)


def show(h, text, trace):
    """Print the scene's text; returns the glyph-frame page ranges, or None to split by gaps."""
    if text == 'trainer':
        h.press('A', after=234)
    elif text == 'talk':
        h.press('A', after=10)
        for i in range(12):
            n = trace.mark()
            h.step(200)
            if trace.mark() == n and i > 0:
                break
            h.press('A', after=10)
    else:
        bank, msg = map(int, text.split('#'))
        h.show_message(bank, msg, name=f'{bank}_{msg}', max_pages=10, settle=200)


def child(args, name):
    from emu_harness import Harness
    payload = load_expected_payload(args)
    spec, text = SCENES[name]
    report = {'status': 'failed', 'scene': name, 'text': text, 'rom_sha256': digest(args.rom), 'modes': {}, 'errors': []}
    errors = report['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            setup(h, spec)
            start = itcm_errors(h, payload)
            require(not start, f'ITCM at start: {start}')
            report['location'] = h.location()
            checkpoint = args.out / 'scene.dst'
            h.save_state(checkpoint)
            probe = attach_probe(h)
            trace = PrinterTrace(h, payload, font=1, probe=probe)
            for mode in MODES:
                h.load_state(checkpoint)
                trace.reset()
                opts = h.array(1)
                h.w16(opts, (h.u16(opts) & ~12) | (mode << 2))
                mark, task_mark = trace.mark(), trace.task_mark()
                show(h, text, trace)
                record, stops, task_errors = judge_message(trace, mode, mark, task_mark)
                tag = checks.NAMES[mode]
                errors.extend(f'{tag}: {e}' for e in task_errors)
                errors.extend(f'{tag}: {e}' for e in trace.state_errors)
                require(record['glyphs'] > 0, f'{tag}: no glyphs printed (vacuous scene)')
                report['modes'][mode] = dict(record, stops=stops, layout=trace.layout(mark),
                                             frame_ends=len(trace.frame_ends))
                h.screenshot(f'{name}-{tag}')
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


def judge(scene):
    """Cross-mode product verdict for one scene report."""
    modes = {int(m): r for m, r in scene['modes'].items()}
    if set(modes) != set(MODES):
        return [f'modes missing: {sorted(set(MODES) - set(modes))}'], []
    errors = []
    base = modes[3]
    for m in (0, 1, 2):
        if modes[m]['glyphs'] != base['glyphs'] or modes[m]['layout'] != base['layout']:
            errors.append(f'{checks.NAMES[m]}: glyphs or layout differ from the original printer')
        if modes[m]['pages'] != base['pages']:
            errors.append(f'{checks.NAMES[m]}: {modes[m]["pages"]} pages, original {base["pages"]}')
    order, notes = checks.order_errors(modes)
    return errors + order, notes


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(p)
    p.add_argument('--scene', choices=sorted(SCENES), help='child mode: run one scene')
    p.add_argument('--scenes', help='diagnosis only: comma-separated subset (validate_release runs all)')
    p.add_argument('--jobs', type=int, default=3)
    args = resolve(p, p.parse_args())
    if args.scene:
        child(args, args.scene)
        return
    payload = load_expected_payload(args)
    names = args.scenes.split(',') if args.scenes else list(SCENES)
    if not set(names) <= set(SCENES):
        p.error(f'unknown scenes {sorted(set(names) - set(SCENES))}')
    report = {'status': 'failed', **identity(args, payload), 'scenes': {}, 'errors': [],
              'complete': set(names) == set(SCENES)}
    errors = report['errors']

    def run(name):
        out = args.out / name
        command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                   '--out', str(out), '--scene', name]
        command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
        with (args.out / f'{name}.log').open('w') as log:
            code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        return name, code, out / 'report.json'

    try:
        missing = [n for n in BUSY if n not in names]
        if args.scenes is None and missing:
            errors.append(f'busy scenes missing: {missing}')
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(run, names))
        for name, code, path in results:
            if not path.exists():
                errors.append(f'{name}: child wrote no report (exit {code})')
                continue
            r = json.loads(path.read_text())
            if r.get('rom_sha256', digest(args.rom)) != digest(args.rom):
                errors.append(f'{name}: wrong candidate executed')
            row = {'text': r['text'], 'location': r.get('location'),
                   'modes': {checks.NAMES[int(m)]: {k: v for k, v in x.items() if k not in ('layout',)}
                             for m, x in r['modes'].items()}}
            if code or r['status'] != 'passed':
                errors.extend(f'{name}: {e}' for e in (r['errors'] or [f'exit {code}']))
            else:
                scene_errors, notes = judge(r)
                row['errors'], row['capped_ties'] = scene_errors, notes
                errors.extend(f'{name}: {e}' for e in scene_errors)
            report['scenes'][name] = row
        report['table'] = {name: {m: (x['frames'], x['drops']) for m, x in row['modes'].items()}
                           for name, row in report['scenes'].items()}
        if not inputs_unchanged(report):
            errors.append('input modified')
        if not errors:
            report['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(report, indent=2, default=str))
    if report['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, errors)))


if __name__ == '__main__':
    main()
