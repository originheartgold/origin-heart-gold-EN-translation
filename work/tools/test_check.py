#!/usr/bin/env python3
"""Unit tests for check.py (the toolchain's check entry point). Run:  python3 -m unittest -v work/tools/test_check.py
The steps themselves are covered by the tests of what they run (test_fixes.py, test_asmpatch.py); these test
the runner, the expected-hash logic and the ruff pin."""
import contextlib
import hashlib
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


class Synthetic(unittest.TestCase):
    def test_without_armips_skip_or_fail(self):
        import asmpatch
        with patch.object(asmpatch, "find_armips", side_effect=asmpatch.AsmError("armips not found")):
            with self.assertRaises(C.Skip) as cm:
                C.step_synthetic(None, required=False)
            self.assertFalse(cm.exception.fail)
            self.assertIn("not found", str(cm.exception))
            with self.assertRaises(C.Skip) as cm:
                C.step_synthetic("/nonexistent/armips", required=True)    # --armips given (CI), or --full
            self.assertTrue(cm.exception.fail)

    def test_assembly_error_fails(self):
        import asmpatch
        with patch.object(asmpatch, "find_armips", return_value="armips"), \
                patch.object(asmpatch, "check_armips", return_value="v0.11.0"), \
                patch.object(asmpatch, "synthetic", side_effect=asmpatch.AsmError("fix t: armips failed")):
            with self.assertRaises(C.Failed) as cm:
                C.step_synthetic(None, required=False)
            self.assertIn("fix t: armips failed", str(cm.exception))


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



class Repro(unittest.TestCase):
    """check.py --full --repro: the second build must equal the first (ROM, xdelta, report without paths)."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.base = self.root / "usa.nds"
        self.base.write_bytes(b"usa")

    def tearDown(self):
        self.td.cleanup()

    def fake_build(self, work, rom=b"rom", xdelta=b"xd", extra=None):
        work = Path(work)
        work.mkdir(parents=True, exist_ok=True)
        (work / "out.nds").write_bytes(rom)
        (work / "out.xdelta").write_bytes(xdelta)
        rep = {"statuses": ["draft"], "base": {"path": str(self.base), "sha1": "b"},
               "rom": {"path": str(work / "out.nds"), "sha1": hashlib.sha1(rom).hexdigest(), "size": len(rom)},
               "patch": {"path": str(work / "out.xdelta"), "sha1": hashlib.sha1(xdelta).hexdigest()},
               "verify": {"note": f"export in {work}/export"}}
        rep.update(extra or {})
        return rep

    def run_repro(self, second_kwargs=None, payload=None):
        first_dir = self.root / "check"
        first = {"report": self.fake_build(first_dir), "work_dir": first_dir}
        calls = []

        def run_build(armips, work_dir, extra=(), env=None, cwd=None):
            calls.append({"work_dir": Path(work_dir), "extra": list(extra), "env": env, "cwd": cwd})
            return self.fake_build(work_dir, **(second_kwargs or {}))
        import text_speed_patch
        pay = payload or {"return_value": {"status": "passed", "compiler": "clang version 1"}}
        with patch.object(C, "run_build", side_effect=run_build), \
                patch.object(text_speed_patch, "verify_reproducible_payload", **pay), \
                patch.object(C, "rom_part_diff", return_value=["arm9 overlay 50 (file 50)"]):
            out = C.step_repro("armips", first, self.root / "check-repro", env=C.REPRO_ENVS[1])
        return out, calls

    def test_identical_builds_pass_in_another_folder_and_environment(self):
        out, calls = self.run_repro()
        self.assertIn("identical", out)
        (call,) = calls
        self.assertEqual(call["work_dir"], self.root / "check-repro")
        self.assertEqual(call["cwd"], self.root / "check-repro")
        self.assertEqual(call["env"], C.REPRO_ENVS[1])
        self.assertNotEqual(C.REPRO_ENVS[0]["TZ"], C.REPRO_ENVS[1]["TZ"])
        self.assertNotEqual(C.REPRO_ENVS[0]["LC_ALL"], C.REPRO_ENVS[1]["LC_ALL"])
        self.assertNotEqual(C.REPRO_ENVS[0]["PYTHONHASHSEED"], C.REPRO_ENVS[1]["PYTHONHASHSEED"])
        base_arg = Path(call["extra"][call["extra"].index("--base") + 1])
        self.assertNotEqual(base_arg.name, self.base.name)                  # the base under another name
        self.assertEqual(base_arg.resolve(), self.base.resolve())
        self.assertIn("--out", call["extra"])
        self.assertIn("--patch", call["extra"])

    def test_rom_difference_names_the_nds_parts(self):
        with self.assertRaises(C.Failed) as cm:
            self.run_repro({"rom": b"other"})
        self.assertIn("the ROM differs", str(cm.exception))
        self.assertIn("arm9 overlay 50", str(cm.exception))

    def test_xdelta_difference_fails(self):
        with self.assertRaises(C.Failed) as cm:
            self.run_repro({"xdelta": b"other"})
        self.assertIn("the xdelta differs", str(cm.exception))

    def test_report_difference_fails_but_paths_do_not(self):
        with self.assertRaises(C.Failed) as cm:
            self.run_repro({"extra": {"graphics_regenerated": {"a.bin": "1"}}})
        self.assertIn("build_report.json differs", str(cm.exception))
        self.assertIn("graphics_regenerated", str(cm.exception))

    def test_payload_not_reproduced_fails(self):
        with self.assertRaises(C.Failed) as cm:
            self.run_repro(payload={"side_effect": ValueError('clang is "Ubuntu clang 18"; pinned to ...')})
        self.assertIn("native payload", str(cm.exception))
        with self.assertRaises(C.Failed):
            self.run_repro(payload={"side_effect": FileNotFoundError("clang")})

    def test_normalized_report(self):
        a = self.fake_build(self.root / "one")
        b = self.fake_build(self.root / "two-longer")
        b["base"]["path"] = "/elsewhere/renamed.nds"
        self.assertEqual(C.normalized_report(a, self.root / "one"), C.normalized_report(b, self.root / "two-longer"))
        self.assertNotIn(str(self.root), C.normalized_report(a, self.root / "one"))

    def test_rom_parts_names_files_and_overlays(self):
        from types import SimpleNamespace as NS

        class Names:
            def filenameOf(self, i):
                return {1: "a/0/2/7"}.get(i)
        rom = NS(files=[b"ov", b"msg", b"x"], filenames=Names(), arm9=b"9", arm7=b"7", arm9OverlayTable=b"",
                 arm7OverlayTable=b"", iconBanner=b"", debugRom=b"", name=b"POKEMON HG",
                 loadArm9Overlays=lambda: {0: NS(fileID=0)}, loadArm7Overlays=lambda: {})
        parts = C.rom_parts(rom)
        self.assertIn("arm9 overlay 0 (file 0)", parts)
        self.assertIn("a/0/2/7 (file 1)", parts)
        self.assertIn("file 2", parts)
        self.assertIn("header fields", parts)

    def test_repro_flags(self):
        for args in (["--repro"],):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                C.main(args)
        seen = []
        with patch.object(C, "run", side_effect=lambda steps: seen.append([n for n, _ in steps]) or 0):
            C.main(["--full", "--strict-release"])
            C.main(["--full"])
        self.assertEqual(seen[0][-2:], ["build", "repro"])                 # a release always checks it
        self.assertEqual(seen[1][-1], "build")

    def test_prereq_refuses_other_xdelta3(self):
        import asmpatch
        import build
        with patch.object(asmpatch, "find_armips", return_value="armips"), \
                patch.object(asmpatch, "check_armips", return_value="v0.11.0"), \
                patch.object(build, "check_xdelta3", side_effect=build.ToolchainError("xdelta3 3.0.11 ...")):
            with self.assertRaises(C.Skip) as cm:
                C.full_prerequisites(None)
        self.assertTrue(cm.exception.fail)
        self.assertIn("xdelta3 3.0.11", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
