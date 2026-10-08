"""Natural trainer dialogue after choosing each speed through native Options touch input.

One cold boot per speed (own process, private battery directory, pinned clock),
using the frame schedule of the former native_probe 'fieldboot' run: Continue,
open Options with buttons, check the old-save default NORMAL, touch-select the
speed (not committed early), Confirm (neighbouring Options bits kept), then the
trainer's first page (54 glyphs) is printed with no harness checkpoint.

The original printer (unknown value 3 written after Confirm) is the baseline; its run
touches NORMAL, as the NORMAL run does, so both runs get the same input.
Requires per mode: NORMAL delegates every task to the original printer; FAST keeps
the design glyph budget and a valid stop reason for every native task, every frame
decision equal to the payload's frame model and the payload's frame state equal to
the costs the gate measured itself (text_speed_checks.task_errors,
gate_common.PrinterTrace); completed pixels and glyph layout identical to the
original; and the product rules of text_speed_checks.order_errors: NORMAL identical
to the original printer, FAST at most NORMAL's printing frames (strictly fewer where a
NORMAL frame had room for one more glyph), no more dropped frames than NORMAL
(dropped frame = a frame in which the printer's task did not run), none dropped only
because of extra glyphs.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gate_common import (CLOCK, PrinterTrace, ROOT, add_arguments, attach_probe, digest, identity,  # noqa: E402
                         inputs_unchanged, itcm_errors, judge_message, load_expected_payload, memory_errors,
                         memory_summary, require, resolve)
import text_speed_checks as checks  # noqa: E402

NAMES = {checks.NORMAL: 'normal', checks.FAST: 'fast', checks.ORIGINAL: 'original'}
TOUCH_X = {checks.NORMAL: 130, checks.FAST: 210}     # inside the TEXT SPEED touch columns


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
            require((opened['count'], opened['value']) == (2, checks.NORMAL), f'old-save default changed: {opened}')
            ui = checks.NORMAL if mode == checks.ORIGINAL else mode
            h.touch(TOUCH_X[ui], 152, frames=6, after=60)
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
            record, stops, stop_errors = judge_message(trace, mode, mark, task_mark)
            errors.extend(stop_errors)
            errors.extend(trace.state_errors)
            result.update(options=expected, glyphs=len(glyphs), cadence=summary, stops=stops, record=record,
                          frame_span=record['frames'], lag_frames=record['drops'],
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
    parser.add_argument('--mode', type=int, choices=sorted(NAMES))
    args = resolve(parser, parser.parse_args())
    if args.mode is not None:
        child(args)
        return
    payload = load_expected_payload(args)
    summary = {'status': 'failed', **identity(args, payload), 'modes': {}, 'errors': []}
    try:
        for mode, name in NAMES.items():
            out = args.out / name
            command = [sys.executable, '-I', __file__, '--rom', str(args.rom), '--save', str(args.save),
                       '--out', str(out), '--mode', str(mode)]
            command += ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
            with (args.out / f'{name}.log').open('w') as log:
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
            r = json.loads((out / 'report.json').read_text())
            summary['modes'][name] = {k: r.get(k) for k in ('status', 'glyphs', 'frame_span', 'lag_frames',
                                                            'options', 'stops', 'record', 'errors')}
            summary['modes'][name]['per_task'] = (r.get('cadence') or {}).get('per_task')
            if code or r['status'] != 'passed':
                summary['errors'].append(f'{name}: {r.get("errors")}')
            else:
                summary['modes'][name].update(layout=r['layout'], pixels=r['pixels'])
        if not summary['errors']:
            modes = summary['modes']
            base = modes['original']
            for name in (NAMES[checks.NORMAL], NAMES[checks.FAST]):
                if modes[name]['pixels'] != base['pixels']:
                    summary['errors'].append(f'{name}: completed dialogue pixels differ from the original printer')
                if modes[name]['layout'] != base['layout']:
                    summary['errors'].append(f'{name}: glyph layout differs from the original printer')
            order, notes = checks.order_errors({m: modes[n]['record'] for m, n in NAMES.items()})
            summary['errors'] += [f'frame order: {e}' for e in order]
            summary['capped_ties'] = notes
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
