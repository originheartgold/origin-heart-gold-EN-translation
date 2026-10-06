"""Run every text-speed runtime gate on one candidate ROM and write one bound report.

    python work/research/text_speed/validate_release.py --rom CANDIDATE.nds \\
        --save trainer.sav --out work/build/text-speed/<run> [--jobs 4]

Each gate runs as its own process (own DeSmuME battery directory, own output
directory under --out) with a timeout; a timeout, crash, missing report or a
report without status "passed" fails that gate. The summary report.json binds
the run to the ROM, battery and payload SHA-256 and the git commit, and lists
each gate's status and key observations. Status is "passed" only if every gate
passed. Also runs text_speed_patch.py --check-payload (payload recompiles).

--fault-payload PAYLOAD runs the same gates on a fault_fixture.py ROM instead;
the summary then lists which gates detected the fault (status "fault-detected"
if at least one did) and is never release evidence.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from gate_common import ROOT, add_arguments, digest, identity, inputs_unchanged, load_expected_payload, resolve

HERE = Path(__file__).resolve().parent
TIMEOUT = 3600


def gates(args, out):
    """name -> (command, report path)."""
    py = sys.executable
    rom, save = str(args.rom), str(args.save)
    fault = ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
    plain = lambda script, name, extra=(): ([py, str(HERE / script), '--rom', rom, '--save', save,
                                             '--out', str(out / name), *extra, *fault], out / name / 'report.json')
    control_rom = out / 'controls-fixture' / 'control.nds'
    return {
        'options': plain('harness_options.py', 'options'),
        'music': plain('music_interaction.py', 'music'),
        'save': plain('save_persistence.py', 'save'),
        'new-game': ([py, str(HERE / 'new_game_default.py'), '--rom', rom, '--out', str(out / 'new-game')],
                     out / 'new-game' / 'report.json'),
        'lifecycle': plain('printer_lifecycle.py', 'lifecycle'),
        'fallbacks': plain('harness_fallbacks.py', 'fallbacks'),
        'callbacks': plain('callback_regression.py', 'callbacks'),
        'corpus': plain('harness_regression.py', 'corpus'),
        'controls': ([py, '-c', ';'.join([
            'import subprocess,sys',
            f'subprocess.run([sys.executable,{str(HERE / "control_fixture.py")!r},{rom!r},{str(control_rom)!r}],check=True)',
            f'sys.exit(subprocess.run([sys.executable,{str(HERE / "harness_regression.py")!r},"--controls","--rom",'
            f'{str(control_rom)!r},"--save",{save!r},"--out",{str(out / "controls")!r}]+{fault!r}).returncode)'])],
            out / 'controls' / 'report.json'),
        'battle': plain('battle_pacing.py', 'battle'),
        'natural-dialogue': plain('natural_dialogue.py', 'natural-dialogue'),
    }


def observations(name, r):
    """A few key numbers per gate for the summary (full detail stays in each report)."""
    try:
        if name == 'corpus' or name == 'controls':
            out = {'print_frames': {o['message']: o['print_frames'] for o in r.get('speed_order', [])},
                   'max_tasks_per_frame': r.get('max_tasks_per_frame')}
            if name == 'controls':
                out['explicit_pause_frames'] = r.get('explicit_pause_frames')
            out['heap_checks'] = [m.get('memory', {}).get('heap_checks') for m in r.get('modes', [])]
            return out
        if name == 'battle':
            return {'segments': [{'segment': s['segment'], 'frames': {m: run['frames'] for m, run in s['runs'].items()},
                                  'messages': [(x['text'][:32], x['glyphs'], x['print_frames'], x['after_last'])
                                               for x in s['runs']['3']['messages']]} for s in r['segments']],
                    'max_tasks_per_frame': r.get('max_tasks_per_frame'), 'heap_checks': r['memory']['heap_checks']}
        if name == 'fallbacks':
            return {k: v['span'] for k, v in r['cases'].items()}
        if name == 'callbacks':
            return {k: {'glyphs': v['glyph_count'], 'page2_latency': v.get('page2_latency'),
                        'per_task': v.get('cadence', {}).get('per_task')} for k, v in r['cases'].items()}
        if name == 'natural-dialogue':
            return r['modes']
        if name == 'lifecycle':
            return {k: r.get(k) for k in ('messages', 'constructors', 'reused_allocations', 'live_after',
                                          'heap_idle_spread')}
        if name == 'options':
            return {'checks': len(r['checks']), 'labels': [x['case'] for x in r.get('labels', [])],
                    'heap_checks': r['memory']['heap_checks']}
        if name == 'music':
            return {'combinations': len(r['cross_product']), 'getter_checks': r['getter_checks']}
        if name == 'save':
            return r['modes']
        if name == 'new-game':
            return [e['event'] for e in r['events']]
    except (KeyError, TypeError) as exc:
        return {'unavailable': repr(exc)}
    return {}


def run_gate(name, command, report_path, log):
    if report_path.exists():
        report_path.unlink()
    try:
        with log.open('w') as handle:
            code = subprocess.run(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT,
                                  timeout=TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        return {'status': 'failed', 'reason': f'timeout after {TIMEOUT}s'}
    if not report_path.exists():
        return {'status': 'failed', 'reason': f'exit {code}, no report'}
    r = json.loads(report_path.read_text())
    status = 'passed' if code == 0 and r.get('status') == 'passed' else 'failed'
    row = {'status': status, 'exit': code, 'report': str(report_path.relative_to(ROOT))}
    if status != 'passed':
        row['errors'] = r.get('errors') or f"report status {r.get('status')}"
    if name != 'new-game' and r.get('payload_sha256') is None:
        row['status'], row['reason'] = 'failed', 'report not bound to a payload'
    if r.get('warnings'):
        row['warnings'] = r['warnings']
    row['observations'] = observations(name, r)
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(p)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--only', help='comma-separated gate names (default: all)')
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    if args.fault_payload is None and args.rom.name.startswith('FAULT-'):
        p.error('fault fixture ROMs need --fault-payload and are never release candidates')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    summary = {'status': 'failed', **identity(args, payload), 'rom_sha256': digest(args.rom),
               'save_sha256': digest(args.save), 'git_head': head, 'git_dirty': dirty,
               'started': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'gates': {}}
    try:
        check = subprocess.run([sys.executable, str(ROOT / 'work/tools/text_speed_patch.py'), '--check-payload'],
                               cwd=ROOT, capture_output=True, text=True)
        summary['payload_reproduction'] = {'exit': check.returncode, 'output': check.stdout.strip()[-400:]}
        selected = gates(args, args.out)
        if args.only:
            names = args.only.split(',')
            unknown = set(names) - set(selected)
            if unknown:
                p.error(f'unknown gates {sorted(unknown)}')
            selected = {k: v for k, v in selected.items() if k in names}
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {name: pool.submit(run_gate, name, cmd, path, args.out / f'{name}.log')
                       for name, (cmd, path) in selected.items()}
            for name, future in futures.items():
                summary['gates'][name] = future.result()
                print(name, summary['gates'][name]['status'], flush=True)
        control = args.out / 'controls-fixture' / 'control.nds'
        if control.exists():
            summary['control_fixture_sha256'] = digest(control)
        assert inputs_unchanged(summary), 'source ROM or battery changed during validation'
        failed = sorted(n for n, g in summary['gates'].items() if g['status'] != 'passed')
        summary['failed_gates'] = failed
        summary['warnings'] = {n: g['warnings'] for n, g in summary['gates'].items() if g.get('warnings')}
        if args.fault_payload:
            summary['status'] = 'fault-detected' if failed else 'fault-missed'
        elif not failed and check.returncode == 0 and not args.only:
            summary['status'] = 'passed'
        elif not failed and check.returncode == 0:
            summary['status'] = 'partial-passed'
    finally:
        summary['finished'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        (args.out / 'report.json').write_text(json.dumps(summary, indent=2, default=str))
    print('status', summary['status'], 'failed', summary.get('failed_gates'))
    if summary['status'] not in ('passed', 'fault-detected', 'partial-passed'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
