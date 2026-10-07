"""Chinese-ROM regressions for reviewed trainer scene associations."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_docs as G


@unittest.skipUnless(os.path.isfile(G.R.ROM_PATH), 'local CN ROM unavailable')
class TrainerContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = G.Ctx()
        cls.locations = G.trainer_locations(cls.ctx)

    def test_blue_old_gym_script_has_no_trigger(self):
        c = self.ctx
        z = next(z for z in c.zones if z['zone_id'] == 496)
        ev = c.events[z['events_bank']]
        self.assertFalse(any(e['script'] == 1 for k in ('obj', 'bg', 'coord') for e in ev[k]))
        self.assertEqual(c.rom['scripts'][z['script_header_bank']], bytes.fromhex('0203000000000000'))
        self.assertEqual(G.reach_owner(c.S[741])[151], {0})
        gym = [x for x in self.locations[261] if x[0] == 496]
        self.assertTrue(gym)
        self.assertTrue(all(G.DEAD_SCENE in x[2] for x in gym))
        self.assertTrue(any(x[0] != 496 and G.DEAD_SCENE not in x[2] for x in self.locations[261]))

    def test_actual_viridian_opponent_and_later_blue(self):
        self.assertEqual(self.ctx.S[741]['ins'][2311][1][:2], [662, 0])
        self.assertEqual(self.ctx.S[741]['ins'][2863][1], [7])
        self.assertTrue(any(z == 496 and G.DEAD_SCENE not in conds
                            for z, _how, conds in self.locations[727]))

    def test_all_explicit_memory_opponents_have_both_formats(self):
        expected = {287, 288, 479, 487, 498, 503, 544, 557, 558, 700, 733, 734, 863, 864, 865, 866, 867}
        self.assertEqual(set(G.memory_trainer_ids(self.ctx)), expected)
        for tid in expected:
            rows = [x for x in self.locations[tid] if x[0] == 528 and 'memory rematch' in x[1]]
            self.assertEqual(len(rows), 2)
            self.assertTrue(any(x[1].startswith('single') for x in rows))
            self.assertTrue(any('against this one team' in x[1] for x in rows))
            self.assertTrue(all(len(conds) == 1 and 'after the final Hall of Fame, if you pick' in conds[0]
                                for _zone, _how, conds in rows))

    def test_misty_gym_partner_is_not_an_opponent(self):
        rows = [x for x in self.locations[989] if x[0] == 427]
        self.assertTrue(rows)
        self.assertTrue(all(x[1].startswith('your partner') for x in rows))
        self.assertTrue(any(z == 427 and how == 'single battle'
                            for z, how, _conds in self.locations[254]))

    def test_page_has_unique_teams_and_separates_misty_appearances(self):
        tds, parties = G.load_trainers(self.ctx)
        sections = G.trainer_page_sections(self.ctx, tds, parties, self.locations)
        ids = [tid for s in sections for entry in s['entries'] for tid in entry['ids']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(254, sections[0]['entries'][1]['ids'])
        other = next(s for s in sections if s['title'] == 'Other Gym Leader battles')
        misty = next(e for e in other['entries'] if e['title'] == 'Misty')
        self.assertTrue({83, 84, 123, 272, 989} <= set(misty['ids']))
        self.assertNotIn(254, misty['ids'])
        reference = next(s for s in sections if s['title'] == 'Encounters not confirmed')
        self.assertTrue({707, 708, 709, 710, 711, 760} <= {t for e in reference['entries'] for t in e['ids']})

    def test_starmie_item_and_known_form_examples(self):
        _tds, parties = G.load_trainers(self.ctx)
        starmie = parties[254][2]
        self.assertEqual((starmie['species'], starmie['ability'], starmie['item']), (121, 35, 267))
        self.assertEqual((starmie['hp_ivs'], starmie['ivs']), (10, 12))
        giratina = parties[1015][0]
        self.assertEqual((giratina['species'], giratina['form']), (487, 1))
        self.assertIn('Origin', self.ctx.sp(giratina['species'], giratina['form']))


if __name__ == '__main__':
    unittest.main()
