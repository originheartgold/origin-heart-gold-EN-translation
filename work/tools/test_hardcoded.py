#!/usr/bin/env python3
"""Unit tests for hardcoded.py (the [[string]] view, RomView, the survey scan). Run:
    python3 -m unittest -v work/tools/test_hardcoded.py
The bytes the strings fix writes are tested in test_asmpatch.py (armips). The ROM tests are skipped when
work/rom/origin_v4.0.3_cn.nds is missing."""
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixes as fixreg  # noqa: E402
import hardcoded as hc  # noqa: E402
import msgtool as m  # noqa: E402

CM = m.Charmap.load([str(HERE / "charmap_en.tsv"), str(HERE / "charmaps" / "charmap_zh_xzonn_gen4.tsv")])
ROM_CN = HERE.parent / "rom" / "origin_v4.0.3_cn.nds"


class TestRegistryEntries(unittest.TestCase):
    """The [[string]] entries of work/patches, as hardcoded.load() gives them (`hardcoded.py list`)."""

    def test_schema(self):
        cfg = hc.load()
        self.assertEqual(set(cfg), {"strings"})
        ids = set()
        for e in cfg["strings"]:
            self.assertEqual(e["id"], f"{e['file']}:{e['offset']}")
            self.assertNotIn(e["id"], ids)
            ids.add(e["id"])
            self.assertEqual(len(m.encode_text(e["zh"], CM)) - 1, e["max_units"], e["id"])
            self.assertTrue(re.fullmatch(r"0x[0-9A-F]+", e["offset"]), e["id"])
            self.assertEqual(e["fix"], "outfit-chooser-strings")
            n = len(m.encode_text(e["en"], CM)) - 1
            self.assertLessEqual(n, e["max_units"] if not e.get("pointers") else e["reloc_max_units"], e["id"])
        self.assertEqual(len(ids), 4)

    def test_selection_limits_entries(self):
        act = fixreg.select(fixreg.load_all(), without="outfit-chooser-strings")
        self.assertEqual(hc.load(fixes=act), {"strings": []})


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

    def test_romview_grows_an_overlay_and_its_ram_size(self):
        rom = m.load_rom(ROM_CN)
        view = hc.RomView(rom)
        view.set("overlay58", self.orig_ov58 + b"\xff" * 8)
        self.assertEqual(view.table_ram_size(58), len(self.orig_ov58) + 8)
        t0, t1 = bytes(self.rom.arm9OverlayTable), bytes(rom.arm9OverlayTable)
        self.assertEqual({i // 32 for i in range(len(t0)) if t0[i] != t1[i]}, {58})


    def test_romview_itcm(self):
        # "itcm": the ARM9 autoload section at 0x01FF8000; writing it back rebuilds the ARM9 file with ndspy
        rom = m.load_rom(ROM_CN)
        view = hc.RomView(rom)
        itcm = view.get("itcm")
        self.assertEqual((view.base("itcm"), len(itcm)), (0x01FF8000, 0x620))
        before = bytes(rom.arm9)
        view.set("itcm", itcm)
        self.assertEqual(bytes(rom.arm9), before)                 # same bytes: the same ARM9 file
        view.set("itcm", itcm + bytes(32))
        self.assertEqual(view.get("itcm"), itcm + bytes(32))
        self.assertEqual(len(rom.arm9), len(before) + 32)


if __name__ == "__main__":
    unittest.main()
