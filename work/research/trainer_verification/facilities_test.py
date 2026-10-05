"""Boundary regressions for manually traced policies; not CPU/emulator tests."""
import unittest
from facilities_models import *
class ConstructorTests(unittest.TestCase):
    def test_ev_budget_and_order(self):
        self.assertEqual(evs(0),[0,0,0,0,0,0])
        self.assertEqual(evs(8),[0,0,0,255,0,0])
        self.assertEqual(evs(0x11),[255,0,0,0,255,0])
        self.assertEqual(evs(0x29),[170,0,0,170,0,170])
        self.assertEqual(evs(15),[127,127,127,127,0,0])
        self.assertEqual(evs(63),[85]*6)
        with self.assertRaises(ValueError):evs(64)
    def test_form_truncation(self):
        self.assertEqual(unpack_form(0x22),2)
        self.assertEqual(unpack_form(0xffff),31)
    def test_packed_ivs_no_hp_override(self):
        self.assertEqual(packed_ivs(0),0)
        self.assertEqual(packed_ivs(31),0x3fffffff)
        self.assertEqual(packed_ivs(33),0x02108421)
    def test_iv_boundaries(self):
        self.assertEqual([standard_trainer_iv(i) for i in [0,99,100,119,120,139,140,159,160,179,180,199,200,219,220,314]],
            [3,3,6,6,9,9,12,12,15,15,18,18,21,21,31,31])
    def test_level_sentinels(self):
        self.assertEqual([materialized_level(i) for i in [1,50,100,119,120,121,122]], [1,50,100,119,50,100,122])
class SelectionTests(unittest.TestCase):
    def test_legacy_item_threshold_keeps_species_exclusion(self):
        self.assertEqual(legacy_candidate(2,10,[(1,10)],conflicts=49),(False,50))
        self.assertEqual(legacy_candidate(2,10,[(1,10)],conflicts=50),(True,50))
        self.assertEqual(legacy_candidate(1,20,[(1,10)],conflicts=50),(False,50))
        self.assertEqual(legacy_candidate(2,20,[(1,10)],excluded_species=[2],conflicts=50),(False,50))
    def test_zero_items_are_policy_specific(self):
        self.assertEqual(legacy_candidate(2,0,[(1,0)]),(True,0))
        self.assertEqual(shared_candidate(2,0,[(1,0)]),(False,0))
    def test_shared_threshold_relaxes_only_external_exclusions(self):
        self.assertEqual(shared_candidate(2,20,[(1,10)],[(2,30)],49),(False,50))
        self.assertEqual(shared_candidate(2,20,[(1,10)],[(2,30)],50),(True,50))
        self.assertEqual(shared_candidate(1,20,[(1,10)],[],50),(False,50))
        self.assertEqual(shared_candidate(2,10,[(1,10)],[],50),(False,50))
    def test_factory_rentals_have_no_conflict_counter_escape(self):
        self.assertFalse(factory_rental_candidate(2,0,[(1,0)]))
        self.assertFalse(factory_rental_candidate(2,20,[(1,10)],[(2,30)]))
        self.assertTrue(factory_rental_candidate(3,30,[(1,10)],[(2,20)]))
    def test_internal_conflicts_do_not_advance_shared_counter(self):
        self.assertEqual(shared_candidate(2,10,[(1,10)],[(2,20)],49),(False,49))
if __name__=='__main__':unittest.main()
