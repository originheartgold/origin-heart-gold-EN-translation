"""Natural trainer dialogue after choosing each speed through native Options touch input.

One cold boot per speed (own process, private battery directory, pinned clock),
using the frame schedule of the former native_probe 'fieldboot' run: Continue,
open Options with buttons, check the old-save default SLOW, touch-select the
speed (not committed early), Confirm (neighbouring Options bits kept), then the
trainer's first page (54 glyphs) is printed with no harness checkpoint.

Requires per mode the design glyph budget per task, identical completed pixels
and glyph layout, and strictly decreasing printing frames SLOW > MEDIUM > FAST. This is an ordinary
60 fps field scene: frames in which the game skips the printer task because the
previous frame overran (lag frames) are excluded from that rule and reported; a
first-to-last span inversion that the lag explains is a warning, not a pass
silently (see text_speed_checks.speed_order_with_lag).
"""
import argparse
import hashlib
import json
import subprocess
import sys

from gate_common import (CLOCK, PrinterTrace, ROOT, add_arguments, attach_probe, digest, identity, inputs_unchanged,
                         itcm_errors, load_expected_payload, memory_errors, memory_summary, resolve)
import text_speed_checks as checks

NAMES = ('slow', 'medium', 'fast')


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
            assert h.run_until(lambda h: h.in_field(), 600, every=10), 'did not reach the field'
            start = itcm_errors(h, payload)
            assert not start, start
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
            assert menus, 'Options did not open'
            opened = row6()
            assert (opened['count'], opened['value']) == (3, 0), ('old-save default changed', opened)
            h.touch((130, 177, 227)[mode], 152, frames=6, after=60)
            selected = row6()
            assert selected['value'] == mode, 'touch selection missed'
            assert selected['saved'] == opened['saved'], 'selection committed early'
            h.touch(149, 180, frames=6, after=300)
            expected = (opened['saved'] & ~12) | (mode << 2)
            assert h.u16(h.array(1)) == expected, 'Confirm lost neighbouring options'
            mark = trace.mark()
            h.press('A', after=234)
            glyphs = trace.since(mark)
            assert len(glyphs) == 54, f'expected the 54-glyph trainer page, observed {len(glyphs)}'
            h.screenshot('page1')
            crop = h.emu.screenshot().crop((8, 153, 236, 182)).tobytes()
            assert checks.nonblank(crop), 'blank message window'
            summary, cadence_errors = checks.cadence(mode, glyphs)
            errors.extend(cadence_errors)
            frames = sorted({f for _, _, f in glyphs})
            result.update(options=expected, glyphs=len(glyphs), cadence=summary,
                          frame_span=frames[-1] - frames[0],
                          lag_frames=sum(b - a - 1 for a, b in zip(frames, frames[1:])),
                          layout=trace.layout(mark), pixels=hashlib.sha256(crop).hexdigest())
            h.press('A', after=234)
            assert trace.mark() > mark + 54, 'second page did not start'
            result['memory'] = memory_summary(probe)
            errors.extend(memory_errors(result['memory']))
            errors.extend(f'end of session: {e}' for e in itcm_errors(h, payload))
            assert not errors, errors
            result['status'] = 'passed'
    except BaseException as exc:
        if str(exc) != str(errors):
            errors.append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (args.out / 'report.json').write_text(json.dumps(result, indent=2, default=str))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    parser.add_argument('--mode', type=int, choices=range(3))
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
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900).returncode
            r = json.loads((out / 'report.json').read_text())
            summary['modes'][name] = {k: r.get(k) for k in ('status', 'glyphs', 'frame_span', 'lag_frames',
                                                            'options', 'errors')}
            summary['modes'][name]['per_task'] = (r.get('cadence') or {}).get('per_task')
            if code or r['status'] != 'passed':
                summary['errors'].append(f'{name}: {r.get("errors")}')
            else:
                summary['modes'][name].update(layout=r['layout'], pixels=r['pixels'])
        if not summary['errors']:
            modes = summary['modes']
            if not modes['slow']['pixels'] == modes['medium']['pixels'] == modes['fast']['pixels']:
                summary['errors'].append('completed dialogue pixels differ between speeds')
            if not modes['slow']['layout'] == modes['medium']['layout'] == modes['fast']['layout']:
                summary['errors'].append('glyph layout differs between speeds')
            spans = {m: modes[n]['frame_span'] for m, n in enumerate(NAMES)}
            lag = {m: modes[n]['lag_frames'] for m, n in enumerate(NAMES)}
            order, summary['warnings'] = checks.speed_order_with_lag(spans, lag)
            summary['errors'] += [f'frame order: {e}' for e in order]
        assert inputs_unchanged(summary), 'source input changed'
        if not summary['errors']:
            summary['status'] = 'passed'
    finally:
        (args.out / 'report.json').write_text(json.dumps(summary, indent=2, default=str))
    if summary['status'] != 'passed':
        raise SystemExit('\n'.join(map(str, summary['errors'])))


if __name__ == '__main__':
    main()
