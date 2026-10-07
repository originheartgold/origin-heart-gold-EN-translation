"""Natural trainer dialogue after choosing each speed through native Options touch input.

One cold boot per speed (own process, private battery directory, pinned clock),
using the frame schedule of the former native_probe 'fieldboot' run: Continue,
open Options with buttons, check the old-save default SLOW, touch-select the
speed (not committed early), Confirm (neighbouring Options bits kept), then the
trainer's first page (54 glyphs) is printed with no harness checkpoint.

The original printer (reserved value 3 written after Confirm) is the baseline.
Requires per mode: the design glyph budget and a valid stop reason for every
native task (text_speed_checks.task_errors, including the VCOUNT frame rule);
completed pixels and glyph layout identical to the original; total printing
frames original > SLOW >= MEDIUM >= FAST, where a tie is allowed only if the
faster speed stopped on the frame limit (text_speed_checks.frame_order); and no
speed may drop more than one frame more than the original while printing
(dropped frame = a frame in which the printer's task did not run).
"""
import argparse
import hashlib
import json
import subprocess
import sys

from gate_common import (CLOCK, PrinterTrace, ROOT, add_arguments, attach_probe, digest, identity, inputs_unchanged,
                         itcm_errors, load_expected_payload, memory_errors, memory_summary, require, resolve)
import text_speed_checks as checks

NAMES = ('slow', 'medium', 'fast', 'original')


def child(args):
    from emu_harness import Harness
    payload = load_expected_payload(args)
    mode = args.mode
    result = {'status': 'failed', 'mode': mode, 'rom_sha256': digest(args.rom), 'errors': []}
    errors = result['errors']
    try:
        with Harness(args.rom, args.save, out=args.out, verbose=False, rtc=CLOCK) as h:
            h.set_clock(CLOCK)
            h.step(2400)
            h.press('START', after=400)
            for _ in range(2):
                h.press('A', after=300)
            require(h.run_until(lambda h: h.in_field(), 600, every=10), 'did not reach the field')
            start = itcm_errors(h, payload)
            require(not start, f'ITCM at start: {start}')
            probe = attach_probe(h)
            menus = []
            h.on_exec(payload['symbols']['load_rows'] & ~1, lambda h: menus.append(h.reg.r0))
            trace = PrinterTrace(h, payload, font=1, probe=probe)

            def row6():
                d = menus[-1]
                return {'count': h.u16(d + 0x84 + 6 * 84), 'value': h.u16(d + 0x86 + 6 * 84),
                        'saved': h.u16(h.u32(d + 0x24))}
            h.press('X', after=90)
            for key in ('RIGHT', 'DOWN', 'DOWN'):
                h.press(key, after=30)
            h.press('A', after=300)
            require(menus, 'Options did not open')
            opened = row6()
            require((opened['count'], opened['value']) == (3, 0), f'old-save default changed: {opened}')
            ui = 1 if mode == checks.ORIGINAL else mode
            h.touch((130, 177, 227)[ui], 152, frames=6, after=60)
            selected = row6()
            require(selected['value'] == ui, 'touch selection missed')
            require(selected['saved'] == opened['saved'], 'selection committed early')
            h.touch(149, 180, frames=6, after=300)
            expected = (opened['saved'] & ~12) | (ui << 2)
            require(h.u16(h.array(1)) == expected, 'Confirm lost neighbouring options')
            if mode == checks.ORIGINAL:
                expected |= 12          # controlled: reserved value -> original printer task
                h.w16(h.array(1), expected)
            mark, task_mark = trace.mark(), trace.task_mark()
            h.press('A', after=234)
            glyphs = trace.since(mark)
            require(len(glyphs) == 54, f'expected the 54-glyph trainer page, observed {len(glyphs)}')
            h.screenshot('page1')
            crop = h.emu.screenshot().crop((8, 153, 236, 182)).tobytes()
            require(checks.nonblank(crop), 'blank message window')
            summary, cadence_errors = checks.cadence(mode, glyphs)
            errors.extend(cadence_errors)
            tasks = trace.tasks_since(task_mark, set(trace.printers_since(mark)))
            stops, stop_errors = checks.task_errors(mode, tasks)
            errors.extend(stop_errors)
            frames = sorted({f for _, _, f in glyphs})
            result.update(options=expected, glyphs=len(glyphs), cadence=summary, stops=stops,
                          frame_span=frames[-1] - frames[0], lag_frames=trace.lag(mark),
                          layout=trace.layout(mark), pixels=hashlib.sha256(crop).hexdigest())
            h.press('A', after=234)
            require(trace.mark() > mark + 54, 'second page did not start')
            result['memory'] = memory_summary(probe)
            errors.extend(memory_errors(result['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
            if not errors:
                result['status'] = 'passed'
    except BaseException as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(result, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument('--mode', type=int, choices=range(4))
    args = resolve(parser, parser.parse_args())
    if args.mode is not None:
        child(args)
        return
    payload = load_expected_payload(args)
    summary = {'status': 'failed', **identity(args, payload), 'modes': {}, 'errors': []}
    try:
        for mode, name in enumerate(NAMES):
            out = args.out / name
            command = [sys.executable, __file__, '--rom', str(args.rom), '--save', str(args.save),
                       '--out', str(out), '--mode', str(mode)]
            command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
            with (args.out / f'{name}.log').open('w') as log:
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
            r = json.loads((out / 'report.json').read_text())
            summary['modes'][name] = {k: r.get(k) for k in ('status', 'glyphs', 'frame_span', 'lag_frames',
                                                            'options', 'stops', 'errors')}
            summary['modes'][name]['per_task'] = (r.get('cadence') or {}).get('per_task')
            if code or r['status'] != 'passed':
                summary['errors'].append(f'{name}: {r.get("errors")}')
            else:
                summary['modes'][name].update(layout=r['layout'], pixels=r['pixels'])
        if not summary['errors']:
            modes = summary['modes']
            base = modes['original']
            for name in NAMES[:3]:
                if modes[name]['pixels'] != base['pixels']:
                    summary['errors'].append(f'{name}: completed dialogue pixels differ from the original printer')
                if modes[name]['layout'] != base['layout']:
                    summary['errors'].append(f'{name}: glyph layout differs from the original printer')
            spans = {m: modes[n]['frame_span'] for m, n in enumerate(NAMES)}
            lag = {m: modes[n]['lag_frames'] for m, n in enumerate(NAMES)}
            limited = {m: (modes[n]['stops'] or {}).get('frame', 0) for m, n in enumerate(NAMES)}
            order, notes = checks.frame_order(spans, limited)
            summary['errors'] += [f'frame order: {e}' for e in order]
            summary['errors'] += [f'dropped frames: {e}' for e in checks.lag_errors(lag)]
            summary['frame_limited_ties'] = notes
        if not inputs_unchanged(summary):
            summary['errors'].append('source input changed')
        if not summary['errors']:
            summary['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(summary, indent=2, default=str))
    if summary['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, summary['errors'])))


if __name__ == '__main__':
    main()
