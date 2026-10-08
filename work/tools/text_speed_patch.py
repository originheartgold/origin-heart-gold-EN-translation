"""Text speed (fix work/patches/text-speed): the native payload and the checks around it.

The ROM edits are the armips source work/patches/text-speed/text-speed.asm, applied by
asmpatch.py like every code fix; its payload bytes come from payload.json through
load_payload(). This module holds what the build and the release gates check, and
changes no ROM:
  * the payload: compile_payload() (clang, the reviewed flags), validate_payload() and
    the reviewed sha256 pin, verify_reproducible_payload() (release gate: recompile);
  * precheck(): before assembling, the hack's base ARM9, ITCM and overlays 50/92 are the
    reviewed images and no other fix touches text speed's edits or dependencies;
  * receipt() and verify(): after writing, the hashes and the runtime contract.
Native payload is original project code, not extracted ROM data.

  python3 work/tools/text_speed_patch.py --check-payload
  python3 work/tools/text_speed_patch.py --compile work/build/text-speed/payload.json
"""
from pathlib import Path
import hashlib,json,re,struct,subprocess,tempfile

WORK=Path(__file__).resolve().parents[1]
ASSETS=WORK/'patches/text-speed'  # the fix folder: fix.toml, native.c, labels.h, payload.json
BASE=0x01ff8620
OVBASE=0x021e4980
# This reviewed pin lives in patcher source, never in the mutable cache. Updating
# native code requires review of its reproducible payload and this separate pin.
REVIEWED_PAYLOAD_SHA256='587f29a5a2b19e1c71a24b5df6104c5588d2a54a45fca16fe4bf6dc6ee12933e'
REQUIRED_SYMBOLS=frozenset(('print_task','load_rows','load_choice','load_label',
                            'commit_speed','exit_free','draw_label','setup_sprites',
                            'frame_end','pass_end','text_speed_state','call_print'))
# The one data symbol: the runtime frame state (zero at boot), the last
# STATE_SIZE bytes of the block. Every other symbol is a Thumb entry point.
STATE_SYMBOL='text_speed_state'
STATE_SIZE=52
# The game loop's last call before its wait for VBlank (NitroMain, 0x02000C88):
# 'bl 0x020272d4' at this address is redirected to the payload's pass_end, which
# calls frame_end (that call first, then the frame measurement) and then the
# printer catch-up (D-1603).
FRAME_END_CALL=(0x02000de0,0x020272d4)
MAX_PAYLOAD_SIZE=0x01ffa000-BASE
OVHASH='852d8fcd01bf09ba54bee1a24609e2a82e71d25b5d6dd84c5d919cc0b3418856'
OVERLAY=50
# Pokégear overlay (JP-base numbering 92) of the untouched Chinese hack; identical in
# the English build. Its one phone-call page printer (0x021f11e8, used by outgoing
# and incoming calls) calls AddTextPrinterParameterized at CALL_SITE; text speed
# redirects that call to call_print (D-1600, bug D-1599). The whole file is pinned
# before and after.
CALL_OVERLAY=92
CALL_OVBASE=0x021e67c0
CALL_OVSIZE=0x13ae0
CALL_OVHASH='63d914533045a08e813808869b72afe6042a832acbf183236c4f245ba5244ac6'
CALL_SITE=0x021f1228
ADD_PRINTER=0x02020834
ARM9BASE=0x02000000
# Main ARM9 section of the untouched Chinese hack (origin_v4.0.3_cn.nds). apply()
# compares it after every arm9 [[code]] region of the other fixes (work/patches/*/fix.toml,
# fixes.py) is put back to its 'expect' bytes, so new reviewed fixes elsewhere in ARM9
# do not invalidate this pin; fixes touching text-speed bytes still fail closed.
REVIEWED_BASE_ARM9_SHA256='b3249c2996c204695a2528e2e52bf0d9841ec05263a6bcecfc7db181204f96cf'
REVIEWED_ITCM_SHA256='838df87fbcf4107eb85d4c97d9fab741fd0a99d24a4dc85577e3bc8c3eded3c1'
# Text speed depends on this region of the msgload fix (msgload-all, demand-loading heap fix;
# fix.toml requires = ["msgload"]).
HEAP_FIX=(0xba9a,0x2501)
# Original ARM9 code and data text speed relies on without editing it, as
# [start,end) RAM addresses. No code patch may overlap these or the edited bytes.
# Routine extents come from a recursive Thumb disassembly (capstone) of the base
# ARM9 above: from the entry, follow fall-through and in-function branches until
# every path returns (pop {pc} / bx), include PC-relative literal pools, and for
# a 'ldr rX,=target; bx rX' trampoline also the routine it tail-calls.
# test_text_speed_patch.RomTests re-derives every extent from the ROM and checks
# that each FN() call target in native.c starts one of these routines.
CALLED_ROUTINES=(
    (0x02001194,0x020011a0,'runtime save pointer'),
    (0x02002b50,0x02002b8c,'text flags: SetAutoScrollParam (auto bit 2, auto A/B bit 5)'),
    (0x020071ac,0x020071b0,'overlay manager data getter'),
    (0x020071b0,0x020071c0,'overlay manager data free'),
    (0x0200bb0c,0x0200bb3e,'message load into string'),
    (0x0200bb40,0x0200bb6c,'message load new string'),
    (0x0200d8cc,0x0200d8d8,'sprite trampoline'),
    (0x02025014,0x0202501a,'  tail-called by sprite trampoline'),
    (0x0201dda8,0x0201ddf8,'window copy to VRAM'),
    (0x0202075c,0x020207a4,'printer finish'),
    (0x02020834,0x02020884,'add printer'),
    (0x02020a1c,0x02020a88,'original print task'),
    (0x02020a88,0x02020a9a,'render glyphs'),
    (0x02020a9c,0x02020b40,'set text colours'),
    (0x02024e48,0x02024e64,'sprite visibility'),
    (0x020272d4,0x020272f8,'3D swap request (the game loop call frame_end makes first)'),
    (0x02026864,0x02026890,'string new'),
    (0x02026eb8,0x02026f1c,'string copy characters'),
    (0x02029348,0x02029354,'Options accessor trampoline'),
    (0x02027740,0x02027764,'  tail-called save block getter'),
)
# Hand-reviewed jump tables. The traversal refuses any computed PC write except
# these. Both use the compiler's Thumb switch idiom, decoded by hand from the base
# ARM9: 'cmp r1,#8; bls/bhi default; adds r1,r1,r1; add r1,pc; ldrh r1,[r1,#6];
# lsls r1,#16; asrs r1,#16; add pc,r1'. The 9 signed halfword offsets start 2
# bytes after the 'add pc,r1' at P, and case i jumps to P+4+offset[i]. The table
# bytes are part of the routine's extent, and every case target is traversed.
REVIEWED_SWITCHES={
    # RenderText printer state (+0x28): 0..8, else default 0x020027e8.
    0x020022f0:(0x02002304,0x02002698,0x020026b2,0x020026dc,0x0200270c,
                0x02002762,0x0200276e,0x0200278e,0x020027b8),
    # RenderText control codes 0x200..0x208, else default 0x02002622.
    0x02002424:(0x0200246e,0x020024ee,0x02002510,0x02002528,0x02002534,
                0x02002540,0x0200256c,0x0200249a,0x020024c4),
}
# Whole routines containing text-speed ARM9 edits or that the batching loop relies
# on (same derivation; the RenderText state machine uses REVIEWED_SWITCHES), plus data.
# print_task's loop calls 0x02020a88, which renders through 0x02002e40 into the
# 0x020022d0 state machine. The loop relies on its results 0/1/3 and on which
# controls it stops before (0xffff, 0xfffe, 0x25bc, 0x25bd, 0xf0fd).
DEPENDENT_CODE=(
    (0x02000c88,0x02000e38,'game loop NitroMain (frame-end hook site; its VBlank wait follows the hooked call)'),
    (0x02002e40,0x02002e70,'RenderText entry called by the glyph loop'),
    (0x020022d0,0x020027ee,'RenderText control-code state machine (two reviewed jump tables)'),
    (0x020208d4,0x02020a1c,'printer constructor (task pointer)'),
    (0x0202b168,0x0202b1b4,'Options init (new-game default)'),
    (0x0202b1c4,0x0202b1d0,'music speed getter'),
    (0x0202b1d0,0x0202b1e4,'music speed setter'),
    (0x020d1a1c,0x020d1a38,'SDK arena bounds table (ITCM arena start)'),
    # Printer catch-up (pass_end): the 8 printer task slots (0x021d0efc, .bss) are
    # filled only by the slot allocator and cleared by printer finish; a task is run
    # as the queue run runs it (+0x10 data, +0x14 func, +0x18 added-during-run skip
    # flag, which the task add routine sets).
    (0x02020728,0x0202075c,'printer task slot allocator (slot array 0x021d0efc)'),
    (0x02020040,0x0202007e,'task queue run (the task layout pass_end mirrors)'),
    (0x02020094,0x02020114,'task queue add (sets the +0x18 skip flag)'),
    (0x02000ba0,0x02000bb8,'code settings / autoload list words rewritten by code.save()'),
    # Sub-line timing (D-2269): the payload reads the SDK tick count as OS_GetTick does,
    # OSi_TickCounter (0x021e0a5c, the low word of the u64 at struct 0x021e0a54 + 8) and
    # timer 0 (0x04000100), which OS_InitTick starts at prescaler 64 with its overflow
    # interrupt, and that interrupt handler counts. Both are ARM code.
    (0x020d2180,0x020d21f0,'OS_InitTick (timer 0 at bus clock / 64, overflow interrupt) and its literals'),
    (0x020d2208,0x020d2270,'tick timer interrupt (counts OSi_TickCounter) and its literals'),
    (0x020d2270,0x020d2310,'OS_GetTick (the read the payload mirrors) and its literals'),
)
DEPENDENCIES=CALLED_ROUTINES+DEPENDENT_CODE
# The batching loop and frame_end also read VCOUNT (0x04000006), the DS display
# line I/O register, and the SDK's VBlank counter HW_VBLANK_COUNT_BUF (0x027FFC3C,
# the main-memory system word OS_GetVBlankCount reads). Neither is ARM9 code or
# data in the ARM9 binary, so no code patch can overlap them and they have no
# dependency range. The same holds for timer 0 (0x04000100) and the interrupt
# flags (0x04000214), read for the tick count. The printer task slot array
# (0x021d0efc) that pass_end reads and OSi_TickCounter (0x021e0a54) are .bss,
# outside the ARM9 binary; the routines that own them are reviewed above.

def native_call_targets():
    """Every FN(address, ...) call target in native.c (source pinned via the payload)."""
    import re
    return sorted({int(x,16) for x in re.findall(r'FN\((0x[0-9a-fA-F]+)\s*,',(ASSETS/'native.c').read_text(encoding='utf-8'))})

def dependency_ranges(main_size):
    """Reviewed dependency ranges as ARM9 offsets; fail closed on an unreviewed call target."""
    entries={lo for lo,_,_ in CALLED_ROUTINES}
    for target in native_call_targets():
        if target&1==0:raise ValueError(f'Native code calls ARM-mode {target:#x}; review it')
        if OVBASE<=target<OVBASE+0x121c:continue  # overlay 50 code: whole file hash-pinned (OVHASH)
        if not ARM9BASE<=target<ARM9BASE+main_size or target&~1 not in entries:
            raise ValueError(f'Native code calls unreviewed routine {target:#x}; add its extent to CALLED_ROUTINES')
    return [(lo-ARM9BASE,hi-ARM9BASE) for lo,hi,_ in DEPENDENCIES]

def digest(b):return hashlib.sha256(b).hexdigest()

def source_digest():return digest((ASSETS/'native.c').read_bytes()+(ASSETS/'labels.h').read_bytes())

CLANG='clang'

def pinned_compiler():
    """The reviewed compiler: the text-speed fix's [native] compiler (the fix registry), the first line of
    `clang --version` that compiled payload.json."""
    import fixes as fixreg
    fx=next((f for f in fixreg.load_all() if f['id']==FIX_ID),None)
    pin=((fx or {}).get('native') or {}).get('compiler')
    if not isinstance(pin,str) or not pin.strip():
        raise ValueError(f'fix {FIX_ID} has no [native] compiler pin (work/patches/{FIX_ID}/fix.toml)')
    return pin.strip()

def clang_version(clang=None):
    """The first line of `clang --version` (e.g. 'Apple clang version 21.0.0 (clang-2100.0.123.102)')."""
    clang=clang or CLANG
    try:r=subprocess.run([clang,'--version'],capture_output=True,text=True,timeout=60)
    except OSError as error:raise FileNotFoundError(f'cannot run {clang}: {error}') from None
    except subprocess.TimeoutExpired:raise ValueError(f'{clang} --version did not finish') from None
    lines=(r.stdout or r.stderr).splitlines()
    if r.returncode or not lines:raise ValueError(f'{clang} --version failed (exit {r.returncode})')
    return lines[0].strip()

def clang_family(line):
    """(vendor, major) of a `clang --version` first line: ('Apple clang', 21); (None, None) when unreadable."""
    mo=re.match(r'^(.*?clang) version (\d+)\.',line)
    return (mo.group(1),int(mo.group(2))) if mo else (None,None)

def check_clang(clang=None):
    """(version line, warning or None). Refused (ValueError) unless clang is the pinned vendor and major
    version (fix.toml [native] compiler, 'Apple clang' 21): other compilers lay the code out differently. The
    same major with another minor or build only warns: the payload comparison (verify_reproducible_payload,
    the reviewed digest) decides whether its bytes are the reviewed ones."""
    have,want=clang_version(clang),pinned_compiler()
    if have==want:return have,None
    if clang_family(have)!=clang_family(want) or None in clang_family(want):
        raise ValueError(f'{clang or CLANG} is "{have}"; the text-speed payload is pinned to "{want}" '
                         f'(fix.toml [native] compiler; the same vendor and major version are required). Use that '
                         f'clang, or review a new payload compiled by this one (work/notes/toolchain.md: Native code)')
    return have,(f'{clang or CLANG} is "{have}", not the pinned "{want}": the same vendor and major version, so it '
                 f'runs; the payload comparison decides whether it emits the reviewed bytes')

def compile_payload(out,enforce=True):
    """Compile the self-contained C section; refuse unresolved text relocations. enforce: refuse a clang
    check_clang() refuses (the default; --compile of a new payload passes False and reports the version)."""
    import sys
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    if enforce:
        _,warning=check_clang()
        if warning:print(f'warning: {warning}',file=sys.stderr)
    subprocess.run([CLANG,'-target','arm-none-eabi','-march=armv5te','-mthumb','-Os','-Wall','-Werror','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-c',str(ASSETS/'native.c'),'-o',str(out)],check=True)
    b=out.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',b)
    if h[0][:7]!=b'\x7fELF\x01\x01\x01' or h[2]!=40:raise ValueError('Not ARM ELF32')
    sections=[struct.unpack_from('<10I',b,h[6]+i*h[11]) for i in range(h[12])]
    def data(s):return b[s[4]:s[4]+s[5]]
    names=data(sections[h[13]])
    def name(off,tab=names):return tab[off:].split(b'\0',1)[0].decode()
    placed={};image=bytearray()
    # Code and constant data first, zero-initialised data (.bss: the runtime frame
    # state) last, so the state is the tail of the block and everything before it
    # is fixed bytes that the gates can compare in RAM.
    for kind in (1,8):
        for i,s in enumerate(sections):
            if not s[2]&2 or name(s[0]).startswith('.ARM.exidx'):continue
            if s[1] not in (1,8):raise ValueError('Unexpected allocated section')
            if s[1]!=kind:continue
            align=max(4,s[8]);image.extend(bytes((-len(image))%align));placed[i]=len(image)
            image.extend(data(s) if s[1]==1 else bytes(s[5]))
    tables={};symbols={}
    for i,s in enumerate(sections):
        if s[1]!=2:continue
        strings=data(sections[s[6]]);table=[]
        for off in range(s[4],s[4]+s[5],16):
            n,v,size,info,other,idx=struct.unpack_from('<IIIBBH',b,off)
            address=BASE+placed[idx]+v if idx in placed else None
            table.append(address)
            if idx in placed and info>>4==1:symbols[name(n,strings)]=address
        tables[i]=table
    for s in sections:
        if s[1] not in (4,9) or s[7] not in placed:continue
        if s[1]!=9:raise ValueError('Unsupported ELF RELA')
        for off in range(s[4],s[4]+s[5],8):
            target,info=struct.unpack_from('<II',b,off);kind=info&255
            if kind not in (2,10):raise ValueError(f'Unsupported native relocation {kind}')
            address=tables[s[6]][info>>8]
            if address is None:raise ValueError('Undefined native symbol')
            pos=placed[s[7]]+target
            if kind==2:  # R_ARM_ABS32: literal word
                addend=struct.unpack_from('<I',image,pos)[0]
                struct.pack_into('<I',image,pos,(addend+address)&0xffffffff)
                continue
            # R_ARM_THM_CALL: a Thumb 'bl' to a Thumb function of the payload itself
            # (pass_end calls frame_end). The addend is the instruction's own offset.
            hi,lo=struct.unpack_from('<HH',image,pos)
            if hi>>11!=0b11110 or lo>>11!=0b11111 or not address&1:
                raise ValueError('Native call relocation is not a Thumb bl to Thumb code')
            addend=((hi&0x7ff)<<12)|((lo&0x7ff)<<1)
            if addend&0x400000:addend-=0x800000
            value=(address&~1)+addend-(BASE+pos)
            if not -0x400000<=value<0x400000:raise ValueError('Native call out of range')
            struct.pack_into('<HH',image,pos,0xf000|((value>>12)&0x7ff),0xf800|((value>>1)&0x7ff))
    payload={'source_sha256':source_digest(),'base':BASE,'code':image.hex(),'symbols':symbols}
    return payload

def bl(src,dst):
    delta=(dst&~1)-src-4
    if delta&1 or not -(1<<22)<=delta<(1<<22):raise ValueError('BL out of range')
    return struct.pack('<HH',0xf000|((delta>>12)&2047),0xf800|((delta>>1)&2047))

def payload_digest(payload):
    """Canonical digest binds executable bytes, entry points, base and source."""
    return digest(json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii'))

def validate_payload(payload):
    """Fail closed before using either a cached or explicitly supplied payload.

    The source hash alone is a claim, not proof of compilation. The independent
    reviewed pin binds that claim to the entire cache; RC checks also recompile.
    """
    if type(payload) is not dict or set(payload)!={'source_sha256','base','code','symbols'}:
        raise ValueError('Invalid native payload schema')
    if payload['source_sha256']!=source_digest():raise ValueError('Stale native payload; regenerate and review it')
    if type(payload['base']) is not int or payload['base']!=BASE:raise ValueError('Native payload base changed')
    encoded=payload['code']
    if type(encoded) is not str or not 4<=len(encoded)<=MAX_PAYLOAD_SIZE*2 or len(encoded)%4:
        raise ValueError('Invalid native payload size')
    try:blob=bytes.fromhex(encoded)
    except ValueError as error:raise ValueError('Invalid native payload encoding') from error
    if blob.hex()!=encoded:raise ValueError('Native payload encoding must be canonical lowercase hex')
    symbols=payload['symbols']
    if type(symbols) is not dict or set(symbols)!=REQUIRED_SYMBOLS:
        raise ValueError('Native payload symbol inventory changed')
    state=symbols[STATE_SYMBOL]
    if type(state) is not int or state!=BASE+len(blob)-STATE_SIZE or state&3 or any(blob[-STATE_SIZE:]):
        raise ValueError(f'Native frame state must be the zeroed last {STATE_SIZE} bytes of the payload')
    for name,address in symbols.items():
        if name==STATE_SYMBOL:continue
        if type(address) is not int or not address&1 or not BASE<address<state:
            raise ValueError(f'Invalid native Thumb entry point: {name}')
    if len(set(symbols.values()))!=len(symbols):raise ValueError('Native entry points overlap')
    if payload_digest(payload)!=REVIEWED_PAYLOAD_SHA256:
        raise ValueError('Native payload differs from the independently reviewed digest')
    return payload

def load_payload():
    return validate_payload(json.loads((ASSETS/'payload.json').read_text(encoding='utf-8')))

def verify_reproducible_payload():
    """Mandatory RC gate; compilation failure/missing clang is never a skip.

    Normal cached builds do not need a compiler. Release validation requires the
    reviewed compiler output to match both cached bytes and every symbol exactly.
    """
    payload=load_payload()
    have,warning=check_clang()
    with tempfile.TemporaryDirectory(prefix='text-speed-reproduce-') as directory:
        rebuilt=compile_payload(Path(directory)/'native.o',enforce=False)
    if rebuilt!=payload:
        raise ValueError('Native payload does not reproduce from current source'+(f' ({warning})' if warning else ''))
    out={'status':'passed','reviewed_payload_digest':payload_digest(payload),'native_bytes':len(bytes.fromhex(payload['code'])),
         'compiler':have,'compiler_pin':pinned_compiler()}
    if warning:out['compiler_warning']=warning
    return out

FIX_ID='text-speed'

def registry_code_patches(fixes=None,hc_report=None):
    """The other fixes' [[code]] regions as code-patch dicts {id,file,offset,expect,value,enabled}.

    fixes: the build's selection (default: every enabled fix in work/patches). value: the
    bytes the armips stage wrote (hc_report["code_regions"] "new"), or None when no
    report is given. A fix that touches overlay 50 or 92 in any way (code, strings,
    growth, graphics) fails closed: text speed pins those overlays whole and rewrites them.
    """
    import fixes as fixreg
    if fixes is None:fixes=[f for f in fixreg.load_all() if f.get('enabled')]
    new={r['id']:r['new'] for r in (hc_report or {}).get('code_regions',[])}
    out=[]
    for fx in fixes:
        if fx['id']==FIX_ID:continue
        for row in fixreg.footprint(fx):
            if row[0]=='itcm':
                raise ValueError(f'Fix {fx["id"]} ({row[3]}) touches the ITCM block, which text speed pins and extends; review both together')
            if row[0] in (f'overlay{OVERLAY}',f'overlay{CALL_OVERLAY}'):
                raise ValueError(f'Fix {fx["id"]} ({row[3]}) touches {row[0]}, which text speed rewrites; review both together')
    for fx in fixreg.code_entries_fixes(fixes):
        if fx['id']==FIX_ID:continue
        for e in fx.get('code',[]):
            if 'expect' not in e:
                raise ValueError(f'Code region {e["id"]} of fix {fx["id"]} has no expect halfwords; text speed cannot normalise it')
            out.append({'id':e['id'],'file':e['file'],'offset':e['offset'],'expect':e['expect'],
                        'value':new.get(e['id']),'enabled':True,'fix':fx['id']})
    return out

def code_patch_ranges(code_patches=None):
    """Enabled code regions of the other fixes as (id,file,offset,expect bytes,value bytes or None).

    code_patches: dicts as registry_code_patches() returns them (default: the
    enabled fixes, without values). Sizes and formats use fixes.py's halfword
    parser. A region on the Options or Pokégear overlay fails closed: text speed
    pins those overlays' hashes and rewrites them.
    """
    import re,fixes as fixreg
    patches=registry_code_patches() if code_patches is None else code_patches
    out=[]
    for cp in patches:
        if type(cp) is not dict:raise ValueError(f'Invalid code patch entry {cp!r}')
        if not cp.get('enabled'):continue
        name=cp.get('id')
        try:
            key=cp['file'];off=fixreg._int(cp['offset'])
            want=fixreg.halfwords(cp['expect'])
            new=None if cp.get('value') is None else fixreg.halfwords(cp['value'])
        except (KeyError,TypeError,ValueError) as error:raise ValueError(f'Invalid code patch {name!r}') from error
        if not want or (new is not None and len(want)!=len(new)) or off<0 or any(not 0<=u<=0xffff for u in want+(new or [])):
            raise ValueError(f'Invalid code patch {name!r}')
        mo=re.fullmatch(r'overlay(\d+)',str(key))
        if mo and int(mo.group(1)) in (OVERLAY,CALL_OVERLAY):
            raise ValueError(f'Code patch {name} targets overlay {int(mo.group(1))}, which text speed rewrites; review both together')
        out.append((name,key,off,struct.pack(f'<{len(want)}H',*want),
                    None if new is None else struct.pack(f'<{len(new)}H',*new)))
    return out

def arm9_code_patches(rom_arm9,main,code_patches=None):
    """Check every enabled arm9 code patch against the ROM; return them for normalising.

    Offsets index the uncompressed ARM9 file, whose start is the main section. Each
    patch must lie inside the main section (ITCM/DTCM are pinned and extended by
    text speed) and currently hold exactly its 'value' or its 'expect' bytes (a
    region given without its value, i.e. without the armips report, may hold any
    bytes: normalising it to 'expect' and the base digest still pin the result).
    """
    patches=[cp for cp in code_patch_ranges(code_patches) if cp[1]=='arm9']
    if patches and bytes(rom_arm9[:len(main)])!=bytes(main):
        raise ValueError('ARM9 file does not start with its uncompressed main section')
    for name,_,off,want,new in patches:
        if off+len(want)>len(main):raise ValueError(f'Code patch {name} lies outside the ARM9 main section')
        cur=bytes(main[off:off+len(want)])
        if cur!=want and new is not None and cur!=new:raise ValueError(f'Code patch {name}: ARM9+{off:#x} is neither its expect nor its value bytes')
    return patches

def overlapping(patches,ranges):
    """Code patches whose bytes overlap any [start,end) ARM9 offset range."""
    return sorted({name for name,_,off,want,_ in patches for lo,hi in ranges if off<hi and lo<off+len(want)})

def own_arm9_ranges(fixes=None):
    """[start,end) ARM9 offsets of text speed's own arm9 [[code]] regions (work/patches/text-speed/fix.toml)."""
    import fixes as fixreg
    pool=fixreg.load_all() if fixes is None else fixes
    fx=[f for f in pool if f['id']==FIX_ID]
    if len(fx)!=1:raise ValueError(f'Fix {FIX_ID} not found in the registry')
    return [(r[1],r[2]) for r in fixreg.footprint(fx[0]) if r[0]=='arm9']

def precheck(rom,fixes=None,code_patches=None):
    """Before the armips stage assembles text-speed.asm: the inputs are the reviewed ones.

    The payload is the reviewed one (schema, source digest, pin). The hack's main
    ARM9 section, with the other fixes' arm9 regions put back to their 'expect'
    bytes, is the reviewed base; the ITCM section, the Options overlay 50 and the
    Pokégear overlay 92 are the reviewed images. No other selected fix touches a
    byte text speed edits, overlays 50/92, or the original routines and data it
    depends on (DEPENDENCIES). Raises ValueError; changes nothing.
    fixes: the build's selection (default: every enabled fix); code_patches: the other
    fixes' regions as registry_code_patches() gives them (default: from fixes).
    """
    load_payload()  # validates payload.json (raises ValueError)
    code=rom.loadArm9();current=bytes(code.sections[0].data)
    source=registry_code_patches(fixes) if code_patches is None else code_patches
    # The demand-loading heap fix (msgload-all) is assembled in the same armips stage: it must be selected,
    # and its region must cover HEAP_FIX with that value (or an unknown value, before the stage has run).
    heap=[c for c in code_patch_ranges(source) if c[1]=='arm9' and c[2]<=HEAP_FIX[0]<c[2]+len(c[3])]
    if not heap or any(c[4] is not None and struct.unpack_from('<H',c[4],HEAP_FIX[0]-c[2])[0]!=HEAP_FIX[1] for c in heap):
        raise ValueError('Text speed requires the demand-loading heap fix (fix msgload, region msgload-all)')
    cps=arm9_code_patches(rom.arm9,current,source)
    a=bytearray(current)
    for _,_,off,want,_ in cps:a[off:off+len(want)]=want
    if digest(a)!=REVIEWED_BASE_ARM9_SHA256:raise ValueError('Unreviewed ARM9 image')
    itcm=code.sections[1]
    if itcm.ramAddress!=0x01ff8000 or len(itcm.data)!=0x620 or itcm.bssSize:raise ValueError('ITCM layout changed')
    if digest(itcm.data)!=REVIEWED_ITCM_SHA256:raise ValueError('Unreviewed ITCM image')
    ovs=rom.loadArm9Overlays();ov=ovs[OVERLAY]
    if digest(ov.data)!=OVHASH or ov.bssSize or ov.ramAddress!=OVBASE:raise ValueError('Options overlay changed')
    gear=ovs[CALL_OVERLAY]
    if (digest(gear.data)!=CALL_OVHASH or gear.bssSize or gear.ramAddress!=CALL_OVBASE
            or gear.ramSize!=CALL_OVSIZE or len(gear.data)!=CALL_OVSIZE or gear.compressed):
        raise ValueError('Pokégear overlay changed')
    clash=overlapping(cps,own_arm9_ranges(fixes))
    if clash:raise ValueError('Code patches overlap text-speed ARM9 edits: '+', '.join(clash))
    clash=overlapping(cps,dependency_ranges(len(a)))
    if clash:raise ValueError('Code patches overlap original ARM9 code text speed depends on: '+', '.join(clash))
    return {'normalised_to_expect':[c[0] for c in cps]}

def receipt(rom,code_patches=None):
    """After the armips stage wrote text-speed.asm: the hashes verify() checks, and which arm9 regions of
    the other fixes hold the bytes the armips stage wrote (code_patches with values, as
    registry_code_patches(fixes, hc_report) gives them)."""
    payload=load_payload();blob=bytes.fromhex(payload['code']);end=(BASE+len(blob)+31)&~31
    main=bytes(rom.loadArm9().sections[0].data)
    if struct.unpack_from('<H',main,HEAP_FIX[0])[0]!=HEAP_FIX[1]:raise ValueError('Text speed requires the demand-loading heap fix')
    cps=[c for c in code_patch_ranges(code_patches) if c[1]=='arm9']
    ovs=rom.loadArm9Overlays()
    return {'itcm_start':hex(BASE),'itcm_end':hex(end),'payload_code_sha256':digest(blob),
            'overlay_sha256':digest(ovs[OVERLAY].data),'call_overlay_sha256':digest(ovs[CALL_OVERLAY].data),
            'arm9_sha256':digest(rom.arm9),'source_code_sha256':source_digest(),'labels':3,
            'arm9_code_patches':{'normalised_to_expect':[c[0] for c in cps],
                                 'held_value':[c[0] for c in cps if c[4] is not None and main[c[2]:c[2]+len(c[4])]==c[4]]}}

def verify(rom,report,code_patches=None):
    payload=load_payload()
    if report['source_code_sha256']!=source_digest():raise ValueError('Patch source changed')
    if digest(rom.arm9)!=report['arm9_sha256']:raise ValueError('Patched ARM9 changed')
    ov=rom.loadArm9Overlays()[50]
    if digest(ov.data)!=report['overlay_sha256']:raise ValueError('Patched Options overlay changed')
    if ov.ramAddress!=OVBASE or ov.ramSize!=len(ov.data) or ov.bssSize:
        raise ValueError('Patched Options overlay layout changed')
    # Pokégear: the receipt hash, and independently the call redirect itself, with
    # every other byte of the overlay still the reviewed original.
    gear=rom.loadArm9Overlays()[CALL_OVERLAY];g=bytes(gear.data)
    if digest(g)!=report.get('call_overlay_sha256'):raise ValueError('Patched Pokégear overlay changed')
    if (gear.ramAddress!=CALL_OVBASE or gear.ramSize!=CALL_OVSIZE or len(g)!=CALL_OVSIZE
            or gear.bssSize or gear.compressed):
        raise ValueError('Patched Pokégear overlay layout changed')
    site=CALL_SITE-CALL_OVBASE
    if g[site:site+4]!=bl(CALL_SITE,payload['symbols']['call_print']):
        raise ValueError(f'Native runtime contract changed at {CALL_SITE:08x}: phone-call printer not redirected')
    if digest(g[:site]+bl(CALL_SITE,ADD_PRINTER)+g[site+4:])!=CALL_OVHASH:
        raise ValueError('Pokégear overlay differs from the reviewed original outside the call redirect')
    sections=rom.loadArm9().sections
    blob=bytes.fromhex(payload['code'])
    if digest(bytes(sections[1].data[:0x620]))!=REVIEWED_ITCM_SHA256:raise ValueError('Original ITCM section changed')
    if bytes(sections[1].data[0x620:0x620+len(blob)])!=blob:raise ValueError('Native payload changed')
    if struct.unpack_from('<H',sections[0].data,HEAP_FIX[0])[0]!=HEAP_FIX[1]:raise ValueError('Heap fix missing')
    # Verify release-critical behaviour independently of the recorded output hashes.
    # This catches future build composition mistakes even if a fresh receipt was
    # recorded after a hook, allocation or default was accidentally overwritten.
    end=(BASE+len(blob)+31)&~31
    if (sections[0].ramAddress!=0x02000000 or sections[1].ramAddress!=0x01ff8000
            or sections[1].bssSize or len(sections[1].data)!=end-0x01ff8000):
        raise ValueError('Native runtime section layout changed')
    critical={
        0x020d1a28:struct.pack('<I',end),
        0x02020a18:struct.pack('<I',payload['symbols']['print_task']),
        FRAME_END_CALL[0]:bl(FRAME_END_CALL[0],payload['symbols']['pass_end']),
        0x0202b176:struct.pack('<HH',0x2004,0x4301),
        0x0202b1c6:struct.pack('<HH',0x0780,0x0f80),
        0x0202b1d2:struct.pack('<H',0x2203),
        0x0202b1da:struct.pack('<H',0x2103),
    }
    # Same rule as apply(): no current code patch may own a critical byte or a
    # reviewed dependency.
    clash=overlapping([cp for cp in code_patch_ranges(code_patches) if cp[1]=='arm9'],
                      [(addr-ARM9BASE,addr-ARM9BASE+len(want)) for addr,want in critical.items()]
                      +dependency_ranges(len(sections[0].data)))
    if clash:raise ValueError('Code patches overlap the native runtime contract: '+', '.join(clash))
    for addr,want in critical.items():
        off=addr-0x02000000
        if bytes(sections[0].data[off:off+len(want)])!=want:
            raise ValueError(f'Native runtime contract changed at {addr:08x}')
    return {'status':'passed','native_bytes':len(blob),'options_rows':7,'phone_call_wait':True,'new_game_default':'FAST','legacy_save_default':'NORMAL','speeds':['NORMAL','FAST']}

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check-payload',action='store_true',help='Required RC gate: reproduce the reviewed payload with clang')
    ap.add_argument('--compile',type=Path,metavar='OUT.json',
                    help='Compile native.c into a candidate payload (under work/build) and print its symbols as '
                         'text-speed.asm .definelabel lines; review it, then replace payload.json, the pin and the labels')
    args=ap.parse_args()
    if args.check_payload==bool(args.compile):ap.error('give --check-payload or --compile')
    if args.check_payload:print(json.dumps(verify_reproducible_payload()));raise SystemExit(0)
    if not args.compile.resolve().is_relative_to((WORK/'build').resolve()):ap.error('Output must be in this worktree work/build')
    args.compile.parent.mkdir(parents=True,exist_ok=True)
    have,pin=clang_version(),pinned_compiler()
    print(f'compiler: {have}')
    if have!=pin:print(f'note: the pin is "{pin}"; if this payload is reviewed and adopted, set fix.toml [native] '
                       f'compiler = "{have}" with it')
    payload=compile_payload(args.compile.parent/'native.o',enforce=False);args.compile.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print(f'payload digest {payload_digest(payload)}, {len(payload["code"])//2} bytes')
    for name,address in sorted(payload['symbols'].items(),key=lambda kv:kv[1]):
        print(f'.definelabel {name+",":18s} 0x{address&~1:08X}')
