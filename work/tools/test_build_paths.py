"""Verify isolated build state without loading, saving, or building a ROM."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build as B


class StopBeforeRomLoad(Exception):
    pass


class BuildPathsTests(unittest.TestCase):
    def exercise_export(self, explicit):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "legacy"
            chosen = root / "review"
            (legacy / "export").mkdir(parents=True)
            sentinel = legacy / "export" / "keep.json"
            sentinel.write_text("legacy export")
            report = legacy / "build_report.json"
            report.write_text("legacy report")
            target = chosen if explicit else legacy
            seen = []

            def export(workspace, extract, out, statuses, lenient):
                seen.append(out)
                out.mkdir(parents=True, exist_ok=True)
                (out / "fresh.json").write_text("new export")
                return {"strings": 1}, []

            args = ["--work-dir", str(chosen)] if explicit else []
            with patch.object(B, "BUILD", legacy), patch.object(B.ws, "export", side_effect=export), \
                 patch.object(B, "sha1", return_value=B.US_SHA1), \
                 patch.object(B.asmpatch, "find_armips", return_value="/armips"), \
                 patch.object(B.asmpatch, "check_armips", return_value=B.asmpatch.PINNED_VERSION), \
                 patch.object(B.m, "load_rom", side_effect=StopBeforeRomLoad) as load, \
                 patch.object(B, "log"):
                with self.assertRaises(StopBeforeRomLoad):
                    B.main(args + ["--no-patch"])
                load.assert_called_once()
            self.assertEqual(seen, [target / "export"])
            self.assertEqual((target / "export" / "fresh.json").read_text(), "new export")
            self.assertEqual(report.read_text(), "legacy report")
            if explicit:
                self.assertEqual(sentinel.read_text(), "legacy export")

    def test_isolated_export_preserves_legacy_state(self):
        self.exercise_export(True)

    def test_default_export_location_unchanged(self):
        self.exercise_export(False)

    def test_outputs_preserve_default_and_explicit_paths(self):
        paths = B.build_paths(B.BUILD)
        self.assertEqual(paths["rom"], B.OUT_ROM)
        self.assertEqual(paths["patch"], B.OUT_PATCH)
        self.assertEqual(paths["report"], B.BUILD / "build_report.json")
        paths = B.build_paths(Path("review"), "custom.bin", "custom.patch")
        self.assertEqual(paths["rom"], Path("custom.bin"))
        self.assertEqual(paths["patch"], Path("custom.patch"))
        self.assertEqual(paths["work"], Path("review"))



def completed(out="", err="", code=0):
    return B.subprocess.CompletedProcess(["x"], code, stdout=out, stderr=err)


class ToolchainPinTests(unittest.TestCase):
    """xdelta3 is pinned (refused at another version), Python / ndspy / pillow only warn."""

    def test_xdelta3_version_parsed_and_pinned(self):
        with patch.object(B.subprocess, "run", return_value=completed(err="Xdelta version 3.2.0, Copyright (C)")), \
                patch.object(B.shutil, "which", return_value="/usr/bin/xdelta3"):
            self.assertEqual(B.xdelta3_version(), "3.2.0")
            self.assertEqual(B.check_xdelta3(), (B.XDELTA3_VERSION, True))

    def test_other_xdelta3_refused_unless_unpinned(self):
        with patch.object(B.subprocess, "run", return_value=completed(err="Xdelta version 3.0.11, Copyright")), \
                patch.object(B.shutil, "which", return_value="/usr/bin/xdelta3"):
            with self.assertRaisesRegex(B.ToolchainError, "3.0.11 .* pinned to xdelta3 3.2.0.*--unpinned-xdelta3"):
                B.check_xdelta3()
            self.assertEqual(B.check_xdelta3(allow_other=True), ("3.0.11", False))

    def test_missing_or_foreign_xdelta3(self):
        with patch.object(B.shutil, "which", return_value=None):
            with self.assertRaisesRegex(B.ToolchainError, "not on PATH"):
                B.check_xdelta3()
        with patch.object(B.subprocess, "run", return_value=completed(out="usage: something else")), \
                patch.object(B.shutil, "which", return_value="/usr/bin/xdelta3"):
            with self.assertRaisesRegex(B.ToolchainError, "does not look like xdelta3"):
                B.check_xdelta3()

    def test_build_stops_on_unpinned_xdelta3_before_export(self):
        with patch.object(B, "check_xdelta3", side_effect=B.ToolchainError("xdelta3 3.0.11 ... pinned")), \
                patch.object(B.asmpatch, "find_armips", return_value="/armips"), \
                patch.object(B.asmpatch, "check_armips", return_value=B.asmpatch.PINNED_VERSION), \
                patch.object(B.ws, "export") as export, patch.object(B, "log"), \
                tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit) as cm:
                B.main(["--work-dir", td])
            self.assertIn("pinned", str(cm.exception.code))
            export.assert_not_called()

    def test_python_and_package_versions_only_warn(self):
        pins = {"ndspy": "4.2.0", "pillow": "12.3.0"}
        same = {"ndspy": "4.2.0", "pillow": "12.3.0"}
        self.assertEqual(B.python_warnings(B.VALIDATED_PYTHON, same, pins), [])
        warn = B.python_warnings((3, 12), {"ndspy": "4.1.0", "pillow": None}, pins)
        self.assertEqual(len(warn), 3, warn)
        self.assertIn("Python 3.12", warn[0])
        self.assertIn("ndspy 4.1.0", warn[1])
        self.assertIn("pillow not installed", warn[2])
        self.assertEqual(B.pinned_requirements()["ndspy"], "4.2.0")      # requirements-runtime.txt

    def test_patch_names_are_the_standard_ones(self):
        with tempfile.TemporaryDirectory() as td:
            base, target = Path(td) / "my dump.nds", Path(td) / "custom-out.nds"
            base.write_bytes(b"a")
            target.write_bytes(b"b")
            with patch.object(B.subprocess, "run") as run:
                B.make_patch(base, target, Path(td) / "p.xdelta", Path(td))
            argv = run.call_args.args[0]
            self.assertEqual([Path(argv[-3]).name, Path(argv[-2]).name], [B.PATCH_SOURCE_NAME, B.PATCH_TARGET_NAME])
            self.assertEqual(argv[:6], ["xdelta3", "-e", "-9", "-S", "lzma", "-s"])

    @unittest.skipUnless(B.shutil.which("xdelta3"), "xdelta3 not installed")
    def test_patch_bytes_do_not_depend_on_file_names(self):
        """xdelta3 writes the file names into the patch; make_patch makes them the standard ones."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = bytes(range(256)) * 64
            outs = []
            for i, (bname, tname) in enumerate((("base.nds", "out.nds"), ("other dump.nds", "renamed.nds"))):
                d = root / str(i)
                d.mkdir()
                (d / bname).write_bytes(src)
                (d / tname).write_bytes(src[:1000] + b"changed" + src[1000:])
                B.make_patch(d / bname, d / tname, d / "p.xdelta", d)
                outs.append((d / "p.xdelta").read_bytes())
                self.assertEqual(sorted(x.name for x in d.iterdir()), sorted([bname, tname, "p.xdelta"]))
            self.assertEqual(outs[0], outs[1])
            self.assertIn(B.PATCH_SOURCE_NAME.encode(), outs[0])


if __name__ == "__main__":
    unittest.main()
