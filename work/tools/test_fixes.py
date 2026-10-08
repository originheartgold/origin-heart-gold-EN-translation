#!/usr/bin/env python3
"""Unit tests for fixes.py (the work/patches registry). Run:  python3 -m unittest -v work/tools/test_fixes.py"""
import contextlib
import io
import json
import re
import shutil
import sys
import tempfile
import textwrap
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fixes as F  # noqa: E402

DECS = {"D-0001", "D-0002"}


def fix_toml(fid, kind="code", enabled=True, requires=(), entries="", extra="", asm=None):
    """A fix.toml; kinds code, data and strings get asm = "<fid>.asm" unless asm is given ("" = none)."""
    if asm is None:
        asm = f"{fid}.asm" if kind in ("code", "data", "strings") else ""
    head = textwrap.dedent(f"""\
        id = "{fid}"
        title = "Title of {fid}"
        kind = "{kind}"
        enabled = {"true" if enabled else "false"}
        decisions = ["D-0001"]
        requires = {list(requires)!r}
        why = "the hack does X"
        what = "now it does Y"
        evidence = ["work/notes/x.md"]
        """).replace("'", '"')
    if asm:
        head += f'asm = "{asm}"\n'
    return head + extra + "\n" + textwrap.dedent(entries)


def code_entry(eid, offset="0x10", expect="0x2305", file="arm9"):
    return f"""
[[code]]
id = "{eid}"
file = "{file}"
offset = "{offset}"
expect = "{expect}"
notes = "n"
"""


BASES = {"arm9": 0x02000000, "overlay58": 0x021E83C0}


def asm_header(fid, decisions="D-0001"):
    """The header comment the asm lint requires on line 1."""
    return f"; {fid} - Title of {fid}. {decisions}\n"


def asm_for(toml_text):
    """A minimal armips source that passes the asm lint: the header, every file the fix's entries name opened at
    its load address, and each [[string]] en written with .string in an appended (expect_end) area."""
    fid = re.search(r'^id = "([^"]+)"', toml_text, re.M).group(1)
    files = sorted(set(re.findall(r'^file = "((?:arm9|overlay\d+))"', toml_text, re.M)))
    ens = re.findall(r'^en = "([^"]*)"', toml_text, re.M)
    head = asm_header(fid) + '.include "../include/guards.inc"\n' + \
        ('.loadtable "../include/charmap.tbl", "UTF-8"\n' if ens else "")
    out = head
    for i, f in enumerate(files):
        base = BASES.get(f, 0x02200000)
        out += f'.open "{f}.bin", 0x{base:08X}\n'
        if i == 0 and ens:
            out += (f".org 0x{base + 0x1000:08X}\n.area 64\n    expect_end\n" +
                    "".join(f'    .string "{en}"\n' for en in ens) + ".endarea\n")
        out += ".close\n"
    return out


GFX = """
[[graphics]]
op = "copy_us"
narc = "a/0/0/8"
members = [1, 2]
notes = "n"
"""


class Registry(unittest.TestCase):
    """Synthetic registries in a temp folder."""

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def write(self, fid, text, folder=None):
        d = self.root / (folder or fid)
        d.mkdir(parents=True, exist_ok=True)
        (d / "fix.toml").write_text(text, encoding="utf-8")
        mo = re.search(r'^asm = "([^"/]+)"', text, re.M)
        if mo:
            (d / mo.group(1)).write_text(asm_for(text), encoding="utf-8")

    def load(self):
        return F.load_all(self.root, decisions=DECS)

    def problems(self):
        fixes = F.load_all(self.root, validate_all=False)
        return F.validate(fixes, decisions=DECS)

    # -- schema ------------------------------------------------------------------------
    def test_valid(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1")))
        self.write("b", fix_toml("b", kind="graphics", requires=["a"], entries=GFX))
        self.assertEqual([f["id"] for f in self.load()], ["a", "b"])

    def test_unknown_keys(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1") + 'colour = "red"\n', extra='typo = 1\n'))
        probs = self.problems()
        self.assertTrue(any("unknown key 'typo'" in p for p in probs), probs)
        self.assertTrue(any("unknown key 'colour'" in p for p in probs), probs)

    def test_missing_and_wrong_types(self):
        self.write("a", 'id = "a"\nkind = "code"\nenabled = "yes"\n' + code_entry("a-1"))
        probs = self.problems()
        self.assertTrue(any("'enabled' must be bool" in p for p in probs), probs)
        self.assertTrue(any("missing 'why'" in p for p in probs), probs)

    def test_id_must_match_folder_and_be_unique(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1")), folder="a")
        self.write("a", fix_toml("a", entries=code_entry("a-2", offset="0x20")), folder="b")
        probs = self.problems()
        self.assertTrue(any("differs from its folder name" in p for p in probs), probs)
        self.assertTrue(any("duplicate fix id 'a'" in p for p in probs), probs)

    def test_sha1_region_native_payload_and_itcm(self):
        sha = 'length = 64\nexpect_sha1 = "' + "0" * 40 + '"'
        region = code_entry("t-1", file="overlay50", offset="0x0").replace('expect = "0x2305"', sha)
        native = '[native]\nsource = "n.c"\npayload = "p.json"\nmodule = "text_speed_patch"\n'
        grow = '\n[[grow]]\nfile = "itcm"\nmax = 6624\n'
        self.write("t", fix_toml("t", extra=native, entries=region + grow))
        (self.root / "t" / "n.c").write_text("int x;\n")
        (self.root / "t" / "p.json").write_text('{"symbols": {"entry": 33523233, "state": 33524672}}')
        asm = (self.root / "t" / "t.asm")
        good = (asm_header("t") + '.include "../include/guards.inc"\n'
                '.definelabel entry, 0x01FF8620\n.definelabel state, 0x01FF8BC0\n'
                '.open "itcm.bin", 0x01FF8000\n.org 0x01FF8620\n.area 0x1A00\n    expect_end\n'
                '.incbin "../native/t.bin"\n.endarea\n.close\n'
                '.open "overlay50.bin", 0x02200000\n.close\n')
        asm.write_text(good)
        self.write("u", fix_toml("u", entries=code_entry("u-1", offset="0x20", file="overlay50")))
        probs = self.problems()
        self.assertEqual([p for p in probs if "overlap" not in p], [])
        self.assertTrue(any("overlap in overlay50" in p for p in probs), probs)   # the sha1 region is 64 bytes
        fixes = F.load_all(self.root, validate_all=False)
        self.assertIn("original SHA-1", F.render_docs(fixes, {"overlay50": 0x021E4980}))
        self.assertIn("Native code: `n.c`", F.render_docs(fixes, {"overlay50": 0x021E4980}))
        # a label off by the Thumb bit, a missing .incbin, an unknown module, ITCM at the wrong address
        asm.write_text(good.replace("0x01FF8620", "0x01FF8621").replace('.incbin "../native/t.bin"\n', "")
                       .replace('"itcm.bin", 0x01FF8000', '"itcm.bin", 0x01FF8020'))
        self.write("t", fix_toml("t", extra=native.replace("text_speed_patch", "evil"), entries=region + grow))
        asm.write_text(good.replace("0x01FF8620", "0x01FF8621").replace('.incbin "../native/t.bin"\n', "")
                       .replace('"itcm.bin", 0x01FF8000', '"itcm.bin", 0x01FF8020'))
        self.write("u", fix_toml("u", entries=code_entry("u-1", offset="0x20").replace('expect = "0x2305"',
                                                                                      'length = 3')))
        probs = self.problems()
        # the ITCM block only grows: a region or string in it is refused
        self.write("v", fix_toml("v", entries=code_entry("v-1", file="itcm")))
        probs = self.problems()
        self.assertTrue(any("(the ITCM block 'itcm' may only grow" in p for p in probs), probs)
        for want in ("wrong or missing: entry", "must include the payload once", "module 'evil' is unknown",
                     "itcm.bin opened at 0x01ff8020", "length must be a positive even",
                     "missing 'expect' (or 'length' + 'expect_sha1'"):
            self.assertTrue(any(want in p for p in probs), (want, probs))

    def test_duplicate_entry_ids(self):
        self.write("a", fix_toml("a", entries=code_entry("x")))
        self.write("b", fix_toml("b", entries=code_entry("x", offset="0x40")))
        self.assertTrue(any("[[code]] id 'x' in both a and b" in p for p in self.problems()))

    def test_kind_and_entries(self):
        self.write("a", fix_toml("a", kind="graphics", entries=code_entry("a-1")))
        self.write("b", fix_toml("b", kind="code"))
        self.write("c", fix_toml("c", kind="magic", entries=code_entry("c-1", offset="0x80")))
        probs = self.problems()
        self.assertTrue(any("kind 'graphics' cannot have [[code]]" in p for p in probs), probs)
        self.assertTrue(any("b/fix.toml: kind 'code' needs at least one [[code]]" in p for p in probs), probs)
        self.assertTrue(any("kind must be one of" in p for p in probs), probs)

    def test_code_entry_checks(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1", offset="16", expect="01DE 12B")
                                 + 'value = "0x2307"\n'))
        self.write("b", fix_toml("b", entries=code_entry("b-1", file="a/0/4/1")))
        probs = self.problems()
        self.assertTrue(any("offset must be hex" in p for p in probs), probs)
        self.assertTrue(any("'01DE 12B': write one halfword" in p for p in probs), probs)
        self.assertTrue(any("'value' is gone: the fix's asm writes the new bytes" in p for p in probs), probs)
        self.assertTrue(any("b-1: file must be 'arm9' or 'overlayNN'" in p for p in probs), probs)

    def test_graphics_op_keys(self):
        self.write("a", fix_toml("a", kind="graphics", entries="""
            [[graphics]]
            op = "copy_us"
            narc = "a/0/0/8"
            member = 3
            [[graphics]]
            op = "paint"
            """))
        probs = self.problems()
        self.assertTrue(any("unknown key 'member'" in p for p in probs), probs)
        self.assertTrue(any("missing 'members'" in p for p in probs), probs)
        self.assertTrue(any("unknown op 'paint'" in p for p in probs), probs)

    def test_decisions(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1")).replace('["D-0001"]', '["D-9999", "D-12"]'))
        probs = self.problems()
        self.assertTrue(any("D-9999 is not in the decision register" in p for p in probs), probs)
        self.assertTrue(any("'D-12' is not a D-NNNN id" in p for p in probs), probs)

    def test_asm_required_for_code_and_data_only(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1"), asm=""))
        self.write("b", fix_toml("b", kind="graphics", entries=GFX, asm="b.asm"))
        self.write("c", fix_toml("c", kind="data", entries=code_entry("c-1", offset="0x20"), asm="sub/c.asm"))
        probs = self.problems()
        self.assertTrue(any("a/fix.toml: kind 'code' needs asm" in p for p in probs), probs)
        self.assertTrue(any("b/fix.toml: 'asm' only belongs to kinds strings, data, code" in p for p in probs), probs)
        self.assertTrue(any("c/fix.toml: asm must be a .asm file name" in p for p in probs), probs)

    def test_asm_file_and_opens(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1") + code_entry("a-2", file="overlay58")))
        (self.root / "overlays.toml").write_text("[overlay58]\nram = 0x021E83C0\n")
        self.assertEqual(self.problems(), [])
        asm = self.root / "a" / "a.asm"

        def probs_for(text):
            asm.write_text(text, encoding="utf-8")
            return F.validate(F.load_all(self.root, validate_all=False), decisions=DECS,
                              overlay_bases=F.load_overlays(self.root))
        probs = probs_for('.open "arm9.bin", 0x02000000 ; arm9\n.open "overlay58.bin", 0x021E8000\n'
                          '.open "overlay12.bin", 0x02200000\n  .OPEN BIN, 0x02000000\n'
                          '.openfile "arm9.bin", "out.bin", 0x02000000\n')
        self.assertTrue(any("a.asm:2: overlay58.bin opened at 0x021e8000, but its load address is 0x021e83c0"
                            in p for p in probs), probs)
        self.assertTrue(any("a.asm:3: opens 'overlay12.bin', but the fix declares no [[code]] / [[string]] / "
                            "[[grow]] in it" in p for p in probs), probs)
        self.assertTrue(any("a.asm:4: write .open as" in p for p in probs), probs)
        self.assertTrue(any("a.asm:5: write .open as" in p for p in probs), probs)
        probs = probs_for(asm_header("a") + '; .open "overlay58.bin", 0x021E83C0 is only a comment\n'
                          '.open "arm9.bin", 0x02000000\n')
        self.assertEqual(probs, ["a/fix.toml: entries in overlay58, but a.asm never opens overlay58.bin"])
        probs = probs_for('.open "arm9.bin", 0x02000000\n.open "overlay58.bin", 0x021E83C0\n'
                          '  .headersize 0x02000010\n.CreateFile "x.bin", "y.bin", 0 ; no\n.create "z.bin", 0\n')
        for want in ("a.asm:3: .headersize is not allowed", "a.asm:4: .createfile is not allowed",
                     "a.asm:5: .create is not allowed"):
            self.assertTrue(any(want in p for p in probs), (want, probs))
        asm.unlink()
        self.assertTrue(any("asm file a.asm does not exist" in p for p in self.problems()))

    STRINGS = """
[[grow]]
file = "overlay58"
max = 64
notes = "n"

[[string]]
id = "overlay58:0x10"
file = "overlay58"
offset = "0x10"
zh = "形象1"
en = "Outfit 1"
max_units = 3
pointers = ["0x0"]
reloc_max_units = 15
"""

    def test_strings_fix_asm_literals_match_toml_en(self):
        (self.root / "overlays.toml").write_text("[overlay58]\nram = 0x021E83C0\n")
        self.write("s", fix_toml("s", kind="strings", entries=self.STRINGS))
        self.assertEqual(self.problems(), [])
        fx = self.load()[0]
        self.assertEqual(F.footprint(fx)[-1], ("overlay58", 1 << 40, (1 << 40) + 1, "overlay58 growth"))
        asm = self.root / "s" / "s.asm"
        good = asm.read_text(encoding="utf-8")
        asm.write_text(good.replace('"Outfit 1"', '"Outfit 2"'), encoding="utf-8")
        probs = self.problems()
        self.assertTrue(any("its .string literals ['Outfit 2'] differ from the [[string]] en values ['Outfit 1']"
                            in p for p in probs), probs)
        asm.write_text(good.replace('.loadtable "../include/charmap.tbl", "UTF-8"\n', ""), encoding="utf-8")
        self.assertTrue(any(".string needs the game's character table" in p for p in self.problems()))
        self.assertEqual(F.asm_strings('lab: .string "a\\"b" ; c\n  .stringn "x"\n; .string "no"\n'),
                         [(1, 'a"b'), (2, "x")])
        for bad in ('.string "Outfit 1", 0', '.string "Outfit", " 1"', "lab: .str 0x41", '.stringn "Outfit 1",0'):
            with self.subTest(form=bad):
                asm.write_text(good.replace('.string "Outfit 1"', bad), encoding="utf-8")
                probs = self.problems()
                self.assertTrue(any("write one literal per line" in p and bad in p for p in probs), probs)
        self.assertEqual(F.asm_string_forms('; .string "a", 0\n.string "a;b" ; c\n.strings\n'), [])
        asm.write_text(good, encoding="utf-8")
        md = F.render_docs(self.load(), overlay_bases={"overlay58": 0x021E83C0})
        self.assertIn("`overlay58`: may grow by up to 64 bytes (appended at its end)", md)
        self.assertIn("`overlay58+0x10` (RAM 0x021E83D0) (slot of 3 characters, pointers 0x0): 形象1 → 'Outfit 1' "
                      "(relocated, at most 15 characters there)", md)

    def test_grow_checks(self):
        (self.root / "overlays.toml").write_text("[overlay58]\nram = 0x021E83C0\n")
        bad = self.STRINGS.replace('file = "overlay58"\nmax = 64', 'file = "arm9"\nmax = 0')
        self.write("s", fix_toml("s", kind="strings", entries=bad))
        probs = self.problems()
        self.assertTrue(any("file must be 'overlayNN' or 'itcm'" in p for p in probs), probs)
        self.assertTrue(any("max must be 1..4096 bytes" in p for p in probs), probs)
        self.write("s", fix_toml("s", kind="strings", entries=self.STRINGS))
        self.write("t", fix_toml("t", entries='[[grow]]\nfile = "overlay58"\nmax = 8\n' +
                                 code_entry("t-1", file="overlay58", offset="0x40")))
        probs = self.problems()
        self.assertTrue(any("overlap in overlay58" in p and "growth" in p for p in probs), probs)
        self.write("t", fix_toml("t", kind="graphics", entries='[[grow]]\nfile = "overlay58"\nmax = 8\n' + GFX))
        self.assertTrue(any("[[grow]] only belongs to kinds" in p for p in self.problems()))

    def test_code_from_us_offsets_are_hex_strings(self):
        op = ('[[graphics]]\nop = "code_from_us"\nfile = "overlay14"\noffset = "0x4C0A8"\nus_file = "overlay12"\n'
              'us_offset = "0x36340"\nlength = 4\nexpect_sha1 = "a"\nus_sha1 = "b"\n')
        self.write("g", fix_toml("g", kind="graphics", entries=op))
        self.assertFalse([p for p in self.problems() if "code_from_us" in p or "offset" in p])
        self.write("g", fix_toml("g", kind="graphics", entries=op.replace('"0x4C0A8"', "311464")))
        self.assertTrue(any("'offset' must be string" in p for p in self.problems()))
        self.write("g", fix_toml("g", kind="graphics", entries=op.replace('"0x36340"', '"36340"')))
        self.assertTrue(any("us_offset must be hex" in p for p in self.problems()))

    def test_include_folder_is_not_a_fix(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1")))
        (self.root / "include").mkdir()
        (self.root / "include" / "guards.inc").write_text("; macros\n")
        self.assertEqual([f["id"] for f in self.load()], ["a"])

    def test_missing_requires_and_cycle(self):
        self.write("a", fix_toml("a", requires=["nope"], entries=code_entry("a-1")))
        self.assertTrue(any("requires unknown fix 'nope'" in p for p in self.problems()))
        self.write("a", fix_toml("a", requires=["b"], entries=code_entry("a-1")))
        self.write("b", fix_toml("b", requires=["c"], entries=code_entry("b-1", offset="0x20")))
        self.write("c", fix_toml("c", requires=["a"], entries=code_entry("c-1", offset="0x30")))
        probs = self.problems()
        self.assertTrue(any("dependency cycle: a -> b -> c -> a" in p for p in probs), probs)
        with self.assertRaises(F.FixError):
            self.load()

    def test_overlap(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1", offset="0x10", expect="0001 0002")))
        self.write("b", fix_toml("b", entries=code_entry("b-1", offset="0x12")))
        self.write("c", fix_toml("c", entries=code_entry("c-1", offset="0x14")))     # adjacent: fine
        probs = self.problems()
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("overlap in arm9: a (a-1", probs[0])
        self.assertIn("b (b-1", probs[0])

    def test_overlap_only_counts_enabled_fixes(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1")))
        self.write("b", fix_toml("b", enabled=False, entries=code_entry("b-1")))
        self.assertEqual(self.problems(), [])
        with self.assertRaises(F.FixError) as cm:
            F.select(self.load(), only="a,b")
        self.assertIn("overlap", str(cm.exception))

    def test_graphics_member_overlap_includes_also(self):
        self.write("a", fix_toml("a", kind="graphics", entries=GFX))
        self.write("b", fix_toml("b", kind="graphics", entries="""
            [[graphics]]
            op = "copy_us"
            narc = "a/0/6/8"
            also = ["a/0/0/8"]
            members = [2]
            """))
        self.assertTrue(any("overlap in a/0/0/8#2" in p for p in self.problems()))

    def test_registry_folder_problems(self):
        with self.assertRaises(F.FixError) as cm:
            F.load_all(self.root / "missing", decisions=DECS)
        self.assertIn("does not exist", str(cm.exception))
        with self.assertRaises(F.FixError) as cm:
            self.load()                                      # empty root
        self.assertIn("no */fix.toml found", str(cm.exception))
        self.write("a", fix_toml("a", entries=code_entry("a-1")))
        (self.root / "assets").mkdir()
        with self.assertRaises(F.FixError) as cm:
            self.load()
        self.assertIn("assets/: folder without fix.toml", str(cm.exception))

    def test_halfword_notation(self):
        self.assertEqual(F.halfwords("0x2305"), [0x2305])
        self.assertEqual(F.halfwords("0x1"), [1])
        self.assertEqual(F.halfwords("01DE 012B"), [0x01DE, 0x012B])
        for bad in ("2320", "0x12345", "01DE 12B", "0x01DE 0x012B", "", "01DE", 0x2305, ["0x1"]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                F.halfwords(bad)
        self.write("a", fix_toml("a", entries=code_entry("a-1", expect="2320")))
        self.assertTrue(any("'2320': write one halfword as 0xNNNN" in p for p in self.problems()))

    def test_list_element_types(self):
        self.write("a", fix_toml("a", requires=[], entries=code_entry("a-1")).replace(
            "requires = []", "requires = [1]").replace('evidence = ["work/notes/x.md"]', 'evidence = [2]'))
        self.write("b", fix_toml("b", kind="graphics", entries="""
            [[graphics]]
            op = "copy_us"
            narc = "a/0/0/8"
            members = ["1"]
            also = [3]
            [[graphics]]
            op = "tiles_from_us"
            narc = "a/0/0/8"
            member = 4
            tiles = [[5, 1], [1, 2, 3]]
            """))
        self.write("c", fix_toml("c", kind="font", entries="""
            [[font]]
            narc = "a/0/1/6"
            fonts = ["0"]
            codes = ["01AF", 431]
            source = "usa"
            """))
        probs = self.problems()            # no crash on a non-string requires element
        for want in ("'requires' must be a list of str", "'evidence' must be a list of str",
                     "'members' must be a list of int", "'also' must be a list of str",
                     "tiles must be [first, last] pairs", "'fonts' must be a list of int",
                     "'codes' must be a list of str"):
            self.assertTrue(any(want in p for p in probs), (want, probs))
        self.write("c", fix_toml("c", kind="font", entries="""
            [[font]]
            narc = "a/0/1/6"
            fonts = [0]
            codes = ["01AF"]
            source = "usa"
            """))
        self.assertTrue(any("code '01AF' must be hex" in p for p in self.problems()))

    def test_bad_containers_are_reported_not_crashing(self):
        cases = {
            "code-ints": ("code", "code = [1, 2]\n", "'code' must be a list of table"),
            "string-int": ("strings", "string = [1]\n", "'string' must be a list of table"),
            "graphics-int": ("graphics", "graphics = [1]\n", "'graphics' must be a list of table"),
            "font-int": ("font", "font = [1]\n", "'font' must be a list of table"),
            "grow-int": ("strings", 'grow = [1]\n[[string]]\nid = "arm9:0x0"\nfile = "arm9"\n'
                         'offset = "0x0"\nzh = "z"\nmax_units = 1\n', "'grow' must be a list of table"),
            "string-file": ("strings", '[[string]]\nid = "a/0/4/1:0x0"\nfile = "a/0/4/1"\noffset = "0x0"\nzh = "z"\n'
                            'max_units = 1\n', "file must be 'arm9' or 'overlayNN'"),
            "files-list": ("graphics", '[[graphics]]\nop = "member_from_file"\nnarc = "a/0/0/8"\nfiles = [1]\n',
                           "'files' must be a table of table"),
            "op-list": ("graphics", '[[graphics]]\nop = ["copy_us"]\nnarc = "a/0/0/8"\n', "unknown op"),
            "id-list": ("code", code_entry("x").replace('id = "x"', 'id = ["x"]'), "'id' must be string"),
            "string-offset": ("strings", '[[string]]\nid = "a:10"\nfile = "a"\noffset = "10"\nzh = "z"\n'
                              'max_units = 1\n', "offset must be hex like '0x6F0'"),
            "string-offset-zz": ("strings", '[[string]]\nid = "a:zz"\nfile = "a"\noffset = "zz"\nzh = "z"\n'
                                 'max_units = 1\n', "offset must be hex like '0x6F0'"),
        }
        for name, (kind, body, want) in cases.items():
            with self.subTest(name=name):
                for d in self.root.iterdir():
                    shutil.rmtree(d)
                self.write("a", fix_toml("a", kind=kind, entries=body))
                self.write("b", fix_toml("b", entries=code_entry("b-1", offset="0x80")))
                probs = self.problems()
                self.assertTrue(any(want in p for p in probs), (want, probs))
                with self.assertRaises(F.FixError):
                    self.load()

    def test_overlay_bases(self):
        self.write("a", fix_toml("a", entries=code_entry("a-1", file="overlay58")))
        with self.assertRaises(F.FixError) as cm:
            self.load()
        self.assertIn("overlay58 has no RAM base in overlays.toml", str(cm.exception))
        (self.root / "overlays.toml").write_text("[overlay58]\nram = 0x021E83C0\n")
        self.assertEqual(F.load_overlays(self.root), {"overlay58": 0x021E83C0})
        md = F.render_docs(self.load())
        self.assertIn("`overlay58+0x10` (RAM 0x021E83D0) `a-1`", md)
        (self.root / "overlays.toml").write_text("[overlay58]\nram = 0x021E83C0\nsize = 1\n")
        with self.assertRaises(F.FixError):
            F.load_overlays(self.root)
        (self.root / "overlays.toml").write_text("[overlay58\nram = \n")
        with self.assertRaises(F.FixError) as cm:
            F.load_overlays(self.root)
        self.assertIn("overlays.toml", str(cm.exception))

    def test_sizes(self):
        self.assertEqual(F.load_sizes(self.root), {})
        (self.root / "sizes.toml").write_text("[arm9]\nsize = 0x40\n[itcm]\nsize = 0x20\nbss = 0\n"
                                              "[overlay58]\nsize = 0x7E0\nbss = 0\n")
        self.assertEqual(F.load_sizes(self.root), {"arm9": {"size": 0x40}, "itcm": {"size": 0x20, "bss": 0},
                                                   "overlay58": {"size": 0x7E0, "bss": 0}})
        for bad in ("[arm9]\nsize = 1\nbss = 0\n", "[overlay58]\nsize = 1\n", "[a/0/2/7]\nsize = 1\n",
                    "[overlay58]\nsize = -1\nbss = 0\n", "[itcm]\nsize = '1'\nbss = 0\n"):
            (self.root / "sizes.toml").write_text(bad)
            with self.assertRaises(F.FixError, msg=bad):
                F.load_sizes(self.root)

    # -- order and selection -------------------------------------------------------------
    def _chain(self):
        self.write("zeta", fix_toml("zeta", entries=code_entry("z-1")))
        self.write("alpha", fix_toml("alpha", kind="graphics", requires=["zeta"], entries=GFX))
        self.write("mid", fix_toml("mid", enabled=False, entries=code_entry("m-1", offset="0x40")))
        return self.load()

    def test_order_puts_required_first(self):
        self.assertEqual([f["id"] for f in F.order(self._chain())], ["zeta", "alpha", "mid"])

    def test_select_default_enabled(self):
        self.assertEqual([f["id"] for f in F.select(self._chain())], ["zeta", "alpha"])

    def test_select_without(self):
        fixes = self._chain()
        self.assertEqual([f["id"] for f in F.select(fixes, without="alpha")], ["zeta"])
        with self.assertRaises(F.FixError) as cm:
            F.select(fixes, without="zeta")
        msg = str(cm.exception)
        self.assertIn("'alpha' requires 'zeta', which is excluded by --without", msg)
        self.assertIn("--without alpha", msg)
        self.assertEqual(F.select(fixes, without="zeta,alpha"), [])

    def test_select_only_and_kinds(self):
        fixes = self._chain()
        self.assertEqual([f["id"] for f in F.select(fixes, only="mid")], ["mid"])      # disabled, but named
        with self.assertRaises(F.FixError) as cm:
            F.select(fixes, only=["alpha"])
        self.assertIn("not in --only", str(cm.exception))
        with self.assertRaises(F.FixError) as cm:
            F.select(fixes, without_kinds=("code",))
        self.assertIn("excluded by its kind", str(cm.exception))
        self.assertEqual([f["id"] for f in F.select(fixes, without_kinds=("graphics",))], ["zeta"])

    def test_select_disabled_requirement(self):
        self.write("b", fix_toml("b", requires=["c"], entries=code_entry("b-1")))
        self.write("c", fix_toml("c", enabled=False, entries=code_entry("c-1", offset="0x20")))
        with self.assertRaises(F.FixError) as cm:
            F.select(self.load())
        self.assertIn("disabled (enabled = false)", str(cm.exception))

    def test_unknown_ids(self):
        with self.assertRaises(F.FixError) as cm:
            F.select(self._chain(), without="nope")
        self.assertIn("unknown fix id(s): nope", str(cm.exception))

    def test_views(self):
        fixes = self._chain()
        act = F.select(fixes)
        ce = F.code_entries(fixes)
        self.assertEqual({e["id"]: e["enabled"] for e in ce}, {"m-1": False, "z-1": True})
        mid_only = F.code_entries(F.select(fixes, only="mid"), all_enabled=True)
        self.assertEqual([(e["fix"], e["enabled"]) for e in mid_only], [("mid", True)])
        man = F.graphics_manifest(act)
        self.assertEqual(man, [{"op": "copy_us", "narc": "a/0/0/8", "members": [1, 2], "notes": "n", "fix": "alpha"}])
        self.assertIsNone(F.font_spec(act))

    # -- docs and TOML output -----------------------------------------------------------
    def test_docs(self):
        fixes = self._chain()
        md = F.render_docs(fixes, overlay_bases={})
        self.assertTrue(md.startswith("# Fixes to the Chinese ROM"))
        for fid in ("zeta", "alpha", "mid"):
            self.assertIn(f"\n## {fid}\n", md)
        self.assertIn("| [`mid`](#mid) | code | **no** |", md)
        self.assertIn("- Required by: `alpha`", md)
        self.assertIn("- Decisions: D-0001\n", md)
        self.assertIn("`arm9+0x10` (RAM 0x02000010) `z-1`: 2 bytes, was `2305`", md)
        self.assertIn("<summary>zeta.asm</summary>\n\n```asm\n; zeta - Title of zeta. D-0001\n"
                      ".include \"../include/guards.inc\"\n.open \"arm9.bin\", 0x02000000\n.close\n```", md)
        self.assertIn("`a/0/0/8` #1, #2: `copy_us` from USA ROM", md)

    def test_cli(self):
        self._chain()
        out = self.root / "FIXES.md"
        with patch.object(F, "load_decision_ids", return_value=DECS), \
                contextlib.redirect_stdout(io.StringIO()):
            F.main(["--root", str(self.root), "docs", "--out", str(out)])
            F.main(["--root", str(self.root), "check"])
            with self.assertRaises(SystemExit):
                F.main(["--root", str(self.root), "check", "--without", "zeta"])
        self.assertIn("## alpha", out.read_text(encoding="utf-8"))

    def test_toml_table_round_trip(self):
        op = {"op": "member_from_file", "narc": "a/2/6/4",
              "files": {"0": {"src": "generated/a.bin", "expect_sha1": "bf02687c695d"}},
              "notes": "quote \" backslash \\ 中文 'x'", "also": ["x", "y"], "tiles": [[1, 2], [3, 4]]}
        text = F.toml_table("graphics", op)
        self.assertEqual(tomllib.loads(text)["graphics"], [op])


class AsmLint(unittest.TestCase):
    """fixes.lint_asm: the static rules for a fix's armips source (each rule positive and negative)."""

    HEAD = '; t - Title. D-0001\n.nds\n.thumb\n.include "../include/guards.inc"\n.open "arm9.bin", 0x02000000\n'
    GOOD = ".org 0x02000010\n.area 2\n    expect16 0x2305\n    mov r3, #7\n.endarea\n"

    def fx(self, decisions=("D-0001",), regions=(("0x10", "0x2305"),), grow=None):
        f = {"id": "t", "kind": "code", "decisions": list(decisions),
             "code": [{"id": f"t-{i}", "file": "arm9", "offset": o, "expect": e, "notes": "n"}
                      for i, (o, e) in enumerate(regions)]}
        if grow:
            f["grow"] = [{"file": grow, "max": 64}]
        return f

    def lint(self, body, head=None, **kw):
        return F.lint_asm((self.HEAD if head is None else head) + body + ".close\n", self.fx(**kw), name="t.asm")

    def assertProblem(self, probs, *parts):
        self.assertTrue(any(all(x in p for x in parts) for p in probs), (parts, probs))

    def test_clean_source(self):
        self.assertEqual(self.lint(self.GOOD), [])

    # -- header ------------------------------------------------------------------------------------
    def test_header_names_the_fix(self):
        probs = self.lint(self.GOOD, head=self.HEAD.replace("; t - Title. D-0001\n", ".nds ; t - Title. D-0001\n"))
        self.assertProblem(probs, "t/t.asm:1: the source must start with a header comment '; t - <title>")
        probs = self.lint(self.GOOD, head=self.HEAD.replace("; t -", "; other -"))
        self.assertProblem(probs, "t/t.asm:1: the source must start with a header comment")

    def test_header_names_every_decision(self):
        self.assertEqual(self.lint(self.GOOD, decisions=("D-0001",)), [])
        probs = self.lint(self.GOOD, decisions=("D-0001", "D-0002"))
        self.assertProblem(probs, "t/t.asm:1: the header comment does not name D-0002")
        # the header is the leading comment paragraph: a decision named after the first ';' line does not count
        head = self.HEAD.replace("D-0001\n", "\n;\n; D-0002\n")
        self.assertProblem(self.lint(self.GOOD, head=head, decisions=("D-0002",)), "does not name D-0002")
        head = self.HEAD.replace("D-0001\n", "\n; continued: D-0002\n;\n")
        self.assertEqual(self.lint(self.GOOD, head=head, decisions=("D-0002",)), [])

    def test_header_names_a_pending_decision(self):
        probs = self.lint(self.GOOD, head=self.HEAD.replace(" D-0001", ""), decisions=())
        self.assertProblem(probs, "fix.toml lists no decision, so the header comment must name the pending decision")
        self.assertEqual(self.lint(self.GOOD, head=self.HEAD.replace("D-0001", "D-2043 (pending)"), decisions=()), [])

    # -- line length -------------------------------------------------------------------------------
    def test_line_length(self):
        ok = ".org 0x02000010" + " " * 20 + ";" + "x" * (F.ASM_MAX_LINE - 36) + "\n"
        self.assertEqual(len(ok), F.ASM_MAX_LINE + 1)
        self.assertEqual(self.lint(ok + self.GOOD), [])
        probs = self.lint(ok.replace(";", ";x") + self.GOOD)
        self.assertProblem(probs, "t/t.asm:6: line is 121 characters, more than 120")
        inc = F.lint_includes(F.PATCHES_DIR)
        self.assertEqual(inc, [])

    # -- area --------------------------------------------------------------------------------------
    def test_write_outside_an_area(self):
        probs = self.lint(".org 0x02000010\n    expect16 0x2305\n    mov r3, #7\n")
        self.assertProblem(probs, "t/t.asm:8: write outside an .area")
        probs = self.lint(".org 0x02000010\n    expect16 0x2305\n    .halfword 7\n")
        self.assertProblem(probs, "t/t.asm:8: write outside an .area")

    def test_write_outside_an_area_in_a_macro(self):
        mac = ".macro put, v\n    .halfword v\n.endmacro\n"
        probs = self.lint(mac + ".org 0x02000010\n    expect16 0x2305\n    put 7\n")
        self.assertProblem(probs, "t/t.asm:11 (macro line t.asm:7): write outside an .area")
        self.assertEqual(self.lint(mac + ".org 0x02000010\n.area 2\n    expect16 0x2305\n    put 7\n.endarea\n"), [])

    def test_area_rules(self):
        self.assertProblem(self.lint(".area 2\n    mov r3, #7\n.endarea\n"), "t/t.asm:6: .area before any .org")
        probs = self.lint(self.GOOD + ".area 2\n    expect16 0x2305\n    mov r3, #7\n.endarea\n",
                          regions=(("0x10", "2305 2305"),))
        self.assertProblem(probs, "t/t.asm:11: a second .area after one .org")
        probs = self.lint(".org 0x02000010\n.area 2\n.org 0x02000010\n    expect16 0x2305\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "t/t.asm:8: .org inside an .area")
        self.assertProblem(self.lint(".org 0x02000010\n.area 2\n"), "an .area is not closed")
        self.assertProblem(self.lint(".endarea\n"), "t/t.asm:6: .endarea without .area")
        self.assertProblem(self.lint(".org 0x02000010\n.area 2\n.frobnicate 1\n.endarea\n"),
                           "t/t.asm:8: unknown directive .frobnicate")
        self.assertProblem(self.lint(".orga 0x10\n"), ".orga takes a file offset")

    # -- guard -------------------------------------------------------------------------------------
    def test_unguarded_area(self):
        probs = self.lint(".org 0x02000010\n.area 2\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "t/t.asm:7: the .area's first write (line 8) has no guard since its .org")

    def test_guard_forms(self):
        for guard in ("    expect16 0x2305\n", "    expect16_at 0, 0x2305\n", "    expect32_at -2, 0x23050000\n",
                      ".if readu8(outputname(), org() - headersize()) != 5\n  .error \"x\"\n.endif\n"):
            with self.subTest(guard=guard):
                self.assertEqual(self.lint(".org 0x02000010\n.area 2\n" + guard + "    mov r3, #7\n.endarea\n"), [])
                self.assertEqual(self.lint(".org 0x02000010\n" + guard + ".area 2\n    mov r3, #7\n.endarea\n"), [])

    def test_guard_must_follow_the_org(self):
        # a guard of the previous .org block does not cover the next one
        probs = self.lint(self.GOOD + ".org 0x02000012\n.area 2\n    mov r3, #7\n.endarea\n",
                          regions=(("0x10", "2305 2305"),))
        self.assertProblem(probs, "t/t.asm:12: the .area's first write (line 13) has no guard")
        # a guard after the first write does not count
        probs = self.lint(".org 0x02000010\n.area 2\n    mov r3, #7\n    expect16 0x2305\n.endarea\n")
        self.assertProblem(probs, "has no guard")

    def test_read_only_check_is_not_a_guard(self):
        probs = self.lint(".org 0x02000010\n    expect32_abs 0x02000020, org()\n.area 2\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "has no guard")
        self.assertIsNone(F.guard_kind("text_speed_state != org() - 26"))
        self.assertEqual(F.guard_kind("readu32(outputname(), (0x02000020) - headersize()) != (org())"), "abs")
        self.assertEqual(F.guard_kind("readu16(outputname(), org() + (2) - headersize()) != (5)"), "pos")
        self.assertEqual(F.guard_kind("filesize(outputname()) != org() - headersize()"), "end")

    # -- region ------------------------------------------------------------------------------------
    def test_area_outside_the_regions(self):
        probs = self.lint(".org 0x02000012\n.area 2\n    expect16 0\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "t/t.asm:7: .area 0x02000012-0x02000014 (arm9+0x12, 2 bytes) is not inside one "
                                  "region fix.toml declares in arm9")
        probs = self.lint(".org 0x02000010\n.area 4\n    expect16 0x2305\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "0x02000010-0x02000014")
        # adjacent regions together cover an area
        self.assertEqual(self.lint(".org 0x02000010\n.area 4\n    expect32 0x23052305\n    .word 0\n.endarea\n",
                                   regions=(("0x10", "0x2305"), ("0x12", "0x2305"))), [])

    def test_region_from_names_and_macros(self):
        body = ("T_ADDR equ 0x02000000 + 0x10\n.definelabel T_Label, T_ADDR - 2\nSIZE equ 2\n"
                ".macro patch, addr, value\n.org addr\n.area SIZE\n    expect16 0x2305\n    .halfword value\n"
                ".endarea\n.endmacro\n    patch T_Label + 2, 7\n")
        self.assertEqual(self.lint(body), [])
        self.assertProblem(self.lint(body.replace("T_Label + 2, 7", "T_Label, 7")), "is not inside one region")

    def test_unresolvable_org(self):
        probs = self.lint(".org somewhere\n.area 2\n    expect16 0x2305\n    mov r3, #7\n.endarea\n")
        self.assertProblem(probs, "cannot resolve .org somewhere statically")

    def test_appended_area_needs_a_grow(self):
        body = ".org 0x02000040\n.area 16\n    expect_end\nlab:\n    .word 1\n.endarea\n"
        self.assertProblem(self.lint(body), "data appended to arm9.bin (expect_end), but fix.toml has no [[grow]]")
        self.assertEqual(self.lint(body, grow="arm9"), [])

    def test_read_only_block_may_be_anywhere(self):
        self.assertEqual(self.lint(".org 0x02000100\n    expect16_at 0, 0x1234\n    expect16_at 2, 0x5678\n"
                                   + self.GOOD), [])

    def test_negative_area_and_block_comments(self):
        probs = self.lint(".org 0x02000010\n.area 2 - 4\n    expect16 0x2305\n    mov r3, #7\n.endarea\n")
        self.assertEqual(probs, ["t/t.asm:7: .area 2 - 4 is -2 bytes (must be positive)"])
        probs = self.lint("/* .org 0x02000010\n.halfword 1 */\n" + self.GOOD)
        self.assertProblem(probs, "t/t.asm:6: /* */ block comments are not supported")
        self.assertEqual(self.lint('; /* in a comment */\n.org 0x02000010 ; "/*"\n.area 2\n    expect16 0x2305\n'
                                   '    .halfword 7\n.endarea\n'), [])

    def test_include_files_define_only(self):
        good = "; helpers\nX equ 2\n.definelabel L, 0x02000010\n.macro put, v\n    .halfword v\n.endmacro\n"
        self.assertEqual(F.include_problems(good.splitlines(), "inc"), [])
        bad = good + ".org 0x02000010\n    .halfword 1\n/* x */\n"
        probs = F.include_problems(bad.splitlines(), "inc")
        self.assertEqual(len(probs), 4, probs)             # .org, .halfword, the block comment twice
        self.assertIn("inc:7: an include file may only define macros, equ constants and .definelabel labels "
                      "(found: .org 0x02000010)", probs[1])
        self.assertIn("inc:9: /* */ block comments", probs[0])
        with tempfile.TemporaryDirectory() as td:          # a shared include: every file of include/ is checked
            (Path(td) / F.INCLUDE_DIR).mkdir()
            (Path(td) / F.INCLUDE_DIR / "local.inc").write_text(bad, encoding="utf-8")
            probs = F.lint_includes(td)
            self.assertTrue(any(p.startswith("include/local.inc:7: an include file may only define") for p in probs),
                            probs)
        probs = self.lint('.include "../include/missing.inc"\n' + self.GOOD)
        self.assertIn("t/t.asm: .include '../include/missing.inc' not found", probs)
        self.assertEqual(F.lint_includes(), [])            # guards.inc, charmap.inc, charmap.tbl

    def test_include_only_in_its_canonical_form(self):
        # armips resolves includes against its working directory (<stage>/rom): only ../include/<name>.inc
        # is staged and linted; any other form could pull in a file nobody checked
        for line in ('.include "local.inc"\n', '.include "../include/helper.s"\n', 'lbl: .include "../include/x.inc"\n',
                     'F equ "../include/x.inc"\n.include F\n', '.include "../include/guards.inc", "UTF-8"\n',
                     '.INCLUDE "../t/other.inc"\n'):
            probs = self.lint(line + self.GOOD)
            self.assertProblem(probs, "write includes as `.include \"../include/<name>.inc\"`")
        self.assertEqual(self.lint('.include "../include/charmap.inc" ; ok\n' + self.GOOD), [])

    def test_include_folder_holds_only_checked_files(self):
        with tempfile.TemporaryDirectory() as td:
            inc = Path(td) / F.INCLUDE_DIR
            inc.mkdir()
            (inc / "helper.s").write_text(".definelabel GUARDS_OFF, 1\n")
            (inc / "sub").mkdir()
            (inc / "t.tbl").write_text("2B01=A\n/FFFF\n.definelabel X, 1\n")
            (inc / "a.inc").write_text('X equ 1\n.include "../include/b.s"\n')
            probs = F.lint_includes(td)
            for want in ("include/helper.s: only .inc includes and .tbl table files", "include/sub: only .inc",
                         "include/t.tbl:3: not an armips table line", "include/a.inc:2: write includes as"):
                self.assertTrue(any(p.startswith(want) for p in probs), (want, probs))

    # -- guards off ---------------------------------------------------------------------------------
    def test_guards_off_name_is_reserved(self):
        for line in (".definelabel GUARDS_OFF, 1\n", "guards_off equ 1\n", ".if defined(GUARDS_OFF)\n.endif\n"):
            probs = self.lint(line + self.GOOD)
            self.assertProblem(probs, "t/t.asm:6: GUARDS_OFF is reserved")
        self.assertEqual(self.lint("; GUARDS_OFF in a comment is fine\n" + self.GOOD), [])
        self.assertEqual(self.lint(".definelabel GUARDS_OFF_X, 1\n" + self.GOOD), [])     # another name
        # only guards.inc may test it, and only with defined()
        lines = [".macro m", "  .if !defined(GUARDS_OFF) && 1", "  .endif", ".endmacro"]
        self.assertEqual(F.guards_off_problems(lines, "include/guards.inc", allow_defined=True), [])
        self.assertTrue(F.guards_off_problems(lines, "include/other.inc"))
        self.assertTrue(F.guards_off_problems(["GUARDS_OFF equ 1"], "include/guards.inc", allow_defined=True))
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / F.INCLUDE_DIR).mkdir()
            (Path(td) / F.INCLUDE_DIR / "other.inc").write_text(".definelabel GUARDS_OFF, 1\n")
            self.assertTrue(any("include/other.inc:1: GUARDS_OFF is reserved" in p for p in F.lint_includes(td)))
        guards = (F.PATCHES_DIR / F.INCLUDE_DIR / F.GUARDS_INC).read_text(encoding="utf-8")
        self.assertEqual(guards.count("!defined(GUARDS_OFF) && "), 4)       # every guard macro's condition

    def test_comments_and_quotes(self):
        self.assertEqual(F._strip_comment('.string "a;b\\"c;d" ; x'), '.string "a;b\\"c;d" ')
        self.assertEqual(F._strip_comment("mov r0, #1 // x"), "mov r0, #1 ")
        self.assertEqual(F._split_args('a, f(b, c), "d,e"'), ["a", "f(b, c)", '"d,e"'])
        self.assertEqual(F.eval_asm_expr("BASE + 4 * (2 << 1) - 0x10 / 4", {"base": "0x100"}), 0x100 + 16 - 4)
        self.assertIsNone(F.eval_asm_expr("org() + 2", {}))

    def test_real_source_without_its_guard(self):
        fx = {f["id"]: f for f in F.load_all()}["namelen"]
        src = F.asm_path(fx).read_text(encoding="utf-8")
        probs = F.lint_asm(src.replace("    expect16 0x2305             ; mov r3, #5\n", "", 1), fx,
                           F.load_overlays(), name="namelen.asm")
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("namelen/namelen.asm:23: the .area's first write (line 24) has no guard", probs[0])

    def test_real_sources_are_clean(self):
        bases = F.load_overlays()
        for fx in F.load_all():
            src = F.asm_path(fx)
            if src is None:
                continue
            with self.subTest(fix=fx["id"]):
                self.assertEqual(F.lint_asm(src.read_text(encoding="utf-8"), fx, bases, name=src.name), [])


class RealRegistry(unittest.TestCase):
    """The checked-in work/patches."""

    @classmethod
    def setUpClass(cls):
        cls.fixes = F.load_all()

    def test_valid_and_complete(self):
        self.assertEqual(F.validate(self.fixes), [])
        ids = {f["id"] for f in self.fixes}
        for fid in ("namelen", "naming-keyboard", "msgload", "font-glyphs", "outfit-chooser-strings",
                    "gfx-naming-tabs", "gfx-title-subtitle"):
            self.assertIn(fid, ids)
        self.assertIn("naming-keyboard", {f["id"]: f for f in self.fixes}["gfx-naming-tabs"]["requires"])

    def test_every_fix_documents_itself(self):
        register = F.WORK / "translate" / "decisions" / "decisions.jsonl"
        known = {json.loads(line)["id"] for line in register.read_text(encoding="utf-8").splitlines() if line.strip()}
        for f in self.fixes:
            # every fix names its decisions, and they are in the register
            self.assertTrue(f["decisions"], f["id"])
            self.assertLessEqual(set(f["decisions"]), known, f["id"])
            self.assertGreater(len(f["why"].strip()), 80, f["id"])
            self.assertGreater(len(f["what"].strip()), 30, f["id"])

    def test_overlay_bases_match_rom(self):
        rom_cn = F.ROM_CN
        if not rom_cn.exists():
            self.skipTest("Chinese ROM missing")
        import msgtool as m
        F.check_overlay_bases(m.load_rom(rom_cn))
        bases = F.load_overlays()
        self.assertEqual(bases["overlay58"], 0x021E83C0)
        self.assertEqual(bases["overlay14"], 0x022007E0)

    def test_sizes_match_rom(self):
        rom_cn = F.ROM_CN
        if not rom_cn.exists():
            self.skipTest("Chinese ROM missing")
        import msgtool as m
        rom = m.load_rom(rom_cn)
        sizes = F.load_sizes()
        self.assertEqual(F.rom_sizes(rom, sizes), sizes)        # also part of check_overlay_bases (above)
        files = {e["file"] for fx in self.fixes if fx.get("asm") for t in ("code", "string", "grow")
                 for e in fx.get(t, [])}
        self.assertEqual(set(sizes), files, "regenerate: python3 work/tools/fixes.py overlays")
        with tempfile.TemporaryDirectory() as td:
            shutil.copy(F.PATCHES_DIR / "overlays.toml", td)
            (Path(td) / "sizes.toml").write_text("[overlay58]\nsize = 0x7E4\nbss = 0\n")
            with self.assertRaises(F.FixError) as cm:
                F.check_overlay_bases(rom, td)
            self.assertIn("overlay58: sizes.toml size 0x7e4, bss 0x0, ROM size 0x7e0, bss 0x0",
                          str(cm.exception))

    def test_default_selection(self):
        act = F.select(self.fixes)
        self.assertEqual({f["id"] for f in act}, {f["id"] for f in self.fixes if f["enabled"]})
        with self.assertRaises(F.FixError):
            F.select(self.fixes, without="naming-keyboard")
        self.assertEqual(F.font_spec(act), ("a/0/1/6", (0, 1, 2, 4), (0x01AF, 0x01B4, 0x01B5)))

    def test_generated_docs_are_current(self):
        md = (F.PATCHES_DIR / "FIXES.md").read_text(encoding="utf-8")
        self.assertEqual(md, F.render_docs(self.fixes), "regenerate: python3 work/tools/fixes.py docs "
                                                        "--out work/patches/FIXES.md")


class BuildFlags(unittest.TestCase):
    def test_without_required_fix_stops_before_export(self):
        import build as B
        with tempfile.TemporaryDirectory() as td, \
                patch.object(B.ws, "export", side_effect=AssertionError("export must not run")):
            with self.assertRaises(SystemExit) as cm:
                B.main(["--work-dir", td, "--without", "naming-keyboard"])
            self.assertIn("requires 'naming-keyboard'", str(cm.exception.code))
            with self.assertRaises(SystemExit) as cm:
                B.main(["--work-dir", td, "--no-hardcoded"])
            self.assertIn("excluded by its kind", str(cm.exception.code))


if __name__ == "__main__":
    unittest.main()
