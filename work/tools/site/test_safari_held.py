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
            # These are object requirement bytes, deliberately not valid species.
            data.extend(b'\xff\xff\xff\xff' * count)
        return data

    def test_boundaries_and_object_requirements(self):
        rows = list(parse_safari_area(self.fixture(), 4))
        self.assertEqual(len(rows), 162)
        self.assertEqual(rows[0], dict(species=100, level=10, area='Rocky Beach',
                                     method='Grass', time='morning', conditional=False))
        self.assertEqual(rows[30]['species'], 300)
        self.assertTrue(rows[30]['conditional'])
        self.assertEqual(rows[32]['time'], 'night')
        self.assertEqual(rows[33]['method'], 'Surfing')
        self.assertEqual(rows[33]['species'], 110)
        self.assertFalse(rows[33]['conditional'])
        self.assertEqual(rows[-1]['species'], 342)
        self.assertEqual(rows[-1]['method'], 'Super Rod')

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
