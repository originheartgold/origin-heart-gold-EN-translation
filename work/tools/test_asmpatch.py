#!/usr/bin/env python3
"""Unit tests for asmpatch.py (the armips code/data fix engine). Run:
    ARMIPS=/path/to/armips python3 -m unittest -v work/tools/test_asmpatch.py
Tests that assemble are skipped when armips v0.11.0 is not found ($ARMIPS, then PATH); the ROM tests are
also skipped when work/rom/origin_v4.0.3_cn.nds is missing. The ROM tests prove that the armips sources write
exactly the bytes of the legacy Python engine (legacy_code_patches.toml), per fix and all together."""
import re
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asmpatch as A  # noqa: E402
import fixes as F  # noqa: E402

ROM_CN = HERE.parent / "rom" / "origin_v4.0.3_cn.nds"
CODE_FIXES = ("namelen", "naming-keyboard", "msgload", "pcbox-name-width", "ivev-panel")


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


class Locate(unittest.TestCase):
    def test_find_armips_explicit_env_and_missing(self):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "armips"
            fake.write_text("#!/bin/sh\necho 'armips assembler v0.10.0 (Jan 1 2020) by Kingcom'\nexit 1\n")
            fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(A.find_armips(str(fake), env={}), str(fake))
            self.assertEqual(A.find_armips(None, env={A.ENV_VAR: str(fake)}), str(fake))
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
        return A.assemble([fx], {"arm9": data}, ARMIPS)

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
@unittest.skipUnless(ROM_CN.exists(), "Chinese ROM missing")
class RealFixes(unittest.TestCase):
    """The checked-in sources against the Chinese ROM, compared with the legacy Python engine."""

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

    def both(self, ids):
        fixes = [self.fixes[i] for i in ids]
        py = self.m.load_rom(ROM_CN)
        self.hc.apply(py, cfg={"files": {}, "strings": []}, code_patches=self.hc.load_code_patches(fixes=fixes))
        asm = self.m.load_rom(ROM_CN)
        rep = A.apply(asm, fixes, ARMIPS)
        return self.images(py), self.images(asm), rep

    def test_every_code_fix_has_a_source(self):
        self.assertEqual(sorted(f["id"] for f in F.code_entries_fixes(self.fixes.values())), sorted(CODE_FIXES))

    def test_each_fix_equals_the_python_engine(self):
        orig, _ = self.images(self.cn)
        for fid in CODE_FIXES:
            with self.subTest(fix=fid):
                (py, py_t), (asm, asm_t), rep = self.both([fid])
                self.assertEqual(py_t, asm_t)
                for k in self.keys:
                    self.assertEqual(py[k], asm[k], f"{fid}: {k} differs between the engines")
                self.assertTrue(any(asm[k] != orig[k] for k in self.keys), fid)
                self.assertEqual({r["fix"] for r in rep["code_patches"]}, {fid})

    def test_all_fixes_together_equal_the_python_engine(self):
        (py, py_t), (asm, asm_t), rep = self.both(CODE_FIXES)
        self.assertEqual(py_t, asm_t)
        for k in self.keys:
            self.assertEqual(py[k], asm[k], f"{k} differs between the engines")
        self.assertEqual(len(rep["code_patches"]), 29)
        self.assertEqual(rep["armips"]["version"], A.PINNED_VERSION)
        # the report is what hardcoded.verify reads back
        rom = self.m.load_rom(ROM_CN)
        rep = A.apply(rom, [self.fixes[i] for i in CODE_FIXES], ARMIPS)
        self.assertEqual(self.hc.verify(rom, {"strings": [], "code_patches": rep["code_patches"],
                                              "files": rep["files"]}), "ok (0 strings, 29 code patches)")

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


if __name__ == "__main__":
    unittest.main()
