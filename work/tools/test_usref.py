#!/usr/bin/env python3
"""Unit tests for the USA-ROM claims: the [[us_ref]] schema and the citation lint (fixes.py, no ROM), and
usref.py's check (synthetic images; the real claims when the USA and Chinese ROMs are there). Run:
    ARMIPS=/path/to/armips python3 -m unittest -v work/tools/test_usref.py"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import asmpatch as A  # noqa: E402
import fixes as F  # noqa: E402
import usref as U  # noqa: E402

ROM_US = U.ROM_US


def hw(*units):
    return b"".join(u.to_bytes(2, "little") for u in units)


class Citations(unittest.TestCase):
    CITED = {("arm9", "ram", 0x020830D8), ("arm9", "ram", 0x020431D6), ("overlay14", "off", 0x12BB4)}

    def probs(self, text, label="t.asm"):
        return F.us_citation_problems(text, label, self.CITED)

    def assertRefused(self, text, num, label="t.asm"):
        probs = self.probs(text, label)
        self.assertTrue(any(f"{num} follows" in p and "write a USA address as `US <file> 0x<RAM address>`" in p
                            for p in probs), (text, probs))

    def test_cited_and_backed(self):
        self.assertEqual(self.probs("; CreateArgs (hack 0x02081DA4, US arm9 0x020830D8) in Oak's speech\n"), [])
        self.assertEqual(self.probs("the USA table (US overlay14+0x12BB4).\n"), [])
        self.assertEqual(self.probs("; US limits, the US sizes; USA ROM. 0x02001234 is the hack's\n"), [])

    def test_prose_around_a_citation_is_not_refused(self):
        for text in ("; US arm9 0x020431D6 and the hack 0x02081DA4 match\n",
                     "; US arm9 0x020431D6, value 0x0BB809B9\n",
                     "# USA: 0xFFFF terminates\n",
                     "; the USA key handler, hack 0x02083814\n",
                     "; the US version, Chinese arm9 0x02083814\n",
                     "; let us see: 0x1234\n"):
            with self.subTest(text=text):
                self.assertEqual(self.probs(text), [])

    def test_citation_without_us_ref(self):
        probs = self.probs("x\n; script (US arm9 0x02043292)\n")
        self.assertEqual(len(probs), 1)
        self.assertIn("t.asm:2: 'US arm9 0x02043292' has no [[us_ref]]", probs[0])

    def test_free_form_addresses_are_refused(self):
        cases = [("; kind 7 (US overlay 43 0x0222CD5C; pret NAME_SCREEN_UNK7)", "0x0222CD5C"),
                 ("(US ov14 0x12BB4)", "0x12BB4"), ("(US 0x02043292)", "0x02043292"),
                 ("US overlay14+0x12BB4 for [0]-[8], overlay14+0x12C3C for [17]-[19]", "0x12C3C"),
                 ("; as in us 0x02043292\n", "0x02043292"), ("; the U.S. 0x02043292 has it\n", "0x02043292"),
                 ("; USA: arm9 2084884\n", "2084884"), ("; see the USA key handler at\n; 0x02084884\n", "0x02084884")]
        for text, num in cases:
            with self.subTest(text=text):
                self.assertRefused(text, num)
        # fix.toml prose continues on the next line; an asm code line does not continue a comment
        self.assertRefused("as in the USA ROM at\n0x02084884, too", "0x02084884", label="t/fix.toml")
        self.assertEqual(self.probs("; the USA ROM has it\n.org 0x02084884\n"), [])


class Schema(unittest.TestCase):
    def probs(self, *refs, code=("t-1",)):
        fx = {"id": "t", "kind": "code", "code": [{"id": c} for c in code], "us_ref": list(refs)}
        out = []
        F._validate_us_refs(fx, "t/fix.toml", out)
        return out

    def ref(self, **kw):
        return {"id": "r", "claim": "c", "file": "arm9", "address": "0x02000000", "expect": "0x2307", **kw}

    def test_valid(self):
        self.assertEqual(self.probs(self.ref()), [])
        r = self.ref()
        del r["expect"]
        self.assertEqual(self.probs(dict(r, new="t-1")), [])
        self.assertEqual(self.probs(dict(r, hack="arm9 0x02083814", length=6)), [])
        self.assertEqual(self.probs({"id": "n", "claim": "c", "file": "a/1/5/2", "members": [2], "lz10": True}), [])

    def test_problems(self):
        r = self.ref()
        cases = [
            (dict(r, offset="0x10"), "give address (RAM) or offset"),
            (dict(r, address="0x2000"), "address must be a RAM address"),
            (dict(r, new="t-1"), "give one of expect"),
            ({k: v for k, v in r.items() if k != "expect"} | {"new": "nope"}, "is not a [[code]] region"),
            ({k: v for k, v in r.items() if k != "expect"} | {"hack": "arm9 0x02083814"}, "length (bytes) goes"),
            (dict(r, expect="2307"), "write one halfword as 0xNNNN"),
            ({"id": "n", "claim": "c", "file": "a/1/5/2"}, "a NARC reference needs members"),
            ({"id": "n", "claim": "c", "file": "a/1/5/2", "members": [1], "address": "0x02000000"}, "belongs to an arm9"),
            (dict(r, file="ov14"), "file must be 'arm9', 'overlayNN'"),
        ]
        for ref, want in cases:
            with self.subTest(want=want):
                probs = self.probs(ref)
                self.assertTrue(any(want in p for p in probs), probs)


class FakeImages:
    def __init__(self, files, bases=None, narcs=None):
        self.files, self.bases, self.narcs = files, bases or {}, narcs or {}

    def base(self, key):
        return self.bases.get(key, 0x02000000)

    def get(self, key):
        return self.files[key]

    def narc_members(self, path):
        return self.narcs[path]


class CheckRef(unittest.TestCase):
    def setUp(self):
        self.us = FakeImages({"arm9": hw(0, 0x2307, 0x1C0B), "overlay43": hw(0x2107, 0x9201, 0x1C20, 0x1C0B)},
                             {"overlay43": 0x0222CD56})
        self.cn = FakeImages({"arm9": hw(0, 0x2307, 0x1C0B)}, narcs={"a/1/5/2": [b"x", b"same"]})

    def test_expect(self):
        e = {"id": "r", "claim": "c", "file": "overlay43", "address": "0x0222CD5C", "expect": "0x1C0B"}
        self.assertIn("2 bytes", U.check_ref({}, e, self.us))
        # the address cited before it was corrected (0x0222CD5A) holds another instruction
        with self.assertRaises(U.UsRefError) as cm:
            U.check_ref({}, dict(e, address="0x0222CD5A"), self.us)
        self.assertIn("US overlay43 0x0222CD5A holds 0x1c20, not 0x1c0b (fix.toml expect)", str(cm.exception))

    def test_calls_and_unique(self):
        # mov r3, #7 at 0x02000000, then bl 0x02000100 (bl at +4: 0x100 - 8 = 0xF8: halfwords F000 F87C)
        us = FakeImages({"arm9": hw(0x2307, 0x2000, 0xF000, 0xF87C, 0x2307)})
        e = {"id": "r", "claim": "c", "file": "arm9", "address": "0x02000000", "expect": "0x2307"}
        self.assertIn("then bl 0x02000100", U.check_ref({}, dict(e, calls="0x02000100"), us))
        with self.assertRaises(U.UsRefError) as cm:
            U.check_ref({}, dict(e, calls="0x02000200"), us)
        self.assertIn("the bl after it goes to 0x02000100, not 0x02000200", str(cm.exception))
        with self.assertRaises(U.UsRefError) as cm:                # mov r3, #7 is there twice
            U.check_ref({}, dict(e, unique=True), us)
        self.assertIn("occur 2 times", str(cm.exception))
        far = FakeImages({"arm9": hw(0x2307, 0x2000, 0x2000, 0x2000, 0x2000, 0xF000, 0xF87C)})
        with self.assertRaises(U.UsRefError) as cm:                # the bl is more than 8 bytes away
            U.check_ref({}, dict(e, calls="0x02000100"), far)
        self.assertIn("no Thumb bl within 8 bytes", str(cm.exception))

    def test_hack_and_narc(self):
        e = {"id": "r", "claim": "c", "file": "arm9", "offset": "0x2", "hack": "arm9+0x2", "length": 4}
        self.assertIn("4 bytes", U.check_ref({}, e, self.us, self.cn))
        self.cn.files["arm9"] = hw(0, 0x2305, 0x1C0B)
        with self.assertRaises(U.UsRefError):
            U.check_ref({}, e, self.us, self.cn)
        self.us.narcs = {"a/1/5/2": [b"y", b"same"]}
        n = {"id": "n", "claim": "c", "file": "a/1/5/2", "members": [1]}
        self.assertIn("1 members", U.check_ref({}, n, self.us, self.cn))
        with self.assertRaises(U.UsRefError):
            U.check_ref({}, dict(n, members=[0, 1]), self.us, self.cn)


@unittest.skipUnless(ROM_US.exists() and F.ROM_CN.exists(), "needs the USA and the Chinese ROM")
class RealClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import msgtool as m
        cls.us = m.load_rom(str(ROM_US))
        cls.cn = m.load_rom(str(F.ROM_CN))
        cls.fixes = {f["id"]: f for f in F.load_all()}

    def test_every_claim_holds(self):
        import asmlisting
        try:
            armips = A.find_armips()
            A.check_armips(armips)
        except A.AsmError:
            self.skipTest("armips v0.11.0 not found")
        fixes = list(self.fixes.values())
        done = asmlisting.assemble_each(self.cn, [f for f in fixes if any("new" in e for e in f.get("us_ref", []))],
                                        armips)
        rows, probs = U.check_all(fixes, self.us, self.cn, done)
        self.assertEqual(probs, [])
        self.assertGreaterEqual(len(rows), 18)

    def test_the_two_corrected_citations_are_caught(self):
        us, cn = U.CodeImages(self.us), U.CodeImages(self.cn)
        kind7 = next(e for e in self.fixes["namelen"]["us_ref"] if e["id"] == "namelen-us-kind7")
        self.assertIn("then bl 0x020830D8", U.check_ref(self.fixes["namelen"], kind7, us, cn))
        with self.assertRaises(U.UsRefError):                     # the earlier citation 0x0222CD5A
            U.check_ref(self.fixes["namelen"], dict(kind7, address="0x0222CD5A"), us, cn)
        # pcbox [17]-[19]: the USA table at 0x12C3C equals the fix's new bytes; the earlier 0x12C42 does not.
        # The fix's new bytes are taken from its source's values (the asm writes the USA templates).
        fx = self.fixes["pcbox-name-width"]
        ref = next(e for e in fx["us_ref"] if e["id"] == "pcbox-us-templates-2")
        new16 = bytearray(cn.get("overlay16"))
        new16[0x12F24:0x12F24 + 24] = bytes.fromhex("04010b08020fe30004010f0b020ff3000401130c020f0901")
        import asmlisting
        done = asmlisting.Assembled(fx, {"overlay16": cn.get("overlay16")}, {"overlay16": bytes(new16)},
                                    {"overlay16": cn.base("overlay16")}, "")
        self.assertIn("24 bytes", U.check_ref(fx, ref, us, cn, done))
        with self.assertRaises(U.UsRefError):
            U.check_ref(fx, dict(ref, offset="0x12C42"), us, cn, done)


if __name__ == "__main__":
    unittest.main()
