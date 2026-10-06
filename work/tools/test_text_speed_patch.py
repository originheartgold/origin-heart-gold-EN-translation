"""Native patch guards and binary round-trip tests; ROM stays local and optional.

Set TEXT_SPEED_TEST_ROM to an existing English ROM with the demand-loading fix.
"""
import copy,json,os,struct,sys,unittest,shutil,tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import text_speed_patch as speed

class PayloadTests(unittest.TestCase):
    def test_payload_is_current_and_entries_are_in_reserved_code(self):
        p=speed.load_payload();code=bytes.fromhex(p['code'])
        self.assertEqual(p['source_sha256'],speed.source_digest())
        self.assertLessEqual(speed.BASE+len(code),0x01ffa000)
        for name in ['print_task','load_rows','load_choice','load_label','exit_free','draw_label','setup_sprites']:
            target=p['symbols'][name]
            self.assertEqual(target&1,1,name)
            self.assertTrue(speed.BASE <= (target&~1) < speed.BASE+len(code),name)

    @unittest.skipUnless(shutil.which('clang'), 'ARM clang is required to reproduce the native payload')
    def test_cached_payload_reproduces_from_source(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(speed.compile_payload(Path(directory)/'native.o'), speed.load_payload())
        self.assertEqual(speed.verify_reproducible_payload()['status'],'passed')

    def invalid_payloads(self):
        original=speed.load_payload()
        changes={
            'corrupted instruction':lambda p:p.update(code='fee7'+p['code'][4:]),
            'redirected outside payload':lambda p:p['symbols'].update(print_task=0x02020a1d),
            'redirected inside payload':lambda p:p['symbols'].update(print_task=speed.BASE+3),
            'ARM entry point':lambda p:p['symbols'].update(print_task=speed.BASE),
            'entry at end':lambda p:p['symbols'].update(print_task=speed.BASE+len(bytes.fromhex(p['code']))+1),
            'duplicate entry':lambda p:p['symbols'].update(print_task=p['symbols']['load_rows']),
            'missing entry':lambda p:p['symbols'].pop('exit_free'),
            'extra entry':lambda p:p['symbols'].update(unknown=speed.BASE+3),
            'stale source':lambda p:p.update(source_sha256='0'*64),
            'wrong base':lambda p:p.update(base=speed.BASE+4),
            'missing code':lambda p:p.pop('code'),
            'extra claimed hash':lambda p:p.update(code_sha256=speed.digest(bytes.fromhex(p['code']))),
            'empty code':lambda p:p.update(code=''),
            'oversize code':lambda p:p.update(code='00'*(speed.MAX_PAYLOAD_SIZE+2)),
            'odd instruction size':lambda p:p.update(code=p['code']+'00'),
            'invalid hex':lambda p:p.update(code='zzzz'),
            'noncanonical hex':lambda p:p.update(code=p['code'].upper()),
            'noncanonical whitespace':lambda p:p.update(code=p['code']+'    '),
            'string address':lambda p:p['symbols'].update(print_task=str(speed.BASE+1)),
            'boolean address':lambda p:p['symbols'].update(print_task=True),
        }
        for name,change in changes.items():
            payload=copy.deepcopy(original);change(payload)
            yield name,payload

    def test_cached_and_explicit_payloads_reject_corruption_before_rom_access(self):
        # An unusable ROM sentinel proves validation happens before any ROM read
        # or mutation, including callers bypassing the JSON loader with a dict.
        for name,payload in self.invalid_payloads():
            with self.subTest(case=name):
                with patch.object(speed.json,'loads',return_value=payload):
                    with self.assertRaises(ValueError):speed.load_payload()
                with self.assertRaises(ValueError):speed.apply(object(),payload)

    def test_reviewed_pin_is_independent_of_cache(self):
        payload=speed.load_payload();payload['code']='fee7'+payload['code'][4:]
        # A cache still claiming the correct sources must fail the independent
        # pin even when its structure and entry points are otherwise plausible.
        self.assertEqual(payload['source_sha256'],speed.source_digest())
        with self.assertRaisesRegex(ValueError,'independently reviewed digest'):
            speed.validate_payload(payload)

    def test_release_reproduction_never_skips_missing_compiler_or_changed_output(self):
        with patch.object(speed,'compile_payload',side_effect=FileNotFoundError('clang')):
            with self.assertRaises(FileNotFoundError):speed.verify_reproducible_payload()
        rebuilt=speed.load_payload();rebuilt['code']='fee7'+rebuilt['code'][4:]
        with patch.object(speed,'compile_payload',return_value=rebuilt):
            with self.assertRaisesRegex(ValueError,'does not reproduce'):
                speed.verify_reproducible_payload()
        rebuilt=speed.load_payload();rebuilt['symbols']['print_task']=speed.BASE+3
        with patch.object(speed,'compile_payload',return_value=rebuilt):
            with self.assertRaisesRegex(ValueError,'does not reproduce'):
                speed.verify_reproducible_payload()

    def test_branch_matches_known_original_instruction(self):
        self.assertEqual(speed.bl(0x021e5366,0x0200bb41).hex(),'26f6ebfb')
        self.assertEqual(speed.bl(0x02020a42,0x02020a89).hex(),'00f021f8')
        for target in [0x02800000,0x01000000]:
            with self.assertRaises(ValueError):speed.bl(0x02000000,target)

ROM=os.environ.get('TEXT_SPEED_TEST_ROM')
@unittest.skipUnless(ROM and Path(ROM).is_file(),'Set TEXT_SPEED_TEST_ROM for local binary tests')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ndspy.rom
        cls.original=ndspy.rom.NintendoDSRom.fromFile(ROM)
        cls.patched=copy.deepcopy(cls.original)
        cls.report=speed.apply(cls.patched)

    def test_guarded_roundtrip_and_unmodified_game_data(self):
        import ndspy.rom
        reparsed=ndspy.rom.NintendoDSRom(self.patched.save())
        self.assertEqual(speed.verify(reparsed,self.report)['status'],'passed')
        changed=[i for i,(a,b) in enumerate(zip(self.original.files,reparsed.files)) if a!=b]
        self.assertEqual(changed,[self.original.loadArm9Overlays()[50].fileID])
        self.assertEqual(self.original.arm7,reparsed.arm7)
        self.assertEqual(self.original.arm7OverlayTable,reparsed.arm7OverlayTable)
        # The ITCM extension does not move main code, DTCM, or main BSS.
        before=self.original.loadArm9();after=reparsed.loadArm9()
        self.assertEqual(before.sections[0].ramAddress,after.sections[0].ramAddress)
        self.assertEqual(len(before.sections[0].data),len(after.sections[0].data))
        self.assertEqual(before.sections[2].data,after.sections[2].data)
        off=before.codeSettingsOffs
        self.assertEqual(before.sections[0].data[off+12:off+20],after.sections[0].data[off+12:off+20])
        self.assertEqual(struct.unpack_from('<H',after.sections[0].data,0xba9a)[0],0x2501)

    def test_private_printer_storage_and_new_game_default(self):
        data=self.patched.loadArm9().sections[0].data
        self.assertEqual(struct.unpack_from('<H',data,0x208ea)[0],0x2138)
        self.assertEqual(bytes(data[0x20962:0x20966]),speed.bl(0x2020962,speed.load_payload()['symbols']['init_printer']))
        self.assertEqual(struct.unpack_from('<HH',data,0x2b176),(0x2004,0x4301))
        # Only the default initializer changes; the original save structure stays two bytes.
        self.assertEqual(bytes(data[0x2b16e:0x2b170]),bytes(self.original.loadArm9().sections[0].data[0x2b16e:0x2b170]))

    def test_menu_choice_and_touch_tables(self):
        ov=self.patched.loadArm9Overlays()[50];b=ov.data;base=ov.ramAddress
        counts_ptr=struct.unpack_from('<I',b,0x21e53e0-base)[0]
        self.assertEqual(struct.unpack_from('<8I',b,counts_ptr-base),(3,2,2,2,3,20,3,2))
        # The two pointers into the mapping must relocate together.
        row_ptr=struct.unpack_from('<I',b,0x21e5930-base)[0]
        choice_ptr=struct.unpack_from('<I',b,0x21e5938-base)[0]
        self.assertEqual(choice_ptr,row_ptr+4)
        self.assertEqual(struct.unpack_from('<6I',b,row_ptr-base+16*8),(6,0,6,1,6,2))
        self.assertEqual(struct.unpack_from('<4I',b,row_ptr-base+14*8),(7,5,7,6))

    def test_unknown_binary_fails_before_mutation(self):
        for kind in ['arm9','overlay']:
            rom=copy.deepcopy(self.original)
            if kind=='arm9':
                a=bytearray(rom.arm9);a[0x20a46]^=1;rom.arm9=bytes(a)
            else:
                i=rom.loadArm9Overlays()[50].fileID;b=bytearray(rom.files[i]);b[0]^=1;rom.files[i]=bytes(b)
            before=rom.save()
            with self.assertRaises(ValueError):speed.apply(rom)
            self.assertEqual(before,rom.save())

    def test_double_apply_and_stale_payload_fail_closed(self):
        with self.assertRaises(ValueError):speed.apply(copy.deepcopy(self.patched))
        p=speed.load_payload();p['source_sha256']='0'*64
        with self.assertRaises(ValueError):speed.apply(copy.deepcopy(self.original),p)

    def test_invalid_explicit_payload_does_not_mutate_rom(self):
        for kind in ('code','symbol','base'):
            with self.subTest(kind=kind):
                rom=copy.deepcopy(self.original);before=rom.save();p=speed.load_payload()
                if kind=='code':p['code']='fee7'+p['code'][4:]
                elif kind=='symbol':p['symbols']['print_task']=speed.BASE+3
                else:p['base']+=4
                with self.assertRaises(ValueError):speed.apply(rom,p)
                self.assertEqual(before,rom.save())

    def test_artifact_mutation_is_detected(self):
        rom=copy.deepcopy(self.patched);a=bytearray(rom.arm9);a[-40]^=1;rom.arm9=bytes(a)
        with self.assertRaises(ValueError):speed.verify(rom,self.report)
        rom=copy.deepcopy(self.patched);i=rom.loadArm9Overlays()[50].fileID;b=bytearray(rom.files[i]);b[-4]^=1;rom.files[i]=bytes(b)
        with self.assertRaises(ValueError):speed.verify(rom,self.report)
        rom=copy.deepcopy(self.patched);table=bytearray(rom.arm9OverlayTable)
        for off in range(0,len(table),32):
            if struct.unpack_from('<I',table,off)[0]==50:
                struct.pack_into('<I',table,off+8,4);break
        rom.arm9OverlayTable=bytes(table)
        with self.assertRaises(ValueError):speed.verify(rom,self.report)

if __name__=='__main__':unittest.main()
