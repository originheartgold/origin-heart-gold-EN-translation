"""Unit tests for the text-speed release runner's fail-closed rules (no emulator)."""
from pathlib import Path
import os
import sys
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research/text_speed'))
import fault_fixture  # noqa: E402
import gate_common  # noqa: E402
import validate_release  # noqa: E402


def row(status, errors=None):
    out = {'status': status}
    if errors is not None:
        out['errors'] = errors
    return out


class Require(unittest.TestCase):
    def test_require_raises_with_message(self):
        gate_common.require(True, 'unused')
        with self.assertRaisesRegex(gate_common.GateError, 'boom'):
            gate_common.require(False, 'boom')


class TraceMetrics(unittest.TestCase):
    def trace(self, tasks, glyphs=()):
        t = gate_common.PrinterTrace.__new__(gate_common.PrinterTrace)
        t.tasks, t.glyphs = tasks, list(glyphs)
        t.task_frames = {}
        for rec in tasks:
            t.task_frames.setdefault(rec['printer'], set()).add(rec['frame'])
        return t

    def test_control_latency(self):
        R, G = ('render',), ('glyph', 0x12B)
        tasks = [{'printer': 1, 'frame': 10, 'events': [R, G, ('check', 160), R, G]},
                 {'printer': 1, 'frame': 11, 'events': [R]},            # page prompt one task later
                 {'printer': 2, 'frame': 11, 'events': [R]},            # another printer is ignored
                 {'printer': 1, 'frame': 13, 'events': [R, G, R]}]    # batching ran into the control
        self.assertEqual(self.trace(tasks).control_latencies(0, {1}), [1, 0])

    def test_lag_counts_frames_without_the_printers_task(self):
        tasks = [{'printer': 1, 'frame': f, 'events': []} for f in (10, 11, 13, 15)]
        glyphs = [(1, None, f, 0, 0) for f in (10, 13, 15)]
        self.assertEqual(self.trace(tasks, glyphs).lag(0), 2)


class Faults(unittest.TestCase):
    def test_every_fault_declares_known_gates_or_dead_code(self):
        class A:
            rom = save = Path('x.nds')
            fault_payload = None
        known = set(validate_release.gates(A, Path('/tmp/out')))
        for name, spec in fault_fixture.FAULTS.items():
            self.assertTrue(spec.get('gates') or spec.get('dead'), name)
            self.assertFalse(spec.get('gates') and spec.get('dead'), name)
            self.assertLessEqual(set(spec.get('gates', {})), known, name)
            for address, before, after in spec['edits']:
                self.assertLessEqual(len(after), len(before), name)

    def test_verdict_needs_every_declared_gate_to_fail_for_its_reason(self):
        fault = {'name': 'fast-budget'}
        gates = {g: row('failed', [f'x: {text} (from the check)'])
                 for g, text in fault_fixture.FAULTS['fast-budget']['gates'].items()}
        self.assertEqual(validate_release.fault_verdict(fault, gates)[0], 'fault-detected')
        missing = dict(gates)
        missing.pop('corpus')
        self.assertEqual(validate_release.fault_verdict(fault, missing)[0], 'fault-missed')
        passed = dict(gates, corpus=row('passed'))
        self.assertEqual(validate_release.fault_verdict(fault, passed)[0], 'fault-missed')
        crashed = dict(gates, corpus={'status': 'failed', 'reason': 'timeout'})
        self.assertEqual(validate_release.fault_verdict(fault, crashed)[0], 'fault-missed')
        other = dict(gates, corpus=row('failed', ['pixels differ']))
        self.assertEqual(validate_release.fault_verdict(fault, other)[0], 'fault-missed')

    def test_every_detection_names_a_check(self):
        import text_speed_checks
        for name, spec in fault_fixture.FAULTS.items():
            for gate, text in spec.get('gates', {}).items():
                self.assertIsInstance(text, str, (name, gate))
                self.assertTrue(text.strip(), (name, gate))
            self.assertLessEqual(set(spec.get('checker', {})), text_speed_checks.FAULT_KNOBS, name)

    def test_unexpected_exceptions_never_count_as_detection(self):
        fault = {'name': 'commit-noop'}
        text = fault_fixture.FAULTS['commit-noop']['gates']['options']
        gates = {g: row('failed', [f'GateError: {t} (Options 0x200, expected 0x204)'])
                 for g, t in fault_fixture.FAULTS['commit-noop']['gates'].items()}
        self.assertEqual(validate_release.fault_verdict(fault, gates)[0], 'fault-detected')
        crashed = dict(gates, options=row('failed', [f'KeyError: {text}']))
        self.assertEqual(validate_release.fault_verdict(fault, crashed)[0], 'fault-missed')
        nested = dict(gates, options=row('failed', [f'mode 1 child failed: ["RuntimeError: {text}"]']))
        self.assertEqual(validate_release.fault_verdict(fault, nested)[0], 'fault-missed')
        with unittest.mock.patch.dict(fault_fixture.FAULTS, {'commit-noop': dict(
                fault_fixture.FAULTS['commit-noop'], gates={'options': None})}):
            self.assertEqual(validate_release.fault_verdict(fault, gates)[0], 'fault-missed')

    def test_dead_code_fault_is_reported_as_such(self):
        self.assertEqual(validate_release.fault_verdict({'name': 'no-state-stop'}, {})[0], 'fault-dead-code')


class Isolation(unittest.TestCase):
    def test_gates_run_isolated_with_a_clean_environment(self):
        class A:
            rom = save = Path('x.nds')
            fault_payload = None
        commands = validate_release.gates(A, Path('/tmp/out'))
        self.assertIn('scenes', commands)
        for name, (command, _) in commands.items():
            self.assertEqual(command[1], '-I', name)
        with unittest.mock.patch.dict(os.environ, {'PYTHONPATH': '/x', 'PYTHONSTARTUP': '/y', 'PATH': '/bin',
                                                   'EMU_HARNESS_MAX_EMULATORS': '3'}):
            env = validate_release.gate_env(Path('/tmp/w'))
        self.assertFalse([k for k in env if k.startswith('PYTHON')])
        self.assertEqual(env['EMU_HARNESS_WAIT_LOG'], '/tmp/w')
        self.assertEqual(env['EMU_HARNESS_MAX_EMULATORS'], '3')

    def test_busy_scenes_are_in_the_scene_gate(self):
        import scene_pacing
        self.assertLessEqual(set(scene_pacing.BUSY), set(scene_pacing.SCENES))
        for name in ('goldenrod-dept-6f', 'celadon-gym', 'route1-idle', 'trainer-after-options'):
            self.assertIn(name, scene_pacing.BUSY)


if __name__ == '__main__':
    unittest.main()


class FieldRate(unittest.TestCase):
    """field_rate.judge: the catch-up gate's cross-run rules (synthetic scene reports)."""

    def report(self, on_fpg=0.99, off_fpg=2.0, tasks=200, overruns=0, idle=(300, 300), runs=None):
        def run(fpg, passes):
            text = {'glyphs': 92, 'pages': 2, 'layout': [(0, 0)], 'windows': ['aa'], 'fpg': fpg, 'passes': 400,
                    'queue_runs': 400 if runs is None else runs, 'elapsed': {}, 'other_tasks': {}, 'slot_errors': []}
            return {'idle': {'passes': passes, 'queue_runs': passes, 'other_tasks': {}, 'elapsed': {}},
                    'text': text}
        return {'on': run(on_fpg, idle[1]), 'off': run(off_fpg, idle[0]),
                'catch_up': {'tasks': tasks, 'overruns': overruns, 'late_passes': tasks, 'decisions': tasks}}

    def test_clean_scene_passes(self):
        import field_rate
        self.assertEqual(field_rate.judge(self.report()), [])
        self.assertEqual(field_rate.judge(self.report(on_fpg=0.99, off_fpg=1.0, tasks=0)), [])   # 60 fps scene

    def test_each_rule_fails(self):
        import field_rate
        self.assertIn('frames per glyph', ' '.join(field_rate.judge(self.report(on_fpg=1.9))))
        self.assertIn('idle', ' '.join(field_rate.judge(self.report(idle=(300, 299)))))
        self.assertIn('dropped frames', ' '.join(field_rate.judge(self.report(overruns=1))))
        self.assertIn('ran no catch-up task', ' '.join(field_rate.judge(self.report(tasks=0))))
        self.assertIn('once per pass', ' '.join(field_rate.judge(self.report(runs=401))))
        r = self.report()
        r['on']['text']['windows'] = ['bb']
        self.assertIn('pixels differ', ' '.join(field_rate.judge(r)))
        r = self.report()
        r['on']['text']['layout'] = [(1, 0)]
        self.assertIn('layout', ' '.join(field_rate.judge(r)))

    def test_gate_and_fault_are_wired(self):
        class A:
            rom = save = Path('x.nds')
            fault_payload = None
        self.assertIn('field-rate', validate_release.gates(A, Path('/tmp/out')))
        spec = fault_fixture.FAULTS['no-catch-up']
        self.assertEqual(spec['gates'], {'field-rate': 'frames per glyph'})
        self.assertEqual(spec['checker'], {'NO_CATCH_UP': True})
