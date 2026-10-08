"""Synthetic adversarial tests: no real ROMs or build artifacts needed."""
import copy
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ndspy.fnt
import ndspy.rom
import text_boundary_check as B


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "candidate.nds"
        self.path.write_bytes(b"\0" * 0x4000)
        donor = patch.object(B.build, "US_SHA1", hashlib.sha1(self.path.read_bytes()).hexdigest())
        donor.start()
        self.addCleanup(donor.stop)
        self.rom = ndspy.rom.NintendoDSRom()
        # Nested message archive paths plus a protected gameplay file.
        leaf = ndspy.fnt.Folder(files=["7"], firstID=0)
        node = ndspy.fnt.Folder(folders=[("2", leaf)])
        zero = ndspy.fnt.Folder(folders=[("0", node)])
        battle = ndspy.fnt.Folder(folders=[("string", ndspy.fnt.Folder(files=["battle_string.narc"], firstID=1))])
        self.rom.filenames = ndspy.fnt.Folder(folders=[("a", zero), ("battle", battle)], files=["gameplay"], firstID=2)
        self.rom.files = [B.m.Narc([b"abc"]).build(), B.m.Narc([b"def"]).build(), b"gameplay"]
        self.rom.pad200 = bytearray(0x3e00)
        struct.pack_into("<I", self.rom.pad200, 0xe00, 0x4000)
        self.rom.rsaSignature = b""

    def compare(self, candidate):
        return B._compare(self.rom, candidate, self.path)[0]

    def test_identical_components(self):
        self.assertEqual(self.compare(copy.deepcopy(self.rom)), [])

    def test_message_payload_changes_allowed(self):
        r = copy.deepcopy(self.rom)
        r.files[0] = B.m.Narc([b"changed payload"]).build()
        self.assertEqual(self.compare(r), [])

    def test_message_metadata_and_padding_protected(self):
        for candidate in [B.m.Narc([b"abc"], btnf=b"12345678").build(),
                          B.m.Narc([b"abc"], pad_byte=0).build(),
                          B.m.Narc([b"abc", b"new"]).build()]:
            with self.subTest(candidate=candidate):
                r = copy.deepcopy(self.rom)
                r.files[0] = candidate
                self.assertTrue(self.compare(r))

    def test_every_nonmessage_component_protected(self):
        for attr in ("arm9", "arm7", "arm9OverlayTable", "arm7OverlayTable", "iconBanner", "name", "pad016"):
            with self.subTest(attr=attr):
                r = copy.deepcopy(self.rom)
                setattr(r, attr, b"tampered")
                self.assertTrue(self.compare(r))
        r = copy.deepcopy(self.rom)
        r.files[2] = b"changed gameplay"
        self.assertTrue(self.compare(r))

    def test_paths_inventory_and_order_protected(self):
        r = copy.deepcopy(self.rom)
        r.filenames.files[0] = "renamed"
        self.assertTrue(self.compare(r))
        r = copy.deepcopy(self.rom)
        r.files.append(b"extra")
        self.assertTrue(self.compare(r))
        r = copy.deepcopy(self.rom)
        r.sortedFileIds = [2, 1, 0]
        self.assertTrue(self.compare(r))

    def test_only_signature_pointer_word_can_change(self):
        r = copy.deepcopy(self.rom)
        # The source hack may contain an invalid legacy pointer.
        struct.pack_into("<I", self.rom.pad200, 0xe00, 0xdeadbeef)
        self.assertEqual(self.compare(r), [])
        r.pad200[0xe04] = 1
        self.assertTrue(self.compare(r))

    def test_signature_pointer_must_be_structurally_valid(self):
        for pointer in (0, 0x4001, 0x3fff):
            r = copy.deepcopy(self.rom)
            struct.pack_into("<I", r.pad200, 0xe00, pointer)
            self.assertTrue(self.compare(r))

    def test_missing_prerequisite_incomplete(self):
        result = B.check_boundary(self.path, self.path, self.path.with_name("absent"))
        self.assertEqual(result["status"], "incomplete")
        self.assertTrue(result["gaps"])

    def test_declared_policy_failure_fails(self):
        with patch.object(B, "_expected_rom", side_effect=ValueError("source bytes unexpected")):
            result = B.check_boundary(self.path, self.path, self.path)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["errors"])

    def test_unapproved_donor_fails(self):
        with patch.object(B.build, "US_SHA1", "unapproved"):
            self.assertEqual(B.check_boundary(self.path, self.path, self.path)["status"], "failed")

    def test_candidate_failure_fails(self):
        with patch.object(B, "_expected_rom", return_value=self.rom):
            result = B.check_boundary(self.path, self.path, self.path)
        self.assertEqual(result["status"], "failed")


    def test_armips_missing_is_a_gap_wrong_version_fails(self):
        with patch.object(B.asmpatch, "find_armips", side_effect=B.asmpatch.AsmError("armips not found")):
            with self.assertRaises(FileNotFoundError):
                B._armips()
        with patch.object(B.asmpatch, "find_armips", return_value="/x/armips"), \
                patch.object(B.asmpatch, "check_armips", side_effect=B.asmpatch.AsmError("is armips v0.10.0")):
            with self.assertRaises(B.ToolchainError):
                B._armips()
            with patch.object(B, "_expected_rom", side_effect=lambda *a: B._armips()):
                result = B.check_boundary(self.path, self.path, self.path)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], ["wrong toolchain, cannot derive declared translation boundary: "
                                            "is armips v0.10.0"])


if __name__ == "__main__":
    unittest.main()
