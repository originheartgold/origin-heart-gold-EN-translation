"""Regression coverage for the reviewed Chinese v4.0.3 trainer loader.

Synthetic tests run without game data. The optional local-ROM check pins the
reviewed code regions by hashes, without embedding or distributing ROM bytes.
"""
import hashlib
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import romdata as R


def record(level=20, form=0, iv=100, evs=(0, 0, 0, 0, 0, 0)):
    return (bytes([iv, 0, form, 255]) + struct.pack('<4H', 26, level, 479, 0)
            + bytes(8) + bytes(evs) + bytes(2))


class TrainerRuntimeTests(unittest.TestCase):
    def test_form_is_separate_byte(self):
        mon = R.parse_trpoke(record(form=4), 1)[0]
        self.assertEqual((mon['species'], mon['form']), (479, 4))

    def test_ev_display_order_follows_engine_stat_ids(self):
        mon = R.parse_trpoke(record(evs=(1, 2, 3, 4, 5, 6)), 1)[0]
        self.assertEqual(mon['evs'], [1, 2, 3, 5, 6, 4])

    def test_hp_iv_override_boundaries_and_other_ivs(self):
        for level, hp in [(1, 10), (40, 10), (41, 20), (79, 20), (80, 31), (100, 31)]:
            with self.subTest(level=level):
                mon = R.parse_trpoke(record(level=level), 1)[0]
                self.assertEqual(mon['hp_ivs'], hp)
                self.assertEqual(mon['ivs'], 12)
                self.assertEqual(mon['iv'], 100)

    @unittest.skipUnless(os.path.isfile(R.ROM_PATH), 'local CN ROM unavailable')
    def test_reviewed_loader_and_stat_calculator_code(self):
        import ndspy.rom
        arm9 = ndspy.rom.NintendoDSRom.fromFile(R.ROM_PATH).arm9
        regions = [
            # Form byte and initial scaled IV creation.
            (0x727A2, 0x7282E, '019c2e1a9247c2050612b1ca02b761a20f0c0ff7cec268b0bc9cbc2323412b43'),
            # Six EV fields, ids 13..18.
            (0x72880, 0x728C8, '3233058fd0f68914b722a1996931e956f135bc04ccc3d1afa736e5462ae2595c'),
            # Level-based HP override; loop repeatedly uses field 70.
            (0x728E0, 0x72914, 'd464f650d6a4f75925ce9aa1eb993eb1f743fc0f97f4c99ffdf135fe29c92661'),
            # Field 70 writes the low five IV bits only.
            (0x6E478, 0x6E48C, '1e94dc120e84cd25055fbf3daa59d80d9133ac777f73903543e4d2d6891e0769'),
            # EV reads and use with personal Speed/SpA/SpD bytes 3/4/5.
            (0x6D5FC, 0x6D644, '8453d0f451e8a5b81dec4d5b76c15a3c0f48c40693d38ad44da35f808e6d98fb'),
            (0x6D72A, 0x6D7E8, '48ee4de2af64a8c3f31280400c645e4c8109ef0e94091cedd4d5b2ddaad23b3d'),
        ]
        for start, end, expected in regions:
            with self.subTest(address=hex(0x02000000 + start)):
                self.assertEqual(hashlib.sha256(arm9[start:end]).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
