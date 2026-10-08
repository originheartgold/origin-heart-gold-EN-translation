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
import re
import subprocess
import sys
import time

if sys.flags.optimize:
    raise SystemExit('validate_release.py refuses to run with python -O (sys.flags.optimize is set)')

import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import ROOT, add_arguments, digest, identity, inputs_unchanged, load_expected_payload, resolve
import text_speed_checks as checks  # noqa: E402  (work/tools, on the path via gate_common)

HERE = Path(__file__).resolve().parent
TIMEOUT = 3600          # seconds of running time per gate, excluding waits for an emulator slot
# Timing gates (D-2175): their verdicts compare frames, passes or latencies, so each runs once
# per input phase (gate_common.PHASES: inputs as written and one frame later), from its own
# cold boot; the gate passes only if every phase passes. Phase p > 0 writes to <name>-phase<p>.
PHASED = ('fallbacks', 'callbacks', 'corpus', 'controls', 'battle', 'natural-dialogue', 'scenes', 'field-rate')


def gates(args, out):
    """name -> [(command, report path), ...]: one run, or one per input phase for PHASED gates."""
    from gate_common import PHASES
    runs = {}
    for phase in PHASES:
        where = out if phase == 0 else out / f'phase{phase}'
        for name, run in _gates(args, where, phase, control_fixture(out)).items():
            if phase == 0 or name in PHASED:
                runs.setdefault(name, []).append(run)
    return runs


def control_fixture(out):
    """The authored control-message ROM of the controls gate: written once per run (every phase
    uses it)."""
    return out / 'controls-fixture' / 'control.nds'


def make_control_fixture(args):
    """Write control_fixture(args); returns None, or why it failed."""
    rom, out = control_fixture(args.out), args.out / 'controls-fixture.log'
    with out.open('w') as log:
        code = subprocess.run([sys.executable, '-I', str(HERE / 'control_fixture.py'), str(args.rom), str(rom)],
                              cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=gate_env(out.with_suffix('.waits')))
    return None if code.returncode == 0 and rom.exists() else f'control fixture failed (exit {code.returncode})'


def _gates(args, out, phase, control_rom):
    """name -> (command, report path) at one input phase."""
    py = [sys.executable, '-I']     # isolated: no PYTHONPATH, no user site, no script-directory injection
    rom, save = str(args.rom), str(args.save)
    fault = ['--fault-payload', str(args.fault_payload)] if args.fault_payload else []
    fault += ['--phase', str(phase)] if phase else []
    plain = lambda script, name, extra=(): ([*py, str(HERE / script), '--rom', rom, '--save', save,
                                             '--out', str(out / name), *extra, *fault], out / name / 'report.json')
    control_rom = str(control_rom)
    return {
        'options': plain('harness_options.py', 'options'),
        'music': plain('music_interaction.py', 'music'),
        'save': plain('save_persistence.py', 'save'),
        'new-game': ([*py, str(HERE / 'new_game_default.py'), '--rom', rom, '--out', str(out / 'new-game')],
                     out / 'new-game' / 'report.json'),
        'lifecycle': plain('printer_lifecycle.py', 'lifecycle'),
        'fallbacks': plain('harness_fallbacks.py', 'fallbacks'),
        'callbacks': plain('callback_regression.py', 'callbacks'),
        'corpus': plain('harness_regression.py', 'corpus'),
        'controls': ([*py, str(HERE / 'harness_regression.py'), '--controls', '--rom', control_rom, '--save', save,
                      '--out', str(out / 'controls'), *fault], out / 'controls' / 'report.json'),
        'battle': plain('battle_pacing.py', 'battle'),
        'natural-dialogue': plain('natural_dialogue.py', 'natural-dialogue'),
        'phone-call': plain('phone_call_wait.py', 'phone-call'),
        'printers': plain('printer_smoke.py', 'printers'),
        'scenes': plain('scene_pacing.py', 'scenes'),
        'field-rate': plain('field_rate.py', 'field-rate'),
    }


# Gate processes get only these variables from the caller's environment (plus the
# slot-wait log): no PYTHON* variable or other injection reaches them.
ENV_KEEP = ('PATH', 'HOME', 'USER', 'LOGNAME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE', 'EMU_HARNESS_MAX_EMULATORS')


def gate_env(waits):
    env = {k: os.environ[k] for k in ENV_KEEP if k in os.environ}
    env['EMU_HARNESS_WAIT_LOG'] = str(waits)
    return env


def observations(name, r):
    """A few key numbers per gate for the summary (full detail stays in each report)."""
    try:
        if name == 'corpus' or name == 'controls':
            out = {'print_frames': {o['message']: o['print_frames'] for o in r.get('speed_order', [])},
                   'lag_frames': {o['message']: o['lag_frames'] for o in r.get('speed_order', [])},
                   'control_latency': {o['message']: o['control_latency'] for o in r.get('speed_order', [])},
                   'capped_ties': r.get('capped_ties'),
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
            return {k: {'glyphs': v['glyph_count'], 'prompt_tasks': v.get('prompt_tasks'),
                        'accept_tasks': v.get('accept_tasks'),
                        'per_task': v.get('cadence', {}).get('per_task'),
                        'stops': (v.get('stops') or {}).get('reasons')} for k, v in r['cases'].items()}
        if name == 'natural-dialogue':
            return {n: {k: m.get(k) for k in ('frame_span', 'lag_frames', 'stops', 'per_task')}
                    for n, m in r['modes'].items()} | {'capped_ties': r.get('capped_ties')}
        if name == 'scenes':
            return {'table': r.get('table'), 'capped_ties': {n: x.get('capped_ties') for n, x in r['scenes'].items()
                                                             if x.get('capped_ties')}}
        if name == 'field-rate':
            return {'table': r.get('table')}
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
        if name == 'phone-call':
            return {n: {'flags_before_call': s.get('flags_before_call'),
                        'messages': (s.get('call') or {}).get('messages'),
                        'auto_waits': (s.get('call') or {}).get('auto_waits'),
                        'pages': [(p['glyphs'], (p.get('hold') or {}).get('glyphs'), p.get('press_latency'))
                                  for p in s.get('pages', [])],
                        'next_battle_auto': (s.get('next_battle') or {}).get('auto_wait_completions')}
                    for n, s in r['scenarios'].items()}
        if name == 'new-game':
            return [e['event'] for e in r['events']]
    except (KeyError, TypeError) as exc:
        return {'unavailable': repr(exc)}
    return {}


def mid_update_samples(directory):
    """Heap walks re-checked clean on the next frame (gate_common.attach_probe), from every
    report under a gate's output directory, without duplicates (summaries repeat children)."""
    found = {}

    def scan(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'mid_update_samples' and isinstance(value, list):
                    for sample in value:
                        found.setdefault(json.dumps(sample, sort_keys=True), sample)
                else:
                    scan(value)
        elif isinstance(node, list):
            for value in node:
                scan(value)
    for path in sorted(Path(directory).rglob('report.json')):
        try:
            scan(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
    return list(found.values())


def run_gate(name, command, report_path, log):
    """Run one gate; its timeout counts running time only, not waits for an emulator slot."""
    from emu_harness import slot_wait_seconds
    if report_path.exists():
        report_path.unlink()
    log.parent.mkdir(parents=True, exist_ok=True)
    waits = log.with_suffix('.slot-waits')
    waits.unlink(missing_ok=True)
    env = gate_env(waits)
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
    if name != 'new-game' and r.get('payload_code_sha256') is None:
        row['status'], row['reason'] = 'failed', 'report not bound to a payload'
    if r.get('warnings'):
        row['warnings'] = r['warnings']
    if r.get('overrun_budget'):
        row['overrun_budget'] = r['overrun_budget']
    row['observations'] = observations(name, r)
    row['mid_update_samples'] = mid_update_samples(report_path.parent)
    return row


def merge_phases(rows):
    """One gate row from its runs at each input phase (D-2175): passed only if every phase passed;
    errors and failure reasons are prefixed with their phase; phase 0's observations stay at the
    top level (report_summary reads them), later phases' under 'phase<p>'."""
    if len(rows) == 1:
        return rows[0]
    row = dict(rows[0])
    row['phases'] = {str(p): {k: r.get(k) for k in ('status', 'report', 'exit', 'reason', 'slot_wait_seconds')}
                     for p, r in enumerate(rows)}
    row['status'] = 'passed' if all(r['status'] == 'passed' for r in rows) else 'failed'
    errors, reasons = [], []
    for p, r in enumerate(rows):
        if r['status'] == 'passed':
            continue
        if 'errors' in r:
            listed = r['errors'] if isinstance(r['errors'], list) else [r['errors']]
            errors += [f'phase {p}: {e}' for e in listed]
        else:
            reasons.append(f"phase {p}: {r.get('reason')}")
    row.pop('errors', None)
    row.pop('reason', None)
    if errors:
        row['errors'] = errors
    if reasons:
        row['reason'] = '; '.join(reasons)
    warnings = {str(p): r['warnings'] for p, r in enumerate(rows) if r.get('warnings')}
    row.pop('warnings', None)
    if warnings:
        row['warnings'] = warnings
    for p, r in enumerate(rows[1:], 1):
        row['observations'] = dict(row.get('observations') or {}, **{f'phase{p}': r.get('observations')})
    row['mid_update_samples'] = [s for r in rows for s in r.get('mid_update_samples', [])]
    budgets = [r['overrun_budget'] for r in rows if r.get('overrun_budget')]
    if budgets:
        row['overrun_budget'] = add_budgets(budgets)
    return row


def add_budgets(budgets):
    """Sum gate 'overrun_budget' counts (FAST printing frames, unforced overruns; D-2276)."""
    return {k: sum(b.get(k, 0) for b in budgets) for k in ('fast_frames', 'unforced_overruns')}


def tree_state():
    """(HEAD, porcelain status including untracked files)."""
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=True)
    status = subprocess.run(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    return head.stdout.strip(), status.stdout.splitlines()


# An unexpected Python exception recorded in a gate's errors ('KeyError: ...', 'RuntimeError: ...'
# up to the end of that error string) never counts as detection; GateError is how checks fail.
UNEXPECTED = re.compile(r'(?<![A-Za-z])(?!GateError\b)[A-Z][A-Za-z]*(?:Error|Exception|Interrupt)\b: [^"\\]*')


def checks_text(errors):
    """The gate's errors as one string, with unexpected exceptions removed."""
    return UNEXPECTED.sub('<exception>', json.dumps(errors))


def fault_verdict(fault, gates):
    """Did every gate the fault declares fail, with the declared error text from its checks?"""
    from fault_fixture import FAULTS
    spec = FAULTS.get(fault['name'])
    if spec is None:
        return 'fault-missed', [f"unknown fault {fault['name']!r}"]
    if 'dead' in spec:
        return 'fault-dead-code', [spec['dead']]
    problems = []
    for gate, text in spec['gates'].items():
        row = gates.get(gate)
        if not isinstance(text, str) or not text.strip():
            problems.append(f'{gate}: the fault declares no failure text (detection must name the check)')
        elif row is None:
            problems.append(f'{gate}: declared gate was not run')
        elif row['status'] != 'failed':
            problems.append(f'{gate}: passed although it must catch {fault["name"]}')
        elif 'errors' not in row:
            problems.append(f"{gate}: failed without a report ({row.get('reason')}), not by its checks")
        elif text not in checks_text(row['errors']):
            problems.append(f'{gate}: failed, but not with {text!r} from its checks')
    return ('fault-detected' if not problems else 'fault-missed'), problems


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(p)
    p.add_argument('--jobs', type=int, default=4)
    p.add_argument('--only', help='comma-separated gate names (default: all)')
    p.add_argument('--allow-dirty', action='store_true',
                   help='run on a modified tree; the result can only be "passed-not-releasable"')
    p.add_argument('--summary', action='store_true',
                   help='print the compact report_summary.py summary of report.json at the end')
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
        check = subprocess.run([sys.executable, '-I', str(ROOT / 'work/tools/text_speed_patch.py'), '--check-payload'],
                               cwd=ROOT, capture_output=True, text=True, env=gate_env(args.out / 'payload.slot-waits'))
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
        if 'controls' in selected:
            problem = make_control_fixture(args)
            if problem:
                summary['gates']['controls'] = {'status': 'failed', 'reason': problem}
                del selected['controls']
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = {name: [pool.submit(run_gate, name, cmd, path, path.parent.parent / f'{name}.log')
                              for cmd, path in runs]
                       for name, runs in selected.items()}
            for name, runs in futures.items():
                summary['gates'][name] = merge_phases([f.result() for f in runs])
                print(name, summary['gates'][name]['status'], flush=True)
        control = control_fixture(args.out)
        if control.exists():
            summary['control_fixture_sha256'] = digest(control)
        if not inputs_unchanged(summary):
            failures.append('source ROM or battery changed during validation')
        end_head, end_dirty = tree_state()
        summary['git_head_at_end'], summary['git_dirty_at_end'] = end_head, end_dirty
        if (end_head, end_dirty) != (head, dirty):
            failures.append('work tree or HEAD changed during validation')
        summary['overrun_budget'] = add_budgets([g['overrun_budget'] for g in summary['gates'].values()
                                                 if g.get('overrun_budget')])
        budget_error = checks.overrun_budget_error(summary['overrun_budget'])
        if budget_error:
            failures.append(budget_error)
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
    if args.summary:
        import report_summary
        report_summary.main(['summary', str(args.out / 'report.json')])
    if summary['status'] not in ('passed', 'fault-detected', 'fault-dead-code', 'partial-passed',
                                 'passed-not-releasable'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
