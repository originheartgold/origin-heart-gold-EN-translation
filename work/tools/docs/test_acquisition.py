"""Acquisition regressions: source identity, reachability and temporary loans."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import acquisition as A
import gen_docs as G


class AcquisitionTests(unittest.TestCase):
    def test_exclusion_is_source_specific(self):
        raw = [('static', 4, 0, 15, 175), ('gift', 4, 0, 10, 751), ('gift', 4, 0, 5, 738)]
        reviews = [dict(species=4, file=175, kind='static', level=15, excluded=True),
                   dict(species=4, file=751, kind='gift', level=10, conditions=['Pikachu starters only.'])]
        with patch.object(A, 'reviews', return_value=reviews):
            sources = list(A.scripted_sources(None, raw))
        self.assertEqual([s['file'] for s in sources], [751, 738])
        self.assertEqual(sources[0]['conditions'], ['Pikachu starters only.'])
        self.assertFalse(sources[1]['reviewed'])
        self.assertIn('not been verified', sources[1]['conditions'][0])

    def test_reviews_do_not_cross_levels_and_keep_forms(self):
        raw = [('static', 382, 0, 50, 134), ('static', 382, 0, 80, 134), ('gift', 133, 1, 10, 1)]
        with patch.object(A, 'reviews', return_value=[dict(species=382, file=134, kind='static', level=50, excluded=True)]):
            rows = list(A.scripted_sources(None, raw))
        self.assertEqual([(r['species'], r['form'], r['level']) for r in rows], [(382, 0, 80), (133, 1, 10)])

    def test_temporary_loans_do_not_seed_evolution_or_breeding(self):
        ctx = SimpleNamespace(enc_usage={}, S={}, rom={'trade': []}, personal={}, evos={},
                              sp=lambda sp: str(sp), place_str=lambda file: 'Forest', species_ids=lambda: [18])
        loan = dict(give=18, ask=18, file=115, loan=True, conditions=['Return it after the League.'])
        with patch.object(G, 'acquisition_sources', return_value=[]), \
             patch.object(G, 'trade_sources', return_value=[loan]), \
             patch.object(G, 'reviewed', return_value={}), patch.object(G, 'evo_parents', return_value={}):
            result = G.availability(ctx)
        self.assertEqual(result[18], '')
        self.assertEqual(ctx._acquisition[18][0]['kind'], 'loan')
        self.assertEqual(ctx._acquisition[18][0]['conditions'], loan['conditions'])


if __name__ == '__main__':
    unittest.main()
