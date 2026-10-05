"""Unit tests for emu_harness's pure parts (no emulator, no ROM, no save fixtures)."""
import binascii
import random
import struct
import tempfile
import unittest
from pathlib import Path

import emu_harness as E


def _encrypted_mon(seed=1, species=201, item=0, form=0):
    rnd = random.Random(seed)
    raw = bytearray(rnd.getrandbits(8) for _ in range(136))
    struct.pack_into("<IHH", raw, 0, rnd.getrandbits(32), 0, 0)
    return E.encode_pokemon(bytes(raw), species=species, item=item, form=form)


class PokemonCodec(unittest.TestCase):
    def test_roundtrip_and_checksum(self):
        for seed in range(30):
            raw = _encrypted_mon(seed, species=200 + seed, item=seed, form=seed % 28)
            mon = E.decode_pokemon(raw)
            self.assertTrue(mon["checksum_ok"])
            self.assertEqual((mon["species"], mon["item"], mon["form"]), (200 + seed, seed, seed % 28))

    def test_form_keeps_gender_bits(self):
        raw = _encrypted_mon(3)
        before = E.decode_pokemon(raw)
        after = E.decode_pokemon(E.encode_pokemon(raw, form=5))
        self.assertEqual(after["form"], 5)
        self.assertEqual(after["fateful"], before["fateful"])


class SaveFileEdits(unittest.TestCase):
    def _save(self, newest=0x40000):
        data = bytearray(524288)
        for counter, base in ((5, 0), (6, 0x40000)):
            if base != newest:
                counter = 4
            struct.pack_into("<IIIH", data, base + E.GENERAL_SIZE - 16, counter, E.GENERAL_SIZE, E.FOOTER_MAGIC, 0)
            crc = binascii.crc_hqx(bytes(data[base:base + E.GENERAL_SIZE - 16]), 0xFFFF)
            struct.pack_into("<H", data, base + E.GENERAL_SIZE - 2, crc)
        path = Path(tempfile.mkdtemp()) / "t.sav"
        path.write_bytes(bytes(data))
        return path

    def test_edits_newest_block_and_fixes_crc(self):
        path = self._save()
        sf = E.SaveFile(path)
        self.assertEqual(sf.base, 0x40000)
        sf.set_location(315, 17, 24)
        sf.set_flag(2423)
        out = path.with_name("o.sav")
        sf.write(out)
        again = E.SaveFile(out)
        self.assertEqual(again.base, 0x40000)
        self.assertEqual(again.location()["map"], 315)
        self.assertTrue(again.get_flag(2423))
        self.assertFalse(again.get_flag(2424))
        self.assertEqual(out.read_bytes()[:E.GENERAL_SIZE], path.read_bytes()[:E.GENERAL_SIZE])

    def test_place_player_moves_player_and_drops_npcs(self):
        path = self._save()
        sf = E.SaveFile(path)
        for slot, obj_id in ((0, E.PLAYER_OBJ_ID), (1, E.FOLLOWER_OBJ_ID), (2, 3)):
            a = sf._a(E.ARR_MAP_OBJECTS, E.MAP_OBJECT_SIZE * slot)
            struct.pack_into("<I", sf.data, a, 0xC061)
            sf.data[a + 8] = obj_id
        sf.place_player(315, 17, 24)
        objs = {o["id"]: o for o in sf.map_objects()}
        self.assertEqual(set(objs), {E.PLAYER_OBJ_ID, E.FOLLOWER_OBJ_ID})
        self.assertEqual((objs[E.PLAYER_OBJ_ID]["x"], objs[E.PLAYER_OBJ_ID]["z"]), (17, 24))


if __name__ == "__main__":
    unittest.main()
