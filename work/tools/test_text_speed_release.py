"""Unit tests for the text-speed release runner's fail-closed rules (no emulator)."""
from pathlib import Path
import sys
import unittest

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
        glyphs = [(1, None, None, f, 0, 0) for f in (10, 13, 15)]
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
        fault = {'name': 'slow-flat'}
        gates = {g: row('failed', ['x: stopped after 1 of 2 glyphs without a reason'])
                 for g in fault_fixture.FAULTS['slow-flat']['gates']}
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

    def test_dead_code_fault_is_reported_as_such(self):
        self.assertEqual(validate_release.fault_verdict({'name': 'no-state-stop'}, {})[0], 'fault-dead-code')


if __name__ == '__main__':
    unittest.main()
