import struct
import unittest

from safari_held import parse_safari_area


class SafariHeldTests(unittest.TestCase):
    def fixture(self):
        counts = (1, 0, 2, 0, 1)
        data = bytearray(bytes(counts) + bytes(3))
        for method, count in enumerate(counts):
            for conditional, slots in ((False, 10), (True, count)):
                for time in range(3):
                    for slot in range(slots):
                        species = 100 + method * 10 + time + conditional * 200
                        data.extend(struct.pack('<HH', species, 10 + slot))
            # Each slot keeps its own requirements across all three time tables.
            for slot in range(count):
                data.extend(bytes((3, 56 + slot, 2, 35)))
        return data

    def test_boundaries_and_object_requirements(self):
        rows = list(parse_safari_area(self.fixture(), 4))
        self.assertEqual(len(rows), 162)
        self.assertEqual(rows[0], dict(species=100, level=10, area='Rocky Beach',
                                     method='Grass', time='morning', conditional=False))
        self.assertEqual(rows[30]['species'], 300)
        self.assertTrue(rows[30]['conditional'])
        self.assertEqual(rows[30]['requirements'], [dict(category='Peak', points=56),
                                                   dict(category='Forest', points=35)])
        self.assertEqual(rows[32]['requirements'], rows[30]['requirements'])
        self.assertEqual(rows[32]['time'], 'night')
        self.assertEqual(rows[33]['method'], 'Surfing')
        self.assertEqual(rows[33]['species'], 110)
        self.assertFalse(rows[33]['conditional'])
        self.assertEqual(rows[-1]['species'], 342)
        self.assertEqual(rows[-1]['method'], 'Super Rod')
        old = [r for r in rows if r['method'] == 'Old Rod' and r['conditional']]
        self.assertEqual([r['requirements'][0]['points'] for r in old], [56, 57] * 3)

    def test_rejects_invalid_object_category(self):
        data = self.fixture()
        data[8 + 120 + 12] = 5
        with self.assertRaises(ValueError):
            list(parse_safari_area(data, 0))

    def test_rejects_truncated_or_extra_bytes(self):
        data = self.fixture()
        for invalid in (data[:7], data[:-1], data + b'\0'):
            with self.assertRaises(ValueError):
                list(parse_safari_area(invalid, 0))

    def test_rejects_invalid_slot(self):
        data = self.fixture()
        struct.pack_into('<H', data, 8, 0)
        with self.assertRaises(ValueError):
            list(parse_safari_area(data, 0))


if __name__ == '__main__':
    unittest.main()
