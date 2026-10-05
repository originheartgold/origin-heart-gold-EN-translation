import unittest
from work.research.trainer_verification import reachability as R

class Reachability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx=R.G.Ctx()
        cls.result=R.build(cls.ctx)

    def test_conditional_header_is_not_script_code(self):
        self.assertEqual(R.headers(bytes.fromhex('0201000000010100000000244100000200000000')),
                         [{'type':2,'script':1,'offset':0}, {'type':1,'script':2,'variable':0x4124,'expected':0,'offset':11}])
        self.assertEqual(R.headers(bytes(4)),[])

    def test_full_callsite_coverage_and_real_frontiers(self):
        self.assertEqual(len(self.result['encounters']),941)
        self.assertEqual(self.result['summary']['entry_linked'],914)
        self.assertEqual({x['script'] for x in self.result['decode_frontiers']},{225,232,243,246,934,937,958})
        self.assertTrue(all(x['opcode']==2009 for x in self.result['decode_frontiers']))
        self.assertEqual(self.result['summary']['unreferenced'],[86,89,260,440,488,492,609,706,707,708,709,710,711,760,947])

    def test_engine_roots_and_ribbon_fault_signatures(self):
        rows=[x for x in self.result['encounters'] if x['engine_entry_linked']]
        self.assertEqual({(x['script'],x['pc']) for x in rows},{(949,3908),(949,4101),(949,4348)})
        self.assertEqual(self.result['summary']['no_static_root_found'],24)
        self.assertEqual(int.from_bytes(self.ctx.rom.a9(0x020F78CC,4),'little'),843)
        self.assertEqual(self.ctx.rom.a9(0x0203FC20,8),R.struct.pack('<II',5000,2999))
        ribbons=set()
        for row in self.result['decode_frontiers']:
            ins=self.ctx.S[row['script']]['ins'];pc=row['pc']
            self.assertEqual(ins[pc-4][1],[20])
            self.assertEqual(R.G.R.cmds()[ins[pc-10][0]][0],'GiveRibbon')
            ribbons.add(ins[pc-10][1][1])
        self.assertEqual(ribbons,set(range(59,66)))

    def test_old_blue_does_not_gain_header_root(self):
        row=next(x for x in self.result['encounters'] if (x['script'],x['pc'])==(741,151))
        self.assertEqual(row['entry_linked_zones'],[])
        self.assertTrue(row['curated_dead_scene'])
        live=next(x for x in self.result['encounters'] if (x['script'],x['pc'])==(741,2311))
        self.assertIn(496,live['entry_linked_zones'])

    def test_menu_explicit_exit_and_unrecognized_result_differ(self):
        ins=self.ctx.S[78]['ins']
        self.assertEqual(R.menu_outcome(ins,913,7)['kind'],'End')
        for value in (8,65534,65535):
            self.assertEqual(R.menu_outcome(ins,913,value),dict(kind='TrainerBattle',pc=1040,value=value))
            self.assertEqual(R.menu_outcome(ins,331,value)['kind'],'End')
        self.assertEqual(R.menu_outcome(ins,913,0),dict(kind='TrainerBattle',pc=1040,value=734))


class PhoneRematches(unittest.TestCase):
    def test_phone_table_references_are_not_encounter_proof(self):
        from work.research.trainer_verification import reachability_phone as P
        result=P.build(R.G.Ctx())
        self.assertEqual(result['summary']['encounter_unreferenced_with_table_reference'],[440,609])
        self.assertEqual(result['summary']['encounter_unreferenced_with_caller_candidate'],[])
        matches=[r for r in result['candidates'] if r['trainer_id'] in (440,609)]
        self.assertEqual({(r['contact_id'],r['base_trainer_id'],r['stage'],r['trainer_id']) for r in matches},
                         {(40,211,2,440),(42,113,4,609)})
        self.assertEqual(result['direct_trainer_standard_calls'],[])
        self.assertEqual({r['contact_id'] for r in result['command_calls'] if r['contact_id'] is not None},{17,36,38})

if __name__=='__main__':unittest.main()
