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


if __name__ == "__main__":
    unittest.main()
