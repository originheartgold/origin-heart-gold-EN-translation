#!/usr/bin/env python3
"""Unit tests for narcpatch.py (the [[narc_bytes]] build stage). Run:  python3 -m unittest -v work/tools/test_narcpatch.py"""
import functools
import hashlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixes as F  # noqa: E402
import msgtool as m  # noqa: E402
import narcpatch as N  # noqa: E402

BOLDORE = bytes.fromhex("05000000 0e02".replace(" ", "")) + bytes(54)
OTHER = bytes.fromhex("04001900 0d02".replace(" ", "")) + bytes(54)


def entry(eid="e", member=1, offset="0x0", expect="0005 0000 020E", new="0004 0023 020E", sha1=None):
    return {"id": eid, "narc": "a/0/3/4", "member": member, "offset": offset, "expect": expect, "new": new,
            "member_sha1": sha1 or hashlib.sha1(BOLDORE).hexdigest(), "notes": "n"}


class Stage(unittest.TestCase):
    def setUp(self):
        self.store = {"a/0/3/4": m.Narc([OTHER, BOLDORE, OTHER]).build()}
        self.get = self.store.__getitem__
        self.set = self.store.__setitem__

    def fix(self, *entries):
        return [{"id": "f", "kind": "narc", "narc_bytes": list(entries)}]

    def members(self):
        return m.Narc.parse(self.store["a/0/3/4"]).files

    def test_apply_and_verify(self):
        rows = N.apply(self.get, self.set, self.fix(entry()))
        files = self.members()
        self.assertEqual(files[1][:6].hex(), "040023000e02")
        self.assertEqual(files[1][6:], BOLDORE[6:])
        self.assertEqual((files[0], files[2]), (OTHER, OTHER))
        self.assertEqual(rows[0]["fix"], "f")
        self.assertEqual(N.verify(self.get, rows), "ok (1 entries, 1 members)")
        self.set("a/0/3/4", m.Narc([OTHER, BOLDORE, OTHER]).build())
        with self.assertRaises(AssertionError):
            N.verify(self.get, rows)

    def test_two_entries_in_one_member(self):
        N.apply(self.get, self.set, self.fix(entry("a", expect="0x5", new="0x4", offset="0x0"),
                                             entry("b", expect="0000 020E", new="0023 020E", offset="0x2")))
        self.assertEqual(self.members()[1][:6].hex(), "040023000e02")

    def test_refusals(self):
        before = self.store["a/0/3/4"]
        cases = [(entry(sha1="0" * 40), "member SHA-1 is"),
                 (entry(expect="0005 0000 020F", new="0004 0023 020F"), "expected 05 00 00 00 0f 02"),
                 (entry(member=7), "the NARC has 3 members"),
                 (entry(offset="0x3A"), "run past the member")]
        for e, msg in cases:
            with self.assertRaises(N.NarcPatchError) as cm:
                N.apply(self.get, self.set, self.fix(e))
            self.assertIn(msg, str(cm.exception))
            self.assertEqual(self.store["a/0/3/4"], before)        # nothing written


class Schema(unittest.TestCase):
    def fx(self, *entries, kind="narc"):
        return {"id": "f", "title": "t", "kind": kind, "enabled": True, "decisions": [], "requires": [],
                "why": "w", "what": "w", "evidence": ["e"], "narc_bytes": list(entries)}

    def problems(self, *fixes):
        return F.validate(list(fixes), decisions=set())

    def test_valid(self):
        self.assertEqual(self.problems(self.fx(entry())), [])

    def test_bad_entries(self):
        probs = self.problems(self.fx(entry(expect="05 00"), entry("x", sha1="4cd8fb7ba6dc"),
                                      entry("y", new="0004 0023"), entry("z", new="0005 0000 020E"),
                                      dict(entry("w"), narc="a 0 3 4", offset="0")))
        for msg in ("expect '05 00'", "member_sha1 must be 40", "as many halfwords as expect",
                    "new equals expect", "narc must be a NARC path", "offset must be hex"):
            self.assertTrue(any(msg in p for p in probs), (msg, probs))

    def test_kind_and_asm(self):
        probs = self.problems(self.fx(entry(), kind="graphics"), dict(self.fx(), id="g"))
        self.assertTrue(any("kind 'graphics' cannot have [[narc_bytes]]" in p for p in probs), probs)
        self.assertTrue(any("kind 'narc' needs at least one [[narc_bytes]]" in p for p in probs), probs)
        probs = self.problems(dict(self.fx(entry()), asm="f.asm"))
        self.assertTrue(any("'asm' only belongs to kinds" in p for p in probs), probs)

    def test_overlaps(self):
        a = self.fx(entry("a"))
        b = dict(self.fx(entry("b", offset="0x2", expect="0x0", new="0x1")), id="g")
        c = dict(self.fx(entry("c", offset="0x6", expect="0x0", new="0x1")), id="h")     # adjacent: fine
        probs = self.problems(a, b, c)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("overlap in a/0/3/4#1: f (a", probs[0])
        gfx = {"id": "x", "title": "t", "kind": "graphics", "enabled": True, "decisions": [], "requires": [],
               "why": "w", "what": "w", "evidence": ["e"],
               "graphics": [{"op": "copy_us", "narc": "a/0/3/4", "members": [1]}]}
        probs = self.problems(c, gfx)
        self.assertTrue(any("overlap in a/0/3/4#1" in p for p in probs), probs)

    def test_duplicate_ids_and_docs(self):
        probs = self.problems(self.fx(entry("a")), dict(self.fx(entry("a", member=2)), id="g"))
        self.assertTrue(any("[[narc_bytes]] id 'a' in both f and g" in p for p in probs), probs)
        lines = F._touched(self.fx(entry()))
        self.assertTrue(lines[0].startswith("`a/0/3/4` #1 +0x0 `e`: `0005 0000 020E` → `0004 0023 020E` (member"), lines)


class RealFix(unittest.TestCase):
    """trade-evolutions-levelup against the Chinese ROM: only members 525 and 533 of a/0/3/4 change."""

    def test_on_rom(self):
        if not F.ROM_CN.exists():
            self.skipTest("Chinese ROM missing")
        rom = m.load_rom(F.ROM_CN)
        fix = [f for f in F.load_all() if f["id"] == "trade-evolutions-levelup"]
        before = m.Narc.parse(m.get_file(rom, "a/0/3/4")).files
        rows = N.apply(functools.partial(m.get_file, rom), functools.partial(m.set_file, rom), fix)
        after = m.Narc.parse(m.get_file(rom, "a/0/3/4")).files
        self.assertEqual([i for i in range(len(after)) if after[i] != before[i]], [525, 533])
        self.assertEqual(after[525][:6].hex(), "040023000e02")      # level up, Lv 35, Gigalith
        self.assertEqual(after[533][:6].hex(), "040028001602")      # level up, Lv 40, Conkeldurr
        self.assertEqual(sum(a != b for a, b in zip(after[525] + after[533], before[525] + before[533],
                                                    strict=True)), 4)
        self.assertEqual(N.verify(functools.partial(m.get_file, rom), rows), "ok (2 entries, 2 members)")


if __name__ == "__main__":
    unittest.main()
