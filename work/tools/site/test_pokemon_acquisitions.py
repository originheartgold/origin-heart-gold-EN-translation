"""Guard complete variable resolution, trade direction and source deduplication."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))
import pokemon_acquisitions as A


class AcquisitionTests(unittest.TestCase):
    def test_sources(self):
        area = dict(slug='town', rank=1)
        records = [dict(kind='mon_give', args=[None, 15], alt0=[1, 4], alt0_complete=True, pc=1),
                   dict(kind='mon_give', args=[None, 20], alt0=[7], alt0_complete=False, pc=2),
                   dict(kind='mon_give', args=[1, 15], pc=3),
                   dict(kind='egg_give', args=[25], pc=4),
                   dict(kind='trade', args=[0], pc=5),
                   dict(kind='loan_give', args=[0], pc=6)]
        ctx = SimpleNamespace(S={10: dict(recs=records)}, file_zones={10: [1]},
                              zname=lambda _: 'Town house', zrank=lambda _: 1,
                              rom={'trade': [dict(give=95, ask=15)]})
        g = SimpleNamespace(form_index=lambda ctx, sp, form: sp, conditions_for=lambda *a: [])
        r = SimpleNamespace(split_species=lambda sp: (sp, 0), parse_trade=lambda value: value)
        notes = {(10, 1): dict(conditions='Pikachu starter', quests=[]), (10, 4): dict(exclude=True)}
        result = A.sources(ctx, g, r, {1: area}, lambda *args: [area], notes)
        self.assertEqual(set(result), {1, 25, 95})
        self.assertEqual(result[1][0]['conditions'], 'Pikachu starter')
        self.assertEqual(result[1][0]['evidence'], [dict(file=10, pc=1), dict(file=10, pc=3)])
        self.assertEqual(result[25][0]['kind'], 'egg')
        self.assertIsNone(result[25][0]['level'])
        self.assertEqual({row['kind']: row['offer'] for row in result[95]}, {'trade': 15, 'loan': None})

    def test_other_sources_preserves_nonduplicated_routes(self):
        summary = ('wild: Route 1; gift (Lv 15), House; gift Egg, Center; in-game trade, Town; '
                   'loan Pokémon, Forest; one-time battle (Lv 10), Cave; revive Old Amber at Museum; breed Aerodactyl')
        self.assertEqual(A.other_sources(summary, True),
                         'one-time battle (Lv 10), Cave; revive Old Amber at Museum; breed Aerodactyl')
        self.assertEqual(A.other_sources('wild: Route 1; evolve Pikachu', False), 'wild: Route 1; evolve Pikachu')


if __name__ == '__main__':
    unittest.main()
