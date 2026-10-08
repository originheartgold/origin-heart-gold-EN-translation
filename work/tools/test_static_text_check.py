import copy
from pathlib import Path
import tempfile
import unittest

import static_text_check as check


class StaticTextTests(unittest.TestCase):
    def payload(self):
        snapshots = {label: {'files': {'.': {'size': 1, 'sha256': 'a'*64}}} for label in ('source', 'candidate', 'us', 'workspace', 'extract', 'tools', 'graphics', 'patches', 'reference_mapping')}
        return {'status': 'passed', 'inputs_before': snapshots, 'inputs_after': copy.deepcopy(snapshots),
                'checks': {**{key: {'status': 'passed', 'counts': {'banks': 1, 'strings': 1, 'records': 1, 'files_compared': 1, 'attributes_compared': 1, 'message_payloads_deferred': 2}, 'findings': {'child': {'status': 'passed'}}} for key in ('inventory', 'binary', 'boundary', 'safety')},
                           'input_stability': {'status': 'passed', 'unchanged': True}}}

    def test_aggregate_missing(self):
        self.assertEqual(check.aggregate({}), 'incomplete')
        self.assertEqual(check.aggregate_report({'status': 'passed'}), 'incomplete')

    def test_aggregate_valid(self):
        self.assertEqual(check.aggregate_report(self.payload()), 'passed')

    def test_missing_or_empty_sections(self):
        for key in ('inventory', 'binary', 'boundary', 'safety', 'input_stability'):
            payload = self.payload()
            del payload['checks'][key]
            self.assertEqual(check.aggregate_report(payload), 'incomplete')
        for counts in ({}, {'banks': 0}, {'banks': True}):
            payload = self.payload()
            payload['checks']['inventory']['counts'] = counts
            self.assertEqual(check.aggregate_report(payload), 'incomplete')

    def test_failure_precedence(self):
        payload = self.payload()
        payload['checks']['inventory']['status'] = 'incomplete'
        payload['checks']['boundary']['status'] = 'failed'
        self.assertEqual(check.aggregate_report(payload), 'failed')

    def test_hidden_binary_failure(self):
        payload = self.payload()
        payload['checks']['binary']['findings']['child']['status'] = 'failed'
        self.assertEqual(check.aggregate_report(payload), 'failed')

    def test_incomplete_input_proof(self):
        payload = self.payload()
        del payload['inputs_before']['tools']
        del payload['inputs_after']['tools']
        self.assertEqual(check.aggregate_report(payload), 'incomplete')
        payload = self.payload()
        payload['inputs_before']['tools']['files'] = {}
        payload['inputs_after']['tools']['files'] = {}
        self.assertEqual(check.aggregate_report(payload), 'incomplete')

    def test_hash_mutation(self):
        payload = self.payload()
        payload['inputs_after']['source']['files']['.']['sha256'] = 'def'
        self.assertEqual(check.aggregate_report(payload), 'incomplete')

    def test_guarded_failure_and_missing_status(self):
        self.assertEqual(check.guarded(lambda: 1 / 0)['status'], 'failed')
        self.assertEqual(check.guarded(lambda: {})['status'], 'incomplete')

    def test_capture_add_remove_and_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'x').write_text('a')
            first = check.capture_inputs({'tree': root})
            (root/'x').write_text('b')
            self.assertNotEqual(first, check.capture_inputs({'tree': root}))
            (root/'y').write_text('a')
            self.assertEqual(len(check.capture_inputs({'tree': root})['tree']['files']), 2)
            (root/'x').unlink()
            self.assertNotEqual(first, check.capture_inputs({'tree': root}))

    def test_output_restricted(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                check.run(None, None, None, None, None, Path(td)/'output')


if __name__ == '__main__':
    unittest.main()
