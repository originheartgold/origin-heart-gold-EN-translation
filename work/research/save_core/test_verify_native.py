"""Portable runner tests: no ROMs, emulator, dependencies or downloads."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import types
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('verify_native', HERE / 'verify_native.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NativeRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.addCleanup(self.tmp.cleanup)
        self.patcher = patch.object(runner, 'ROOT', self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        python = self.root / '.venv/bin/python'
        python.parent.mkdir(parents=True)
        python.write_text('fake interpreter')
        self.inputs = {}
        for index, name in enumerate(runner.INPUTS):
            path = self.root / name
            data = bytes([index]) * (524288 if name == 'seed' else 32)
            path.write_bytes(data)
            self.inputs[name] = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest()}
        self.manifest_path = self.root / 'inputs.json'
        self.raw = {'repo': str(self.root), 'inputs': self.inputs}
        self.save_manifest()
        self.manifest = runner.load_manifest(self.manifest_path)

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.raw))

    def execute(self, plan, run=None, validator=lambda stage: None):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.execute(self.manifest, plan, run=run or (lambda *a, **kw: 0), validator=validator)

    def test_preflight_checks_all_four_hashes_and_sizes(self):
        for name in runner.INPUTS:
            with self.subTest(name=name):
                original = self.inputs[name]['sha256']
                self.inputs[name]['sha256'] = 'f' * 64
                self.save_manifest()
                with self.assertRaisesRegex(ValueError, name + ': SHA-256 mismatch'):
                    runner.load_manifest(self.manifest_path)
                self.inputs[name]['sha256'] = original

    def test_missing_bad_or_extra_manifest_fields_fail(self):
        for value in ({}, {'repo': str(self.root), 'inputs': {}},
                      dict(self.raw, extra=True), {'repo': str(self.root), 'inputs': []}):
            self.manifest_path.write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                runner.load_manifest(self.manifest_path)
        for pin in ('F' * 64, '', 'a' * 63, None):
            self.inputs['cn']['sha256'] = pin
            self.save_manifest()
            with self.assertRaises(ValueError):
                runner.load_manifest(self.manifest_path)

    def test_bad_seed_size_rejected_even_with_matching_hash(self):
        Path(self.inputs['seed']['path']).write_bytes(b'not a save')
        self.inputs['seed']['sha256'] = hashlib.sha256(b'not a save').hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, '512 KiB'):
            runner.load_manifest(self.manifest_path)

    def test_plan_covers_both_languages_and_full_persistence(self):
        plan = runner.make_plan(self.manifest, 'test')
        self.assertEqual(len(plan['stages']), 12)
        self.assertEqual({s['name'] for s in plan['stages']}, {
            'loader-cn', 'loader-en', 'parity-cn', 'parity-en', 'harness-cn', 'harness-en',
            'harness-short-cn', 'harness-short-en', 'core-preflight', 'combined-fixture', 'persistence-cn', 'persistence-en'})
        for stage in plan['stages']:
            self.assertTrue(stage['selected'])
            if stage['group'] == 'persistence' and stage['name'] != 'combined-fixture':
                for flag in ('--persistence', '--observe-traits', '--expect', '--expect-stats', '--expect-traits', '--expect-inventory'):
                    self.assertIn(flag, stage['command'])
                self.assertEqual(stage['depends'], ['core-preflight', 'combined-fixture'])
        self.assertFalse(Path(plan['build']).exists())

    def test_reject_invalid_run_names_and_limits(self):
        for name in ('../outside', '/tmp/absolute', '', 'a' * 81, 'a/b', 'space bad'):
            with self.assertRaises(ValueError):
                runner.make_plan(self.manifest, name)
        for timeout in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                runner.make_plan(self.manifest, 'x', timeout=timeout)
        for groups in ([], ['unknown']):
            with self.assertRaises(ValueError):
                runner.make_plan(self.manifest, 'x', groups=groups)

    def test_plan_cli_does_not_spawn(self):
        with patch.object(runner, 'execute', side_effect=AssertionError('must not execute')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = runner.main(['--inputs', str(self.manifest_path), '--run-id', 'cli', '--plan'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())['status'], 'planned')
        self.assertFalse((self.root / 'work/build/save-core-native-cli').exists())

    def test_bad_hash_cli_never_creates_output(self):
        self.inputs['en']['sha256'] = '0' * 64
        self.save_manifest()
        with contextlib.redirect_stderr(io.StringIO()):
            code = runner.main(['--inputs', str(self.manifest_path), '--run-id', 'bad'])
        self.assertEqual(code, 1)
        self.assertFalse((self.root / 'work').exists())

    def test_reports_full_success_and_environment(self):
        invocations = []
        def run(command, **kwargs):
            invocations.append((command, kwargs))
            self.assertEqual(kwargs['cwd'], self.root)
            self.assertEqual(kwargs['env']['MELONDS_SHIM'], self.inputs['shim']['path'])
            return 0
        plan = runner.make_plan(self.manifest, 'all')
        result = self.execute(plan, run)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['counts'], {'passed': 12, 'failed': 0, 'skipped': 0})
        self.assertEqual(len(invocations), 12)
        self.assertEqual(json.loads((Path(plan['build']) / 'report.json').read_text()), result)

    def test_failed_fixture_skips_dependents_not_other_groups(self):
        def run(command, **kwargs):
            return 7 if command[0] == 'node' else 0
        result = self.execute(runner.make_plan(self.manifest, 'failure'), run)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['counts'], {'passed': 9, 'failed': 1, 'skipped': 2})
        self.assertTrue(all(s['reason'] == 'Required earlier stage did not pass' for s in result['stages'] if s['status'] == 'skipped'))

    def test_deselected_groups_report_incomplete(self):
        result = self.execute(runner.make_plan(self.manifest, 'partial', groups=['harness']))
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['counts'], {'passed': 5, 'failed': 0, 'skipped': 7})

    def test_timeout_failure_is_recorded_and_dependent_skipped(self):
        calls = 0
        def run(command, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise subprocess.TimeoutExpired(command, kwargs['timeout'])
            return 0
        result = self.execute(runner.make_plan(self.manifest, 'timeout'), run)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('exceeded', result['stages'][0]['reason'])
        self.assertEqual(result['stages'][1]['status'], 'skipped')

    def test_zero_exit_cannot_hide_bad_evidence(self):
        def validator(stage):
            if stage['name'] == 'harness-cn':
                raise ValueError('Missing evidence')
        result = self.execute(runner.make_plan(self.manifest, 'bad-report'), validator=validator)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['counts']['failed'], 1)

    def test_modified_input_prevents_subsequent_commands(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            Path(self.inputs['cn']['path']).write_bytes(b'changed')
            return 0
        result = self.execute(runner.make_plan(self.manifest, 'modified'), run)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result['inputs_unchanged'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('source input changed', result['input_error'])

    def test_never_reuses_existing_output_or_symlink(self):
        for kind in ('directory', 'symlink'):
            plan = runner.make_plan(self.manifest, kind)
            out = Path(plan['local'])
            out.parent.mkdir(parents=True, exist_ok=True)
            if kind == 'directory':
                out.mkdir()
            else:
                out.symlink_to(self.root / 'missing')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                self.execute(plan)
            self.assertFalse(Path(plan['build']).exists())

    def test_persistence_report_requires_no_gaps_and_reload(self):
        report_path = self.root / 'evidence.json'
        stage = {'validator': 'persistence', 'report': str(report_path)}
        for report in ({'status': 'passed'}, {'status': 'passed', 'gaps': ['missing'], 'in_game_save_reload': 'passed'},
                       {'status': 'passed', 'gaps': [], 'in_game_save_reload': 'not_verified'}):
            report_path.write_text(json.dumps(report))
            with self.assertRaises(ValueError):
                runner.validate_report(stage)
        report_path.write_text(json.dumps({'status': 'passed', 'gaps': [], 'in_game_save_reload': 'passed'}))
        runner.validate_report(stage)

    def test_harness_must_prove_generator_rejection(self):
        path = self.root / 'harness.json'
        stage = {'validator': 'harness', 'report': str(path)}
        path.write_text(json.dumps({'status': 'passed', 'inputs_unchanged': True, 'native_generator': {'status': 'valid'}}))
        with self.assertRaises(ValueError):
            runner.validate_report(stage)

    def test_loader_requires_exact_case_set(self):
        path = self.root / 'loader.json'
        stage = {'validator': 'loader', 'report': str(path)}
        with patch.dict(sys.modules, {'native_loader_probe': types.SimpleNamespace(CASES={'a': (), 'b': ()})}):
            for rows in ([{'case': 'a'}], [{'case': 'a'}, {'case': 'a'}], []):
                path.write_text(json.dumps({'inputs_unchanged': True, 'rows': rows}))
                with self.assertRaises(ValueError):
                    runner.validate_report(stage)
            path.write_text(json.dumps({'inputs_unchanged': True, 'rows': [{'case': 'a'}, {'case': 'b'}]}))
            runner.validate_report(stage)

    def test_malformed_evidence_containers_fail_cleanly(self):
        path = self.root / 'malformed.json'
        for kind in ('loader', 'fixture', 'persistence', 'harness', 'harness-valid'):
            for value in ([], None, 1, 'passed'):
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'JSON object'):
                    runner.validate_report({'validator': kind, 'report': str(path)})
        path.write_text(json.dumps({'status':'passed','inputs_unchanged':True,'native_generator':[]}))
        with self.assertRaises(ValueError):
            runner.validate_report({'validator':'harness','report':str(path)})

    def test_reference_hash_mismatch_is_explicitly_skipped(self):
        source = self.root / 'work/save-editor/src/core/generated-reference.ts'
        source.parent.mkdir(parents=True)
        source.write_text('{"romSha256":"' + 'f' * 64 + '"}')
        result = runner.reference_provenance(self.manifest)
        self.assertEqual(result['status'], 'skipped')
        self.assertFalse(result['rom_hash_matches'])
        self.assertIn('differs from the bundle', result['reason'])

    def test_preflight_failure_skips_every_native_stage(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return 1
        result = self.execute(runner.make_plan(self.manifest, 'stale-core'), run)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['counts'], {'passed': 0, 'failed': 1, 'skipped': 11})

    def test_real_fake_subprocess_logs_and_nonzero(self):
        stdout, stderr = self.root / 'stdout', self.root / 'stderr'
        code = runner.run_process([sys.executable, '-c', 'import sys; print("visible"); print("error", file=sys.stderr); sys.exit(4)'],
                                  cwd=self.root, env=os.environ.copy(), timeout=10, stdout=stdout, stderr=stderr)
        self.assertEqual(code, 4)
        self.assertEqual(stdout.read_text(), 'visible\n')
        self.assertEqual(stderr.read_text(), 'error\n')

    @unittest.skipUnless(os.name == 'posix', 'Process-tree signals require POSIX')
    def test_timeout_kills_native_worker_descendants(self):
        marker = self.root / 'escaped-worker'
        child = f'import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).write_text("alive")'
        parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",' + repr(child) + ']); time.sleep(20)'
        with self.assertRaises(subprocess.TimeoutExpired):
            runner.run_process([sys.executable, '-c', parent], cwd=self.root, env=os.environ.copy(), timeout=0.2,
                               stdout=self.root / 'out', stderr=self.root / 'err')
        time.sleep(1.2)
        self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
