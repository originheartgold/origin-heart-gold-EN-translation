"""Original-table fixtures and normalized comparisons; no local ROM required."""
import json
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import move_comparisons as M


class MoveComparisonTests(unittest.TestCase):
    def test_original_layout_signed_priority_and_gen4_target(self):
        raw = bytearray(16)
        raw[2:8] = bytes([1, 150, 10, 90, 5, 0])
        struct.pack_into('<H', raw, 8, 4)
        raw[10] = 252
        result = M.parse_original_move(raw)
        self.assertEqual(result, dict(typeId=10, categoryId=1, power=150,
                         accuracy=90, pp=5, secondaryChance=0, targetId=4, priority=-4))
        for size in [0, 15, 17, 40]:
            with self.assertRaises(ValueError):
                M.parse_original_move(bytes(size))

    def test_accuracy_sentinels_and_target_enum_are_semantically_equal(self):
        original = dict(typeId=14, categoryId=2, power=0, accuracy=0,
                        pp=10, priority=0, targetId=16)
        move = dict(type='Psychic', cat='Status', power='—', acc='101', pp='10',
                    priority=0, target='User')
        self.assertEqual(M.compare_move(move, original)['fields'], [])
        move['acc'] = '—'
        original['accuracy'] = 101
        self.assertEqual(M.compare_move(move, original)['fields'], [])
        original['targetId'] = 512
        move['target'] = 'All opponents'
        self.assertEqual(M.compare_move(move, original)['fields'], [])

    def test_curated_originals_cover_real_gen4_ids_only(self):
        originals, effects = M.load_comparisons()
        self.assertEqual(list(originals), list(range(1, 468)))
        facts = json.loads((M.HERE / 'move_original_facts.json').read_text())
        self.assertEqual(facts['excludedRecords']['ids'], [0, 468, 469, 470])
        self.assertEqual(facts['evidence']['crc32'], 'C180A0E9')
        self.assertFalse(any('text' in row or 'effectId' in row for row in originals.values()))
        self.assertEqual(originals[307]['power'], 150)
        self.assertEqual(originals[307]['categoryId'], 1)
        self.assertEqual(originals[295]['secondaryChance'], 50)
        self.assertEqual(M.TYPES[originals[174]['typeId']], '???')
        # A tested recharge result does not label the configured burn chance tested.
        self.assertEqual([r['evidence']['kind'] for r in effects[307]], ['tested', 'rom-data'])
        self.assertTrue(effects[337][0]['uncertain'])

    def test_missing_original_does_not_invent_values(self):
        move = dict(type='Fairy', cat='Physical', power='90', acc='100', pp='10',
                    priority=0, target='Selected target')
        comparison = M.compare_move(move, None)
        self.assertIsNone(comparison['baseline'])
        self.assertEqual(comparison['fields'], [])


if __name__ == '__main__':
    unittest.main()
