"""Check Pickup layout and prevent conditional weights becoming per-check odds."""
import struct
import unittest

import pickup as P


class PickupTests(unittest.TestCase):
    def fixture(self):
        base = P.GATE_ADDRESS
        data = bytearray(P.WEIGHTS_ADDRESS - base + 220)
        data[:2] = b'\x0a\x20'
        struct.pack_into('<22H', data, P.ITEMS_ADDRESS - base, *range(1, 23))
        for band in range(10):
            data[P.WEIGHTS_ADDRESS - base + band] = 30
            data[P.WEIGHTS_ADDRESS - base + 10 + band] = 70
        return base, data

    def test_item_major_layout_and_conditional_rates(self):
        base, data = self.fixture()
        table = P.parse_table(data, base)
        self.assertEqual(table['activationPercent'], 10)
        self.assertEqual(table['items'][0], dict(item=1, rates=[30] * 10))
        self.assertEqual(table['items'][1], dict(item=2, rates=[70] * 10))
        self.assertEqual(table['bands'][0], dict(min=1, max=10))
        self.assertEqual(table['bands'][-1], dict(min=91, max=100))

    def test_reject_changed_code_or_bad_table(self):
        base, data = self.fixture()
        data[0] = 11
        with self.assertRaisesRegex(ValueError, 'activation gate'):
            P.parse_table(data, base)
        base, data = self.fixture()
        data[-1] = 1
        with self.assertRaisesRegex(ValueError, 'total 100'):
            P.parse_table(data, base)


if __name__ == '__main__':
    unittest.main()
