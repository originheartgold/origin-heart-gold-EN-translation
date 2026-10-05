"""Synthetic regression tests; no ROM or previous research dump required."""
import copy
import struct
import unittest

import export_index as E


class ResearchEvidenceTests(unittest.TestCase):
    def test_maxima_separate_partner_from_opponents_and_ignore_sentinels(self):
        parties = [[{'level': 100}], [{'level': 90}], [{'level': 30}], [{'level': 40}]]
        self.assertEqual(E.party_maxima('multi_battle', [1, 2, 3], parties), {
            'partner_party_max': 90, 'opponent_party_max': 40,
            'all_participants_party_max': 90})
        self.assertEqual(E.party_maxima('trainer', [0, None], parties), {
            'partner_party_max': None, 'opponent_party_max': None,
            'all_participants_party_max': None})

    def test_static_walk_keeps_both_branches_and_stops_at_return(self):
        # A conditional fork, a cycle, a return and an undecoded frontier.
        d = {'ins': {0: (26, [], 2, 4), 2: (22, [], 4, 0),
                     4: (27, [], 6, None), 6: (0, [], 8, None)}}
        self.assertEqual(E.walk(d, 0), {0, 2, 4})
        self.assertEqual(E.walk(d, 0, lambda p: p == 0), {0})
        self.assertEqual(E.walk(d, 6), {6})

    def test_raw_validator_rejects_old_form_and_ev_layout(self):
        raw = bytearray(28)
        raw[:4] = bytes([255, 1, 3, 255])
        struct.pack_into('<8H', raw, 4, 42, 40, 25, 267, 1, 2, 0, 0)
        raw[20:26] = bytes([1, 2, 3, 4, 5, 6])
        mon = E.R.parse_trpoke(raw, 1)[0]
        E.check_party_bytes(raw, {'count': 1}, [mon])
        for key, bad in [('form', 0), ('evs', [1, 2, 3, 4, 5, 6]), ('hp_ivs', 31)]:
            with self.subTest(field=key):
                changed = copy.deepcopy(mon)
                changed[key] = bad
                with self.assertRaises(AssertionError):
                    E.check_party_bytes(raw, {'count': 1}, [changed])

    def test_hp_iv_thresholds(self):
        for level, expected in [(40, 10), (41, 20), (79, 20), (80, 31)]:
            with self.subTest(level=level):
                raw = bytearray(28)
                struct.pack_into('<H', raw, 6, level)
                party = E.R.parse_trpoke(raw, 1)
                self.assertEqual(party[0]['hp_ivs'], expected)
                E.check_party_bytes(raw, {'count': 1}, party)


if __name__ == '__main__':
    unittest.main()
