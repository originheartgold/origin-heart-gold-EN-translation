"""Run every text-speed runtime gate on one candidate ROM and write one bound report.

    python work/research/text_speed/validate_release.py --rom CANDIDATE.nds \\
        --save trainer.sav --out work/build/text-speed/<run> [--jobs 4]

Each gate runs as its own process (own DeSmuME battery directory, own output
directory under --out) with a timeout; a timeout, crash, missing report or a
report without status "passed" fails that gate. The summary report.json binds
the run to the ROM, battery and payload SHA-256 and the git commit, and lists
each gate's status and key observations. Status is "passed" only if every gate
passed. Also runs text_speed_patch.py --check-payload (payload recompiles).

Fail closed: refuses to run under python -O; refuses a dirty work tree (any
change or untracked file in `git status --porcelain --untracked-files=all`)
unless --allow-dirty, which can only produce status "passed-not-releasable";
the tree and HEAD are checked again at the end. Time a gate spends waiting for
a free emulator slot (emu_harness MAX_EMULATORS) does not count against its
timeout.

--fault-payload PAYLOAD runs the gates on a fault_fixture.py ROM instead. Each
fault declares which gates must catch it and what their errors must say
(fault_fixture.FAULTS); status is "fault-detected" only if every declared gate
failed that way, else "fault-missed". Fault reports are never release evidence.
"""
import argparse
import os
import signal
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

if sys.flags.optimize:
    raise SystemExit('validate_release.py refuses to run with python -O (sys.flags.optimize is set)')

from gate_common import ROOT, add_arguments, digest, identity, inputs_unchanged, load_expected_payload, resolve

HERE = Path(__file__).resolve().parent
TIMEOUT = 3600          # seconds of running time per gate, excluding waits for an emulator slot


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
        'printers': plain('printer_smoke.py', 'printers'),
    }


def observations(name, r):
    """A few key numbers per gate for the summary (full detail stays in each report)."""
    try:
        if name == 'corpus' or name == 'controls':
            out = {'print_frames': {o['message']: o['print_frames'] for o in r.get('speed_order', [])},
                   'lag_frames': {o['message']: o['lag_frames'] for o in r.get('speed_order', [])},
                   'control_latency': {o['message']: o['control_latency'] for o in r.get('speed_order', [])},
                   'frame_limited_ties': r.get('frame_limited_ties'),
                   'max_tasks_per_frame': r.get('max_tasks_per_frame')}
            if name == 'controls':
                out['explicit_pause_frames'] = r.get('explicit_pause_frames')
            out['heap_checks'] = [m.get('memory', {}).get('heap_checks') for m in r.get('modes', [])]
            return out
        if name == 'battle':
            return {'segments': [{'segment': s['segment'], 'frames': {m: run['frames'] for m, run in s['runs'].items()},
                                  'order': s.get('order'),
                                  'messages': [(x['text'][:32], x['glyphs'], x['print_frames'], x['after_last'],
                                                x.get('to_free')) for x in s['runs']['3']['messages']]}
                                 for s in r['segments']],
                    'max_tasks_per_frame': r.get('max_tasks_per_frame'), 'heap_checks': r['memory']['heap_checks']}
        if name == 'fallbacks':
            return {k: {'span': v['span'], 'lag': v['lag_frames'], 'stops': v['stops'].get('reasons')}
                    for k, v in r['cases'].items()}
        if name == 'callbacks':
            return {k: {'glyphs': v['glyph_count'], 'page2_latency': v.get('page2_latency'),
                        'per_task': v.get('cadence', {}).get('per_task'),
                        'stops': (v.get('stops') or {}).get('reasons')} for k, v in r['cases'].items()}
        if name == 'natural-dialogue':
            return {n: {k: m.get(k) for k in ('frame_span', 'lag_frames', 'stops', 'per_task')}
                    for n, m in r['modes'].items()} | {'frame_limited_ties': r.get('frame_limited_ties')}
        if name == 'printers':
            return {s['screen']: {k: s.get(k) for k in ('batched', 'async_starts', 'identical')}
                    for s in r.get('screens', [])}
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
    """Run one gate; its timeout counts running time only, not waits for an emulator slot."""
    from emu_harness import slot_wait_seconds
    if report_path.exists():
        report_path.unlink()
    waits = log.with_suffix('.slot-waits')
    waits.unlink(missing_ok=True)
    env = dict(os.environ, EMU_HARNESS_WAIT_LOG=str(waits))
    started = time.time()
    with log.open('w') as handle:
        # Own process group, so a timeout also stops the gate's child processes. Gates have
        # no inner timeouts: this one, which excludes slot waits, is the only one.
        proc = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
        while True:
            try:
                code = proc.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                running = time.time() - started - slot_wait_seconds(waits)
                if running > TIMEOUT:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    return {'status': 'failed', 'reason': f'timeout after {TIMEOUT}s of running time'}
    waited = round(slot_wait_seconds(waits), 1)
    if not report_path.exists():
        return {'status': 'failed', 'reason': f'exit {code}, no report', 'slot_wait_seconds': waited}
    r = json.loads(report_path.read_text())
    status = 'passed' if code == 0 and r.get('status') == 'passed' else 'failed'
    row = {'status': status, 'exit': code, 'report': str(report_path.relative_to(ROOT)),
           'slot_wait_seconds': waited}
    if status != 'passed':
        row['errors'] = r.get('errors') or f"report status {r.get('status')}"
    if name != 'new-game' and r.get('payload_sha256') is None:
        row['status'], row['reason'] = 'failed', 'report not bound to a payload'
    if r.get('warnings'):
        row['warnings'] = r['warnings']
    row['observations'] = observations(name, r)
    return row


def tree_state():
    """(HEAD, porcelain status including untracked files)."""
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True)
    status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return head.stdout.strip(), status.stdout.splitlines()


def fault_verdict(fault, gates):
    """Did every gate the fault declares fail, with the declared error text?"""
    from fault_fixture import FAULTS
    spec = FAULTS.get(fault['name'])
    if spec is None:
        return 'fault-missed', [f"unknown fault {fault['name']!r}"]
    if 'dead' in spec:
        return 'fault-dead-code', [spec['dead']]
    problems = []
    for gate, text in spec['gates'].items():
        row = gates.get(gate)
        if row is None:
            problems.append(f'{gate}: declared gate was not run')
        elif row['status'] != 'failed':
            problems.append(f'{gate}: passed although it must catch {fault["name"]}')
        elif 'errors' not in row:
            problems.append(f"{gate}: failed without a report ({row.get('reason')}), not by its checks")
        elif text is not None and text not in json.dumps(row['errors']):
            problems.append(f'{gate}: failed, but not with {text!r}')
    return ('fault-detected' if not problems else 'fault-missed'), problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(p)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--only', help='comma-separated gate names (default: all)')
    p.add_argument('--allow-dirty', action='store_true',
                   help='run on a modified tree; the result can only be "passed-not-releasable"')
    args = resolve(p, p.parse_args())
    payload = load_expected_payload(args)
    if args.fault_payload is None and args.rom.name.startswith('FAULT-'):
        p.error('fault fixture ROMs need --fault-payload and are never release candidates')
    head, dirty = tree_state()
    if dirty and not args.allow_dirty and args.fault_payload is None:
        p.error('work tree is not clean (git status --porcelain --untracked-files=all):\n  ' + '\n  '.join(dirty))
    summary = {'status': 'failed', **identity(args, payload), 'rom_sha256': digest(args.rom),
               'save_sha256': digest(args.save), 'git_head': head, 'git_dirty': dirty,
               'releasable': False, 'started': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'gates': {}}
    failures = []
    try:
        check = subprocess.run([sys.executable, str(ROOT / 'work/tools/text_speed_patch.py'), '--check-payload'],
                               cwd=ROOT, capture_output=True, text=True)
        summary['payload_reproduction'] = {'exit': check.returncode, 'output': check.stdout.strip()[-400:]}
        if check.returncode != 0:
            failures.append('payload does not reproduce from source (--check-payload failed)')
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
        if not inputs_unchanged(summary):
            failures.append('source ROM or battery changed during validation')
        end_head, end_dirty = tree_state()
        summary['git_head_at_end'], summary['git_dirty_at_end'] = end_head, end_dirty
        if (end_head, end_dirty) != (head, dirty):
            failures.append('work tree or HEAD changed during validation')
        failed = sorted(n for n, g in summary['gates'].items() if g['status'] != 'passed')
        summary['failed_gates'] = failed
        summary['problems'] = failures
        summary['warnings'] = {n: g['warnings'] for n, g in summary['gates'].items() if g.get('warnings')}
        if args.fault_payload:
            summary['status'], summary['fault_verdict'] = fault_verdict(payload['fault'], summary['gates'])
        elif failed or failures:
            summary['status'] = 'failed'
        elif args.only:
            summary['status'] = 'partial-passed'
        elif dirty or end_dirty:
            summary['status'] = 'passed-not-releasable'
        else:
            summary['status'], summary['releasable'] = 'passed', True
    finally:
        summary['finished'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        (args.out / 'report.json').write_text(json.dumps(summary, indent=2, default=str))
    print('status', summary['status'], 'failed', summary.get('failed_gates'), summary.get('problems') or '',
          summary.get('fault_verdict') or '')
    if summary['status'] not in ('passed', 'fault-detected', 'fault-dead-code', 'partial-passed',
                                 'passed-not-releasable'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
