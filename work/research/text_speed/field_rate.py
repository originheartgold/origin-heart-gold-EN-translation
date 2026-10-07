"""Field text rate in 30 fps and 60 fps maps: the printer catch-up (D-1603), judged against
the same ROM with the catch-up switched off.

The hack's game loop runs the print task queue once per pass and does not cap logic,
so in maps where a pass spans two VBlanks text prints at half the vanilla rate
(vanilla runs the queue twice per pass). pass_end runs each text printer task once
more when a VBlank passed during the pass. This gate proves, per field scene:

- rate: NORMAL (stored 0: the hack's own printer task plus the catch-up, D-1604) prints
  at most MAX_FPG frames per glyph (vanilla FAST measured 0.98 in Viridian);
- no cost without text: idle loop passes over IDLE frames are not fewer than with the
  catch-up off (same checkpoint);
- same text: glyph count, glyph positions, page count and the message window's pixels
  of every page equal the catch-up-off run;
- other queue tasks keep their rate: the print queue is run exactly once per pass in
  both runs (the catch-up never runs the queue), every printer task slot holds a
  printer task, and the catch-up runs only after the model's catch-up decision
  (PrinterTrace: state and decisions equal the payload's);
- no extra dropped frames: no catch-up let the VBlank counter move before the loop's
  wait (catchup_overruns);
- not vacuous: every 30 fps scene (catch-up off: at least SLOW_FPG frames per glyph)
  ran catch-up tasks, and at least MIN_30FPS scenes are 30 fps scenes.

The catch-up-off run uses an execution hook at pass_end's entry that clears the
state's 'ended' byte, so pass_end never sees a late pass (frame_end and print_task
are unchanged). Each scene is a fresh cold boot (own process, private battery,
pinned clock) into the trainer fixture's Route 1 spot, then a scripted warp and 600
frames to settle; both runs start from the same checkpoint.

Goldenrod City is not covered: a scripted warp there leaves a black screen in this
fixture (also on the untouched Chinese ROM), so no message can be injected.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLOCK, GLYPH, ROOT, PrinterTrace, add_arguments, attach_probe, digest, identity,  # noqa: E402
                         inputs_unchanged, itcm_errors, judge_message, load_expected_payload, memory_errors,
                         memory_summary, require, resolve)
import text_speed_checks as checks  # noqa: E402

SCENES = {
    'route1': None,
    'route1-30fps': (9, 1041, 335),
    'viridian-city': (50, 1033, 248),
    'viridian-forest': (147, 90, 73),
    'route29': (33, 626, 390),
    'route30': (34, 568, 295),
    'new-bark': (60, 684, 394),
    'cherrygrove': (67, 564, 392),
    'cherrygrove-pokecenter': (69, 8, 18),
    'violet-city': (73, 479, 258),
}
TEXT = (718, 160)
MODE = checks.NORMAL
MAX_FPG = 1.05        # vanilla US FAST: 0.98 frames per glyph (Viridian, 2026-10-07)
SLOW_FPG = 1.5        # catch-up off at or above this: a 30 fps scene
MIN_30FPS = 5
IDLE = 600
PAGE_GAP = 40
WINDOW = (8, 148, 232, 187)   # message window text area on the top screen (x0, y0, x1, y1); the arrow is outside
GSYS = 0x021D0094
PRINT_QUEUE = GSYS + 0x24
QUEUE_RUN = 0x02020040
PASS_CALL = 0x02000DE0
PRINTER_SLOTS = 0x021D0EFC
VBLANKS = 0x027FFC3C


def setup(h, spec):
    h.set_clock(CLOCK)
    h.step(2400)
    h.press('START', after=400)
    for _ in range(2):
        h.press('A', after=300)
    require(h.run_until(lambda h: h.in_field(), 600, every=10), 'did not reach the field')
    if spec:
        h.warp(*spec, 0)
    h.step(600)


def fpg(frames):
    """Frames per glyph: page spans over glyph steps (pages split at gaps > PAGE_GAP)."""
    pages, span, steps = [], 0, 0
    for f in frames:
        if pages and f - pages[-1][-1] <= PAGE_GAP:
            pages[-1].append(f)
        else:
            pages.append([f])
    for p in pages:
        span += p[-1] - p[0]
        steps += len(p) - 1
    return (round(span / steps, 3) if steps else None), len(pages)


class Loop:
    """Game loop observations: passes, VBlanks per pass, print-queue runs, queue contents."""

    def __init__(self, h, print_task):
        self.h, self.print_task = h, print_task
        self.on = False
        self.reset()
        h.on_exec(PASS_CALL, self._pass)
        h.on_exec(QUEUE_RUN, self._run)

    def reset(self):
        self.passes, self.runs, self.last = 0, 0, None
        self.elapsed, self.others, self.slot_errors = {}, {}, []

    def _pass(self, h):
        if not self.on:
            return
        v = h.u32(VBLANKS)
        if self.last is not None:
            k = str((v - self.last) & 0xFFFFFFFF)
            self.elapsed[k] = self.elapsed.get(k, 0) + 1
        self.last = v
        self.passes += 1
        q = h.u32(PRINT_QUEUE)
        t, n = h.u32(q + 0xC), 0
        while t != q + 4 and n < 64:
            func = h.u32(t + 0x14)
            if func != self.print_task:
                self.others[hex(func)] = self.others.get(hex(func), 0) + 1
            t, n = h.u32(t + 8), n + 1
        for i in range(8):
            t = h.u32(PRINTER_SLOTS + 4 * i)
            if t and h.u32(t + 0x14) != self.print_task and len(self.slot_errors) < 5:
                self.slot_errors.append(f'frame {h.frame}: printer slot {i} holds task func {h.u32(t + 0x14):#x}')

    def _run(self, h):
        if self.on and h.reg.r0 == h.u32(PRINT_QUEUE):
            self.runs += 1


def window(path):
    from PIL import Image
    return Image.open(path).convert('RGB').crop(WINDOW).tobytes()


def measure(h, loop, checkpoint, catch_up, glyphs, name, after_load=lambda: None):
    """One run from the checkpoint: idle passes, then the message in the original printer.
    after_load runs after each savestate load (the trace restarts its model from RAM)."""
    h.load_state(checkpoint)
    after_load()
    loop.reset()
    loop.on = True
    h.step(IDLE)
    idle = {'passes': loop.passes, 'elapsed': dict(loop.elapsed), 'queue_runs': loop.runs,
            'other_tasks': dict(loop.others)}
    h.load_state(checkpoint)
    after_load()
    loop.reset()
    glyphs.clear()
    opts = h.array(1)
    h.w16(opts, (h.u16(opts) & ~12) | (MODE << 2))
    shots = h.show_message(*TEXT, name=f'{name}-{"on" if catch_up else "off"}', max_pages=10, settle=200)
    loop.on = False
    rate, pages = fpg([f for f, _, _ in glyphs])
    text = {'glyphs': len(glyphs), 'pages': pages, 'fpg': rate, 'layout': [(x, y) for _, x, y in glyphs],
            'passes': loop.passes, 'elapsed': dict(loop.elapsed), 'queue_runs': loop.runs,
            'other_tasks': dict(loop.others), 'slot_errors': list(loop.slot_errors),
            'windows': [window(s).hex() for s in shots]}
    return idle, text


def child(args, name):
    from emu_harness import Harness
    payload = load_expected_payload(args)
    spec = SCENES[name]
    report = {'status': 'failed', 'scene': name, 'rom_sha256': digest(args.rom), 'errors': []}
    errors = report['errors']
    state = payload['symbols']['text_speed_state']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            setup(h, spec)
            start = itcm_errors(h, payload)
            require(not start, f'ITCM at start: {start}')
            report['location'] = h.location()
            checkpoint = args.out / 'scene.dst'
            h.save_state(checkpoint)
            loop = Loop(h, payload['symbols']['print_task'])
            off = {'on': True}

            def disable(h):          # pass_end entry: no previous pass end -> never late
                if off['on']:
                    h.w8(state + 25, 0)
            h.on_exec(payload['symbols']['pass_end'] & ~1, disable)
            glyphs = []
            h.on_exec(GLYPH, lambda h: glyphs.append((h.frame, h.u16(h.reg.r4 + 12), h.u16(h.reg.r4 + 14)))
                      if h.u8(h.reg.r4 + 9) == 1 else None)
            idle_off, text_off = measure(h, loop, checkpoint, False, glyphs, name)
            # Catch-up on, with the full printer trace (model, decisions, catch-up tasks).
            off['on'] = False
            h.on_exec(GLYPH, None)
            h.load_state(checkpoint)
            probe = attach_probe(h)
            trace = PrinterTrace(h, payload, font=1, probe=probe,
                                 on_glyph=lambda h, ptr, info: glyphs.append((h.frame, h.u16(ptr + 12),
                                                                              h.u16(ptr + 14))))
            idle_on, text_on = measure(h, loop, checkpoint, True, glyphs, name, after_load=trace.reset)
            # trace.reset() after the last load: everything recorded belongs to the message.
            record, stops, task_errors = judge_message(trace, MODE, 0, 0)
            errors.extend(f'NORMAL: {e}' for e in task_errors)
            errors.extend(trace.state_errors)
            catch = [c for c in trace.catchups if c[3]]
            report['catch_up'] = {'late_passes': sum(1 for c in trace.catchups if c[2]), 'decisions': len(catch),
                                  'tasks': sum(c[4] for c in trace.catchups), 'overruns': trace.catchup_overruns}
            report['off'] = {'idle': idle_off, 'text': text_off}
            report['on'] = {'idle': idle_on, 'text': text_on}
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


def judge(r):
    """Cross-run verdict for one scene report."""
    errors = []
    on, off = r['on'], r['off']
    t_on, t_off = on['text'], off['text']
    if not t_on['glyphs']:
        return ['no glyphs printed (vacuous scene)']
    if t_on['fpg'] is None or t_on['fpg'] > MAX_FPG:
        errors.append(f"original printer: {t_on['fpg']} frames per glyph, at most {MAX_FPG} (vanilla 0.98; "
                      f"catch-up off {t_off['fpg']})")
    if on['idle']['passes'] < off['idle']['passes']:
        errors.append(f"idle: {on['idle']['passes']} loop passes in {IDLE} frames, catch-up off "
                      f"{off['idle']['passes']}")
    for k in ('glyphs', 'pages', 'layout'):
        if t_on[k] != t_off[k]:
            errors.append(f'text differs from the catch-up-off run: {k}')
    if t_on['windows'] != t_off['windows']:
        errors.append('message window pixels differ from the catch-up-off run')
    for run, x in (('on', on), ('off', off)):
        for part in ('idle', 'text'):
            y = x[part]
            if y['queue_runs'] != y['passes']:
                errors.append(f"catch-up {run}, {part}: print queue ran {y['queue_runs']} times in "
                              f"{y['passes']} passes (must be once per pass)")
        errors.extend(f'catch-up {run}: {e}' for e in x['text']['slot_errors'])
    if on['idle']['other_tasks'] != off['idle']['other_tasks']:
        errors.append(f"idle: other print-queue tasks differ: {on['idle']['other_tasks']} / "
                      f"{off['idle']['other_tasks']}")
    c = r['catch_up']
    if c['overruns']:
        errors.append(f"{c['overruns']} catch-ups moved the VBlank counter before the loop's wait (dropped frames)")
    if (t_off['fpg'] or 0) >= SLOW_FPG and not c['tasks']:
        errors.append(f"30 fps scene (catch-up off {t_off['fpg']} frames per glyph) ran no catch-up task")
    return errors


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
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            results = list(pool.map(run, names))
        slow = 0
        for name, code, path in results:
            if not path.exists():
                errors.append(f'{name}: child wrote no report (exit {code})')
                continue
            r = json.loads(path.read_text())
            if r.get('rom_sha256', digest(args.rom)) != digest(args.rom):
                errors.append(f'{name}: wrong candidate executed')
            if code or r['status'] != 'passed':
                errors.extend(f'{name}: {e}' for e in (r['errors'] or [f'exit {code}']))
                continue
            scene_errors = judge(r)
            errors.extend(f'{name}: {e}' for e in scene_errors)
            slow += (r['off']['text']['fpg'] or 0) >= SLOW_FPG
            report['scenes'][name] = {
                'location': r.get('location'), 'errors': scene_errors, 'catch_up': r['catch_up'],
                **{run: {'idle_passes': r[run]['idle']['passes'], 'idle_elapsed': r[run]['idle']['elapsed'],
                         'fpg': r[run]['text']['fpg'], 'glyphs': r[run]['text']['glyphs'],
                         'text_elapsed': r[run]['text']['elapsed']} for run in ('off', 'on')}}
        if args.scenes is None and slow < MIN_30FPS:
            errors.append(f'only {slow} scenes print at 30 fps with the catch-up off, at least {MIN_30FPS} '
                          '(vacuous rate check)')
        report['table'] = {n: {'fpg': (x['off']['fpg'], x['on']['fpg']),
                               'idle_passes': (x['off']['idle_passes'], x['on']['idle_passes']),
                               'catch_up_tasks': x['catch_up']['tasks']} for n, x in report['scenes'].items()}
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
