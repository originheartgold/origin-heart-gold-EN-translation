"""Exercise the boundary guard with deliberate duplicate-codec regressions."""
import tempfile
import unittest
from pathlib import Path

import check_save_architecture as A


class Architecture(unittest.TestCase):
    def test_current_production_boundary(self):
        self.assertEqual(A.scan(), [])
        self.assertEqual(A.scan_editor(), [])

    def test_editor_wrappers_cannot_reintroduce_implementations(self):
        for name, expected in A.EDITOR_REEXPORTS.items():
            with self.subTest(name=name):
                self.assertEqual(A.editor_violations("/* documentation */\n" + expected, name), [])
                self.assertTrue(A.editor_violations(expected + "\nfunction crc16(data) { return 0; }", name))
                self.assertTrue(A.editor_violations(expected.replace("../../../save-core/dist/", "./local/"), name))

    def test_editor_scan_tracks_moved_modules_and_rejects_stale_graph(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "src"
            core = source / "core"
            core.mkdir(parents=True)
            for name, expected in A.EDITOR_REEXPORTS.items():
                (core / f"{name}.ts").write_text(expected)
            self.assertEqual(A.scan_editor(core), [])
            # A duplicate codec in the previous entry point cannot hide behind
            # correct new wrappers: a consumer might still import this old path.
            (source / "pokemon.ts").write_text("export function decrypt() {}")
            self.assertTrue(any("legacy module" in row for row in A.scan_editor(core)))
            (source / "pokemon.ts").unlink()
            # The new binary editors are subject to the same single-source rule.
            (core / "trainer.ts").write_text("export function patchTrainer() {}")
            self.assertTrue(any("src/core/trainer.ts" in row for row in A.scan_editor(core)))
            (core / "trainer.ts").write_text(A.EDITOR_REEXPORTS["trainer"])
            (core / "save.ts").unlink()
            self.assertTrue(any("src/core/save.ts: shared-core compatibility module is missing" in row
                                for row in A.scan_editor(core)))

    def test_reintroduced_crypto_caught_in_new_harness_module(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "save_core.py").write_text("# transport only\n")
            (root / "emu_new_recipe.py").write_text(
                "def scramble(seed, word):\n"
                "    seed = (seed * 1103515245 + 24691) & 0xffffffff\n"
                "    return word ^ (seed >> 16)\n")
            findings = A.scan(root)
            self.assertTrue(any("emu_new_recipe.py:2:" in row for row in findings), findings)

    def test_checksum_alias_rejected(self):
        findings = A.violations("from binascii import crc_hqx as checksum\nchecksum(data, 65535)\n", "emu_bad.py")
        self.assertTrue(any("including aliases" in row for row in findings))

    def test_reintroduced_raw_save_writer_rejected(self):
        for operation in ["struct.pack_into('<H', self._data, 6, value)",
                          "self._data[6:8] = value.to_bytes(2, 'little')",
                          "self._data = bytearray(self._data)"]:
            with self.subTest(operation=operation):
                source = f"class SaveFile:\n    def edit(self, value):\n        {operation}\n"
                self.assertTrue(A.violations(source, "emu_harness.py"))

    def test_oracles_are_independent_and_emulator_memory_remains_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "save_core.py").write_text("# bridge\n")
            oracle = "def independent(seed):\n    return seed * 0x41c64e6d + 0x6073\n"
            for filename in ["memcheck.py", "quality_runner.py", "test_emu_new.py"]:
                (root / filename).write_text(oracle)
            (root / "emu_new.py").write_text(
                "def native_input(h):\n    h.w32(0x02000000, 123)\n"
                "    return struct.pack('<H', 7)\n")
            self.assertEqual(A.scan(root), [])

    def test_comments_strings_and_bridge_delegation_are_allowed(self):
        source = '''
# old codec used 0x41c64e6d; this comment isn't an implementation.
documentation = "crc_hqx(data, 0xffff)"
def encode_pokemon(raw, **fields):
    return core.patch_pokemon(raw, **fields)
'''
        self.assertEqual(A.violations(source, "emu_harness.py"), [])
