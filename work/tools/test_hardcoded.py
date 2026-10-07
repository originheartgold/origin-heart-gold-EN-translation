#!/usr/bin/env python3
"""Unit tests for hardcoded.py. Run:  python3 -m unittest -v work/tools/test_hardcoded.py
The ROM tests are skipped when work/rom/origin_v4.0.3_cn.nds is missing."""
import json
import re
import struct
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixes as fixreg  # noqa: E402
import hardcoded as hc  # noqa: E402
import msgtool as m  # noqa: E402

CM = m.Charmap.load(hc.CHARMAPS)
ROM_CN = HERE.parent / "rom" / "origin_v4.0.3_cn.nds"
BASE = 0x021E0000


def u(text):
    return struct.pack("<%dH" % len(m.encode_text(text, CM)), *m.encode_text(text, CM))


def image():
    """0x00: pointer to 0x10, 0x04: pointer to 0x18, 0x10: 确认 slot (2), 0x16: 形象1 slot (3), 0x1E: pad."""
    d = bytearray(0x20)
    struct.pack_into("<II", d, 0, BASE + 0x10, BASE + 0x16)
    d[0x10:0x16] = u("确认")
    d[0x16:0x1E] = u("形象1")
    return bytes(d)


def entry(off, zh, en, mx, ptr=None, rmax=None):
    e = {"id": f"t:{off:#x}", "file": "t", "offset": hex(off), "zh": zh, "en": en, "max_units": mx}
    if ptr is not None:
        e["pointers"] = [hex(ptr)]
    if rmax:
        e["reloc_max_units"] = rmax
    return e


class TestPlan(unittest.TestCase):
    def plan(self, entries, grow_max=64, others=(), bss=0, data=None):
        return hc.plan_file("t", entries, data or image(), BASE, CM, {"grow_max": grow_max}, list(others),
                            {"bss": bss})

    def test_in_place_pads_with_end(self):
        new, rows, probs = self.plan([entry(0x16, "形象1", "No1", 3)])
        self.assertEqual(probs, [])
        self.assertEqual(new[0x16:0x1E], u("No1"))
        new, rows, probs = self.plan([entry(0x16, "形象1", "A", 3)])
        self.assertEqual(new[0x16:0x1E], u("A") + b"\xff\xff" * 2)
        self.assertEqual(rows[0]["mode"], "in-place")
        self.assertEqual(len(new), 0x20)

    def test_null_en_untouched(self):
        new, rows, probs = self.plan([entry(0x16, "形象1", None, 3)])
        self.assertEqual((new, rows, probs), (image(), [], []))

    def test_too_long_without_pointer_refused(self):
        _, _, probs = self.plan([entry(0x16, "形象1", "Outfit 1", 3)])
        self.assertTrue(probs and "cannot be relocated" in probs[0])

    def test_relocation(self):
        new, rows, probs = self.plan([entry(0x16, "形象1", "Outfit 1", 3, ptr=4, rmax=15)])
        self.assertEqual(probs, [])
        self.assertEqual(rows[0]["mode"], "relocated")
        self.assertEqual(struct.unpack_from("<I", new, 4)[0], BASE + 0x20)
        self.assertEqual(new[0x20:0x20 + len(u("Outfit 1"))], u("Outfit 1"))
        self.assertEqual(len(new) % 4, 0)
        self.assertEqual(new[0x16:0x1E], b"\xff" * 8)          # old slot blanked
        self.assertEqual(new[:4], image()[:4])                  # other pointer untouched

    def test_relocation_limits(self):
        _, _, probs = self.plan([entry(0x16, "形象1", "A very long outfit", 3, ptr=4, rmax=15)])
        self.assertTrue(probs and "at most 15" in probs[0])
        _, _, probs = self.plan([entry(0x16, "形象1", "Outfit 1", 3, ptr=4, rmax=15)], grow_max=8)
        self.assertTrue(any("grow_max" in p for p in probs))
        _, _, probs = self.plan([entry(0x16, "形象1", "Outfit 1", 3, ptr=4, rmax=15)], bss=4)
        self.assertTrue(any(".bss" in p for p in probs))
        _, _, probs = self.plan([entry(0x16, "形象1", "Outfit 1", 3, ptr=0, rmax=15)])
        self.assertTrue(probs and "do not point" in probs[0])

    def test_growth_overlap_check(self):
        e = [entry(0x16, "形象1", "Outfit 1", 3, ptr=4, rmax=15)]
        _, _, probs = self.plan(e, others=[(9, BASE + 0x24, BASE + 0x100)])
        self.assertTrue(any("overlaps overlay 9" in p for p in probs))
        # an overlay that also covers the current image is never co-resident: allowed
        _, _, probs = self.plan(e, others=[(9, BASE - 0x100, BASE + 0x100)])
        self.assertEqual(probs, [])

    def test_source_changed_refused(self):
        _, _, probs = self.plan([entry(0x10, "形象", "OK", 2)])
        self.assertTrue(probs and "does not hold" in probs[0])

    def test_unencodable_refused(self):
        _, _, probs = self.plan([entry(0x10, "确认", "OЖ", 2)])
        self.assertTrue(probs and "does not encode" in probs[0])


class TestRegistryEntries(unittest.TestCase):
    """The [[string]] and [[code]] entries of work/patches, as hardcoded.py sees them."""

    def test_schema(self):
        cfg = hc.load()
        ids = set()
        for e in cfg["strings"]:
            self.assertEqual(e["id"], f"{e['file']}:{e['offset']}")
            self.assertNotIn(e["id"], ids)
            ids.add(e["id"])
            self.assertEqual(len(m.encode_text(e["zh"], CM)) - 1, e["max_units"], e["id"])
            self.assertTrue(re.fullmatch(r"0x[0-9A-F]+", e["offset"]), e["id"])
            if e.get("pointers"):
                self.assertIn(e["file"], cfg["files"])
        cids = set()
        for cp in hc.load_code_patches():
            self.assertNotIn(cp["id"], cids)
            cids.add(cp["id"])
            self.assertIsInstance(cp["enabled"], bool)
            self.assertTrue(re.fullmatch(r"0x[0-9A-F]+", cp["offset"]), cp["id"])
            self.assertEqual(len(hc.halfwords(cp["expect"])), len(hc.halfwords(cp["value"])), cp["id"])
            self.assertTrue(cp.get("fix"), cp["id"])
        # the legacy (frozen) patches cover exactly the registry's [[code]] regions, by id
        regions = {e["id"]: e for e in fixreg.code_entries(fixreg.load_all())}
        self.assertEqual(cids, set(regions))
        self.assertTrue(all(e.get("notes") for e in regions.values()))

    def test_selection_limits_entries(self):
        import fixes
        act = fixes.select(fixes.load_all(), without="ivev-panel")
        ids = {cp["id"] for cp in hc.load_code_patches(fixes=act)}
        self.assertNotIn("ivev-panel-iv-x", ids)
        self.assertIn("msgload-all", ids)
        self.assertTrue(all(cp["enabled"] for cp in hc.load_code_patches(fixes=act)))
        self.assertEqual(hc.load(fixes=[f for f in act if f["id"] != "outfit-chooser-strings"]),
                         {"files": {}, "strings": []})

    def test_halfwords(self):
        self.assertEqual(hc.halfwords("0x2305"), [0x2305])
        self.assertEqual(hc.halfwords("01DE 012B"), [0x01DE, 0x012B])
        with self.assertRaises(ValueError):
            hc.halfwords("2320")             # ambiguous: decimal or hex
        self.assertEqual(hc.halfwords(hc._hw_str([0x2307])), [0x2307])
        self.assertEqual(hc.halfwords(hc._hw_str([0x1DE, 0x12B])), [0x1DE, 0x12B])
        self.assertEqual(hc._hw_str([0x2307]), "0x2307")
        self.assertEqual(hc._hw_str([0x1DE, 0x12B]), "01DE 012B")


@unittest.skipUnless(ROM_CN.exists(), "Chinese ROM missing")
class TestRom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = m.load_rom(ROM_CN)
        cls.orig_ov58 = bytes(hc.RomView(cls.rom).get("overlay58"))

    def test_scan_finds_outfit_chooser(self):
        big = hc._bigrams()
        cm_zh = m.Charmap.load([hc.ZH_CHARMAP])
        hits = {(off, text) for off, _, text in hc.scan_blob(self.orig_ov58, cm_zh, big)}
        self.assertEqual(hits, {(0x6F0, "确认"), (0x6F6, "形象1"), (0x6FE, "形象3"), (0x706, "形象2")})

    def test_apply_and_verify(self):
        rom = m.load_rom(ROM_CN)
        patches = [dict(p, enabled=True) for p in hc.load_code_patches()]
        rep = hc.apply(rom, CM, code_patches=patches)
        self.assertEqual(hc.verify(rom, rep, CM), f"ok (4 strings, {len(patches)} code patches)")
        view = hc.RomView(rom)
        ov = view.get("overlay58")
        self.assertEqual(view.table_ram_size(58), len(ov))
        self.assertGreater(len(ov), len(self.orig_ov58))
        big = hc._bigrams()
        cm_zh = m.Charmap.load([hc.ZH_CHARMAP])
        self.assertEqual(list(hc.scan_blob(ov, cm_zh, big)), [])
        # the other overlay-table rows are untouched
        t0, t1 = bytes(self.rom.arm9OverlayTable), bytes(rom.arm9OverlayTable)
        diff = {i // 32 for i in range(len(t0)) if t0[i] != t1[i]}
        self.assertEqual(diff, {58})
        # the naming keyboard: page 0 (opens first) is ABC in Western codes, no page keeps the IME branch
        arm9 = view.get("arm9")
        self.assertEqual(hc._units(arm9, 0x83C24, 1), [0xE068])
        self.assertEqual(hc._units(arm9, 0x100CE4, 14), list(range(0x12B, 0x138)) + [0xFFFF])
        # a code patch whose expected halfword is wrong is refused, and nothing is written
        rom2 = m.load_rom(ROM_CN)
        bad = [dict(hc.load_code_patches()[0], enabled=True, expect="0x2306")]
        with self.assertRaises(hc.HardcodedError):
            hc.apply(rom2, CM, code_patches=bad)
        self.assertEqual(hc.RomView(rom2).get("overlay58"), self.orig_ov58)


if __name__ == "__main__":
    unittest.main()
