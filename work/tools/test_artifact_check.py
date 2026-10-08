"""Artifact orchestration tests using synthetic inputs; no ROM build or emulator."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import struct
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import artifact_check as A


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        self.a = argparse.Namespace(rom=p / "rom.bin", base=p / "base.bin", build_report=p / "build.json",
                                    ws=p / "ws", extract=p / "extract", output=p / "out")
        self.a.rom.write_bytes(b"synthetic artifact")
        self.a.base.write_bytes(b"synthetic base")
        for folder in (self.a.ws, self.a.extract):
            folder.mkdir()
            (folder / "0000.json").write_text("{}")
        self.prior = {"rom": {"sha1": A.hashes(self.a.rom)["sha1"]},
                      "base": {"sha1": A.hashes(self.a.base)["sha1"]},
                      "statuses": ["draft"], "glyphs": [{"font": 0}],
                      "graphics": [{"synthetic": True}], "hardcoded": {"synthetic": True}}
        self.save_report()

    def save_report(self):
        self.a.build_report.write_text(json.dumps(self.prior))

    def export(self, workspace, extract, out, **kwargs):
        self.assertFalse(kwargs["lenient"])
        for narc in A.build.NARCS:
            (out / narc).mkdir(parents=True, exist_ok=True)
            (out / narc / "0000.json").write_text("{}")
        return {"strings": 2, "en": 2}, []

    @staticmethod
    def rom(native=False):
        main = bytearray(0x20a1c)
        struct.pack_into("<I", main, 0x20a18, 0x01ff8621 if native else 0x02020a1d)
        sections = [SimpleNamespace(ramAddress=0x02000000, data=main),
                    SimpleNamespace(ramAddress=0x01ff8000, data=bytes(0x640 if native else 0x620))]
        return SimpleNamespace(loadArm9=lambda: SimpleNamespace(sections=sections))

    def run_check(self, export=None, verifier=None, native=False):
        with patch.object(A.msgtool, "load_rom", return_value=self.rom(native)), \
             patch.object(A.msgtool, "get_file", return_value=b"font"):
            return A.check(self.a, export or self.export, verifier or (lambda *args: {"synthetic": "ok"}))

    def test_success_and_source_unchanged(self):
        before = self.a.rom.read_bytes()
        result = self.run_check()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(self.a.rom.read_bytes(), before)
        self.assertEqual(len(result["inputs"]["ws"]["sha256"]), 64)

    def test_feature_verifier_rejection_is_release_failure(self):
        self.prior["text_speed"] = {"enabled": True, "source_code_sha256": "synthetic"}
        self.save_report()
        with patch.object(A.build.text_speed_patch, "verify", side_effect=ValueError("feature rejected")) as verify:
            result = self.run_check(native=True)
        verify.assert_called_once()
        self.assertIn("feature rejected", result["reason"])
        self.assertEqual(result["status"], "failed")

    def test_native_missing_metadata_and_false_opt_out_fail(self):
        for metadata in (None, {}, {"enabled": False, "reason": "--no-text-speed"}):
            with self.subTest(metadata=metadata):
                if metadata is None:
                    self.prior.pop("text_speed", None)
                else:
                    self.prior["text_speed"] = metadata
                self.save_report()
                result = self.run_check(native=True)
                self.assertEqual(result["status"], "failed")
                self.assertIn("text", result["reason"])

    def test_explicit_opt_out_and_legacy_do_not_require_compiler(self):
        for metadata in (None, {"enabled": False, "reason": "--no-text-speed"},
                         {"enabled": False, "reason": "--no-hardcoded"}):
            with self.subTest(metadata=metadata):
                if metadata is None:
                    self.prior.pop("text_speed", None)
                else:
                    self.prior["text_speed"] = metadata
                self.save_report()
                with patch.object(A.build.text_speed_patch, "verify_reproducible_payload") as reproduce:
                    result = self.run_check()
                self.assertEqual(result["status"], "passed", result)
                reproduce.assert_not_called()

    def test_enabled_native_requires_reproduction(self):
        self.prior["text_speed"] = {"enabled": True}
        self.save_report()
        with patch.object(A.build.text_speed_patch, "verify", return_value={"status": "passed"}), \
             patch.object(A.build.text_speed_patch, "verify_reproducible_payload",
                          side_effect=ValueError("cached payload does not reproduce")) as reproduce:
            result = self.run_check(native=True)
        reproduce.assert_called_once_with()
        self.assertEqual(result["status"], "failed")
        self.assertIn("does not reproduce", result["reason"])

    def test_enabled_native_reproduction_pass_recorded(self):
        self.prior["text_speed"] = {"enabled": True}
        self.save_report()
        reproduced = {"status": "passed", "payload_sha256": "reviewed"}
        with patch.object(A.build.text_speed_patch, "verify", return_value={"status": "passed"}), \
             patch.object(A.build.text_speed_patch, "verify_reproducible_payload", return_value=reproduced) as reproduce:
            result = self.run_check(native=True)
        self.assertEqual(result["status"], "passed", result)
        self.assertEqual(result["checks"]["text_speed_reproduction"], reproduced)
        reproduce.assert_called_once_with()

    def test_missing_compiler_fails_enabled_release_gate(self):
        self.prior["text_speed"] = {"enabled": True}
        self.save_report()
        with patch.object(A.build.text_speed_patch, "verify", return_value={"status": "passed"}), \
             patch.object(A.build.text_speed_patch, "verify_reproducible_payload", side_effect=FileNotFoundError("clang")):
            result = self.run_check(native=True)
        self.assertEqual(result["status"], "failed")
        self.assertIn("clang", result["reason"])

    def test_enabled_metadata_cannot_certify_unpatched_rom(self):
        self.prior["text_speed"] = {"enabled": True}
        self.save_report()
        result = self.run_check()
        self.assertEqual(result["status"], "failed")
        self.assertIn("no native ROM payload", result["reason"])

    def test_stale_source_fails_native_gate(self):
        self.prior["text_speed"] = {"enabled": True}
        self.save_report()
        with patch.object(A.build.text_speed_patch, "source_digest", return_value="0" * 64):
            result = self.run_check(native=True)
        self.assertEqual(result["status"], "failed")
        self.assertIn("Stale native payload", result["reason"])

    def test_feature_inputs_fingerprinted_and_mutations_rejected(self):
        original = A.hashes
        feature_inputs = ("tools/text_speed_patch.py", "patches/text-speed/native.c",
                          "patches/text-speed/labels.h", "patches/text-speed/payload.json",
                          "patches/text-speed/fix.toml")
        for name in feature_inputs:
            with self.subTest(name=name):
                calls = 0
                def hashes(path):
                    nonlocal calls
                    result = original(path)
                    if path == A.build.WORK / name:
                        calls += 1
                        if calls > 1:
                            result["sha256"] = "changed while verifying"
                    return result
                with patch.object(A, "hashes", side_effect=hashes):
                    result = self.run_check()
                self.assertEqual(result["status"], "failed")
                self.assertIn(name, result["reason"])

    def test_missing_asset_incomplete(self):
        self.a.rom.unlink()
        self.assertEqual(self.run_check()["status"], "incomplete")

    def test_empty_workspace_failed(self):
        (self.a.ws / "0000.json").unlink()
        self.assertEqual(self.run_check()["status"], "failed")

    def test_stale_identity_does_not_export(self):
        self.a.rom.write_bytes(b"changed")
        result = self.run_check(export=lambda *args, **kwargs: self.fail("export must not run"))
        self.assertEqual(result["status"], "failed")
        self.assertIn("stale", result["reason"])

    def test_stale_base(self):
        self.a.base.write_bytes(b"changed")
        self.assertIn("base ROM identity", self.run_check()["reason"])

    def test_export_fallback_fails(self):
        result = self.run_check(export=lambda *args, **kwargs: ({"strings": 2}, ["source mismatch"]))
        self.assertEqual(result["status"], "failed")

    def test_zero_export_fails(self):
        self.assertEqual(self.run_check(export=lambda *args, **kwargs: ({}, []))["status"], "failed")

    def test_zero_banks_fails(self):
        result = self.run_check(export=lambda *args, **kwargs: ({"strings": 2}, []))
        self.assertEqual(result["status"], "failed")
        self.assertIn("zero banks", result["reason"])

    def test_missing_dependency_incomplete(self):
        def missing(*args, **kwargs):
            raise ModuleNotFoundError("ndspy")
        self.assertEqual(self.run_check(export=missing)["status"], "incomplete")

    def test_verifier_failure(self):
        def fail(*args):
            raise AssertionError("message differs")
        result = self.run_check(verifier=fail)
        self.assertEqual(result["status"], "failed")
        self.assertIn("message differs", result["reason"])

    def test_changed_workspace_fails(self):
        def change(*args):
            (self.a.ws / "0000.json").write_text('{"changed":true}')
            return {}
        self.assertIn("ws changed", self.run_check(verifier=change)["reason"])

    def test_optimized_python_incomplete(self):
        with patch.object(A.sys, "flags", argparse.Namespace(optimize=1)):
            self.assertEqual(self.run_check()["status"], "incomplete")

    def test_missing_metadata_incomplete(self):
        del self.prior["graphics"]
        self.save_report()
        self.assertEqual(self.run_check()["status"], "incomplete")

    def test_output_outside_ignored_build_rejected(self):
        for flag in ("--output", "--json"):
            with self.assertRaises(SystemExit) as error:
                A.main([flag, str(Path(self.temp.name) / "forbidden")])
            self.assertEqual(error.exception.code, 2)
            self.assertFalse((Path(self.temp.name) / "forbidden").exists())


if __name__ == "__main__":
    unittest.main()
