"""Conservative comparisons: no ROM, workbook, runtime or network required."""
import json
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_compare as C


def lookup(rows):
    result={}
    for row in rows:
        for name in (row['name'],row.get('game')):
            if name: result.setdefault(C.key(name),[]).append(row)
    return result


class CompareTests(unittest.TestCase):
    def test_gender_signs_do_not_collapse(self):
        self.assertNotEqual(C.key('Nidoran♀'),C.key('Nidoran♂'))

    def test_exact_base_wins_over_shared_form_alias(self):
        l=lookup([dict(id=201,name='Unown',formId=0),dict(id=1072,name='Unown (B)',game='Unown',formId=1)])
        self.assertEqual(C.species_match('Unown',l)['id'],201)

    def test_regional_and_named_aliases_keep_record_identity(self):
        l=lookup([dict(id=1035,name='Alolan Sandshrew',formId=1),dict(id=1147,name='Heat Rotom',formId=1)])
        self.assertEqual(C.species_match('Sandshrew Alolan',l)['id'],1035)
        self.assertEqual(C.species_match('Rotom Heat',l)['id'],1147)

    def evo(self,note,conds):
        target=dict(id=25,evoTo=[dict(id=26,how='fixture',conds=conds)],evoFrom=[])
        items=lookup([dict(id=83,name='Thunder Stone'),dict(id=108,name='Dusk Stone')])
        moves=lookup([dict(id=87,name='Thunder')])
        return C.evolution_compare(note,target,items,moves)

    def test_item_name_does_not_imply_similarly_named_move(self):
        self.assertTrue(self.evo('Thunder Stone',[dict(text='using {}',item=83)])['equal'])

    def test_explicit_use_and_hold_operations_are_distinct(self):
        use = [dict(text='using {}',item=83)]
        hold = [dict(text='holding {}',item=83)]
        self.assertTrue(self.evo('Use Thunder Stone',use)['equal'])
        self.assertFalse(self.evo('Use Thunder Stone',hold)['equal'])
        self.assertTrue(self.evo('Hold Thunder Stone',hold)['equal'])
        self.assertFalse(self.evo('Holding Thunder Stone',use)['equal'])
        for conds in (use,hold):
            result = self.evo('Thunder Stone',conds)
            self.assertTrue(result['equal'])
            self.assertFalse(any(t == 'operation' for t,v in result['alternatives'][0]['constraints']))

    def test_explicit_level_up_holding_keeps_both_requirements(self):
        items = lookup([dict(id=81,name='Moon Stone')])
        target = dict(id=217,evoFrom=[],evoTo=[dict(id=901,
            how='level up holding Moon Stone (night)',
            conds=[dict(text='holding {}',item=81),dict(text='at night (20:00–3:59)')])])
        compare = lambda note: C.evolution_compare(note,target,items,{})
        self.assertFalse(compare('Use a Moon Stone at Night')['equal'])
        self.assertTrue(compare('Level up holding Moon Stone at night')['equal'])
        target['evoTo'][0]['how'] = 'trade holding Moon Stone'
        self.assertFalse(compare('Level up holding Moon Stone at night')['equal'])
        self.assertTrue(compare('Hold Moon Stone at night')['equal'])

    def test_dusk_stone_is_not_a_dusk_time_window(self):
        self.assertTrue(self.evo('Dusk Stone',[dict(text='using {}',item=108)])['equal'])

    def test_level_and_all_alternatives_must_match(self):
        self.assertTrue(self.evo(16,[dict(text='at Lv 16')])['equal'])
        self.assertFalse(self.evo(36,[dict(text='at Lv 32')])['equal'])
        self.assertFalse(self.evo('16 / Thunder Stone',[dict(text='at Lv 16')])['equal'])

    def test_friendship_threshold_is_not_approximately_equal(self):
        self.assertFalse(self.evo('Friendship 150',[dict(text='with friendship 158 or more')])['equal'])

    def test_calendar_and_breeding_are_not_evolution_matches(self):
        for note in ('7.14 Ilex Forest','Breed while holding Sea Incense'):
            self.assertIsNone(self.evo(note,[])['equal'])

    def test_route_prefix_does_not_match_another_route(self):
        areas=[dict(name='Route 2',slug='route-2'),dict(name='Route 25',slug='route-25')]
        rows=[dict(area='route-2'),dict(area='route-25')]
        self.assertEqual(C.place_matches('Route 25',rows,areas),['route-25'])

    def test_known_empty_cost_is_free_unknown_is_not(self):
        self.assertTrue(C.cost_compare('None',[[]]))
        self.assertFalse(C.cost_compare('None',[None]))
        self.assertTrue(C.cost_compare('Lure Ball',[['Lure Ball ×1']]))
        self.assertIsNone(C.cost_compare('Heavy Ball',[['Lure Ball ×1']]))

    def test_summary_respects_walk_rate_and_forms(self):
        table=dict(rates=dict(walk=20,surf=0,rock=0,old=0,good=0,super=0),morning=[29,29],day=[29],night=[32],hoenn=[29],sinnoh=[32],swarm=dict(land=0,surf=0,night_fish=0,fish=0))
        l=lookup([dict(id=29,name='Nidoran♀',baseSpeciesId=29,formId=0),dict(id=32,name='Nidoran♂',baseSpeciesId=32,formId=0)])
        result=C.summary_compare(['Nidoran♀','Nidoran♀','Nidoran♂','Nidoran♀, Nidoran♂',None,None,None,None,None,None],table,l)
        self.assertTrue(all(x['equal'] for x in result.values()))

    def test_curated_content_is_english_and_contradictions_are_specific(self):
        data=json.loads((Path(__file__).parent/'reference_content.json').read_text())
        self.assertEqual(len(data['itemNotes']),450)
        self.assertEqual(len(data['tutorNotes']),79)
        n=next(n for n in data['itemNotes'] if n['itemId']==15)
        self.assertIn('standard v4 Poké Mart',n['configuredNote'])
        self.assertIn('Saffron',n['configuredNote'])
        for n in data['itemNotes']:
            for field in ('changeNote','effectNote','acquisitionNote','useNote','configuredNote'):
                text=n.get(field) or ''
                self.assertFalse(any('\u4e00'<=c<='\u9fff' for c in text),(n['itemId'],field))


if __name__=='__main__': unittest.main()
