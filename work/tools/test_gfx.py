#!/usr/bin/env python3
"""Unit tests for the graphics helpers in gfx.py that need no ROM (run with the other tests:
python3 -m unittest discover -s work/tools -p 'test_*.py')."""
import os
import random
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gfx  # noqa: E402


def _ncgr(tiles, bpp=4):
    """Minimal uncompressed RGCN container holding `tiles` (lists of 64 indices)."""
    data = b"".join(bytes((t[i] & 15) | (t[i + 1] & 15) << 4 for i in range(0, 64, 2)) if bpp == 4 else bytes(t)
                    for t in tiles)
    rahc = b"RAHC" + struct.pack("<I", 0x20 + len(data)) + struct.pack(
        "<HHIIIII", 1, len(tiles), 3 if bpp == 4 else 4, 0, 0, len(data), 0x18) + data
    return b"RGCN" + struct.pack("<HHIHH", 0xFEFF, 0x0101, 16 + len(rahc), 16, 1) + rahc


def _nscr(w, h, ents):
    data = b"".join(struct.pack("<H", e) for e in ents)
    nrcs = b"NRCS" + struct.pack("<I", 0x14 + len(data)) + struct.pack("<HHII", w, h, 0, len(data)) + data
    return b"RCSN" + struct.pack("<HHIHH", 0xFEFF, 0x0100, 16 + len(nrcs), 16, 1) + nrcs


class Lz11(unittest.TestCase):
    def test_roundtrip(self):
        rnd = random.Random(1)
        for data in (b"a", bytes(5000), bytes(rnd.randrange(4) for _ in range(20000)),
                     b"abcabcabcabd" * 900):
            self.assertEqual(gfx.lz11_decompress(gfx.lz11_compress(data)), data)


class Screens(unittest.TestCase):
    def test_block_order_of_wide_screens(self):
        sc = gfx.NSCR(_nscr(512, 256, list(range(2048))))
        self.assertEqual(sc.pos(0), (0, 0))
        self.assertEqual(sc.pos(32), (0, 8))       # second row of the left 256x256 block
        self.assertEqual(sc.pos(1024), (256, 0))   # first entry of the right block

    def test_retile_keeps_unchanged_cells_and_uses_pool(self):
        blank, a, b = [0] * 64, [1] * 64, [2] * 64
        g = gfx.NCGR(_ncgr([blank, a, a, blank]))
        sc = gfx.NSCR(_nscr(16, 8, [1, 1]))         # both cells show tile 1
        tgt = gfx.screen_to_image(sc, g)
        for y in range(8):
            for x in range(8, 16):
                tgt[y][x] = (0, 2)                  # right cell becomes colour 2
        tiles, (ents,) = gfx.retile(g, [(sc, tgt)], pool=[3, 2])
        self.assertEqual(ents[0], 1)                # unchanged cell keeps its tile
        self.assertEqual(tiles[ents[1] & 0x3FF], b)
        self.assertEqual(tiles[1], a)
        out = gfx.NSCR(sc.with_entries(ents))
        self.assertEqual(out.ents, ents)

    def test_tile_range_op(self):
        g = _ncgr([[0] * 64] * 4)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            png = Path(td) / "s.png"
            _write_indexed_png(png, 32, 8, [[5] * 32] * 8)
            new = gfx._patched_member({"op": "tile_range_from_png", "first": 0, "src": "s.png"}, 0, g, None,
                                      Path(td))
        self.assertEqual(gfx.NCGR(new).tiles, [[5] * 64] * 4)


class CodeOp(unittest.TestCase):
    class View:
        def __init__(self, files):
            self.files = dict(files)

        def get(self, key):
            return self.files[key]

        def set(self, key, data):
            assert len(data) == len(self.files[key])
            self.files[key] = data

    def _op(self, cn, us, **kw):
        import hashlib
        op = {"op": "code_from_us", "file": "overlay14", "offset": "0x4", "us_file": "overlay12", "us_offset": "0x2",
              "length": 3, "expect_sha1": hashlib.sha1(cn[4:7]).hexdigest()[:12],
              "us_sha1": hashlib.sha1(us[2:5]).hexdigest()[:12]}
        op.update(kw)
        return op

    def test_copies_range_and_verifies(self):
        cn, us = bytes(range(10)), bytes(range(100, 110))
        code, usv = self.View({"overlay14": cn}), self.View({"overlay12": us})
        rep = gfx.apply_patches(None, None, None, manifest=[self._op(cn, us)], code=code, us_code=usv)
        self.assertEqual(code.files["overlay14"], cn[:4] + us[2:5] + cn[7:])
        self.assertEqual(gfx.verify_code_rows(code, rep), 1)

    def test_refuses_changed_hack_bytes(self):
        cn, us = bytes(range(10)), bytes(range(100, 110))
        code, usv = self.View({"overlay14": cn}), self.View({"overlay12": us})
        with self.assertRaises(ValueError):
            gfx.apply_patches(None, None, None, manifest=[self._op(cn, us, expect_sha1="000000000000")],
                              code=code, us_code=usv)


class RuntimeLayouts(unittest.TestCase):
    def test_rejects_unloaded_tile_even_when_present_in_file(self):
        g = gfx.NCGR(_ncgr([[0] * 64] * 96))
        sc = gfx.NSCR(_nscr(8, 8, [74]))
        with self.assertRaisesRegex(ValueError, "runtime loads only tiles 0..47"):
            gfx.validate_screen_tiles(sc, g, 0x600, "Chain Logger")

    def test_tile_limit_ignores_palette_and_flip_flags(self):
        g = gfx.NCGR(_ncgr([[0] * 64] * 96))
        sc = gfx.NSCR(_nscr(8, 8, [0xBC00 | 47]))
        self.assertEqual(gfx.validate_screen_tiles(sc, g, 0x600, "bar"),
                         {"loaded_tiles": 48, "highest_tile": 47})

    def test_8bpp_tiles_use_64_bytes(self):
        g = gfx.NCGR(_ncgr([[0] * 64] * 4, bpp=8))
        sc = gfx.NSCR(_nscr(8, 8, [2]))
        with self.assertRaisesRegex(ValueError, "tiles 0..1"):
            gfx.validate_screen_tiles(sc, g, 128, "8bpp")
        self.assertEqual(gfx.validate_screen_tiles(sc, g, 0, "whole member")["loaded_tiles"], 4)

    def test_refuses_invalid_load_sizes(self):
        g = gfx.NCGR(_ncgr([[0] * 64] * 4))
        sc = gfx.NSCR(_nscr(8, 8, [0]))
        for size in (-32, 33, 160):
            with self.subTest(size=size), self.assertRaises(ValueError):
                gfx.validate_screen_tiles(sc, g, size, "bad size")

    def test_replacement_cannot_grow_a_character_buffer(self):
        with self.assertRaisesRegex(ValueError, "count/mapping changed"):
            gfx.validate_member_layout(_ncgr([[0] * 64]), _ncgr([[0] * 64] * 2), "replacement")

    def test_replacement_cannot_resize_a_screen(self):
        with self.assertRaisesRegex(ValueError, "dimensions/entry count changed"):
            gfx.validate_member_layout(_nscr(8, 8, [0]), _nscr(16, 8, [0, 0]), "replacement")

    def test_unregistered_screen_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError, "no audited runtime allocation"):
            gfx.check_layouts(None, rules=[], changed_screens=[("new.narc", 2)])

    def test_loader_change_invalidates_audited_limit(self):
        rule = {"narc": "bar.narc", "graphic": 1, "screens": [0], "loaded_bytes": 32,
                "load_sites": [{"file": "overlay28", "offset": 0, "length": 4,
                                "expect_sha1": "000000000000"}]}
        with self.assertRaisesRegex(ValueError, "audited graphics loader changed"):
            gfx.check_layouts(None, code=CodeOp.View({"overlay28": b"abcd"}), rules=[rule])


def _write_indexed_png(path, w, h, rows):
    import zlib

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\0" + bytes(r) for r in rows)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0)) + \
        chunk(b"PLTE", bytes(48)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(png)


class Png(unittest.TestCase):
    def test_write_read_roundtrip_8bit(self):
        import tempfile
        from pathlib import Path
        px = [random.randrange(16) for _ in range(24 * 16)]
        pal = [(i * 16, 255 - i * 16, i) for i in range(16)]
        with tempfile.TemporaryDirectory() as td:
            p = gfx.write_indexed_png(Path(td) / "x.png", 24, 16, px, pal)
            w, h, rows, got_pal = gfx.read_indexed_png(p, with_palette=True)
        self.assertEqual((w, h), (24, 16))
        self.assertEqual(b"".join(rows), bytes(px))
        self.assertEqual(got_pal[:16], pal)

    def test_reads_4bit_png(self):
        import tempfile
        import zlib
        from pathlib import Path
        w, h = 5, 2
        px = [[1, 2, 3, 15, 7], [0, 9, 4, 5, 6]]

        def chunk(t, b):
            return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b))
        raw = b""
        for r in px:
            r = r + [0]
            raw += b"\x00" + bytes(r[i] << 4 | r[i + 1] for i in range(0, len(r), 2))
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 4, 3, 0, 0, 0))
                + chunk(b"PLTE", bytes(48)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.png"
            p.write_bytes(data)
            _, _, rows = gfx.read_indexed_png(p)
        self.assertEqual([list(r) for r in rows], px)

    def test_manifest_src_outside_graphics(self):
        from pathlib import Path
        self.assertEqual(gfx._manifest_src(gfx.GRAPHICS / "generated" / "a.bin"), "generated/a.bin")
        self.assertEqual(gfx._manifest_src("/tmp/elsewhere/a.bin"), str(Path("/tmp/elsewhere/a.bin").resolve()))


if __name__ == "__main__":
    unittest.main()
