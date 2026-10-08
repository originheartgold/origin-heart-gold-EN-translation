#!/usr/bin/env python3
"""Unit tests for asmpatch.py (the armips code/data fix engine). Run:
    ARMIPS=/path/to/armips python3 -m unittest -v work/tools/test_asmpatch.py
Tests that assemble are skipped when armips v0.11.0 is not found ($ARMIPS, then PATH); the ROM tests are
also skipped when work/rom/origin_v4.0.3_cn.nds is missing. The ROM tests compare the assembled binaries with
golden SHA-1s (GOLDEN), recorded on 2026-10-08 from the run that proved the armips sources write exactly the
bytes of the retired Python engine, per fix and all together (work/notes/toolchain.md). The antipiracy entry
was added on 2026-10-08 when the fix was ported from code_patches.json: its overlay114 equals the one of the
text-speed release candidate (fb5fa7e), built by the retired Python engine; the text-speed entry the same
day, when its armips source replaced text_speed_patch.apply(): arm9 (with the grown ITCM block), overlays 50 and
92 equal the release candidate's, alone and together with every other fix; overworld-texture-frame-bounds
was added later from a build equal to its code_patches.json original (same note)."""
import hashlib
import os
import re
import shutil
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asmpatch as A  # noqa: E402
import fixes as F  # noqa: E402

ROM_CN = HERE.parent / "rom" / "origin_v4.0.3_cn.nds"
ASM_FIXES = ("outfit-chooser-strings", "namelen", "naming-keyboard", "msgload", "pcbox-name-width", "ivev-panel",
             "antipiracy", "text-speed", "overworld-texture-frame-bounds")
# SHA-1 of every binary each fix changes (alone, and all together as "all") and of the y9 overlay table
GOLDEN = {
    "outfit-chooser-strings": {
        "overlay58": "8fb5f17c824265a0e8da07803410d5d4999b84a4",
        "y9": "90ebb4a7ba151c4e4d3ae19a06be6f06451dabb1"
    },
    "namelen": {
        "arm9": "4f353f1e220d6ef9ac9ff967c3f7f3fbdd5ba68d",
        "overlay44": "bb8393e2d4c2cd05a094e984597a0de6ce0bd841",
        "overlay49": "dc255061037a45f36d47c7698418f70874c7a035",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "naming-keyboard": {
        "arm9": "3b513dfb3737a997d300a8977bc1cf1b5304bacb",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "msgload": {
        "arm9": "17255012a4c3660b4c872c28b5aa3fb82116b4e9",
        "overlay17": "5015627c82275c7836897b67dfec73c662015635",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "pcbox-name-width": {
        "overlay16": "87cd982681b4164781e92a68994d6190c54d7a35",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "ivev-panel": {
        "arm9": "0c8fd98f8d8fc6e314892055612ebcbaa412f0eb",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "overworld-texture-frame-bounds": {
        "arm9": "e7f21ac23a61fc752c0d0f8e891c93dd205dab41",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "antipiracy": {
        "overlay114": "2ab9890fab31a6b5fa4e432652ffb1a5b5d40a3c",
        "y9": "14a857a74185e918becc63b963a4a7b5a0cf8688"
    },
    "text-speed": {
        "arm9": "6586b58024a267d629e9e9b32d9a4805adc355cc",
        "overlay50": "a6ddf367a7042d7daf573cb5c513ebfb1f4b570f",
        "overlay92": "67f29acd4adb19f049923cd35dc3931a66ff85d3",
        "y9": "25d4a33a740ce2bb960ed27a8afa1a0d3b56208f"
    },
    "all": {
        "arm9": "a7953cc1a9a92c02c7498019618d948e53c4b173",
        "overlay16": "87cd982681b4164781e92a68994d6190c54d7a35",
        "overlay17": "5015627c82275c7836897b67dfec73c662015635",
        "overlay44": "bb8393e2d4c2cd05a094e984597a0de6ce0bd841",
        "overlay49": "dc255061037a45f36d47c7698418f70874c7a035",
        "overlay50": "a6ddf367a7042d7daf573cb5c513ebfb1f4b570f",
        "overlay58": "8fb5f17c824265a0e8da07803410d5d4999b84a4",
        "overlay92": "67f29acd4adb19f049923cd35dc3931a66ff85d3",
        "overlay114": "2ab9890fab31a6b5fa4e432652ffb1a5b5d40a3c",
        "y9": "3483751df97682d807071808d46d411fd316a428"
    }
}



def _armips():
    try:
        p = A.find_armips()
        A.check_armips(p)
        return p
    except A.AsmError:
        return None


ARMIPS = _armips()
needs_armips = unittest.skipUnless(ARMIPS, f"armips {A.PINNED_VERSION} not found ($ARMIPS or PATH)")


class Charmap(unittest.TestCase):
    def test_charmap_inc_matches_charmap_tsv(self):
        tsv = {}
        for line in (HERE / "charmap_en.tsv").read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            code, text = line.split("\t", 1)
            tsv.setdefault(text, int(code, 16))
        inc = (A.INCLUDE_DIR / "charmap.inc").read_text(encoding="utf-8")
        n = 0
        for mo in re.finditer(r"^(\w+)\s+equ\s+0x([0-9A-F]{4})\s+;\s*(.*)$", inc, re.M):
            name, code, comment = mo.group(1), int(mo.group(2), 16), mo.group(3)
            ch = {"ideographic space U+3000": "　", "' '": " "}.get(comment, comment)
            with self.subTest(name=name):
                self.assertEqual(tsv.get(ch), code, f"{name} = {code:#06x}, the charmap has {ch!r} at "
                                                    f"{tsv.get(ch, 0):#06x}")
            n += 1
        self.assertGreater(n, 100)
        names = [mo.group(1).lower() for mo in re.finditer(r"^(\w+)\s+equ", inc, re.M)]
        self.assertEqual(len(names), len(set(names)), "armips names are case-insensitive")

    def test_charmap_tbl_is_current(self):
        self.assertEqual(A.CHARMAP_TBL.read_bytes(), A.charmap_tbl().encode("utf-8"),
                         "regenerate: python3 work/tools/asmpatch.py tbl")
        tbl = A.charmap_tbl()
        self.assertIn("\n2B01=A\n", tbl)          # 0x012B, written little-endian
        self.assertIn("\nDE01= \n", tbl)          # space: the lowest of its codes
        self.assertTrue(tbl.endswith("\n/FFFF\n"))


class Listing(unittest.TestCase):
    def test_double_writes_of_an_empty_listing(self):
        self.assertEqual(A.double_writes(""), [])
        self.assertEqual(A.double_writes("not a listing line\n"), [])


class Locate(unittest.TestCase):
    def test_find_armips_explicit_env_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "armips"
            fake.write_text("#!/bin/sh\necho 'armips assembler v0.10.0 (Jan 1 2020) by Kingcom'\nexit 1\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(A.find_armips(str(fake), env={}), str(fake.resolve()))
            self.assertEqual(A.find_armips(None, env={A.ENV_VAR: str(fake)}), str(fake.resolve()))
            with self.assertRaises(A.AsmError) as cm:
                A.find_armips(str(Path(td) / "nope"), env={})
            self.assertIn("--armips not found", str(cm.exception))
            with self.assertRaises(A.AsmError) as cm:
                A.find_armips(None, env={A.ENV_VAR: str(Path(td) / "nope")})
            self.assertIn("$ARMIPS not found", str(cm.exception))
            self.assertEqual(A.armips_version(fake), "v0.10.0")
            with self.assertRaises(A.AsmError) as cm:
                A.check_armips(fake)
            self.assertIn("pinned to v0.11.0", str(cm.exception))
            fake.write_text("#!/bin/sh\necho hello\n")
            with self.assertRaises(A.AsmError) as cm:
                A.armips_version(fake)
            self.assertIn("does not look like armips", str(cm.exception))

    def test_relative_armips_path_is_made_absolute(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "bin").mkdir()
            fake = Path(td) / "bin" / "armips"
            fake.write_text("#!/bin/sh\necho 'armips assembler v0.11.0 (Jan 1 2020) by Kingcom'\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            old = Path.cwd()
            os.chdir(td)
            try:
                for how in ({"explicit": "bin/armips", "env": {}}, {"env": {A.ENV_VAR: "./bin/armips"}}):
                    p = A.find_armips(**how)
                    self.assertTrue(Path(p).is_absolute(), p)
                    self.assertEqual(p, str(fake.resolve()))
                with self.assertRaises(A.AsmError) as cm:
                    A.find_armips("bin/nope", env={})
                self.assertIn("--armips not found or not executable: bin/nope", str(cm.exception))
            finally:
                os.chdir(old)
            self.assertEqual(A.armips_version(p), "v0.11.0")       # still runs from another directory
            fake.chmod(0o644)                                      # a path that is not executable
            with self.assertRaises(A.AsmError):
                A.find_armips(str(fake), env={})

    def test_armips_that_cannot_run_is_an_asm_error(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / "t"
            d.mkdir()
            (d / "t.asm").write_text('.open "arm9.bin", 0x02000000\n.close\n', encoding="utf-8")
            fx = {"id": "t", "kind": "code", "asm": "t.asm", "_path": d / "fix.toml",
                  "code": [{"id": "t-1", "file": "arm9", "offset": "0x0", "expect": "0x0000", "notes": "n"}]}
            with self.assertRaises(A.AsmError) as cm:
                A.assemble([fx], {"arm9": bytes(8)}, str(Path(td) / "missing" / "armips"))
            self.assertIn("fix t: cannot run armips", str(cm.exception))


@needs_armips
class Assemble(unittest.TestCase):
    """Synthetic fixes over a 64-byte 'arm9' image."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name) / "t"
        self.dir.mkdir()

    def tearDown(self):
        self.td.cleanup()

    def fix(self, body, regions=(("t-1", "0x10", "0x0000"),)):
        (self.dir / "t.asm").write_text('.nds\n.thumb\n.include "../include/guards.inc"\n'
                                        '.open "arm9.bin", 0x02000000\n' + body + "\n.close\n", encoding="utf-8")
        return {"id": "t", "kind": "code", "asm": "t.asm", "_path": self.dir / "fix.toml",
                "code": [{"id": i, "file": "arm9", "offset": o, "expect": e, "notes": "n"} for i, o, e in regions]}

    def run_fix(self, fx, data=bytes(64)):
        new, rows, srows = A.assemble([fx], {"arm9": data}, ARMIPS)
        self.assertEqual(srows, [])
        return new, rows

    def test_writes_inside_its_region(self):
        new, rows = self.run_fix(self.fix(".org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\n.endarea"))
        self.assertEqual(new["arm9"][0x10:0x12], bytes([0x07, 0x23]))
        self.assertEqual(new["arm9"][:0x10] + new["arm9"][0x12:], bytes(62))
        self.assertEqual(rows, [{"id": "t-1", "file": "arm9", "offset": "0x10", "old": "0x0", "new": "0x2307",
                                 "fix": "t", "engine": "armips"}])

    def test_wrong_guard_in_asm_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\nexpect16 0x2305 ; mov r3, #5\nmov r3, #7"))
        msg = str(cm.exception)
        self.assertIn("fix t: armips failed", msg)
        self.assertIn("nothing was written", msg)
        self.assertIn("guard failed at 02000010: expected 2305, found 0000", msg)

    def test_wrong_toml_expect_fails_before_armips(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\nmov r3, #7", regions=(("t-1", "0x10", "0x2305"),)))
        self.assertIn("region t-1: arm9+0x10 is 0x0, expected 0x2305 (fix.toml expect)", str(cm.exception))

    def test_write_outside_region_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\nmov r3, #7\n.org 0x02000020\n.halfword 0x1234"))
        self.assertIn("arm9.bin+0x20..0x22 (RAM 0x02000020) changed, outside every region", str(cm.exception))

    def test_region_left_unchanged_fails(self):
        fx = self.fix(".org 0x02000010\nmov r3, #7", regions=(("t-1", "0x10", "0x0000"), ("t-2", "0x30", "0x0000")))
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(fx)
        self.assertIn("region t-2 declared in fix.toml, but the asm left it unchanged", str(cm.exception))

    def test_growing_the_file_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\nmov r3, #7\n.org 0x02000040\n.halfword 1"))
        self.assertIn("arm9.bin changed size 0x40 -> 0x42", str(cm.exception))

    def test_area_overflow_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\n.area 2\n.halfword 1, 2\n.endarea"))
        self.assertIn("Area overflowed", str(cm.exception))

    def test_double_write_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\nmov r3, #7\n.org 0x02000010\nmov r3, #8"))
        msg = str(cm.exception)
        self.assertIn("writes the same bytes more than once", msg)
        self.assertIn("arm9.bin+0x10..0x12 written twice (t.asm:6 and t.asm:8)", msg)

    def test_double_write_check_ignores_moves_and_labels(self):
        new, rows = self.run_fix(self.fix(".org 0x02000010\nlab:\n.area 4\n.halfword 1\n.endarea\n"
                                          ".org 0x02000020\n.org 0x02000012\n.halfword 2",
                                          regions=(("t-1", "0x10", "0000 0000"),)))
        self.assertEqual(new["arm9"][0x10:0x14], bytes([1, 0, 2, 0]))

    # regression cases from the step-2 review (d, e, l, o; 0x80 moved to 0x30 to fit the 64-byte image)
    def test_double_write_with_definelabel_between(self):          # case d: label value below the write
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(".org 0x02000010\n.halfword 1\n.definelabel foo, 0x02000000\n"
                                  ".org 0x02000030\n.halfword 1\n.org 0x02000010\n.halfword 5",
                                  regions=(("t-1", "0x10", "0x0000"), ("t-2", "0x30", "0x0000"))))
        self.assertIn("arm9.bin+0x10..0x12 written twice", str(cm.exception))

    def test_definelabel_above_is_not_a_double_write(self):        # case e: label value above the write
        new, _ = self.run_fix(self.fix(".org 0x02000010\n.halfword 1\n.definelabel foo, 0x020000F0\n"
                                       ".org 0x02000030\n.halfword 1",
                                       regions=(("t-1", "0x10", "0x0000"), ("t-2", "0x30", "0x0000"))))
        self.assertEqual((new["arm9"][0x10], new["arm9"][0x30]), (1, 1))

    def test_reopen_at_another_base_is_keyed_by_file_offset(self):  # case l
        new, _ = self.run_fix(self.fix(".org 0x02000010\n.halfword 1\n.close\n.open \"arm9.bin\", 0x02000010\n"
                                       ".org 0x02000010\n.halfword 2",
                                       regions=(("t-1", "0x0", "0x0000"), ("t-2", "0x10", "0x0000"))))
        self.assertEqual((new["arm9"][0x0], new["arm9"][0x10]), (2, 1))

    def test_headersize_change_is_keyed_by_file_offset(self):        # case o
        new, _ = self.run_fix(self.fix(".org 0x02000010\n.halfword 1\n.headersize 0x02000010\n"
                                       ".org 0x02000010\n.halfword 2",
                                       regions=(("t-1", "0x0", "0x0000"), ("t-2", "0x10", "0x0000"))))
        self.assertEqual((new["arm9"][0x0], new["arm9"][0x10]), (2, 1))

    def test_change_spanning_adjacent_regions_is_inside(self):
        new, rows = self.run_fix(self.fix(".org 0x02000010\n.word 0x22221111",
                                          regions=(("t-1", "0x10", "0x0000"), ("t-2", "0x12", "0x0000"))))
        self.assertEqual([r["new"] for r in rows], ["0x1111", "0x2222"])

    def test_new_file_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix('.org 0x02000010\nmov r3, #7\n.close\n.create "extra.bin", 0\n.halfword 1'))
        self.assertIn("created or removed files: ['extra.bin']", str(cm.exception))


@needs_armips
class StringsAndGrowth(unittest.TestCase):
    """A synthetic strings fix over a 32-byte 'overlay58' at 0x021E0000 that may grow."""
    BASE = 0x021E0000

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name) / "t"
        self.dir.mkdir()
        cm = A.charmap()
        import msgtool as m
        self.u = lambda t: struct.pack(f"<{len(m.encode_text(t, cm))}H", *m.encode_text(t, cm))
        d = bytearray(32)
        struct.pack_into("<I", d, 0, self.BASE + 0x10)          # pointer to the slot
        d[0x10:0x18] = self.u("形象1")                          # 3 characters + end
        self.image = bytes(d)

    def tearDown(self):
        self.td.cleanup()

    def fix(self, body, en="Outfit 1", grow=64, pointers=True):
        (self.dir / "t.asm").write_text('.nds\n.include "../include/guards.inc"\n'
                                        '.loadtable "../include/charmap.tbl", "UTF-8"\n'
                                        '.open "overlay58.bin", 0x021E0000\n' + body + "\n.close\n",
                                        encoding="utf-8")
        e = {"id": "overlay58:0x10", "file": "overlay58", "offset": "0x10", "zh": "形象1", "en": en,
             "max_units": 3, "reloc_max_units": 15}
        if pointers:
            e["pointers"] = ["0x0"]
        fx = {"id": "t", "kind": "strings", "asm": "t.asm", "_path": self.dir / "fix.toml", "string": [e]}
        if grow:
            fx["grow"] = [{"file": "overlay58", "max": grow}]
        return fx

    RELOC = (".org 0x021E0010\n.area 8\nexpect32_at 0, 0x0BFB05C5\n.fill 8, 0xFF\n.endarea\n"
             ".org 0x021E0000\nexpect32 0x021E0010\n.word new\n"
             ".org 0x021E0020\nexpect_end\nnew: .string \"Outfit 1\"\n.align 4, 0xFF")

    def run_fix(self, fx, layout=None):
        layout = layout if layout is not None else {"overlay58": (self.BASE, 32, 0)}
        return A.assemble([fx], {"overlay58": self.image}, ARMIPS, {"overlay58": self.BASE}, layout=layout)

    def test_relocated_string_grows_the_overlay(self):
        new, rows, srows = self.run_fix(self.fix(self.RELOC))
        ov = new["overlay58"]
        self.assertEqual(len(ov), 32 + 20)
        self.assertEqual(struct.unpack_from("<I", ov, 0)[0], self.BASE + 0x20)
        self.assertEqual(ov[0x20:0x32], self.u("Outfit 1"))
        self.assertEqual(ov[0x32:], b"\xff\xff")
        self.assertEqual(rows, [])
        self.assertEqual(srows, [{"id": "overlay58:0x10", "mode": "relocated", "addr": self.BASE + 0x20, "units": 9,
                                  "en": "Outfit 1", "pointers": ["0x0"], "file": "overlay58", "fix": "t"}])

    def test_in_place_string(self):
        new, _, srows = self.run_fix(self.fix('.org 0x021E0010\n.area 8\n.string "OK"\n.fill 2, 0xFF\n.endarea',
                                              en="OK"))
        self.assertEqual(new["overlay58"][0x10:0x18], self.u("OK") + b"\xff\xff")
        self.assertEqual(srows[0]["mode"], "in-place")

    def test_string_differs_from_toml_en(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC, en="Outfit 2"))
        self.assertIn("does not hold fix.toml en 'Outfit 2'", str(cm.exception))

    def test_relocated_too_long_for_its_consumer(self):
        fx = self.fix(self.RELOC)
        fx["string"][0]["reloc_max_units"] = 7
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(fx)
        self.assertIn("relocated it may have at most reloc_max_units = 7", str(cm.exception))

    def test_growth_needs_a_grow_entry(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC, grow=None))
        self.assertIn("overlay58.bin changed size 0x20 -> 0x34 (no [[grow]] for it in fix.toml)", str(cm.exception))

    def test_growth_past_max(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC, grow=16))
        self.assertIn("grew by 20 bytes, its [[grow]] max is 16", str(cm.exception))

    def test_growth_must_stay_word_aligned(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC.replace("\n.align 4, 0xFF", "")))
        self.assertIn("keep it a multiple of 4", str(cm.exception))

    def test_growth_with_bss_or_into_another_overlay(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC), layout={"overlay58": (self.BASE, 32, 4)})
        self.assertIn("overlay58 has .bss (4 bytes)", str(cm.exception))
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC), layout={"overlay58": (self.BASE, 32, 0),
                                                       "overlay9": (self.BASE + 0x24, 0x100, 0)})
        self.assertIn("grown range 0x21e0020-0x21e0034 overlaps overlay9", str(cm.exception))
        # an overlay that also covers the current image is never co-resident: allowed
        self.run_fix(self.fix(self.RELOC), layout={"overlay58": (self.BASE, 32, 0),
                                                   "overlay9": (self.BASE - 0x100, 0x200, 0)})

    def test_growth_without_the_overlay_table_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC), layout={})
        self.assertIn("its overlay-table row is unknown", str(cm.exception))

    def test_expect_end_guard(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix(self.RELOC.replace(".org 0x021E0020\nexpect_end", ".org 0x021E0024\nexpect_end")))
        self.assertIn("guard failed at 021E0024: the file ends at 021E0020", str(cm.exception))

    def test_character_outside_the_table_fails(self):
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(self.fix('.org 0x021E0010\n.area 8\n.string "Ж"\n.endarea', en="Ж"))
        self.assertIn("Failed to encode", str(cm.exception))

    def test_toml_zh_checked_before_armips(self):
        fx = self.fix(self.RELOC)
        fx["string"][0]["zh"] = "形象2"
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(fx)
        self.assertIn("region overlay58:0x10: overlay58+0x10 is", str(cm.exception))


class Synthetic(unittest.TestCase):
    """asmpatch.synthetic: the sources assembled without the ROM over zero-filled stand-ins, guards off."""

    setUp, tearDown, fix, run_fix = Assemble.setUp, Assemble.tearDown, Assemble.fix, Assemble.run_fix

    def run_synthetic(self, fx, data=bytes(64)):
        return A.assemble([fx], A.SyntheticImages({"arm9": data}), ARMIPS)

    def test_stand_ins_cover_every_armips_file(self):
        fixes = F.load_all()
        images, bases, layout = A.synthetic_inputs(A.asm_fixes(fixes))
        self.assertIsInstance(images, A.SyntheticImages)
        sizes = F.load_sizes()
        self.assertEqual({k: len(v) for k, v in images.items()}, {k: v["size"] for k, v in sizes.items()})
        self.assertEqual(set(layout), set(sizes) - {"arm9"})
        # the regions hold their fix.toml expect bytes, everything else is zero
        nl = next(f for f in fixes if f["id"] == "namelen")
        r = A.regions(nl, bases)[0]
        self.assertEqual(images[r.file][r.start:r.end], r.expect)
        with tempfile.TemporaryDirectory() as td:
            shutil.copy(F.PATCHES_DIR / "overlays.toml", td)
            with self.assertRaises(A.AsmError) as cm:
                A.synthetic_inputs([nl], td)
            self.assertIn("no size in work/patches/sizes.toml", str(cm.exception))

    def test_guards_off_name_refused_before_armips(self):
        # without armips: refused before it would run, in a real build and in the synthetic one
        for data in ({"arm9": bytes(64)}, A.SyntheticImages({"arm9": bytes(64)})):
            fx = self.fix(".definelabel GUARDS_OFF, 1\n.org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\n.endarea")
            with self.assertRaises(A.AsmError) as cm:
                A.assemble([fx], data, "/nonexistent/armips")
            self.assertIn("t/t.asm:5: GUARDS_OFF is reserved", str(cm.exception))

    def test_obfuscated_includes_refused_before_armips(self):
        # the review's bypasses: a non-.inc file in include/, reached through a labelled or equ-named include
        good = ".org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\n.endarea"
        with tempfile.TemporaryDirectory() as td:
            inc = Path(td) / "include"
            shutil.copytree(A.INCLUDE_DIR, inc)
            for line in ('lbl: .include "../include/helper.s"', 'F equ "../include/helper.s"\n.include F',
                         '.include"../include/helper.s"', '.include "local.inc"'):
                with self.assertRaises(A.AsmError, msg=line) as cm:
                    A.assemble([self.fix(line + "\n" + good)], {"arm9": bytes(64)}, "/nonexistent/armips",
                               include_dir=inc)
                self.assertIn("write includes as", str(cm.exception))
            (inc / "helper.s").write_text(".definelabel GUARDS_OFF, 1\n")
            with self.assertRaises(A.AsmError) as cm:
                A.assemble([self.fix(good)], {"arm9": bytes(64)}, "/nonexistent/armips", include_dir=inc)
            msg = str(cm.exception)
            self.assertIn("include/helper.s: only .inc includes and .tbl table files", msg)

    @needs_armips
    def test_real_run_refuses_guards_off_in_the_symbol_file(self):
        # the last line of defence: whatever slipped past the static checks, armips's symbol file shows it
        from unittest import mock
        # (GUARDS_REAL keeps the guards on anyway: this guard matches, so armips succeeds and -sym must refuse)
        fx = self.fix(".definelabel GUARDS_OFF, 1\n.org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\n.endarea")
        with mock.patch.object(A, "guards_live_problems", return_value=[]):
            with self.assertRaises(A.AsmError) as cm:
                self.run_fix(fx)
            self.assertIn("GUARDS_OFF was defined while assembling against the ROM", str(cm.exception))
            self.assertIn("guards_off", str(cm.exception))
        self.assertEqual(A.guards_off_symbols("02000000 0\n00000001 guards_off\n00000001 guards_off_x\n"),
                         ["00000001 guards_off"])

    @needs_armips
    def test_guards_real_keeps_the_guards_on(self):
        # a label outside .open defines GUARDS_OFF but escapes -sym; GUARDS_REAL (every real run) keeps the guard
        from unittest import mock
        (self.dir / "t.asm").write_text('.nds\n.thumb\n.include "../include/guards.inc"\nguards_off:\n'
                                        '.open "arm9.bin", 0x02000000\n.org 0x02000010\n.area 2\nexpect16 0x2305\n'
                                        'mov r3, #7\n.endarea\n.close\n', encoding="utf-8")
        fx = {"id": "t", "kind": "code", "asm": "t.asm", "_path": self.dir / "fix.toml",
              "code": [{"id": "t-1", "file": "arm9", "offset": "0x10", "expect": "0x0000", "notes": "n"}]}
        with mock.patch.object(A, "guards_live_problems", return_value=[]):
            with self.assertRaises(A.AsmError) as cm:
                self.run_fix(fx)
        self.assertIn("guard failed at 02000010: expected 2305, found 0000", str(cm.exception))

    @needs_armips
    def test_stale_listing_or_symbol_file_is_not_reused(self):
        # two fixes in one stage: the second "armips" run writes nothing, so the first run's files must not count
        import subprocess
        from unittest import mock
        real_run = subprocess.run
        body = ".org 0x{:08X}\n.area 2\nexpect16 0\nmov r3, #7\n.endarea"
        fx1 = self.fix(body.format(0x02000010))
        d2 = Path(self.td.name) / "u"
        d2.mkdir()
        (d2 / "u.asm").write_text((self.dir / "t.asm").read_text(encoding="utf-8").replace("0x02000010",
                                                                                           "0x02000020"))
        fx2 = {"id": "u", "kind": "code", "asm": "u.asm", "_path": d2 / "fix.toml",
               "code": [{"id": "u-1", "file": "arm9", "offset": "0x20", "expect": "0x0000", "notes": "n"}]}
        for data, want in (({"arm9": bytes(64)}, "armips wrote no symbol file"),
                           (A.SyntheticImages({"arm9": bytes(64)}), "armips wrote no listing")):
            calls = []

            def fake(cmd, calls=calls, **kw):
                calls.append(cmd)
                if len(calls) == 1:
                    return real_run(cmd, **kw)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            with mock.patch.object(A.subprocess, "run", side_effect=fake):
                with self.assertRaises(A.AsmError) as cm:
                    A.assemble([fx1, fx2], data, ARMIPS)
            self.assertIn(f"fix u: {want}", str(cm.exception))

    @needs_armips
    def test_guards_are_off_only_for_synthetic_images(self):
        fx = self.fix(".org 0x02000010\n.area 2\nexpect16 0x2305\nmov r3, #7\n.endarea")
        with self.assertRaises(A.AsmError) as cm:
            self.run_fix(fx)                                   # real images: the guard fires
        self.assertIn("guard failed at 02000010: expected 2305, found 0000", str(cm.exception))
        new, rows, _ = self.run_synthetic(fx)
        self.assertEqual(new["arm9"][0x10:0x12], bytes([0x07, 0x23]))

    @needs_armips
    def test_synthetic_still_catches_overflow_outside_writes_and_double_writes(self):
        cases = [(".org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\nmov r3, #8\n.endarea", "overflow"),
                 (".org 0x02000020\n.area 2\nexpect16 0\nmov r3, #7\n.endarea", "outside every region"),
                 (".org 0x02000010\n.area 2\nexpect16 0\nmov r3, #7\n.endarea\n"
                  ".org 0x02000010\n.area 2\nexpect16 0\nmov r3, #6\n.endarea", "more than once"),
                 (".org 0x02000010\n.area 2\nexpect16 0\nmovs r3, #7\n.endarea", "armips failed")]
        for body, want in cases:
            with self.assertRaises(A.AsmError, msg=want) as cm:
                self.run_synthetic(self.fix(body))
            self.assertIn(want, str(cm.exception).lower() if want == "overflow" else str(cm.exception))

    @needs_armips
    def test_every_source_assembles_without_the_rom(self):
        summary = A.synthetic(ARMIPS)
        self.assertIn(f"{len(ASM_FIXES)} armips fixes assembled without the ROM", summary)


@needs_armips
@unittest.skipUnless(ROM_CN.exists(), "Chinese ROM missing")
class RealFixes(unittest.TestCase):
    """The checked-in sources against the Chinese ROM, compared with GOLDEN."""

    @classmethod
    def setUpClass(cls):
        import hardcoded as hc
        import msgtool as m
        cls.hc, cls.m = hc, m
        cls.fixes = {f["id"]: f for f in F.load_all()}
        cls.cn = m.load_rom(ROM_CN)
        view = hc.RomView(cls.cn)
        cls.keys = ["arm9"] + [f"overlay{i}" for i in sorted(view.ovs)]

    def images(self, rom):
        view = self.hc.RomView(rom)
        return {k: view.get(k) for k in self.keys}, bytes(rom.arm9OverlayTable)

    def assembled(self, ids):
        rom = self.m.load_rom(ROM_CN)
        rep = A.apply(rom, [self.fixes[i] for i in ids], ARMIPS)
        return rom, rep

    def check_golden(self, name, ids):
        orig, orig_t = self.images(self.cn)
        rom, rep = self.assembled(ids)
        imgs, table = self.images(rom)
        changed = {k for k in self.keys if imgs[k] != orig[k]}
        want = GOLDEN[name]
        self.assertEqual(changed, set(want) - {"y9"}, f"{name}: changed files")
        for k in changed:
            self.assertEqual(hashlib.sha1(imgs[k]).hexdigest(), want[k], f"{name}: {k}")
        self.assertEqual(hashlib.sha1(table).hexdigest(), want["y9"], f"{name}: y9 overlay table")
        return rom, rep

    def test_every_armips_fix_has_a_source(self):
        self.assertEqual(sorted(f["id"] for f in A.asm_fixes(self.fixes.values())), sorted(ASM_FIXES))

    def test_antipiracy_stubs(self):
        # the six DS Protect entries in overlay114 return the genuine-cart values 0,1,0,1,0,1 ('mov r0,#n;
        # bx lr', ARM); nothing else in the overlay changes
        fx = self.fixes["antipiracy"]
        self.assertEqual([e["offset"] for e in fx["code"]], ["0x864", "0x94C", "0xA34", "0xB1C", "0xC04", "0xCCC"])
        self.assertTrue(fx["enabled"] and all(e["file"] == "overlay114" for e in fx["code"]))
        orig = self.hc.RomView(self.cn).get("overlay114")
        rom, _ = self.assembled(["antipiracy"])
        new = self.hc.RomView(rom).get("overlay114")
        self.assertEqual(len(new), len(orig))
        offs = [int(e["offset"], 16) for e in fx["code"]]
        changed = {i for i in range(len(orig)) if orig[i] != new[i]}
        self.assertTrue(changed <= {o + k for o in offs for k in range(8)})
        for off, ret in zip(offs, (0, 1, 0, 1, 0, 1), strict=True):
            self.assertEqual(orig[off:off + 8].hex(), "f0472de980d04de2")
            self.assertEqual(struct.unpack_from("<2I", new, off), (0xE3A00000 | ret, 0xE12FFF1E))

    def test_text_speed_itcm_block(self):
        # the payload is .incbin'd at the end of the ITCM autoload block, which ndspy writes back with its
        # autoload table; the main section changes only in the fix's regions and the two autoload words
        import text_speed_patch as speed
        rom, rep = self.assembled(["text-speed"])
        code, cn = rom.loadArm9(), self.cn.loadArm9()
        blob = bytes.fromhex(speed.load_payload()["code"])
        itcm = self.hc.RomView(rom).itcm_section(code)
        self.assertEqual((itcm.ramAddress, len(itcm.data), itcm.bssSize), (0x01FF8000, 0xFA0, 0))
        self.assertEqual(bytes(itcm.data[:0x620]), bytes(cn.sections[1].data))
        self.assertEqual(bytes(itcm.data[0x620:0x620 + len(blob)]), blob)
        self.assertEqual(bytes(itcm.data[0x620 + len(blob):]), bytes(0xFA0 - 0x620 - len(blob)))
        self.assertEqual(bytes(code.sections[2].data), bytes(cn.sections[2].data))       # DTCM unchanged
        new, old = code.sections[0].data, cn.sections[0].data
        own = [(r[1], r[2]) for r in F.footprint(self.fixes["text-speed"]) if r[0] == "arm9"]
        off = cn.codeSettingsOffs
        outside = [i for i in range(len(old)) if new[i] != old[i] and not any(a <= i < b for a, b in own)]
        self.assertEqual(sorted({i & ~3 for i in outside}), [off, off + 4])
        self.assertEqual(A.verify(rom, rep), "ok (0 strings, 9 code regions)")
        # growth past the ITCM reserve is refused
        probs = A.growth_problems("t", "itcm", 0x620, 0x2004, 0x19E0, 0x01FF8000, {"itcm": (0x01FF8000, 0x620, 0)})
        self.assertTrue(any("past 0x1ffa000" in p for p in probs), probs)

    def test_each_fix_matches_golden(self):
        for fid in ASM_FIXES:
            with self.subTest(fix=fid):
                _, rep = self.check_golden(fid, [fid])
                self.assertEqual({r["fix"] for r in rep["code_regions"] + rep["strings"]}, {fid})

    def test_all_fixes_together_match_golden(self):
        rom, rep = self.check_golden("all", ASM_FIXES)
        self.assertEqual(len(rep["code_regions"]), 45)
        self.assertEqual([(r["id"], r["mode"], r["en"]) for r in rep["strings"]],
                         [("overlay58:0x6F0", "in-place", "OK"), ("overlay58:0x6F6", "relocated", "Outfit 1"),
                          ("overlay58:0x6FE", "relocated", "Outfit 3"), ("overlay58:0x706", "relocated", "Outfit 2")])
        self.assertEqual(rep["armips"]["version"], A.PINNED_VERSION)
        self.assertEqual(A.verify(rom, rep), "ok (4 strings, 45 code regions)")
        view = self.hc.RomView(rom)
        self.assertEqual(view.table_ram_size(58), 0x818)
        self.assertEqual(rep["grown"], {"overlay58": {"from": 0x7E0, "to": 0x818},
                                        "overlay50": {"from": 0x1600, "to": 0x171C},
                                        "itcm": {"from": 0x620, "to": 0xBE0}})
        # a y9 ramSize that does not follow the grown overlay is caught
        t = bytearray(rom.arm9OverlayTable)
        row = next(r for r in range(len(t) // 32) if struct.unpack_from("<I", t, r * 32)[0] == 58)
        struct.pack_into("<I", t, row * 32 + 8, 0x7E0)
        rom.arm9OverlayTable = bytes(t)
        with self.assertRaises(A.AsmError) as cm:
            A.verify(rom, rep)
        self.assertIn("y9 ramSize 0x7e0", str(cm.exception))
        # a build report from before the rename ("code_patches") still verifies
        old = {k: v for k, v in rep.items() if k not in ("code_regions", "grown")}
        old["code_patches"] = rep["code_regions"]
        self.assertEqual(A.verify(rom, old), "ok (4 strings, 45 code regions)")
        # no Chinese left in the chooser
        cm_zh = self.m.Charmap.load([self.hc.ZH_CHARMAP])
        self.assertEqual(list(self.hc.scan_blob(view.get("overlay58"), cm_zh, self.hc._bigrams())), [])

    def test_verify_catches_a_changed_rom(self):
        rom, rep = self.assembled(["outfit-chooser-strings"])
        view = self.hc.RomView(rom)
        ov = bytearray(view.get("overlay58"))
        ov[0x7E0] ^= 1
        view.set("overlay58", bytes(ov))
        with self.assertRaises(A.AsmError):
            A.verify(rom, rep)

    def copy_fix(self, fid, edit):
        """A copy of a real fix whose asm is changed by edit(text) -> text, in a temp registry."""
        td = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, td)
        src = self.fixes[fid]["_path"].parent
        dst = Path(td) / fid
        shutil.copytree(src, dst)
        asm = dst / self.fixes[fid]["asm"]
        asm.write_text(edit(asm.read_text(encoding="utf-8")), encoding="utf-8")
        return dict(self.fixes[fid], _path=dst / "fix.toml")

    def test_wrong_guard_in_a_real_source_fails(self):
        fx = self.copy_fix("namelen", lambda t: t.replace("expect16 0x2305", "expect16 0x2306", 1))
        rom = self.m.load_rom(ROM_CN)
        before = self.images(rom)
        with self.assertRaises(A.AsmError) as cm:
            A.apply(rom, [fx], ARMIPS)
        msg = str(cm.exception)
        self.assertIn("fix namelen: armips failed", msg)
        self.assertIn("guard failed at 021E49CE: expected 2306, found 2305", msg)
        self.assertEqual(self.images(rom), before)

    def test_real_source_writing_outside_its_regions_fails(self):
        fx = self.copy_fix("ivev-panel", lambda t: t.replace(
            ".close", ".org 0x0208C278\n    mov r2, #0x46     ; the EV column: not declared\n.close"))
        rom = self.m.load_rom(ROM_CN)
        with self.assertRaises(A.AsmError) as cm:
            A.apply(rom, [fx], ARMIPS)
        self.assertIn("fix ivev-panel: arm9.bin+0x8c278..0x8c279 (RAM 0x0208C278) changed, outside every region",
                      str(cm.exception))


    def test_real_strings_source_differing_from_toml_fails(self):
        fx = self.copy_fix("outfit-chooser-strings", lambda t: t.replace('.string "Outfit 3"', '.string "Outfit 4"'))
        rom = self.m.load_rom(ROM_CN)
        before = self.images(rom)
        with self.assertRaises(A.AsmError) as cm:
            A.apply(rom, [fx], ARMIPS)
        self.assertIn("overlay58:0x6FE: overlay58.bin+0x7f2 does not hold fix.toml en 'Outfit 3'", str(cm.exception))
        self.assertEqual(self.images(rom), before)


if __name__ == "__main__":
    unittest.main()
