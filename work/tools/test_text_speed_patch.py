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

def cp(name,file,offset,expect,value,enabled=True):
    return {'id':name,'file':file,'offset':hex(offset),'expect':expect,'value':value,'enabled':enabled}

class CodePatchGuardTests(unittest.TestCase):
    """ARM9 code patches from hardcoded/code_patches.json, without a ROM."""
    main=bytes(range(256))*4

    def with_bytes(self,off,data):
        b=bytearray(self.main);b[off:off+len(data)]=data;return bytes(b)

    def test_patch_holding_value_or_expect_is_accepted(self):
        expect=struct.unpack_from('<H',self.main,0x10)[0]
        patches=[cp('p','arm9',0x10,hex(expect),'0x2220')]
        for main in (self.main,self.with_bytes(0x10,struct.pack('<H',0x2220))):
            self.assertEqual([c[0] for c in speed.arm9_code_patches(main,main,patches)],['p'])

    def test_halfword_runs_use_hardcoded_parser(self):
        run=' '.join(f'{v:04X}' for v in struct.unpack_from('<3H',self.main,0x20))
        got=speed.arm9_code_patches(self.main,self.main,[cp('run','arm9',0x20,run,'01DE 01DE 01DE')])
        self.assertEqual(got[0][3],self.main[0x20:0x26]);self.assertEqual(got[0][4],struct.pack('<3H',0x1de,0x1de,0x1de))

    def test_patch_byte_neither_expect_nor_value_fails(self):
        expect=struct.unpack_from('<H',self.main,0x10)[0]
        main=self.with_bytes(0x10,b'\xaa\xbb')
        with self.assertRaisesRegex(ValueError,'neither its expect nor its value'):
            speed.arm9_code_patches(main,main,[cp('p','arm9',0x10,hex(expect),'0x2220')])

    def test_disabled_patches_are_ignored_and_bad_ones_fail(self):
        self.assertEqual(speed.arm9_code_patches(self.main,self.main,[cp('off','arm9',0x10,'0x1','0x2',False)]),[])
        for bad in (cp('size','arm9',0x10,'0x0100','0101 0202'),cp('wide','arm9',0x10,'0x10000','0x1'),
                    {'id':'missing','file':'arm9','enabled':True}):
            with self.subTest(case=bad['id']),self.assertRaisesRegex(ValueError,'Invalid code patch'):
                speed.arm9_code_patches(self.main,self.main,[bad])

    def test_patch_outside_main_section_or_compressed_arm9_fails(self):
        with self.assertRaisesRegex(ValueError,'outside the ARM9 main section'):
            speed.arm9_code_patches(self.main+b'itcm',self.main,[cp('itcm','arm9',len(self.main),'0x7469','0x0')])
        with self.assertRaisesRegex(ValueError,'uncompressed main section'):
            speed.arm9_code_patches(b'\xff'+self.main[1:],self.main,[cp('p','arm9',0x10,'0x1110','0x0')])

    def test_overlay50_code_patch_fails(self):
        for name in ('overlay50','overlay050'):
            with self.subTest(file=name),self.assertRaisesRegex(ValueError,'targets overlay 50'):
                speed.arm9_code_patches(self.main,self.main,[cp('opt',name,0x10,'0x1','0x2')])
        # Other overlays are not text-speed inputs and are left to hardcoded.py.
        self.assertEqual(speed.arm9_code_patches(self.main,self.main,[cp('o17','overlay17',0x10,'0x1','0x2')]),[])

    def test_overlap_detection_is_byte_exact(self):
        patches=[('a','arm9',0x10,b'\0\0',b'\1\1'),('b','arm9',0x20,b'\0'*4,b'\1'*4)]
        self.assertEqual(speed.overlapping(patches,[(0x12,0x20)]),[])
        self.assertEqual(speed.overlapping(patches,[(0x11,0x12)]),['a'])
        self.assertEqual(speed.overlapping(patches,[(0x0e,0x24)]),['a','b'])
        self.assertEqual(speed.overlapping(patches,[(0x23,0x30)]),['b'])

    def test_real_code_patches_are_text_speed_compatible(self):
        names=[c[0] for c in speed.code_patch_ranges()]
        self.assertIn('msgload-all',names)
        heap=[c for c in speed.code_patch_ranges() if c[0]=='msgload-all'][0]
        self.assertEqual((heap[1],heap[2],heap[4]),('arm9',speed.HEAP_FIX[0],struct.pack('<H',speed.HEAP_FIX[1])))

ROM=os.environ.get('TEXT_SPEED_TEST_ROM')
def ndspy_reparse(rom):
    import ndspy.rom
    return ndspy.rom.NintendoDSRom(rom.save())

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

    def test_critical_runtime_contract_is_independent_of_receipt_hashes(self):
        # Simulate a later build stage overwriting a critical instruction before
        # refreshing its output hash. A self-consistent receipt is not sufficient.
        for off in (0xd1a28,0x20a18,0x208ea,0x20962,0x2b176,0x2b1c6,0x2b1d2,0x2b1da):
            with self.subTest(offset=hex(off)):
                rom=copy.deepcopy(self.patched)
                code=rom.loadArm9();code.sections[0].data[off]^=1
                rom.arm9=code.save(compress=False)
                report=copy.deepcopy(self.report);report['arm9_sha256']=speed.digest(rom.arm9)
                with self.assertRaisesRegex(ValueError,'Native runtime contract changed'):
                    speed.verify(rom,report)

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

    def code_patches(self):
        import hardcoded
        return hardcoded.load_code_patches()

    def arm9_with(self,rom,off,data):
        a=bytearray(rom.arm9);a[off:off+len(data)]=data;rom.arm9=bytes(a)

    def test_arm9_with_code_patches_applied_passes_and_keeps_them(self):
        main=self.original.loadArm9().sections[0].data
        cps=speed.arm9_code_patches(self.original.arm9,main)
        self.assertTrue(any(bytes(main[off:off+len(new)])==new for _,_,off,_,new in cps))
        after=self.patched.loadArm9().sections[0].data
        for name,_,off,want,new in cps:
            with self.subTest(patch=name):
                self.assertEqual(bytes(after[off:off+len(new)]),bytes(main[off:off+len(new)]))

    def test_unpatched_base_still_passes(self):
        # Only the heap fix that text speed needs; every other arm9 code patch at 'expect'.
        rom=copy.deepcopy(self.original);main=rom.loadArm9().sections[0].data
        for name,_,off,want,_ in speed.arm9_code_patches(rom.arm9,main):
            if name!='msgload-all':self.arm9_with(rom,off,want)
        report=speed.apply(rom)
        self.assertEqual(speed.verify(ndspy_reparse(rom),report)['status'],'passed')
        after=rom.loadArm9().sections[0].data
        self.assertEqual(bytes(after[0x8c262:0x8c264]),struct.pack('<H',0x221a))

    def test_patch_byte_neither_expect_nor_value_fails_before_mutation(self):
        rom=copy.deepcopy(self.original);self.arm9_with(rom,0x8c262,struct.pack('<H',0x2221))
        before=rom.save()
        with self.assertRaisesRegex(ValueError,'ivev-panel-iv-x.*neither'):speed.apply(rom)
        self.assertEqual(before,rom.save())

    def test_synthetic_code_patch_overlapping_text_speed_edit_fails(self):
        main=self.original.loadArm9().sections[0].data
        for off in (0x20a18,0x20a1a,0x2b1d2,0xd1a28):
            old=struct.unpack_from('<H',main,off)[0]
            for state in ('expect','value'):
                with self.subTest(offset=hex(off),state=state):
                    rom=copy.deepcopy(self.original)
                    if state=='value':self.arm9_with(rom,off,struct.pack('<H',old^0x40))
                    synthetic=dict(id='synthetic',file='arm9',offset=hex(off),expect=hex(old),value=hex(old^0x40),enabled=True)
                    before=rom.save()
                    with self.assertRaisesRegex(ValueError,'overlap text-speed ARM9 edits: synthetic'):
                        speed.apply(rom,code_patches=self.code_patches()+[synthetic])
                    self.assertEqual(before,rom.save())

    def test_synthetic_code_patch_overlapping_runtime_contract_fails_verify(self):
        data=self.patched.loadArm9().sections[0].data
        old=struct.unpack_from('<H',data,0x2b1d2)[0]
        synthetic=dict(id='synthetic',file='arm9',offset='0x2b1d2',expect=hex(old),value=hex(old),enabled=True)
        with self.assertRaisesRegex(ValueError,'native runtime contract: synthetic'):
            speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

    def test_overlay50_code_patch_fails_before_mutation(self):
        synthetic=dict(id='options',file='overlay50',offset='0x0',expect='0x0',value='0x1',enabled=True)
        rom=copy.deepcopy(self.original);before=rom.save()
        with self.assertRaisesRegex(ValueError,'targets overlay 50'):
            speed.apply(rom,code_patches=self.code_patches()+[synthetic])
        self.assertEqual(before,rom.save())
        with self.assertRaisesRegex(ValueError,'targets overlay 50'):
            speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

if __name__=='__main__':unittest.main()
