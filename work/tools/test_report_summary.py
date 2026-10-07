import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'research' / 'text_speed'))
import report_summary as rs


def gate(status='passed', obs=None, errors=None):
    row = {'status': status, 'exit': 0 if status == 'passed' else 1, 'observations': obs}
    if errors:
        row['errors'] = errors
    return row


def report(**kw):
    r = {'status': 'passed', 'releasable': True, 'rom_sha256': 'a' * 64, 'payload_sha256': 'b' * 64,
         'save_sha256': 'c' * 64, 'git_head': 'd' * 40, 'git_dirty': [], 'git_dirty_at_end': [],
         'gates': {'options': gate(obs={'checks': 9, 'heap_checks': 5}),
                   'fallbacks': gate(obs={'invalid': {'span': 53}, 'normal': {'span': 53}, 'fast': {'span': 21}}),
                   'mystery': gate(obs={'a': 1, 'b': [1, 2]})},
         'problems': [], 'warnings': {}}
    r.update(kw)
    return r


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, data):
        p = Path(self.tmp.name) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data))
        return str(p)

    def run_cli(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = rs.main(list(argv))
        return code, out.getvalue()


class SummaryTests(Base):
    def test_passed(self):
        code, out = self.run_cli('summary', self.write('r.json', report()))
        self.assertEqual(code, 0)
        self.assertIn('rom=aaaaaaaa', out)
        self.assertIn('span o/n/f=53/53/21', out)
        self.assertIn('checks=9 heap=5', out)
        self.assertIn('3 obs', out)
        self.assertLess(len(out.splitlines()), 25)

    def test_failed_gate_error_truncated(self):
        r = report(status='failed', releasable=False,
                   gates={'corpus': gate('failed', None, ['x' * 400])}, problems=list('abcde'))
        code, out = self.run_cli('summary', self.write('r.json', r))
        self.assertEqual(code, 1)
        line = [l for l in out.splitlines() if l.startswith('corpus')][0]
        self.assertLess(len(line), 170)
        self.assertIn('problems: 5', out)
        self.assertNotIn('  d', out)

    def test_not_releasable_is_failure(self):
        code, _ = self.run_cli('summary', self.write('r.json', report(releasable=False)))
        self.assertEqual(code, 1)

    def test_garbage_does_not_crash(self):
        code, out = self.run_cli('summary', self.write('r.json', {'gates': {'x': 5, 'y': {}}}))
        self.assertEqual(code, 1)
        self.assertIn('?', out)


class DiffTests(Base):
    def test_numeric_change_and_status(self):
        old = report()
        new = report()
        new['gates']['options']['observations']['checks'] = 12
        new['gates']['fallbacks']['status'] = 'failed'
        new['gates']['extra'] = gate()
        del new['gates']['mystery']
        code, out = self.run_cli('diff', self.write('o.json', old), self.write('n.json', new))
        self.assertEqual(code, 1)
        self.assertIn('options.checks: 9->12 (+3)', out)
        self.assertIn('gate fallbacks: passed->failed', out)
        self.assertIn('gate added: extra', out)
        self.assertIn('gate removed: mystery', out)
        self.assertNotIn('heap_checks', out)

    def test_identical(self):
        code, out = self.run_cli('diff', self.write('o.json', report()), self.write('n.json', report()))
        self.assertEqual((code, out.strip()), (0, 'no differences'))

    def test_cap(self):
        new = report()
        new['gates']['mystery']['observations'] = {f'k{i}': i for i in range(100)}
        o, n = self.write('o.json', report()), self.write('n.json', new)
        code, out = self.run_cli('diff', o, n)
        self.assertIn('more (use --all)', out)
        self.assertLessEqual(len(out.splitlines()), 62)
        _, full = self.run_cli('diff', o, n, '--all')
        self.assertGreater(len(full.splitlines()), 100)


class FaultTests(Base):
    def fault(self, name, status, failed):
        gates = {g: gate('failed' if g in failed else 'passed') for g in ('corpus', 'battle')}
        self.write(f'{name}/report.json', {'status': status, 'fault_fixture': {'name': name}, 'gates': gates})
        # gate sub-report repeating fault_fixture must not shadow the run report
        self.write(f'{name}/corpus/report.json', {'status': 'failed', 'fault_fixture': {'name': name}})

    def test_detected_and_missed(self):
        self.fault('alpha', 'fault-detected', ['corpus'])
        self.fault('beta', 'fault-missed', [])
        code, out = self.run_cli('faults', self.tmp.name)
        self.assertEqual(code, 1)
        lines = {l.split()[0]: l for l in out.splitlines()[1:]}
        self.assertIn('detected', lines['alpha'])
        self.assertIn('MISSED', lines['beta'])

    def test_all_detected(self):
        self.fault('alpha', 'fault-detected', ['corpus'])
        self.assertEqual(self.run_cli('faults', self.tmp.name)[0], 0)

    def test_empty_dir(self):
        self.assertEqual(self.run_cli('faults', self.tmp.name)[0], 1)


if __name__ == '__main__':
    unittest.main()
