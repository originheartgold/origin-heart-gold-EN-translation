import copy
import hashlib
import struct
from pathlib import Path
import unittest
import opaque_control_proof as p

class OpaqueControlProofTests(unittest.TestCase):
    def test_exact_payload_source_and_ref_required(self):
        proof={'status':'passed'}
        self.assertTrue(p.eligible('a027/0763#66',p.PAYLOAD_HASH,p.PAYLOAD_HASH,proof))
        for ref,a,b,q in [('a027/0763#67',p.PAYLOAD_HASH,p.PAYLOAD_HASH,proof),('a027/0763#66','changed',p.PAYLOAD_HASH,proof),('a027/0763#66',p.PAYLOAD_HASH,'changed',proof),('a027/0763#66',p.PAYLOAD_HASH,p.PAYLOAD_HASH,{'status':'incomplete'})]:
            self.assertFalse(p.eligible(ref,a,b,q))

    def test_changed_command_argcount_slot_argument_or_true_terminator_rejected(self):
        for index in range(6):
            units=list(p.PAYLOAD);units[index]^=1
            changed=hashlib.sha256(struct.pack('<6H',*units)).hexdigest()
            self.assertFalse(p.eligible('a027/0763#66',changed,changed,{'status':'passed'}))

    def test_native_evidence_requires_all_cases_full_copy_output_cleanup(self):
        rows=[dict(ref=ref,slot_units=n,full_copied_payload=list(p.PAYLOAD),source_string_length=4,source_capacity=6,actual_units=[0x012b]*n,terminator=65535,native_call_completed=True) for ref in p.REFS for n in (0,7,31)]
        cleanup={'before':{'blocks':[]},'after':{'blocks':[]}}
        self.assertTrue(p.native_evidence_ok(rows,cleanup))
        self.assertFalse(p.native_evidence_ok(rows[:-1],cleanup))
        self.assertFalse(p.native_evidence_ok(rows+[rows[0]],cleanup))
        for key,value in [('full_copied_payload',list(p.PAYLOAD[:-1])),('source_capacity',5),('source_string_length',5),('actual_units',[4]),('terminator',0),('native_call_completed',False)]:
            bad=copy.deepcopy(rows);bad[0][key]=value
            self.assertFalse(p.native_evidence_ok(bad,cleanup),key)
        self.assertFalse(p.native_evidence_ok(rows,{'before':{'blocks':[]},'after':{'blocks':[1]}}))

    def test_native_code_mutations_invalidate_proof(self):
        path=Path(__file__).resolve().parents[2]/'work/rom/origin_v4.0.3_cn.nds'
        if not path.exists():self.skipTest('Local Chinese ROM unavailable')
        import ndspy.rom
        arm=ndspy.rom.NintendoDSRom.fromFile(str(path)).loadArm9().sections[0]
        self.assertEqual(p.inspect_code(bytes(arm.data))['status'],'passed')
        for address in (0x02026ee4,0x02026eee,0x02020284,0x02020288,0x020202d8,0x0200c766,0x0200c788,0x0200c7b8,0x0200ba46):
            data=bytearray(arm.data);data[address-arm.ramAddress]^=1
            self.assertNotEqual(p.inspect_code(bytes(data))['status'],'passed',hex(address))

if __name__=='__main__':unittest.main()
