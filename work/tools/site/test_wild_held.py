"""Synthetic regression cases for the held-item/encounter join; no ROM required."""
import unittest
import os
import sys
import struct
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from export_data import calendar_wild_rows, safari_wild_rows, held_item_chances, wild_held_sources


class WildHeldTests(unittest.TestCase):
    def test_item_slots(self):
        self.assertEqual(held_item_chances([0, 0]), [])
        self.assertEqual(held_item_chances([4, 0]), [(4, 50)])
        self.assertEqual(held_item_chances([0, 4]), [(4, 5)])
        self.assertEqual(held_item_chances([4, 5]), [(4, 50), (5, 5)])
        self.assertEqual(held_item_chances([4, 4]), [(4, 100)])

    def test_conditions_forms_and_nonwild_species(self):
        ctx = SimpleNamespace(personal={1: {'items': [4, 0]}, 1001: {'items': [0, 5]},
                                        2: {'items': [6, 6]}},
                              sp=lambda sp: {1: 'Base', 1001: 'Form', 2: 'Gift'}[sp])
        row = dict(id=1001, name='Form (Good Rod, replaces the 10% slot)', level='5–7', pct=10)
        block = dict(label='Park: Monday', sections=[dict(title='Fishing at night', rows=[row, row])])
        area = dict(slug='park', name='Park', encounters=[block], headbutt=[], contest=None)
        result = wild_held_sources(ctx, {'Park': area}, {1, 1001, 2})
        self.assertEqual(set(result), {5})  # no base-form items or non-wild gift species
        self.assertEqual(result[5], [dict(species=1001, chance=5, locations=[dict(
            area='park', place='Park: Monday',
            method='Fishing at night: (Good Rod, replaces the 10% slot)',
            level='5–7', encounterRate=10, rateKind='percent')])])

    def test_headbutt_and_contest(self):
        ctx = SimpleNamespace(personal={1: {'items': [4, 4]}}, sp=lambda sp: 'Mon')
        row = dict(id=1, name='Mon', level='10', pct=20, rate=30)
        area = dict(slug='park', name='Park', encounters=[],
                    headbutt=[dict(label='West', sections=[dict(title='Special trees', rows=[row])])],
                    contest=dict(sets=[dict(title='Tuesday', rows=[row])]))
        locations = wild_held_sources(ctx, {'Park': area}, {1})[4][0]['locations']
        self.assertEqual([r['method'] for r in locations],
                         ['Headbutt: Special trees', 'Bug-Catching Contest: Tuesday'])
        self.assertEqual([r['encounterRate'] for r in locations], [20, 30])

    def test_scripted_wild_battles_but_not_gifts(self):
        ctx = SimpleNamespace(personal={1: {'items': [4, 0]}, 2: {'items': [5, 0]}},
                              sp=lambda sp: 'Mon')
        area = dict(slug='cave', name='Cave', encounters=[], headbutt=[], contest=None,
                    statics=[dict(id=1, kind='static', level=20), dict(id=2, kind='gift', level=5)])
        result = wild_held_sources(ctx, {'Cave': area}, {1, 2})
        self.assertEqual(set(result), {4})
        self.assertEqual(result[4][0]['locations'][0]['encounterRate'], None)
        self.assertIn('Scripted wild battle', result[4][0]['locations'][0]['method'])

    def test_calendar_dates_forms_and_disabled_walk(self):
        records = [(7, 14, 0, 648, 0, 0), (7, 18, 0, 720, 1, 2), (4, 16, 1, 721, 0, 0)]
        data = b''.join(struct.pack('<BBHHBB', *r) for r in records)
        area = dict(slug='forest', name='Forest', encounters=[], headbutt=[], contest=None)
        ctx = SimpleNamespace(rom=SimpleNamespace(a9=lambda address, size: data),
                              zones=[dict(wild_encounter_bank=0), dict(wild_encounter_bank=1)],
                              enc_by_file=([dict(rates=dict(walk=30), levels=[6] * 12),
                                            dict(rates=dict(walk=0), levels=[0] * 12)], {}),
                              forms={1001: (720, 1)}, sp=lambda sp: str(sp), zname=lambda zid: 'Forest',
                              personal={648: {'items': [91, 91]}, 1001: {'items': [0, 0]}})
        rows = list(calendar_wild_rows(ctx, {0: area, 1: area}))
        self.assertEqual([r[3]['id'] for r in rows], [648, 1001])
        self.assertIn('July 14, any time', rows[0][2])
        self.assertIn('July 18, night', rows[1][2])
        result = wild_held_sources(ctx, {'Forest': area}, {648, 1001}, rows)
        self.assertEqual(result[91][0]['chance'], 100)
        self.assertEqual(result[91][0]['locations'][0]['encounterRate'], 1)

    def test_safari_groups_time_and_excludes_locked_object_slots(self):
        ctx = SimpleNamespace(rom=SimpleNamespace(path='unused'), sp=str)
        source = dict(species=1, level=20, area='Plains', method='Grass', conditional=False)
        rows = [dict(source, time=time) for time in ('morning', 'day', 'night')]
        rows.append(dict(source, time='night', conditional=True))
        with patch('export_data.SH.safari_rows', return_value=rows):
            result = list(safari_wild_rows(ctx, {357: {'slug': 'safari-zone'}}))
        self.assertEqual(len(result), 1)
        self.assertIn('all day', result[0][2])
        self.assertEqual(result[0][3]['pct'], None)


if __name__ == '__main__':
    unittest.main()
