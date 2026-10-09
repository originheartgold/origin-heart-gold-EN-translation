"""Native patch guards and binary round-trip tests; ROM stays local and optional.

Set TEXT_SPEED_TEST_ROM to an English ROM built without text speed (build.py --without
text-speed); the build_report.json next to it gives the bytes the armips fixes wrote.
"""
import copy,json,os,struct,sys,unittest,shutil,tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import text_speed_patch as speed
try:import capstone
except ImportError:capstone=None

def pinned_clang():
    if not shutil.which('clang'):return False
    try:speed.check_clang()
    except (OSError,ValueError):return False
    return True

def fake_clang(first_line,returncode=0):
    return patch.object(speed.subprocess,'run',return_value=speed.subprocess.CompletedProcess(
        ['clang','--version'],returncode,stdout=first_line+'\nTarget: arm64-apple-darwin\n',stderr=''))

class CompilerPinTests(unittest.TestCase):
    def test_pin_is_recorded_in_the_registry(self):
        self.assertRegex(speed.pinned_compiler(),r'^Apple clang version 21\.\d+\.\d+')
        self.assertEqual(speed.clang_family(speed.pinned_compiler()),('Apple clang',21))

    def test_pinned_version_accepted_without_warning(self):
        with fake_clang(speed.pinned_compiler()):
            self.assertEqual(speed.check_clang(),(speed.pinned_compiler(),None))

    def test_same_major_other_build_warns(self):
        with fake_clang('Apple clang version 21.0.1 (clang-2100.1.5.2)'):
            have,warning=speed.check_clang()
        self.assertEqual(have,'Apple clang version 21.0.1 (clang-2100.1.5.2)')
        self.assertIn('payload comparison decides',warning)

    def test_other_vendor_or_major_refused_before_compiling(self):
        for line in ('Ubuntu clang version 21.1.0 (1ubuntu1)','Apple clang version 17.0.0 (clang-1700.0.13.3)',
                     'clang version 21.0.0','gcc (GCC) 14.2.0'):
            with self.subTest(line=line),fake_clang(line) as run:
                with self.assertRaisesRegex(ValueError,'same vendor and major version are required'):
                    speed.check_clang()
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ValueError):speed.compile_payload(Path(directory)/'native.o')
                self.assertEqual([c.args[0][1] for c in run.call_args_list],['--version','--version'])  # never compiled

    def test_reproduction_checks_the_compiler_first(self):
        with fake_clang('Ubuntu clang version 18.1.3 (1ubuntu1)'),patch.object(speed,'compile_payload') as comp:
            with self.assertRaisesRegex(ValueError,'pinned to'):speed.verify_reproducible_payload()
        comp.assert_not_called()

    def test_missing_or_broken_clang_is_an_error_not_a_skip(self):
        with patch.object(speed.subprocess,'run',side_effect=FileNotFoundError('clang')):
            with self.assertRaises(FileNotFoundError):speed.check_clang()
        with fake_clang('',returncode=1):
            with self.assertRaisesRegex(ValueError,'--version failed'):speed.check_clang()

    def test_missing_pin_refused(self):
        fx={'id':speed.FIX_ID,'native':{'source':'native.c'}}
        with patch('fixes.load_all',return_value=[fx]):
            with self.assertRaisesRegex(ValueError,'no \\[native\\] compiler pin'):speed.pinned_compiler()

class PayloadTests(unittest.TestCase):
    def test_payload_is_current_and_entries_are_in_reserved_code(self):
        p=speed.load_payload();code=bytes.fromhex(p['code'])
        self.assertEqual(p['source_sha256'],speed.source_digest())
        self.assertLessEqual(speed.BASE+len(code),0x01ffa000)
        for name in ['print_task','load_rows','load_choice','load_label','exit_free','draw_label','setup_sprites',
                     'frame_end','pass_end','call_print']:
            target=p['symbols'][name]
            self.assertEqual(target&1,1,name)
            self.assertTrue(speed.BASE <= (target&~1) < speed.BASE+len(code),name)
        # The runtime frame state is the zeroed, word-aligned tail of the block.
        state=p['symbols'][speed.STATE_SYMBOL]
        self.assertEqual(state,speed.BASE+len(code)-speed.STATE_SIZE)
        self.assertEqual(code[-speed.STATE_SIZE:],bytes(speed.STATE_SIZE))

    @unittest.skipIf(capstone is None, 'capstone is required to disassemble the payload')
    def test_pass_end_calls_frame_end_then_runs_printer_slots(self):
        # The one intra-payload call (R_ARM_THM_CALL) is pass_end's bl to frame_end; the
        # catch-up reads the printer slot array and calls each task's function by register.
        p=speed.load_payload();code=bytes.fromhex(p['code']);base=p['base']
        start=p['symbols']['pass_end']&~1
        end=min([a&~1 for n,a in p['symbols'].items() if (a&~1)>start and n!=speed.STATE_SYMBOL]
                +[p['symbols'][speed.STATE_SYMBOL]])
        ins=list(capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB).disasm(code[start-base:end-base],start))
        calls=[i for i in ins if i.mnemonic=='bl']
        targets=[int(i.op_str.lstrip('#'),16) for i in calls]
        self.assertEqual(targets[0],p['symbols']['frame_end']&~1)
        self.assertEqual(calls[0].address,ins[2].address)    # push, sub sp, then frame_end first
        # the other bl calls are the payload's own helpers (costs, time left), placed after pass_end
        self.assertTrue(all(start<t<end for t in targets[1:]),[hex(t) for t in targets])
        # by register: the two save accessors of fast() (the anchor wait) and each printer task
        self.assertEqual(sum(1 for i in ins if i.mnemonic=='blx'),3)
        words={struct.unpack_from('<I',code,off)[0] for off in range((start-base+3)&~3,end-base-3,4)}
        for value in (0x021d0efc,0x027ffc3c,0x04000006,0x04000100,0x021e0a5c,p['symbols'][speed.STATE_SYMBOL]):
            self.assertIn(value,words,hex(value))

    def test_thumb_call_relocation_is_the_only_new_kind(self):
        # compile_payload accepts R_ARM_THM_CALL only as a Thumb 'bl' to Thumb payload code.
        src=Path(speed.__file__).read_text()
        self.assertIn("if kind not in (2,10):raise ValueError",src)

    @unittest.skipUnless(pinned_clang(), 'the pinned clang (fix.toml [native] compiler) reproduces the payload; '
                         'the release gate text_speed_patch.py --check-payload never skips')
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
            'entry in the frame state':lambda p:p['symbols'].update(print_task=p['symbols']['text_speed_state']+1),
            'state moved':lambda p:p['symbols'].update(text_speed_state=p['symbols']['text_speed_state']-4),
            'state not zero':lambda p:p.update(code=p['code'][:-2]+'01'),
            'missing state':lambda p:p['symbols'].pop('text_speed_state'),
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
                with self.assertRaises(ValueError):speed.validate_payload(payload)

    def test_reviewed_pin_is_independent_of_cache(self):
        payload=speed.load_payload();payload['code']='fee7'+payload['code'][4:]
        # A cache still claiming the correct sources must fail the independent
        # pin even when its structure and entry points are otherwise plausible.
        self.assertEqual(payload['source_sha256'],speed.source_digest())
        with self.assertRaisesRegex(ValueError,'independently reviewed digest'):
            speed.validate_payload(payload)

    @patch.object(speed,'check_clang',return_value=('Apple clang version 21.0.0',None))
    def test_release_reproduction_never_skips_missing_compiler_or_changed_output(self,_clang):
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
    """ARM9 code regions of the other fixes (work/patches, fixes.py), without a ROM."""
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

    def test_non_dict_code_patch_entry_is_value_error(self):
        for bad in ('arm9:0x10',None,['arm9']):
            with self.subTest(entry=bad),self.assertRaisesRegex(ValueError,'Invalid code patch entry'):
                speed.code_patch_ranges([bad])

    def test_every_native_call_target_is_a_reviewed_routine(self):
        entries={lo for lo,_,_ in speed.CALLED_ROUTINES}
        tails={lo for lo,_,name in speed.CALLED_ROUTINES if 'tail-called' in name}
        main=[t for t in speed.native_call_targets() if t<speed.OVBASE]
        overlay=[t for t in speed.native_call_targets() if t>=speed.OVBASE]
        self.assertEqual(len(main),18)
        self.assertEqual({t&~1 for t in main}|tails,entries)
        self.assertEqual(overlay,[0x021e5335,0x021e5acd])
        # Literal words in the compiled payload that point into main ARM9 code are
        # reviewed entries too (some calls are computed from one base literal).
        code=bytes.fromhex(speed.load_payload()['code'])
        words={w for (w,) in struct.iter_unpack('<I',code[:len(code)//4*4])}
        for w in words:
            if speed.ARM9BASE<=w<0x02110000 and w&1:self.assertIn(w&~1,entries,hex(w))
        self.assertEqual(len(speed.dependency_ranges(0x110000)),len(speed.DEPENDENCIES))
        for lo,hi,name in speed.DEPENDENCIES:self.assertLess(lo,hi,name)

    def test_phone_call_wrapper_targets_are_reviewed(self):
        # call_print clears auto-scroll through SetAutoScrollParam, then calls the
        # original AddTextPrinterParameterized; both entries are reviewed routines.
        targets=speed.native_call_targets()
        for target in (0x02002b51,speed.ADD_PRINTER|1):self.assertIn(target,targets)
        routines={lo:hi for lo,hi,_ in speed.CALLED_ROUTINES}
        self.assertEqual(routines[0x02002b50],0x02002b8c)
        self.assertEqual(routines[speed.ADD_PRINTER],0x02020884)
        # Its range is enforced: a code patch inside the setter is a dependency clash.
        self.assertEqual(speed.overlapping([('p','arm9',0x2b6a,b'\0\0',b'\1\1')],speed.dependency_ranges(0x110000)),['p'])
        with patch.object(speed,'CALLED_ROUTINES',tuple(r for r in speed.CALLED_ROUTINES if r[0]!=0x02002b50)):
            with self.assertRaisesRegex(ValueError,'unreviewed routine 0x2002b51'):speed.dependency_ranges(0x110000)

    def test_overlay92_code_patch_fails(self):
        for name in ('overlay92','overlay092'):
            with self.subTest(file=name),self.assertRaisesRegex(ValueError,'targets overlay 92'):
                speed.code_patch_ranges([cp('gear',name,0x10,'0x1','0x2')])

    def test_unreviewed_native_call_target_fails_closed(self):
        for target in (0x02030001,0x02030000,0x02200001):
            with self.subTest(target=hex(target)):
                with patch.object(speed,'native_call_targets',return_value=speed.native_call_targets()+[target]):
                    with self.assertRaises(ValueError):speed.dependency_ranges(0x110000)

    def test_arm_mode_call_to_a_reviewed_entry_fails_closed(self):
        # Even address of a reviewed Thumb entry: only the ARM-mode check can reject it.
        self.assertIn(0x02020a1c,{lo for lo,_,_ in speed.CALLED_ROUTINES})
        with patch.object(speed,'native_call_targets',return_value=speed.native_call_targets()+[0x02020a1c]):
            with self.assertRaisesRegex(ValueError,'ARM-mode'):speed.dependency_ranges(0x110000)

    @unittest.skipUnless(capstone,'capstone (in the project venv) runs the derivation helper')
    def test_derivation_rejects_backward_branches_and_unreviewed_pc_writes(self):
        B=0x02000000
        cases={'b before entry':'0000 e7fc 4770','beq before entry':'0000 d0fc 4770',
               'unreviewed add pc':'0000 448f 4770','computed bx':'0000 4708'}
        for name,code in cases.items():
            main=bytes.fromhex(code.replace(' ',''))
            main=b''.join(main[i+1:i+2]+main[i:i+1] for i in range(0,len(main),2))+bytes(16)
            with self.subTest(case=name),self.assertRaises(AssertionError):routine_extents(main,B+2)
        main=bytes.fromhex('7047')+bytes(16)
        self.assertEqual(routine_extents(main,B),[(B,B+2)])

    def test_real_code_patches_are_text_speed_compatible(self):
        names=[c[0] for c in speed.code_patch_ranges()]
        self.assertIn('msgload-all',names)
        self.assertNotIn('text-speed-print-task',names)       # its own regions are not 'other fixes'
        heap=[c for c in speed.code_patch_ranges() if c[0]=='msgload-all'][0]
        self.assertEqual((heap[1],heap[2],heap[4]),('arm9',speed.HEAP_FIX[0],None))   # no armips report: no value
        # with the armips stage's report the value is the bytes it wrote
        report={'code_regions':[{'id':'msgload-all','new':hex(speed.HEAP_FIX[1])}]}
        heap=[c for c in speed.code_patch_ranges(speed.registry_code_patches(hc_report=report)) if c[0]=='msgload-all'][0]
        self.assertEqual(heap[4],struct.pack('<H',speed.HEAP_FIX[1]))

    def test_registry_fix_touching_options_or_pokegear_overlay_fails(self):
        import fixes
        for key in ('overlay50','overlay92'):
            for fx in ({'id':'x','kind':'strings','string':[{'id':f'{key}:0x10','file':key,'offset':'0x10','max_units':2,'zh':'a'}]},
                       {'id':'x','kind':'code','grow':[{'file':key,'max':4}]}):
                with self.subTest(key=key,kind=fx['kind']),self.assertRaisesRegex(ValueError,f'touches {key}'):
                    speed.registry_code_patches([fx])
        # nor the ITCM block, which text speed pins and extends (the RC pinned the whole ITCM image)
        for fx in ({'id':'x','kind':'code','grow':[{'file':'itcm','max':4}]},
                   {'id':'x','kind':'code','code':[{'id':'x-1','file':'itcm','offset':'0x10','expect':'0x0'}]}):
            with self.subTest(itcm=list(fx)[-1]),self.assertRaisesRegex(ValueError,'touches the ITCM block'):
                speed.registry_code_patches([fx])
        # text speed's own footprint is not a clash
        own=[f for f in fixes.load_all() if f['id']==speed.FIX_ID]
        self.assertEqual(speed.registry_code_patches(own),[])

ROM=os.environ.get('TEXT_SPEED_TEST_ROM')

def find_armips():
    import asmpatch
    try:
        path=asmpatch.find_armips();asmpatch.check_armips(path);return path
    except asmpatch.AsmError:return None

ARMIPS=find_armips()

def apply_text_speed(rom,cps):
    """What build.py does for the text-speed fix, on a fixture built without it: precheck,
    assemble work/patches/text-speed/text-speed.asm (asmpatch, armips), receipt."""
    import asmpatch,fixes
    speed.precheck(rom,code_patches=cps)
    fx=[f for f in fixes.load_all() if f['id']==speed.FIX_ID]
    try:asmpatch.apply(rom,fx,ARMIPS)
    except asmpatch.AsmError as ex:raise ValueError(str(ex)) from None
    return speed.receipt(rom,cps)

def fixture_code_patches():
    """The other fixes' code regions with the values the fixture's own build wrote (its build_report.json)."""
    report=Path(ROM).parent/'build_report.json'
    if not report.is_file():raise unittest.SkipTest(f'{report} missing: build the fixture with build.py --without text-speed')
    hc=json.loads(report.read_text()).get('hardcoded')
    if not hc:raise unittest.SkipTest(f'{report} has no armips report')
    return speed.registry_code_patches(hc_report=hc)

def routine_extents(main,entry):
    """[start,end) RAM ranges of a Thumb routine, as CALLED_ROUTINES documents.

    Recursive traversal from the entry: fall-through and in-function branches until
    every path returns (pop {pc} / bx); PC-relative literal pools are included; a
    'ldr rX,=target; bx rX' tail call adds the target routine's own extent. A
    computed PC write is accepted only at a hand-reviewed REVIEWED_SWITCHES site,
    whose exact idiom, table and case targets are re-checked here; any other one,
    or a branch to before the entry, is an error rather than a silent gap.
    """
    from capstone import arm
    md=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);md.detail=True
    B=0x02000000
    def one(x):return next(md.disasm(bytes(main[x-B:x-B+4]),x,1))
    seen=set();data=set();work=[entry];tails=[]
    def branch(x,t):
        if not entry<=t<entry+0x1000:raise AssertionError(f'branch outside routine at {x:#x} -> {t:#x}')
        return t
    while work:
        x=work.pop();regs={}
        while x not in seen:
            seen.add(x);i=one(x);m=i.mnemonic;ops=i.operands
            if m.startswith('ldr') and ops[-1].type==arm.ARM_OP_MEM and ops[-1].mem.base==arm.ARM_REG_PC:
                lit=((x+4)&~3)+ops[-1].mem.disp;data.update(range(lit,lit+4))
                regs[ops[0].reg]=struct.unpack_from('<I',main,lit-B)[0]
            if m=='pop' and any(o.reg==arm.ARM_REG_PC for o in ops):break
            if m=='bx':
                if ops[0].reg!=arm.ARM_REG_LR:
                    if ops[0].reg not in regs:raise AssertionError(f'computed jump at {x:#x}')
                    tails.append(regs[ops[0].reg]&~1)
                break
            if m=='b':x=branch(x,ops[0].imm);continue
            if m.startswith('b') and m not in ('bl','blx','bic','bics') and ops and ops[0].type==arm.ARM_OP_IMM:
                work.append(branch(x,ops[0].imm))
            if ops and ops[0].type==arm.ARM_OP_REG and ops[0].reg==arm.ARM_REG_PC:
                if x not in speed.REVIEWED_SWITCHES:raise AssertionError(f'unreviewed pc write at {x:#x}')
                # adds r1,r1,r1; add r1,pc; ldrh r1,[r1,#6]; lsls r1,#16; asrs r1,#16; add pc,r1
                # preceded by its bound check 'cmp r1,#8' (9 cases).
                if (bytes(main[x-10-B:x+2-B])!=bytes.fromhex('49187944c988090409148f44')
                        or b'\x08\x29' not in bytes(main[x-18-B:x-10-B]) or len(speed.REVIEWED_SWITCHES[x])!=9):
                    raise AssertionError(f'switch idiom changed at {x:#x}')
                cases=speed.REVIEWED_SWITCHES[x]
                offsets=struct.unpack_from(f'<{len(cases)}h',main,x+2-B)
                if tuple(x+4+o for o in offsets)!=cases:raise AssertionError(f'switch table changed at {x:#x}')
                data.update(range(x+2,x+2+2*len(cases)))
                work.extend(branch(x,t) for t in cases)
                break
            x+=i.size
    out=[(entry,max([max(seen)+2]+[d+1 for d in data]))]
    for t in tails:out+=routine_extents(main,t)
    return out

def call_targets(main):
    """Every Thumb BL target in the ARM9 main section, plus odd literal words (Thumb pointers)."""
    B=0x02000000;out=set()
    for off in range(0,len(main)-3,2):
        hi,lo=struct.unpack_from('<HH',main,off)
        if hi&0xf800==0xf000 and lo&0xf800==0xf800:
            delta=((hi&0x7ff)<<12|(lo&0x7ff)<<1);delta-=(1<<23) if delta&(1<<22) else 0
            out.add(B+off+4+delta)
    out.update(w&~1 for (w,) in struct.iter_unpack('<I',bytes(main[:len(main)//4*4])) if w&1 and B<=w<B+len(main))
    return out

def is_function_entry(main,start,targets=None):
    """A real routine start: called by a BL, or its Thumb address stored somewhere."""
    return start in (call_targets(main) if targets is None else targets)

def ndspy_reparse(rom):
    import ndspy.rom
    return ndspy.rom.NintendoDSRom(rom.save())

@unittest.skipUnless(ROM and Path(ROM).is_file(),'Set TEXT_SPEED_TEST_ROM for local binary tests')
@unittest.skipUnless(ARMIPS,'armips v0.11.0 ($ARMIPS or PATH) assembles text-speed.asm')
class RomTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ndspy.rom
        cls.original=ndspy.rom.NintendoDSRom.fromFile(ROM)
        cls.patched=copy.deepcopy(cls.original)
        cls.cps=fixture_code_patches()
        cls.report=apply_text_speed(cls.patched,cls.cps)

    def test_guarded_roundtrip_and_unmodified_game_data(self):
        import ndspy.rom
        reparsed=ndspy.rom.NintendoDSRom(self.patched.save())
        self.assertEqual(speed.verify(reparsed,self.report)['status'],'passed')
        changed=[i for i,(a,b) in enumerate(zip(self.original.files,reparsed.files)) if a!=b]
        ovs=self.original.loadArm9Overlays()
        self.assertEqual(changed,sorted([ovs[50].fileID,ovs[92].fileID]))
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

    def test_printer_unchanged_and_new_game_default(self):
        data=self.patched.loadArm9().sections[0].data
        original=self.original.loadArm9().sections[0].data
        # No private printer storage since D-1604 (no SLOW phase): the constructor's
        # allocation size and its call of the original initializer are untouched.
        self.assertEqual(struct.unpack_from('<H',data,0x208ea)[0],0x2134)
        self.assertEqual(bytes(data[0x208ea:0x208ec]),bytes(original[0x208ea:0x208ec]))
        self.assertEqual(bytes(data[0x20962:0x20966]),speed.bl(0x2020962,0x2020be8))
        # New games start on FAST (text-speed bits 2..3 = 1, D-1604).
        self.assertEqual(struct.unpack_from('<HH',data,0x2b176),(0x2004,0x4301))
        # The game loop's last call before its VBlank wait goes through pass_end (frame_end, catch-up).
        self.assertEqual(bytes(data[0xde0:0xde4]),speed.bl(0x02000de0,speed.load_payload()['symbols']['pass_end']))
        self.assertEqual(bytes(self.original.loadArm9().sections[0].data[0xde0:0xde4]),speed.bl(0x02000de0,0x020272d4))
        # Only the default initializer changes; the original save structure stays two bytes.
        self.assertEqual(bytes(data[0x2b16e:0x2b170]),bytes(self.original.loadArm9().sections[0].data[0x2b16e:0x2b170]))

    def test_menu_choice_and_touch_tables(self):
        ov=self.patched.loadArm9Overlays()[50];b=ov.data;base=ov.ramAddress
        counts_ptr=struct.unpack_from('<I',b,0x21e53e0-base)[0]
        self.assertEqual(struct.unpack_from('<8I',b,counts_ptr-base),(3,2,2,2,3,20,2,2))   # TEXT SPEED: NORMAL, FAST
        # The two pointers into the mapping must relocate together.
        row_ptr=struct.unpack_from('<I',b,0x21e5930-base)[0]
        choice_ptr=struct.unpack_from('<I',b,0x21e5938-base)[0]
        self.assertEqual(choice_ptr,row_ptr+4)
        self.assertEqual(struct.unpack_from('<4I',b,row_ptr-base+16*8),(6,0,6,1))
        boxes_ptr=row_ptr-19*4               # apply() appends the 19 touch boxes right before the mapping
        boxes=list(struct.iter_unpack('<4B',b[boxes_ptr-base:boxes_ptr-base+19*4]))
        self.assertIn(struct.pack('<I',boxes_ptr),b)
        self.assertEqual(boxes[16:],[(146,166,112,167),(146,166,192,247),(255,0,0,0)])
        # Row 6 label pitch 32 (as the two-choice rows 2 and 3): NORMAL at x 108, FAST at 188.
        self.assertEqual(b[0x21e5bae-base],0x20)
        self.assertEqual(struct.unpack_from('<4I',b,row_ptr-base+14*8),(7,5,7,6))

    def test_unknown_binary_fails_before_mutation(self):
        for kind in ['arm9','overlay','overlay92','overlay92-site']:
            rom=copy.deepcopy(self.original)
            if kind=='arm9':
                a=bytearray(rom.arm9);a[0x20a46]^=1;rom.arm9=bytes(a)
            else:
                n,off=(50,0) if kind=='overlay' else (92,0x100) if kind=='overlay92' else (92,speed.CALL_SITE-speed.CALL_OVBASE)
                i=rom.loadArm9Overlays()[n].fileID;b=bytearray(rom.files[i]);b[off]^=1;rom.files[i]=bytes(b)
            before=rom.save()
            with self.subTest(kind=kind),self.assertRaisesRegex(ValueError,'changed|Unreviewed'):apply_text_speed(rom,self.cps)
            self.assertEqual(before,rom.save())

    def gear(self,rom):
        o=rom.loadArm9Overlays()[92];return o.fileID,bytearray(rom.files[o.fileID])

    def test_phone_call_redirect(self):
        fid,g=self.gear(self.patched);site=speed.CALL_SITE-speed.CALL_OVBASE
        call=speed.load_payload()['symbols']['call_print']
        self.assertEqual(bytes(g[site:site+4]),speed.bl(speed.CALL_SITE,call))
        _,o=self.gear(self.original)
        self.assertEqual(bytes(o[site:site+4]),speed.bl(speed.CALL_SITE,speed.ADD_PRINTER))
        # Exactly one four-byte difference in the overlay; size and table entry unchanged.
        self.assertEqual([i for i in range(len(o)) if o[i]!=g[i]],[i for i in range(site,site+4) if o[i]!=g[i]])
        self.assertEqual(len(o),len(g))
        # The fix declares exactly this region in overlay 92: the call, with its original bytes.
        import fixes
        fx=[f for f in fixes.load_all() if f['id']==speed.FIX_ID][0]
        self.assertEqual([(e['offset'],e['expect']) for e in fx['code'] if e['file']=='overlay92'],
                         [(hex(site).upper().replace('0X','0x'),
                           ' '.join(f'{h:04X}' for h in struct.unpack('<2H',speed.bl(speed.CALL_SITE,speed.ADD_PRINTER))))])
        self.assertEqual(self.report['call_overlay_sha256'],speed.digest(bytes(g)))

    def test_overlay92_already_redirected_is_refused(self):
        # Only the Pokégear edit present (e.g. a partial earlier application).
        rom=copy.deepcopy(self.original);fid,g=self.gear(rom);site=speed.CALL_SITE-speed.CALL_OVBASE
        g[site:site+4]=speed.bl(speed.CALL_SITE,speed.load_payload()['symbols']['call_print']);rom.files[fid]=bytes(g)
        before=rom.save()
        with self.assertRaisesRegex(ValueError,'Pokégear overlay changed'):apply_text_speed(rom,self.cps)
        self.assertEqual(before,rom.save())

    def test_verify_fails_without_phone_call_redirect(self):
        # Undo only the Pokégear redirect; a refreshed receipt must not hide it.
        rom=copy.deepcopy(self.patched);fid,g=self.gear(rom);site=speed.CALL_SITE-speed.CALL_OVBASE
        g[site:site+4]=speed.bl(speed.CALL_SITE,speed.ADD_PRINTER);rom.files[fid]=bytes(g)
        report=copy.deepcopy(self.report)
        with self.assertRaisesRegex(ValueError,'Pokégear overlay changed'):speed.verify(rom,report)
        report['call_overlay_sha256']=speed.digest(bytes(g))
        with self.assertRaisesRegex(ValueError,'phone-call printer not redirected'):speed.verify(rom,report)
        # Redirect present, but another overlay byte changed: still refused.
        rom=copy.deepcopy(self.patched);fid,g=self.gear(rom);g[0x100]^=1;rom.files[fid]=bytes(g)
        report=copy.deepcopy(self.report);report['call_overlay_sha256']=speed.digest(bytes(g))
        with self.assertRaisesRegex(ValueError,'outside the call redirect'):speed.verify(rom,report)
        # A receipt without the Pokégear hash (older candidates) is refused.
        report=copy.deepcopy(self.report);report.pop('call_overlay_sha256')
        with self.assertRaisesRegex(ValueError,'Pokégear overlay changed'):speed.verify(self.patched,report)

    def test_overlay92_code_patch_fails_before_mutation(self):
        synthetic=dict(id='gear',file='overlay92',offset='0x0',expect='0x0',value='0x1',enabled=True)
        rom=copy.deepcopy(self.original);before=rom.save()
        with self.assertRaisesRegex(ValueError,'targets overlay 92'):
            apply_text_speed(rom,self.code_patches()+[synthetic])
        self.assertEqual(before,rom.save())
        with self.assertRaisesRegex(ValueError,'targets overlay 92'):
            speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

    def test_double_apply_and_stale_payload_fail_closed(self):
        with self.assertRaises(ValueError):apply_text_speed(copy.deepcopy(self.patched),self.cps)
        p=speed.load_payload();p['source_sha256']='0'*64
        with patch.object(speed,'load_payload',side_effect=lambda:speed.validate_payload(p)):
            with self.assertRaises(ValueError):apply_text_speed(copy.deepcopy(self.original),self.cps)

    def test_invalid_explicit_payload_does_not_mutate_rom(self):
        for kind in ('code','symbol','base'):
            with self.subTest(kind=kind):
                rom=copy.deepcopy(self.original);before=rom.save();p=speed.load_payload()
                if kind=='code':p['code']='fee7'+p['code'][4:]
                elif kind=='symbol':p['symbols']['print_task']=speed.BASE+3
                else:p['base']+=4
                with patch.object(speed,'load_payload',side_effect=lambda:speed.validate_payload(p)):
                    with self.assertRaises(ValueError):apply_text_speed(rom,self.cps)
                self.assertEqual(before,rom.save())

    def test_critical_runtime_contract_is_independent_of_receipt_hashes(self):
        # Simulate a later build stage overwriting a critical instruction before
        # refreshing its output hash. A self-consistent receipt is not sufficient.
        for off in (0xd1a28,0x20a18,0x2b176,0x2b1c6,0x2b1d2,0x2b1da,0xde0):
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
        rom=copy.deepcopy(self.patched);i=rom.loadArm9Overlays()[92].fileID;b=bytearray(rom.files[i]);b[-4]^=1;rom.files[i]=bytes(b)
        with self.assertRaises(ValueError):speed.verify(rom,self.report)
        rom=copy.deepcopy(self.patched);table=bytearray(rom.arm9OverlayTable)
        for off in range(0,len(table),32):
            if struct.unpack_from('<I',table,off)[0]==50:
                struct.pack_into('<I',table,off+8,4);break
        rom.arm9OverlayTable=bytes(table)
        with self.assertRaises(ValueError):speed.verify(rom,self.report)

    def code_patches(self):
        return list(self.cps)

    def arm9_with(self,rom,off,data):
        a=bytearray(rom.arm9);a[off:off+len(data)]=data;rom.arm9=bytes(a)

    def test_arm9_with_code_patches_applied_passes_and_keeps_them(self):
        main=self.original.loadArm9().sections[0].data
        cps=speed.arm9_code_patches(self.original.arm9,main,self.cps)
        self.assertTrue(any(bytes(main[off:off+len(new)])==new for _,_,off,_,new in cps))
        after=self.patched.loadArm9().sections[0].data
        for name,_,off,want,new in cps:
            with self.subTest(patch=name):
                self.assertEqual(bytes(after[off:off+len(new)]),bytes(main[off:off+len(new)]))

    def test_unpatched_base_still_passes(self):
        # Only the heap fix that text speed needs; every other arm9 code patch at 'expect'.
        rom=copy.deepcopy(self.original);main=rom.loadArm9().sections[0].data
        for name,_,off,want,_ in speed.arm9_code_patches(rom.arm9,main,self.cps):
            if name!='msgload-all':self.arm9_with(rom,off,want)
        report=apply_text_speed(rom,self.cps)
        self.assertEqual(speed.verify(ndspy_reparse(rom),report)['status'],'passed')
        after=rom.loadArm9().sections[0].data
        self.assertEqual(bytes(after[0x8c262:0x8c264]),struct.pack('<H',0x221a))
        ids=[c[0] for c in speed.code_patch_ranges(self.cps) if c[1]=='arm9']
        self.assertEqual(report['arm9_code_patches'],{'normalised_to_expect':ids,'held_value':['msgload-all']})

    def test_patch_byte_neither_expect_nor_value_fails_before_mutation(self):
        rom=copy.deepcopy(self.original);self.arm9_with(rom,0x8c262,struct.pack('<H',0x2221))
        before=rom.save()
        with self.assertRaisesRegex(ValueError,'ivev-panel-iv-x.*neither'):apply_text_speed(rom,self.cps)
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
                        apply_text_speed(rom,self.code_patches()+[synthetic])
                    self.assertEqual(before,rom.save())

    def test_synthetic_code_patch_overlapping_runtime_contract_fails_verify(self):
        data=self.patched.loadArm9().sections[0].data
        old=struct.unpack_from('<H',data,0x2b1d2)[0]
        synthetic=dict(id='synthetic',file='arm9',offset='0x2b1d2',expect=hex(old),value=hex(old),enabled=True)
        with self.assertRaisesRegex(ValueError,'native runtime contract: synthetic'):
            speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

    def base_main(self):
        main=bytearray(self.original.loadArm9().sections[0].data)
        for _,_,off,want,_ in speed.arm9_code_patches(self.original.arm9,main,self.cps):main[off:off+len(want)]=want
        self.assertEqual(speed.digest(main),speed.REVIEWED_BASE_ARM9_SHA256)
        return main

    @unittest.skipUnless(capstone,'capstone (in the project venv) re-derives the routine extents')
    def test_dependency_extents_rederive_from_base_arm9(self):
        main=self.base_main()
        derived=set()
        for target in speed.native_call_targets():
            if target<speed.OVBASE:derived.update(routine_extents(main,target&~1))
        self.assertEqual(derived,{(lo,hi) for lo,hi,_ in speed.CALLED_ROUTINES})
        code=[(lo,hi) for lo,hi,name in speed.DEPENDENT_CODE if lo<0x020d0000 and lo!=0x02000ba0]
        self.assertEqual(len(code),10)
        for lo,hi in code:self.assertEqual(routine_extents(main,lo),[(lo,hi)],hex(lo))
        # A start must be a real routine entry, so a shifted start cannot pass.
        targets=call_targets(main)
        def entry(start):
            before=struct.unpack_from('<H',main,start-2-0x02000000)[0]
            return is_function_entry(main,start,targets) or before==0x4770 or before&0xff00==0xbd00
        for lo,_ in code+[(lo,hi) for lo,hi,_ in speed.CALLED_ROUTINES]:self.assertTrue(entry(lo),hex(lo))
        for wrong in (0x020208e0,0x020208d6,0x0202b1d2,0x02002e42,0x020022d4):self.assertFalse(entry(wrong),hex(wrong))
        # Both reviewed jump tables are traversed: their cases lie inside the extent.
        for site,cases in speed.REVIEWED_SWITCHES.items():
            self.assertTrue(all(0x020022d0<=t<0x020027ee for t in (site,*cases)))
        # Every ARM9 edit (the fix's arm9 [[code]] regions) lies inside a reviewed enclosing routine or data range.
        for lo,hi in speed.own_arm9_ranges():
            addr,end=speed.ARM9BASE+lo,speed.ARM9BASE+hi
            self.assertTrue(any(lo<=addr and end<=hi for lo,hi,_ in speed.DEPENDENT_CODE),hex(addr))
        self.assertEqual(struct.unpack_from('<I',main,0xd1a28)[0],speed.BASE)
        self.assertEqual(self.original.loadArm9().codeSettingsOffs,0xba0)

    def test_code_patch_inside_a_dependency_fails(self):
        main=self.original.loadArm9().sections[0].data
        # Reviewer cases: print task body, Options accessor,
        # exit_free target, message loader, music getter; plus code settings.
        # Glyph path: RenderText entry, state machine code and a jump table.
        # Game loop (pass_end hook site and its VBlank wait) and the call frame_end makes.
        # Printer catch-up: slot allocator, queue run and queue add.
        for off in (0x20a40,0x2934a,0x71b2,0xbb42,0x2b1c4,0xba4,0xd1a1c,
                    0x2e50,0x22d2,0x2400,0x22f4,0x242a,0x27b8,0xde0,0xde8,0xd90,0x272d6,
                    0x20738,0x2005c,0x200c0):
            old=struct.unpack_from('<H',main,off)[0]
            synthetic=dict(id='synthetic',file='arm9',offset=hex(off),expect=hex(old),value=hex(old^0x40),enabled=True)
            with self.subTest(offset=hex(off)):
                rom=copy.deepcopy(self.original);before=rom.save()
                with self.assertRaisesRegex(ValueError,'synthetic'):
                    apply_text_speed(rom,self.code_patches()+[synthetic])
                self.assertEqual(before,rom.save())
                with self.assertRaisesRegex(ValueError,'native runtime contract: synthetic'):
                    speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

    def test_heap_fix_not_selected_fails_before_mutation(self):
        # precheck refuses before anything is assembled when msgload's heap region is not in the selection
        # (or would write another value there)
        rom=copy.deepcopy(self.original);before=rom.save()
        without=[c for c in self.cps if c['id']!='msgload-all']
        other=[dict(c,value='0x2502') if c['id']=='msgload-all' else c for c in self.cps]
        for cps in (without,other):
            with self.assertRaisesRegex(ValueError,'demand-loading heap fix'):apply_text_speed(rom,cps)
            self.assertEqual(before,rom.save())

    def test_verify_detects_a_changed_original_itcm(self):
        # another stage editing the hack's own ITCM bytes is caught, even with a refreshed receipt
        rom=copy.deepcopy(self.patched);code=rom.loadArm9();code.sections[1].data[0x100]^=1
        rom.arm9=code.save(compress=False)
        report=copy.deepcopy(self.report);report['arm9_sha256']=speed.digest(rom.arm9)
        with self.assertRaisesRegex(ValueError,'Original ITCM section changed'):speed.verify(rom,report)

    def test_heap_fix_still_at_expect_fails_closed(self):
        # msgload is assembled in the same armips stage, so the heap fix is checked after it (receipt);
        # the build stops there, before it writes a ROM.
        rom=copy.deepcopy(self.original);self.arm9_with(rom,0xba9a,struct.pack('<H',0x1c05))
        with self.assertRaisesRegex(ValueError,'demand-loading heap fix'):apply_text_speed(rom,self.cps)

    def test_verify_requires_heap_fix(self):
        rom=copy.deepcopy(self.patched);self.arm9_with(rom,0xba9a,struct.pack('<H',0x1c05))
        report=copy.deepcopy(self.report);report['arm9_sha256']=speed.digest(rom.arm9)
        with self.assertRaisesRegex(ValueError,'Heap fix missing'):speed.verify(rom,report)

    def test_report_records_normalised_code_patches(self):
        ids=[c[0] for c in speed.code_patch_ranges(self.cps) if c[1]=='arm9']
        got=self.report['arm9_code_patches']
        self.assertEqual(got['normalised_to_expect'],ids)
        self.assertEqual(got['held_value'],ids)
        self.assertIn('ivev-panel-iv-x',ids)

    def test_overlay50_code_patch_fails_before_mutation(self):
        synthetic=dict(id='options',file='overlay50',offset='0x0',expect='0x0',value='0x1',enabled=True)
        rom=copy.deepcopy(self.original);before=rom.save()
        with self.assertRaisesRegex(ValueError,'targets overlay 50'):
            apply_text_speed(rom,self.code_patches()+[synthetic])
        self.assertEqual(before,rom.save())
        with self.assertRaisesRegex(ValueError,'targets overlay 50'):
            speed.verify(self.patched,self.report,code_patches=self.code_patches()+[synthetic])

if __name__=='__main__':unittest.main()
