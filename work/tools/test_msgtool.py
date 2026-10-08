#!/usr/bin/env python3
"""Unit tests for msgtool.py. Run:  python3 -m unittest -v work/tools/test_msgtool.py"""
import json
import os
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import msgtool as m  # noqa: E402

EN = HERE / "charmap_en.tsv"
ZH = HERE / "charmaps" / "charmap_zh_xzonn_gen4.tsv"


def cm_en():
    return m.Charmap.load([EN])


def cm_mixed():
    return m.Charmap.load([EN, ZH])


def reference_encrypt(seed, strings):
    """Independent re-implementation straight from pret msgenc (MessagesConverter.h)."""
    count = len(strings)
    out = bytearray(struct.pack("<HH", count, seed))
    pos = 4 + 8 * count
    body = bytearray()
    for idx, s in enumerate(strings, start=1):
        alloc_key = (765 * idx * seed) & 0xFFFF
        alloc_key |= alloc_key << 16
        out += struct.pack("<II", pos ^ alloc_key, len(s) ^ alloc_key)
        key = (idx * 596947) & 0xFFFF
        for code in s:
            body += struct.pack("<H", code ^ key)
            key = (key + 18749) & 0xFFFF
        pos += 2 * len(s)
    return bytes(out + body)


class TestCrypto(unittest.TestCase):
    def test_matches_reference_and_roundtrips(self):
        rng = random.Random(1234)
        for _ in range(50):
            seed = rng.randrange(0x10000)
            strings = [[rng.randrange(0x10000) for _ in range(rng.randrange(0, 40))] + [0xFFFF]
                       for _ in range(rng.randrange(0, 30))]
            data = m.encrypt_bank(seed, strings)
            self.assertEqual(data, reference_encrypt(seed, strings))
            s2, got, trailer = m.decrypt_bank(data)
            self.assertEqual((s2, got, trailer), (seed, strings, b""))

    def test_trailer_preserved(self):
        data = m.encrypt_bank(0xBEEF, [[0x12B, 0xFFFF]], b"\x00\x00")
        self.assertEqual(m.decrypt_bank(data)[2], b"\x00\x00")

    def test_data_is_actually_encrypted(self):
        data = m.encrypt_bank(0x1111, [[0x12B, 0x12C, 0xFFFF]])
        self.assertNotIn(struct.pack("<3H", 0x12B, 0x12C, 0xFFFF), data)


class TestCodec(unittest.TestCase):
    def rt(self, text, cm=None):
        cm = cm or cm_en()
        units = m.encode_text(text, cm)
        self.assertEqual(units[-1], 0xFFFF)
        self.assertEqual(m.decode_units(units, cm), text)
        return units

    def test_latin(self):
        u = self.rt("Hello, POKéMON!")
        self.assertEqual(u[0], 0x132)          # 'H'
        self.assertEqual(u[5], 0x1AD)          # ','
        self.assertEqual(u[6], 0x1DE)          # space

    def test_control_codes(self):
        u = self.rt("A{NEWLINE}B{SCROLL}C{CLEAR}D")
        self.assertEqual(u, [0x12B, 0xE000, 0x12C, 0x25BC, 0x12D, 0x25BD, 0x12E, 0xFFFF])

    def test_commands(self):
        u = self.rt("{VAR:0101:0,0} used {VAR:0107:1,0}!{VAR:0201}")
        self.assertEqual(u[:5], [0xFFFE, 0x0101, 2, 0, 0])
        self.assertIn(0x0201, u)
        i = u.index(0x0201)
        self.assertEqual(u[i - 1:i + 2], [0xFFFE, 0x0201, 0])

    def test_unknown_code(self):
        u = self.rt("x{U+ABCD}y{U+0000}")
        self.assertEqual(u[1], 0xABCD)
        self.assertEqual(u[3], 0x0000)

    def test_literal_newline_alias(self):
        self.assertEqual(m.encode_text("A\nB", cm_en()), [0x12B, 0xE000, 0x12C, 0xFFFF])

    def test_mixed_language_bank_text(self):
        cm = cm_mixed()
        u = self.rt("小赤『去吧妙蛙草！{NEWLINE}Go, BULBASAUR!", cm)
        self.assertEqual(u[:2], [cm.enc["小"], cm.enc["赤"]])
        self.assertTrue(all(c >= 0x1FF for c in u[:2]))
        self.assertIn(0x12C, u)                 # 'B' still the vanilla code
        self.assertEqual(cm.enc["的"], 0x096F)  # verified against v4.0.3 font/text

    def test_unencodable_raises(self):
        with self.assertRaises(ValueError):
            m.encode_text("☃☄", cm_en())
        with self.assertRaises(ValueError):
            m.encode_text("{BOGUS}", cm_en())

    def test_compressed_known_vectors(self):
        # taken from v3 Eng trainer-name bank (0x239 region): exact game encoding
        cm = cm_en()
        self.assertEqual(m.encode_text("{COMPRESSED}Don", cm), [0xF100, 0x272E, 0x7A95, 0xFFFF])
        self.assertEqual(m.encode_text("{COMPRESSED}Ed", cm), [0xF100, 0x112F, 0x7FFD, 0xFFFF])
        self.assertEqual(m.encode_text("{COMPRESSED}Abby", cm), [0xF100, 0x0D2B, 0x5A35, 0x7FEB, 0xFFFF])
        for t in ("{COMPRESSED}Don", "{COMPRESSED}Ed", "{COMPRESSED}Abby", "{COMPRESSED}", "{COMPRESSED}Abcdefghijklmno"):
            self.assertEqual(m.decode_units(m.encode_text(t, cm), cm), t)

    def test_compressed_rejects_wide_codes(self):
        with self.assertRaises(ValueError):
            m.encode_text("{COMPRESSED}的", cm_mixed())

    def test_compressed_name_sizes(self):
        # the battle copies a trainer name into u16[8] incl. the terminator (D-1326)
        cm = cm_en()
        for name, units in (("Giovanni", 7), ("Lt. Surge", 8), ("Kangaskhan", 8), ("Gold", 5), ("", 2)):
            u = m.encode_text("{COMPRESSED}" + name, cm)
            self.assertEqual(len(u), units, name)
            self.assertEqual(u[0], 0xF100)
            self.assertTrue(all(x <= 0x7FFF for x in u[1:-1]))       # never an early 0xFFFF / 0xFFFE
            self.assertEqual(m.decode_units(u, cm), "{COMPRESSED}" + name)
        self.assertEqual(len(m.encode_text("{COMPRESSED}Kangaskhan1", cm)), 9)   # 11 chars no longer fit

    def test_game_decompressor_reference(self):
        # independent re-implementation of pret String_Cat_HandleTrainerName (hack arm9 0x0202703C)
        def game_expand(units):
            out, p, bit = [], 1, 0
            while True:
                cur = (units[p] >> bit) & 0x1FF
                bit += 9
                if bit >= 15:
                    p += 1
                    bit -= 15
                    if bit:
                        cur |= (units[p] << (9 - bit)) & 0x1FF
                if cur == 0x1FF:
                    return out
                out.append(cur)
        cm = cm_en()
        for name in ("Giovanni", "Lt. Surge", "Prof. Oak", "Granny Mae", "Mr. Mime", "A", "Poké Fan"):
            plain = m.encode_text(name, cm)[:-1]
            self.assertEqual(game_expand(m.encode_text("{COMPRESSED}" + name, cm)), plain, name)

    def test_stored_name_text(self):
        cm = cm_en()
        self.assertEqual(m.stored_name_text("Giovanni", cm), "{COMPRESSED}Giovanni")
        self.assertEqual(m.stored_name_text("{COMPRESSED}Giovanni", cm), "{COMPRESSED}Giovanni")
        self.assertEqual(m.stored_name_text("Palmer", cm, compress=False), "Palmer")
        with self.assertRaises(ValueError):
            m.stored_name_text("Giovanni", cm, compress=False)              # 9 units plain > 8
        with self.assertRaises(ValueError):
            m.stored_name_text("Kangaskhans", cm)                           # 11 chars: 9 units packed
        cmx = cm_mixed()
        self.assertEqual(m.stored_name_text("坂木", cmx), "坂木")            # cannot pack; fits plain
        with self.assertRaises(ValueError):
            m.stored_name_text("一二三四五六七八", cmx)                         # cannot pack, too long plain

    def test_duplicate_charmap_entries(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.tsv"
            p.write_text("0010\tX\n0020\tX\n0030\tY\n", encoding="utf-8")
            cm = m.Charmap.load([p])
            self.assertEqual(cm.enc["X"], 0x10)
            self.assertEqual(m.decode_units([0x20, 0x10, 0xFFFF], cm), "{U+0020}X")
            p2 = Path(td) / "d.tsv"
            p2.write_text("0010\tZ\n", encoding="utf-8")   # override: X now only at 0x20
            cm2 = m.Charmap.load([p, p2])
            self.assertEqual(cm2.enc["X"], 0x20)
            self.assertEqual(cm2.enc["Z"], 0x10)


class TestBankJson(unittest.TestCase):
    def test_roundtrip_with_pad_raw_and_trailer(self):
        cm = cm_mixed()
        strings = [
            m.encode_text("Hello{NEWLINE}World", cm),
            m.encode_text("你好{VAR:0100:0,0}", cm) + [0xFFFF, 0xFFFF],      # padded slot (v3 style)
            [0x12B, 0xFFFF, 0x12C, 0xFFFF],                                  # junk after terminator
            [0x12B, 0x12C],                                                  # no terminator
            [],                                                              # empty entry
            m.encode_text("{COMPRESSED}Ed", cm),
        ]
        data = m.encrypt_bank(0x4242, strings, b"\x00\x00")
        obj = m.bank_to_json(7, data, cm)
        self.assertEqual(obj["strings"][1].get("pad"), 2)
        self.assertNotIn("raw_hex", obj["strings"][0])
        self.assertIn("raw_hex", obj["strings"][2])
        self.assertIn("raw_hex", obj["strings"][3])
        self.assertIn("raw_hex", obj["strings"][4])
        obj = json.loads(json.dumps(obj, ensure_ascii=False))
        self.assertEqual(m.json_to_bank(obj, cm), data)
        # edit a string that had raw_hex -> the edited text wins
        obj["strings"][2]["text"] = "Changed"
        obj["strings"][0]["text"] = "Bye"
        _, got, _ = m.decrypt_bank(m.json_to_bank(obj, cm))
        self.assertEqual(got[2], m.encode_text("Changed", cm))
        self.assertEqual(got[0], m.encode_text("Bye", cm))


class TestNarc(unittest.TestCase):
    def test_build_parse_roundtrip(self):
        files = [b"abc", b"", b"\x01\x02\x03\x04", b"xyzxy"]
        for pad_last in (True, False):
            for quirks in ((0, 0), (96, 8)):
                n = m.Narc(files, pad_last=pad_last, size_quirks=quirks)
                data = n.build()
                n2 = m.Narc.parse(data)
                self.assertEqual(n2.files, files)
                self.assertEqual(n2.pad_last, pad_last)
                self.assertEqual(n2.size_quirks, quirks)
                self.assertEqual(n2.build(), data)

    def test_matches_ndspy_reader(self):
        import ndspy.narc
        files = [os.urandom(random.randrange(1, 50)) for _ in range(20)]
        data = m.Narc(files).build()
        self.assertEqual([bytes(f) for f in ndspy.narc.NARC(data).files], files)


def make_rom(path: Path, banks: list[bytes]):
    """Tiny synthetic ROM with a/0/2/7 = message NARC built from `banks`."""
    import ndspy.fnt
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom()
    rom.name = bytearray(b"POKEMON HG")
    rom.idCode = bytearray(b"IPKE")
    other = b"other-file"
    msg = m.Narc(banks).build()
    root = ndspy.fnt.Folder(firstID=0)
    root.files = ["readme.txt"]
    a = ndspy.fnt.Folder(firstID=1)
    zero = ndspy.fnt.Folder(firstID=1)
    two = ndspy.fnt.Folder(files=["7"], firstID=1)
    zero.folders = [("2", two)]
    a.folders = [("0", zero)]
    root.folders = [("a", a)]
    rom.filenames = root
    rom.files = [other, msg]
    rom.saveToFile(str(path))


class TestRomLevel(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)
        cm = cm_mixed()
        self.cm_paths = [str(EN), str(ZH)]
        rng = random.Random(7)
        banks = []
        texts = [["Hi{NEWLINE}there", "妙蛙种子", "{VAR:0101:0,0}的{CLEAR}Go!"],
                 ["{COMPRESSED}Abby", "", "A{SCROLL}B"],
                 []]
        for t in texts:
            banks.append(m.encrypt_bank(rng.randrange(0x10000), [m.encode_text(x, cm) for x in t]))
        self.rom = self.dir / "t.nds"
        make_rom(self.rom, banks)

    def tearDown(self):
        self.td.cleanup()

    def test_roundtrip_command(self):
        m.main(["roundtrip", str(self.rom)] + sum([["--charmap", p] for p in self.cm_paths], []) + ["--rebuild-rom"])

    def test_extract_edit_insert(self):
        out = self.dir / "ex"
        cms = sum([["--charmap", p] for p in self.cm_paths], [])
        m.main(["extract", str(self.rom), str(out)] + cms)
        b0 = json.loads((out / "0000.json").read_text(encoding="utf-8"))
        self.assertEqual(b0["strings"][1]["text"], "妙蛙种子")
        b0["strings"][1]["text"] = "BULBASAUR"
        b0["strings"][0]["text"] = "A much longer English line{NEWLINE}than before!"
        (out / "0000.json").write_text(json.dumps(b0, ensure_ascii=False), encoding="utf-8")
        new = self.dir / "new.nds"
        m.main(["insert", str(self.rom), str(out), str(new)] + cms)
        rom = m.load_rom(new)
        narc = m.Narc.parse(m.get_file(rom, m.MSG_NARC_PATH))
        cm = cm_mixed()
        seed, strings, _ = m.decrypt_bank(narc.files[0])
        self.assertEqual(seed, b0["seed"])
        self.assertEqual(m.decode_units(strings[1], cm), "BULBASAUR")
        self.assertEqual(m.decode_units(strings[0], cm), "A much longer English line{NEWLINE}than before!")
        self.assertEqual(m.decode_units(strings[2], cm), "{VAR:0101:0,0}的{CLEAR}Go!")
        self.assertEqual(m.get_file(rom, "readme.txt"), b"other-file")


class TestCharmapGuess(unittest.TestCase):
    def test_guess_from_pairs(self):
        cm = cm_mixed()
        pairs = [(t, m.encode_text(t, cm)) for t in ["妙蛙种子", "妙蛙草", "妙蛙花", "小火龙"]]
        pairs.append(("长度不对", m.encode_text("短", cm)))
        pairs.append(("的的", [0xFFFE, 0x0100, 1, 0, 0x096F, 0xE000, 0x096F, 0xFFFF]))  # commands ignored
        votes, skipped = m.guess_charmap(pairs)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(votes[cm.enc["妙"]], {"妙": 3})
        self.assertEqual(votes[0x096F], {"的": 2})
        for ch in "种子草花小火龙":
            self.assertEqual(list(votes[cm.enc[ch]]), [ch])

    def test_cli_pairs_file(self):
        cm = cm_mixed()
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "pairs.tsv"
            u = m.encode_text("妙蛙", cm)
            p.write_text("妙蛙\t" + " ".join("%04X" % x for x in u) + "\n"
                         "蛙\t" + struct.pack("<2H", cm.enc["蛙"], 0xFFFF).hex() + "\n", encoding="utf-8")
            out = Path(td) / "g.tsv"
            m.main(["charmap-guess", "--pairs", str(p), "--charmap", str(EN), "--charmap", str(ZH), "--out", str(out)])
            rows = [l.split("\t") for l in out.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
            self.assertIn(["%04X" % cm.enc["蛙"], "蛙", "2", ""], rows)


if __name__ == "__main__":
    unittest.main()
