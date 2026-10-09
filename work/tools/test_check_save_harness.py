"""The portable suite classifies prerequisites explicitly and fails closed."""
import contextlib
import io
import unittest
from unittest.mock import patch

import check_save_harness as C


def named_test(identifier):
    class NamedTest(unittest.TestCase):
        def id(self):
            return identifier

        def runTest(self):
            pass
    return NamedTest()


class Classification(unittest.TestCase):
    def tests(self):
        return [named_test(name) for name in [*C.NATIVE_TESTS, *C.IMAGE_TESTS, "new.portable.test"]]

    def test_new_tests_run_and_exact_dependencies_are_excluded(self):
        suite, excluded = C.classify(self.tests())
        self.assertEqual([test.id() for test in C.flatten(suite)], ["new.portable.test"])
        self.assertEqual(excluded.keys(), C.NATIVE_TESTS.keys() | C.IMAGE_TESTS.keys())

    def test_images_are_explicitly_enabled(self):
        suite, excluded = C.classify(self.tests(), with_images=True)
        self.assertEqual(suite.countTestCases(), 1 + len(C.IMAGE_TESTS))
        self.assertEqual(excluded, C.NATIVE_TESTS)

    def test_deleted_or_renamed_classifications_fail(self):
        with self.assertRaisesRegex(ValueError, "missing classified tests"):
            C.classify(self.tests()[1:])

    def test_duplicate_tests_fail(self):
        tests = self.tests()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            C.classify([*tests, tests[0]])

    def test_missing_requested_image_dependency_fails(self):
        with patch.object(C.importlib.util, "find_spec", return_value=None), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                C.main(["--with-images"])
        self.assertEqual(error.exception.code, 2)

    def test_unexpected_skip_fails_even_when_unittest_says_ok(self):
        skipped = named_test("new.optional.test")
        skipped.runTest = lambda: skipped.skipTest("new undeclared dependency")
        with patch("check.preflight_save_core"), patch.object(C, "discover", return_value=[]), \
                patch.object(C, "classify", return_value=(unittest.TestSuite([skipped]), {})), \
                contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(C.main([]), 1)
