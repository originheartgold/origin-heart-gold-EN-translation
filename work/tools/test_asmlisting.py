#!/usr/bin/env python3
"""Unit tests for asmlisting.py (the disassembly snapshots work/patches/<id>/<id>.listing). Run:
    ARMIPS=/path/to/armips python3 -m unittest -v work/tools/test_asmlisting.py
The disassembly tests need capstone (skipped without it); the tests that assemble need armips v0.11.0 and the
Chinese ROM (skipped without them): the committed snapshots must be current, and a changed source must make
its snapshot stale."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asmlisting as L  # noqa: E402
import asmpatch as A  # noqa: E402
import fixes as F  # noqa: E402

try:
    import capstone  # noqa: F401
    HAVE_CS = True
except ImportError:
    HAVE_CS = False
needs_cs = unittest.skipUnless(HAVE_CS, "capstone not installed (work/tools/requirements-dev.txt)")


def _armips():
    try:
        p = A.find_armips()
        A.check_armips(p)
        return p
    except A.AsmError:
        return None


ARMIPS = _armips()


def hw(*units):
    return b"".join(u.to_bytes(2, "little") for u in units)


@needs_cs
class Disassemble(unittest.TestCase):
    def test_thumb(self):
        rows = L.disassemble(hw(0x2305, 0xF7FC, 0xFAC2), 0x02042862, "thumb", {0x0203EDEC: "CallTask"})
        self.assertEqual(rows[0], (0x02042862, "2305", "movs r3, #5"))
        self.assertEqual(rows[1], (0x02042864, "F7FC FAC2", "bl #0x203edec  ; CallTask"))

    def test_arm(self):
        rows = L.disassemble(bytes.fromhex("0000a0e31eff2fe1"), 0x02263A64, "arm")
        self.assertEqual(rows, [(0x02263A64, "E3A00000", "mov r0, #0"), (0x02263A68, "E12FFF1E", "bx lr")])

    def test_undecodable_bytes_are_shown_as_data(self):
        rows = L.disassemble(hw(0xF000), 0x02000000, "thumb")      # half a bl
        self.assertEqual(rows, [(0x02000000, "F000", ".hword 0xF000")])


def fake(old, new, listing="", areas=(), key="arm9", regions=(("t-1", "0x10", "0x2305"),)):
    fx = {"id": "t", "kind": "code", "code": [{"id": i, "file": key, "offset": o, "expect": e, "notes": "n"}
                                              for i, o, e in regions]}
    return L.Assembled(fx, {key: old}, {key: new}, {}, listing, {"areas": list(areas)})


@needs_cs
class RenderArea(unittest.TestCase):
    def area(self, start, size, mode="thumb", writes=("insn",)):
        return {"file": "arm9", "base": 0x02000000, "start": start, "size": size, "mode": mode,
                "appended": False, "writes": list(writes)}

    def render(self, asm, area):
        changed = {k: L._changed_offsets(asm.old[k], asm.new[k]) for k in asm.old}
        return L.render_area(asm, area, {}, changed, {k: L.write_rows(asm, k) for k in asm.old})

    def test_code_area_with_context(self):
        old = hw(0x9000, 0x2050, 0x2305, 0x9101, 0x2000, 0x4770) + bytes(4)
        new = hw(0x9000, 0x2050, 0x2307, 0x9101, 0x2000, 0x4770) + bytes(4)
        out = self.render(fake(old, new, regions=(("t-1", "0x4", "0x2305"),)), self.area(0x02000004, 2))
        self.assertEqual(out[0], "== arm9+0x4 (RAM 0x02000004), 2 bytes, thumb: t-1")
        self.assertEqual([ln[:2] for ln in out[1:]], ["  ", "  ", "- ", "+ ", "  ", "  "])
        self.assertIn("movs r3, #5", out[3])
        self.assertIn("movs r3, #7", out[4])

    def test_context_stops_at_other_edits_and_keeps_bl_pairs(self):
        # the next halfword is changed by the fix too (another area): no context after this one
        old = hw(0x2000, 0x2000, 0x20B5, 0x0080, 0x2000, 0x2000)
        new = hw(0x2000, 0x2000, 0x20CA, 0x0080 | 0x40, 0x2000, 0x2000)
        out = self.render(fake(old, new, regions=(("t-1", "0x4", "0x20B5"),)), self.area(0x02000004, 2))
        self.assertEqual([ln[:2] for ln in out[1:]], ["  ", "  ", "- ", "+ "])
        # a bl that would be cut in half by the 4-byte window is shown whole
        old = hw(0x2000, 0x2305, 0x2000, 0xF7FC, 0xFAC2, 0x2000)
        new = hw(0x2000, 0x2307, 0x2000, 0xF7FC, 0xFAC2, 0x2000)
        out = self.render(fake(old, new, regions=(("t-1", "0x2", "0x2305"),)), self.area(0x02000002, 2))
        self.assertTrue(out[-1].startswith("  02000006  F7FC FAC2  bl "), out)

    def test_data_rows_per_statement(self):
        listing = ('FFFFFFFF .open "arm9.bin",0x02000000 ; /x/t.asm line 3\n'
                   '02000010 .byte 0x04,0x08 ; /x/t.asm line 5\n'
                   '02000012 .halfword 0x0069 ; /x/t.asm line 5\n'
                   '02000014 .endarea ; /x/t.asm line 6\n')
        old = bytes(16) + bytes([4, 7, 0x69, 0])
        new = bytes(16) + bytes([4, 8, 0x69, 0])
        asm = fake(old, new, listing, regions=(("t-1", "0x10", "0704 0069"),))
        out = self.render(asm, self.area(0x02000010, 4, writes=("byte", "halfword")))
        self.assertEqual(out, ["== arm9+0x10 (RAM 0x02000010), 4 bytes, data: t-1",
                               "- 02000010  04 07", "+ 02000010  04 08", "  02000012  0069"])


class SourceLayout(unittest.TestCase):
    """fixes.lint_asm(found=): the areas, their mode and writes, read-only guard blocks, absolute guards."""

    def test_layout(self):
        src = ('; t - Title. D-0001\n.nds\n.include "../include/guards.inc"\n.open "arm9.bin", 0x02000000\n'
               '.org 0x02000100\n    expect16_at 0, 0xB5F8\n    expect16_at 2, 0x2800\n'
               '.thumb\n.org 0x02000010\n.area 2\n    expect16 0x2305\n    mov r3, #7\n.endarea\n'
               '.arm\n.org 0x02000020\n    expect32_abs 0x02000040, 0x02000020\n.area 4\n    expect32 0\n'
               '    .word 1\n.endarea\n.close\n')
        fx = {"id": "t", "kind": "code", "decisions": ["D-0001"],
              "code": [{"id": "a", "file": "arm9", "offset": "0x10", "expect": "0x2305", "notes": "n"},
                       {"id": "b", "file": "arm9", "offset": "0x20", "expect": "0000 0000", "notes": "n"}]}
        found = {}
        self.assertEqual(F.lint_asm(src, fx, name="t.asm", found=found), [])
        self.assertEqual([(a["start"], a["size"], a["mode"], a["writes"]) for a in found["areas"]],
                         [(0x02000010, 2, "thumb", ["insn"]), (0x02000020, 4, "arm", ["word"])])
        self.assertEqual(found["readonly"], [{"file": "arm9", "base": 0x02000000, "start": 0x02000100, "mode": "arm",
                                              "reads": [(0x02000100, 2), (0x02000102, 2)]}])
        self.assertEqual(found["abs"], [("arm9", 0x02000000, 0x02000040, 4)])


class Stale(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        d = Path(self.td.name) / "t"
        d.mkdir()
        (d / "fix.toml").write_text("", encoding="utf-8")
        (d / "t.asm").write_text("", encoding="utf-8")
        self.fx = {"id": "t", "kind": "code", "asm": "t.asm", "_path": d / "fix.toml"}
        self.path = d / "t.listing"

    def tearDown(self):
        self.td.cleanup()

    def test_missing_stale_and_current(self):
        probs = L.stale([self.fx], {"t": "a\nb\n"})
        self.assertTrue(probs and "is missing: python3 work/tools/asmpatch.py listing --write t" in probs[0], probs)
        self.path.write_text("a\nc\n", encoding="utf-8")
        probs = L.stale([self.fx], {"t": "a\nb\n"})
        self.assertEqual(len(probs), 1)
        self.assertIn("is stale (line 2: committed 'c', now 'b')", probs[0])
        self.assertIn("python3 work/tools/asmpatch.py listing --write t", probs[0])
        self.path.write_text("a\nb\n", encoding="utf-8")
        self.assertEqual(L.stale([self.fx], {"t": "a\nb\n"}), [])

    def test_snapshot_of_a_fix_without_asm(self):
        fx = {"id": "t", "kind": "graphics", "_path": self.fx["_path"]}
        self.path.write_text("x\n", encoding="utf-8")
        self.assertIn("has no armips source", L.stale([fx], {})[0])


@needs_cs
@unittest.skipUnless(ARMIPS and F.ROM_CN.exists(), "needs armips v0.11.0 and the Chinese ROM")
class RealSnapshots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import msgtool as m
        cls.m = m
        cls.rom = m.load_rom(str(F.ROM_CN))
        cls.fixes = F.load_all()

    def test_committed_snapshots_are_current(self):
        try:
            L.capstone_version()
        except L.ListingError as ex:
            self.skipTest(str(ex))
        done = L.assemble_each(self.rom, A.asm_fixes(self.fixes), ARMIPS)
        texts = L.snapshots(done, A.armips_version(ARMIPS))
        self.assertEqual(L.stale(self.fixes, texts), [])
        self.assertEqual(set(texts), {f["id"] for f in A.asm_fixes(self.fixes)})

    def test_a_changed_source_makes_its_snapshot_stale(self):
        try:
            L.capstone_version()
        except L.ListingError as ex:
            self.skipTest(str(ex))
        src = F.PATCHES_DIR / "namelen"
        with tempfile.TemporaryDirectory() as td:
            dst = Path(td) / "namelen"
            shutil.copytree(src, dst)
            asm = dst / "namelen.asm"
            asm.write_text(asm.read_text(encoding="utf-8").replace("TRAINER_NAME_LEN equ 7", "TRAINER_NAME_LEN equ 8"),
                           encoding="utf-8")
            fx = dict(next(f for f in self.fixes if f["id"] == "namelen"), _path=dst / "fix.toml")
            texts = L.snapshots(L.assemble_each(self.rom, [fx], ARMIPS), A.armips_version(ARMIPS))
            probs = L.stale([fx], texts)
            self.assertEqual(len(probs), 1, probs)
            self.assertIn("namelen.listing is stale", probs[0])
            self.assertIn("movs r3, #8", probs[0])
            self.assertIn("python3 work/tools/asmpatch.py listing --write namelen", probs[0])


if __name__ == "__main__":
    unittest.main()
