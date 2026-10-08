#!/usr/bin/env python3
"""Unit tests for check.py (the toolchain's check entry point). Run:  python3 -m unittest -v work/tools/test_check.py
The steps themselves are covered by the tests of what they run (test_fixes.py, test_asmpatch.py); these test
the runner, the expected-hash logic and the ruff pin."""
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check as C  # noqa: E402

GOT = {"nontext_sha1": "n" * 40, "text_sha1": "t" * 40, "rom_sha1": "r" * 40, "xdelta_sha1": "x" * 40}


class Expected(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "expected.toml"
            C.write_expected(GOT, p)
            self.assertEqual(C.load_expected(p), GOT)
            text = p.read_text(encoding="utf-8")
            self.assertIn("python3 work/tools/check.py --full --update-expected", text)
            self.assertIn("outfit-chooser-strings", text)                 # what moves nontext_sha1
            self.assertNotIn("recorded =", text)
            self.assertEqual(C.load_expected(Path(td) / "missing.toml"), {})

    def test_same_build_passes(self):
        self.assertEqual(C.compare_expected(GOT, dict(GOT)), ([], []))

    def test_missing_file(self):
        fails, _ = C.compare_expected(GOT, {})
        self.assertIn("--update-expected", fails[0])

    def test_text_change_is_a_note_unless_strict(self):
        want = dict(GOT, text_sha1="T" * 40, rom_sha1="R" * 40, xdelta_sha1="X" * 40)
        fails, notes = C.compare_expected(GOT, want)
        self.assertEqual(fails, [])
        self.assertEqual(len(notes), 3)                       # text, ROM and patch; not the non-text bytes
        self.assertIn("the message-bank text changed since the hashes were recorded", notes[0])
        for n in notes[1:]:
            self.assertIn("the bytes outside it are unchanged", n)
            self.assertIn("python3 work/tools/check.py --full --update-expected", n)
        fails, notes = C.compare_expected(GOT, want, strict=True)
        self.assertEqual((len(fails), notes), (3, []))

    def test_nontext_change_fails_whatever_the_text(self):
        want = dict(GOT, nontext_sha1="N" * 40, text_sha1="T" * 40, rom_sha1="R" * 40)
        fails, notes = C.compare_expected(GOT, want)
        self.assertEqual(len(fails), 1)
        self.assertIn("the ROM outside the message banks changed", fails[0])
        self.assertNotIn("the bytes outside it are unchanged", "".join(notes))
        _, notes = C.compare_expected(GOT, dict(GOT, nontext_sha1="N" * 40, rom_sha1="R" * 40))
        self.assertIn("it follows from the change outside the message banks (above)", notes[0])

    def test_same_text_other_rom_is_unexpected(self):
        fails, notes = C.compare_expected(GOT, dict(GOT, rom_sha1="R" * 40))
        self.assertEqual((fails, len(notes)), ([], 1))
        self.assertIn("are the recorded ones, so this is unexpected", notes[0])
        fails, _ = C.compare_expected(GOT, dict(GOT, rom_sha1="R" * 40), strict=True)
        self.assertEqual(len(fails), 1)


class Runner(unittest.TestCase):
    def run_steps(self, steps):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = C.run(steps)
        return code, out.getvalue()

    def test_pass_skip_and_fail(self):
        def skip():
            raise C.Skip("no ROM")

        def must():
            raise C.Skip("no armips", fail=True)

        def bad():
            raise C.Failed("line 1\nline 2")
        code, out = self.run_steps([("a", lambda: "fine"), ("b", skip)])
        self.assertEqual(code, 0)
        self.assertIn("PASS a", out)
        self.assertIn("SKIP b", out)
        code, out = self.run_steps([("a", lambda: "fine"), ("c", must)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL c", out)
        code, out = self.run_steps([("d", bad)])
        self.assertEqual(code, 1)
        self.assertIn("FAIL d (", out)
        self.assertIn("     line 2", out)

    def test_ruff_pin_and_missing_ruff(self):
        self.assertRegex(C.pinned_ruff(), r"^\d+\.\d+\.\d+$")
        with patch.object(C, "find_ruff", return_value=None):
            with self.assertRaises(C.Skip) as cm:
                C.step_ruff(full=False)
            self.assertFalse(cm.exception.fail)
            self.assertIn("requirements-dev.txt", str(cm.exception))
            with self.assertRaises(C.Skip) as cm:
                C.step_ruff(full=True)
            self.assertTrue(cm.exception.fail)

    def test_update_expected_needs_full(self):
        for args in (["--update-expected"], ["--strict-release"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                C.main(args)


if __name__ == "__main__":
    unittest.main()
