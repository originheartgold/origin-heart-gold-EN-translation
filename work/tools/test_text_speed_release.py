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


class HeapMidUpdate(unittest.TestCase):
    """attach_probe's re-walk (gate_common.heap_frame): only a failure inside heap-list code
    is walked again, and only a clean re-walk turns it into a recorded sample."""
    IN, OUT = 0x020B4428, 0x020D2D28          # RemoveMBlock between its link stores; elsewhere
    BAD = 'heap 5 (022C0E70): free block at 022F363C has a broken back link'

    def run_frames(self, walks, pcs, start=10):
        class P:
            corrupt = None
            heap_checks = 0
        probe, pending = P(), []
        probe.mid_update_samples = []
        results = iter(walks)

        def walk():
            probe.heap_checks += 1
            return next(results)
        probe.heap_walk = walk
        for i, pc in enumerate(pcs):
            gate_common.heap_frame(probe, pending, start + i, pc)
        return probe, pending

    def test_transient_in_heap_code_passes_with_a_recorded_sample(self):
        probe, pending = self.run_frames([self.BAD, None], [self.IN, self.OUT])
        self.assertIsNone(probe.corrupt)
        self.assertEqual(probe.mid_update_samples, [{'frame': 10, 'pc': hex(self.IN),
                                                     'heap': 'heap 5 (022C0E70)', 'message': self.BAD}])
        self.assertEqual((probe.heap_checks, pending), (2, []))

    def test_persistent_failure_fails(self):
        probe, _ = self.run_frames([self.BAD, self.BAD], [self.IN, self.IN])
        self.assertEqual(probe.corrupt, (10, self.BAD))
        self.assertEqual(probe.mid_update_samples, [])

    def test_failure_outside_heap_code_fails(self):
        probe, pending = self.run_frames([self.BAD], [self.OUT])
        self.assertEqual(probe.corrupt, (10, self.BAD))
        self.assertEqual((probe.mid_update_samples, pending), ([], []))
        for pc in (0x020B440B, 0x020B4AE8, 0x020B4684):     # just outside the reviewed routines
            self.assertFalse(gate_common.in_heap_list_code(pc), hex(pc))

    def test_run_ending_before_the_rewalk_fails(self):
        probe, pending = self.run_frames([self.BAD], [self.IN])
        probe.mid_update_pending = pending
        for key in gate_common.MEMORY_KEYS:
            if not hasattr(probe, key):
                setattr(probe, key, [])
        self.assertEqual(gate_common.memory_summary(probe)['corrupt'], (10, self.BAD))

    def test_routines_are_rederived_from_the_rom(self):
        rom = os.environ.get('TEXT_SPEED_TEST_ROM')
        if not rom:
            self.skipTest('TEXT_SPEED_TEST_ROM not set')
        import ndspy.rom
        main = bytes(ndspy.rom.NintendoDSRom.fromFile(rom).loadArm9().sections[0].data)
        self.assertEqual([(lo, hi) for lo, hi, _ in gate_common.HEAP_LIST_CODE],
                         [routine_extent(main, lo) for lo, _, _ in gate_common.HEAP_LIST_CODE])
        # Every call of the three list helpers in the module comes from a listed routine.
        helpers = [lo for lo, _, _ in gate_common.HEAP_LIST_CODE[:3]]
        calls = arm_calls(main, 0x020B3C00, 0x020B5800, helpers)
        self.assertTrue(calls)
        self.assertTrue(all(gate_common.in_heap_list_code(a) for a in calls), [hex(a) for a in calls])


def arm_instructions(main, lo, hi):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True
    return md, md.disasm(main[lo - 0x02000000:hi - 0x02000000], lo)


def arm_calls(main, lo, hi, targets):
    _, ins = arm_instructions(main, lo, hi)
    return [i.address for i in ins if i.mnemonic == 'bl' and int(i.op_str[1:], 16) in targets]


def routine_extent(main, entry):
    """[start, end) of an ARM routine: fall-through and in-routine branches until every path
    returns, plus PC-relative literal pools."""
    import capstone
    md, _ = arm_instructions(main, entry, entry + 4)
    seen, todo, end = set(), [entry], entry
    while todo:
        a = todo.pop()
        while a not in seen:
            seen.add(a)
            i = next(md.disasm(main[a - 0x02000000:a - 0x02000000 + 4], a))
            end = max(end, a + 4)
            if i.mnemonic.startswith('ldr') and '[pc' in i.op_str:
                end = max(end, a + 8 + int(i.op_str.split('#')[-1].rstrip(']'), 16) + 4)
            unconditional = i.cc in (0, capstone.arm.ARM_CC_AL)
            if (i.mnemonic.startswith('b') and i.mnemonic not in ('bl', 'blx', 'bic', 'bics', 'bx')
                    and i.op_str.startswith('#')):
                todo.append(int(i.op_str[1:], 16))
                if unconditional:
                    break
            if unconditional and ((i.mnemonic.startswith(('pop', 'ldm')) and 'pc' in i.op_str)
                                  or (i.mnemonic == 'bx' and i.op_str == 'lr')):
                break
            a += 4
    return entry, end


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
            for address, before, after, *where in spec['edits']:
                self.assertIn(where, ([], [fault_fixture.GEAR]), name)
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

    def test_phone_call_scenario_errors_reach_the_gate(self):
        import phone_call_wait
        child = {'status': 'failed', 'errors': ['page 1 advanced without input during the 600-frame hold']}
        errors = phone_call_wait.scenario_errors('battle-fast', 1, child)
        self.assertEqual(errors, ['battle-fast: page 1 advanced without input during the 600-frame hold'])
        self.assertEqual(phone_call_wait.scenario_errors('control', 0, {'status': 'passed', 'errors': []}), [])
        self.assertTrue(phone_call_wait.scenario_errors('control', 1, {'status': 'passed', 'errors': []}))
        fault = {'name': 'no-call-redirect'}
        self.assertEqual(validate_release.fault_verdict(fault, {'phone-call': row('failed', errors)})[0],
                         'fault-detected')
        # no inner timeout: it counted emulator-slot waits and, when it fired, lost every scenario
        source = Path(phone_call_wait.__file__).read_text()
        self.assertNotIn('timeout=', source)

    def test_model_matched_faults_carry_their_model_in_the_payload(self):
        import json
        import tempfile
        import text_speed_checks
        spec = fault_fixture.FAULTS['tail-ignored']
        payload = {'source_sha256': '', 'base': 0, 'code': '', 'symbols': {}, 'fault': {'name': 'x'},
                   'checker': spec['checker']}
        with tempfile.TemporaryDirectory(dir=gate_common.BUILD) as d:
            path = Path(d) / 'p.json'
            path.write_text(json.dumps(payload))

            class A:
                fault_payload = path
            with unittest.mock.patch.object(text_speed_checks, 'IGNORE_REST', False):
                gate_common.load_expected_payload(A)
                self.assertTrue(text_speed_checks.IGNORE_REST)

    def test_short_history_floor_is_proven_by_the_model_check(self):
        spec = fault_fixture.FAULTS['short-history-unguarded']
        # movs r1,#7 -> movs r1,#0: the short-history branch forces the rest to 0
        self.assertEqual(spec['edits'], [(0x01FF8882, bytes.fromhex('0721'), bytes.fromhex('0021'))])
        self.assertNotIn('checker', spec)       # the gates keep the real floor in their model
        self.assertEqual(spec['gates'], {'scenes': 'drew on after a frame stop'})

    def test_dead_code_fault_is_reported_as_such(self):
        self.assertEqual(validate_release.fault_verdict({'name': 'no-state-stop'}, {})[0], 'fault-dead-code')


class Isolation(unittest.TestCase):
    def test_gates_run_isolated_with_a_clean_environment(self):
        class A:
            rom = save = Path('x.nds')
            fault_payload = None
        commands = validate_release.gates(A, Path('/tmp/out'))
        self.assertIn('scenes', commands)
        for name, runs in commands.items():
            for command, _ in runs:
                self.assertEqual(command[1], '-I', name)
        with unittest.mock.patch.dict(os.environ, {'PYTHONPATH': '/x', 'PYTHONSTARTUP': '/y', 'PATH': '/bin',
                                                   'EMU_HARNESS_MAX_EMULATORS': '3'}):
            env = validate_release.gate_env(Path('/tmp/w'))
        self.assertFalse([k for k in env if k.startswith('PYTHON')])
        self.assertEqual(env['EMU_HARNESS_WAIT_LOG'], '/tmp/w')
        self.assertEqual(env['EMU_HARNESS_MAX_EMULATORS'], '3')

    def test_timing_gates_run_at_every_input_phase(self):
        """D-2175: each timing gate runs once per input phase, phase p > 0 with --phase p and its own
        output directory; the other gates run once."""
        class A:
            rom = save = Path('x.nds')
            fault_payload = None
        commands = validate_release.gates(A, Path('/tmp/out'))
        self.assertEqual(gate_common.PHASES, (0, 1))
        for name, runs in commands.items():
            if name not in validate_release.PHASED:
                self.assertEqual(len(runs), 1, name)
                self.assertNotIn('--phase', runs[0][0], name)
                continue
            self.assertEqual(len(runs), 2, name)
            self.assertNotIn('--phase', runs[0][0], name)
            self.assertEqual(runs[1][0][-2:], ['--phase', '1'], name)
            self.assertNotEqual(runs[0][1], runs[1][1], name)
        self.assertLessEqual({'callbacks', 'scenes', 'field-rate', 'natural-dialogue', 'corpus', 'battle'},
                             set(validate_release.PHASED))

    def test_phases_merge_into_one_gate_row(self):
        ok = dict(row('passed'), observations={'a': 1}, mid_update_samples=[])
        bad = dict(row('failed', ['x: drew on after a frame stop']), observations={'a': 2}, mid_update_samples=[])
        crash = {'status': 'failed', 'reason': 'timeout', 'mid_update_samples': []}
        self.assertEqual(validate_release.merge_phases([ok])['status'], 'passed')
        both = validate_release.merge_phases([ok, ok])
        self.assertEqual(both['status'], 'passed')
        self.assertEqual(both['observations'], {'a': 1, 'phase1': {'a': 1}})
        merged = validate_release.merge_phases([ok, bad])
        self.assertEqual(merged['status'], 'failed')
        self.assertEqual(merged['errors'], ['phase 1: x: drew on after a frame stop'])
        fault = {'name': 'frame-rule-ignored'}
        gates = {g: (merged if g == 'scenes' else row('failed', [f'x: {t}']))
                 for g, t in fault_fixture.FAULTS['frame-rule-ignored']['gates'].items()}
        self.assertEqual(validate_release.fault_verdict(fault, gates)[0], 'fault-detected')
        timeout = validate_release.merge_phases([crash, ok])
        self.assertEqual((timeout['status'], timeout.get('errors')), ('failed', None))
        self.assertIn('phase 0: timeout', timeout['reason'])

    def test_busy_scenes_are_in_the_scene_gate(self):
        import scene_pacing
        self.assertLessEqual(set(scene_pacing.BUSY), set(scene_pacing.SCENES))
        for name in ('goldenrod-dept-6f', 'celadon-gym', 'route1-idle', 'trainer-after-options'):
            self.assertIn(name, scene_pacing.BUSY)


if __name__ == '__main__':
    unittest.main()


class FieldRate(unittest.TestCase):
    """field_rate.judge: the catch-up gate's cross-run rules (synthetic scene reports)."""

    def report(self, on_fpg=0.99, off_fpg=2.0, tasks=200, overruns=0, idle=(300, 300), runs=None, ticks=7,
               idle_tasks=0):
        def run(fpg, passes):
            text = {'glyphs': 92, 'pages': 2, 'layout': [(0, 0)], 'windows': ['aa'], 'fpg': fpg, 'passes': 400,
                    'queue_runs': 400 if runs is None else runs, 'elapsed': {}, 'other_tasks': {}, 'slot_errors': []}
            return {'idle': {'passes': passes, 'queue_runs': passes, 'other_tasks': {}, 'elapsed': {},
                             'pass_end_ticks': ticks, 'pass_ends': passes, 'late_passes': passes // 2,
                             'printer_tasks': idle_tasks},
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
        # D-2175: idle passes are reported, not compared (the input phase decides a frame at the edge)
        self.assertEqual(field_rate.judge(self.report(idle=(342, 340))), [])
        self.assertEqual(field_rate.judge(self.report(ticks=field_rate.IDLE_TICKS)), [])
        self.assertIn('idle: pass_end took', ' '.join(field_rate.judge(self.report(ticks=field_rate.IDLE_TICKS + 1))))
        self.assertIn('printer tasks ran in pass_end without text', ' '.join(field_rate.judge(self.report(idle_tasks=1))))
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
        spec = fault_fixture.FAULTS['catch-up-idle-cost']
        self.assertEqual(spec['gates'], {'field-rate': 'idle: pass_end took'})
