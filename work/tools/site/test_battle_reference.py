"""Numeric fixtures only; parser/evidence regressions need no ROM or workbook."""
import os
import struct
import sys
import unittest
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'docs'))
import romdata as R
import battle_reference as B


class BattleReferenceTests(unittest.TestCase):
    def fixture(self):
        b = bytearray(40)
        b[0:8] = bytes([11, 6, 2, 95, 101, 15, 255, 0x52])
        struct.pack_into('<H', b, 8, 4)
        b[10:16] = bytes([30, 1, 2, 4, 1, 10])
        struct.pack_into('<H', b, 16, 262)
        b[18:22] = bytes([231, 50, 7, 3])
        b[24] = 254
        b[27] = 100
        struct.pack_into('<Q', b, 32, (1 << 34) | (1 << 63) | 7)
        return b

    def test_complete_live_move_layout_and_signed_fields(self):
        m = R.parse_move(self.fixture())
        self.assertEqual(m['priority'], -1)
        self.assertEqual(m['drain'], -25)
        self.assertEqual(m['hits'], [2, 5])
        self.assertEqual(m['condition'], 4)
        self.assertEqual(m['effect'], 262)
        self.assertEqual(m['stat_changes'], [dict(stat=3, stages=-2, chance=100)])
        self.assertEqual(m['flags'], (1 << 34) | (1 << 63) | 7)
        self.assertEqual(m['accuracy'], 101)

    def test_signed_hp_change_bytes_are_not_healing(self):
        for raw, expected in ((0xE7,-25),(0xDF,-33),(0xCE,-50),(50,50),(0,0)):
            b = bytearray(40); b[19] = raw
            parsed = R.parse_move(b)
            self.assertEqual(parsed['heal'], expected)
            row = B.move_reference(165, parsed, {})
            self.assertEqual(row['effects']['heal'], expected)
            text = ' '.join(x['text'] for x in row['effectSummary'])
            if expected < 0:
                self.assertNotIn('healing', text)
                self.assertIn('HP loss/cost field: %d' % expected, text)
                self.assertIn('basis and timing not decoded', text)
            elif expected > 0:
                self.assertIn('healing: 50%', text)
            else:
                self.assertEqual(text, '')

    def test_zero_stat_probability_is_uninterpreted_nonzero_is_preserved(self):
        for quality, stages, chance in ((2,2,0),(2,-1,0),(2,1,0),(6,-1,10),(7,1,30),(6,-1,0)):
            b = bytearray(40); b[1] = quality; b[21] = 1
            b[24] = stages & 255; b[27] = chance
            parsed = R.parse_move(b)
            text = B.effect_summary(14, parsed)[0]['text']
            self.assertEqual(parsed['stat_changes'][0]['chance'], chance)
            if chance:
                self.assertIn('%d%% chance' % chance, text)
            else:
                self.assertNotIn('chance', text)
                self.assertNotIn('100%', text)

    def test_recorded_gameplay_results_are_scoped_and_separate(self):
        for ident in (344,307,461,340):
            row = B.move_reference(ident, R.parse_move(self.fixture()), {})
            self.assertEqual(row['testedNotes'][0]['evidence']['kind'], 'tested')
            self.assertIn('both ROMs', row['testedNotes'][0]['evidence']['source'])
            self.assertTrue(row['testedNotes'][0]['playerSummary'])
            self.assertTrue(row['testedNotes'][0]['limitation'])
            self.assertIn('/guide/known-issues/',row['testedNotes'][0]['href'])
            self.assertFalse(any('needs an in-game test' in x['text'] for x in row['conflicts']))
        lunar = B.move_reference(461,R.parse_move(self.fixture()),{})['testedNotes'][0]['text']
        self.assertIn('Speed and Sp. Atk',lunar)
        self.assertIn('remained in battle',lunar)
        for ident in (308,338,439):
            row = B.move_reference(ident,R.parse_move(self.fixture()),{})
            self.assertEqual(row['testedNotes'],[])
            self.assertTrue(any('needs an in-game test' in x['text'] for x in row['conflicts']))

    def test_reject_truncated_or_wrong_table_record(self):
        for size in (0, 16, 39, 41):
            with self.assertRaises(ValueError):
                R.parse_move(bytes(size))

    def test_unknown_flags_and_targets_are_not_invented(self):
        m = R.parse_move(self.fixture()); m['target'] = 99
        row = B.move_reference(66, m, {})
        self.assertIsNone(row['target'])
        self.assertEqual(row['flags'], ['contact', 'charge', 'recharge', 'slicing'])
        self.assertIn(63, row['flagBits'])
        self.assertEqual(row['conflicts'][0]['kind'], 'unresolved-behavior')
        self.assertTrue(all(r['evidence']['kind']=='rom-data' for r in row['effectSummary']))
        self.assertFalse(any(r['evidence']['kind']=='tested' for r in row['effectSummary']))

    def test_game_description_and_stale_findings_remain_separate(self):
        rows = {55: dict(en='Text{NEWLINE}as written.',status='draft')}
        row = B.move_reference(55,R.parse_move(self.fixture()),rows)
        self.assertEqual(row['description']['text'],'Text as written.')
        self.assertEqual(row['description']['evidence']['kind'],'game-text')
        self.assertEqual(row['conflicts'][0]['kind'],'stale-description')
        self.assertIsNone(B.description(738,1,{1:dict(zh='not exported')}))

    def test_wide_ability_ids_and_slots(self):
        b=bytearray(52)
        struct.pack_into('<HHH',b,22,327,65,327)
        m=R.parse_personal(b)
        self.assertEqual(m['abilities'],[327,65])
        self.assertEqual(m['hidden_ability'],327)

if __name__=='__main__':unittest.main()
