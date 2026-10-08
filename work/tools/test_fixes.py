#!/usr/bin/env python3
"""Unit tests for fixes.py (the work/patches registry). Run:  python3 -m unittest -v work/tools/test_fixes.py"""
import contextlib
import io
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


def asm_for(toml_text):
    """A minimal armips source that opens every file the fix's entries name, at its load address, and writes
    each [[string]] en with .string."""
    files = sorted(set(re.findall(r'^file = "((?:arm9|overlay\d+))"', toml_text, re.M)))
    ens = re.findall(r'^en = "([^"]*)"', toml_text, re.M)
    head = '.loadtable "../include/charmap.tbl", "UTF-8"\n' if ens else ""
    return head + "".join(f'.open "{f}.bin", 0x{BASES.get(f, 0x02200000):08X}\n' +
                          "".join(f'.string "{en}"\n' for en in ens) + ".close\n" for f in files[:1]) + \
        "".join(f'.open "{f}.bin", 0x{BASES.get(f, 0x02200000):08X}\n.close\n' for f in files[1:])


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

    def test_applier_instead_of_asm(self):
        sha = 'length = 64\nexpect_sha1 = "' + "0" * 40 + '"'
        region = code_entry("t-1", file="overlay50", offset="0x0").replace('expect = "0x2305"', sha)
        self.write("t", fix_toml("t", asm="", extra='applier = "text_speed_patch"\n', entries=region))
        self.write("u", fix_toml("u", entries=code_entry("u-1", offset="0x20", file="overlay50")))
        probs = self.problems()
        self.assertTrue(any("overlap in overlay50" in p for p in probs), probs)   # the sha1 region is 64 bytes
        fixes = F.load_all(self.root, validate_all=False)
        self.assertEqual([f["id"] for f in F.applier_fixes(fixes)], ["t"])
        self.assertEqual([f["id"] for f in F.code_entries_fixes(fixes)], ["u"])
        self.assertIn("original SHA-1", F.render_docs(fixes, {"overlay50": 0x021E4980}))
        # unknown applier, applier with asm, half a sha1 region
        self.write("t", fix_toml("t", extra='applier = "evil"\n', entries=code_entry("t-1", offset="0x60")))
        self.write("u", fix_toml("u", entries=code_entry("u-1", offset="0x20").replace('expect = "0x2305"',
                                                                                      'length = 3')))
        probs = self.problems()
        for want in ("unknown applier 'evil'", "give asm or applier, not both", "length must be a positive even",
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
        self.assertTrue(any("a.asm:3: opens 'overlay12.bin', but the fix declares no [[code]] / [[string]] / [[grow]] in it"
                            in p for p in probs), probs)
        self.assertTrue(any("a.asm:4: write .open as" in p for p in probs), probs)
        self.assertTrue(any("a.asm:5: write .open as" in p for p in probs), probs)
        probs = probs_for('; .open "overlay58.bin", 0x021E83C0 is only a comment\n.open "arm9.bin", 0x02000000\n')
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
        self.assertTrue(any("file must be 'overlayNN' (only an overlay can grow)" in p for p in probs), probs)
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
        self.assertIn("<summary>zeta.asm</summary>\n\n```asm\n.open \"arm9.bin\", 0x02000000\n.close\n```", md)
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
        for f in self.fixes:
            # a fix without a decision must say in its evidence which decision is pending
            self.assertTrue(f["decisions"] or any(e.startswith("Decision pending:") for e in f["evidence"]), f["id"])
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
