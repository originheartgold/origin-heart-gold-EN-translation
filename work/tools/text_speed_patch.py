"""Guarded native text speed and Options integration for the reviewed JP hack.

Native payload is original project code, not extracted ROM data. All writes are
prepared on a private ROM object; this module never writes a source ROM file.
"""
from pathlib import Path
import hashlib,json,struct,subprocess,tempfile

WORK=Path(__file__).resolve().parents[1]
ASSETS=WORK/'patches/text_speed'
BASE=0x01ff8620
OVBASE=0x021e4980
# This reviewed pin lives in patcher source, never in the mutable cache. Updating
# native code requires review of its reproducible payload and this separate pin.
REVIEWED_PAYLOAD_SHA256='6a5acbbf84b4e7608b0f3202f0b03d7b002d65865d012bcf311b4291f9b34ab7'
REQUIRED_SYMBOLS=frozenset(('print_task','load_rows','load_choice','load_label',
                            'commit_speed','exit_free','draw_label','setup_sprites','init_printer'))
MAX_PAYLOAD_SIZE=0x01ffa000-BASE
OVHASH='852d8fcd01bf09ba54bee1a24609e2a82e71d25b5d6dd84c5d919cc0b3418856'
OVERLAY=50
ARM9BASE=0x02000000
# Main ARM9 section of the untouched Chinese hack (origin_v4.0.3_cn.nds). apply()
# compares it after every enabled arm9 code patch from hardcoded/code_patches.json
# is put back to its 'expect' bytes, so new reviewed code patches elsewhere in ARM9
# do not invalidate this pin; patches touching text-speed bytes still fail closed.
REVIEWED_BASE_ARM9_SHA256='b3249c2996c204695a2528e2e52bf0d9841ec05263a6bcecfc7db181204f96cf'
REVIEWED_ITCM_SHA256='838df87fbcf4107eb85d4c97d9fab741fd0a99d24a4dc85577e3bc8c3eded3c1'
# Text speed depends on this enabled code patch (msgload-all, demand-loading heap fix).
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
    (0x02020be8,0x02020bee,'printer initializer'),
    (0x02024e48,0x02024e64,'sprite visibility'),
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
    (0x02002e40,0x02002e70,'RenderText entry called by the glyph loop'),
    (0x020022d0,0x020027ee,'RenderText control-code state machine (two reviewed jump tables)'),
    (0x020208d4,0x02020a1c,'printer constructor (alloc size, initializer call, task pointer)'),
    (0x0202b168,0x0202b1b4,'Options init (new-game default)'),
    (0x0202b1c4,0x0202b1d0,'music speed getter'),
    (0x0202b1d0,0x0202b1e4,'music speed setter'),
    (0x020d1a1c,0x020d1a38,'SDK arena bounds table (ITCM arena start)'),
    (0x02000ba0,0x02000bb8,'code settings / autoload list words rewritten by code.save()'),
)
DEPENDENCIES=CALLED_ROUTINES+DEPENDENT_CODE

def native_call_targets():
    """Every FN(address, ...) call target in native.c (source pinned via the payload)."""
    import re
    return sorted({int(x,16) for x in re.findall(r'FN\((0x[0-9a-fA-F]+)\s*,',(ASSETS/'native.c').read_text())})

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

def compile_payload(out):
    """Compile the self-contained C section; refuse unresolved text relocations."""
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(['clang','-target','arm-none-eabi','-march=armv5te','-mthumb','-Os','-Wall','-Werror','-ffreestanding','-fno-builtin','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-c',str(ASSETS/'native.c'),'-o',str(out)],check=True)
    b=out.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',b)
    if h[0][:7]!=b'\x7fELF\x01\x01\x01' or h[2]!=40:raise ValueError('Not ARM ELF32')
    sections=[struct.unpack_from('<10I',b,h[6]+i*h[11]) for i in range(h[12])]
    def data(s):return b[s[4]:s[4]+s[5]]
    names=data(sections[h[13]])
    def name(off,tab=names):return tab[off:].split(b'\0',1)[0].decode()
    placed={};image=bytearray()
    for i,s in enumerate(sections):
        if not s[2]&2 or name(s[0]).startswith('.ARM.exidx'):continue
        if s[1] not in (1,8):raise ValueError('Unexpected allocated section')
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
            if kind!=2:raise ValueError(f'Unsupported native relocation {kind}')
            address=tables[s[6]][info>>8]
            if address is None:raise ValueError('Undefined native symbol')
            pos=placed[s[7]]+target
            addend=struct.unpack_from('<I',image,pos)[0]
            struct.pack_into('<I',image,pos,(addend+address)&0xffffffff)
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
    for name,address in symbols.items():
        if type(address) is not int or not address&1 or not BASE<address<BASE+len(blob):
            raise ValueError(f'Invalid native Thumb entry point: {name}')
    if len(set(symbols.values()))!=len(symbols):raise ValueError('Native entry points overlap')
    if payload_digest(payload)!=REVIEWED_PAYLOAD_SHA256:
        raise ValueError('Native payload differs from the independently reviewed digest')
    return payload

def load_payload():
    return validate_payload(json.loads((ASSETS/'payload.json').read_text()))

def verify_reproducible_payload():
    """Mandatory RC gate; compilation failure/missing clang is never a skip.

    Normal cached builds do not need a compiler. Release validation requires the
    reviewed compiler output to match both cached bytes and every symbol exactly.
    """
    payload=load_payload()
    with tempfile.TemporaryDirectory(prefix='text-speed-reproduce-') as directory:
        rebuilt=compile_payload(Path(directory)/'native.o')
    if rebuilt!=payload:raise ValueError('Native payload does not reproduce from current source')
    return {'status':'passed','payload_sha256':payload_digest(payload),'native_bytes':len(bytes.fromhex(payload['code']))}

def code_patch_ranges(code_patches=None):
    """Enabled hardcoded code patches as (id,file,offset,expect bytes,value bytes).

    Uses hardcoded.py's own loader and halfword parser, so sizes and formats match
    what the build applied. A patch on the Options overlay fails closed: text speed
    pins that overlay's hash and rewrites it.
    """
    import re,hardcoded
    patches=hardcoded.load_code_patches() if code_patches is None else code_patches
    out=[]
    for cp in patches:
        if type(cp) is not dict:raise ValueError(f'Invalid code patch entry {cp!r}')
        if not cp.get('enabled'):continue
        name=cp.get('id')
        try:
            key=cp['file'];off=hardcoded._int(cp['offset'])
            want=hardcoded.halfwords(cp['expect']);new=hardcoded.halfwords(cp['value'])
        except (KeyError,TypeError,ValueError) as error:raise ValueError(f'Invalid code patch {name!r}') from error
        if not want or len(want)!=len(new) or off<0 or any(not 0<=u<=0xffff for u in want+new):
            raise ValueError(f'Invalid code patch {name!r}')
        mo=re.fullmatch(r'overlay(\d+)',str(key))
        if mo and int(mo.group(1))==OVERLAY:
            raise ValueError(f'Code patch {name} targets overlay {OVERLAY}, which text speed rewrites; review both together')
        out.append((name,key,off,struct.pack(f'<{len(want)}H',*want),struct.pack(f'<{len(new)}H',*new)))
    return out

def arm9_code_patches(rom_arm9,main,code_patches=None):
    """Check every enabled arm9 code patch against the ROM; return them for normalising.

    Offsets index the uncompressed ARM9 file, whose start is the main section. Each
    patch must lie inside the main section (ITCM/DTCM are pinned and extended by
    text speed) and currently hold exactly its 'value' or its 'expect' bytes.
    """
    patches=[cp for cp in code_patch_ranges(code_patches) if cp[1]=='arm9']
    if patches and bytes(rom_arm9[:len(main)])!=bytes(main):
        raise ValueError('ARM9 file does not start with its uncompressed main section')
    for name,_,off,want,new in patches:
        if off+len(want)>len(main):raise ValueError(f'Code patch {name} lies outside the ARM9 main section')
        cur=bytes(main[off:off+len(want)])
        if cur not in (want,new):raise ValueError(f'Code patch {name}: ARM9+{off:#x} is neither its expect nor its value bytes')
    return patches

def overlapping(patches,ranges):
    """Code patches whose bytes overlap any [start,end) ARM9 offset range."""
    return sorted({name for name,_,off,want,_ in patches for lo,hi in ranges if off<hi and lo<off+len(want)})

def apply(rom,payload=None,code_patches=None):
    payload=load_payload() if payload is None else validate_payload(payload)
    import msgtool as m
    if payload['source_sha256']!=source_digest():raise ValueError('Stale native payload')
    code=rom.loadArm9();current=bytes(code.sections[0].data)
    # Verify the hack's reviewed base ARM9 main section, independent of our reviewed code patches:
    # put each enabled arm9 code patch back to its 'expect' bytes, then hash. The
    # text-speed edits below are made on this base and checked against it.
    cps=arm9_code_patches(rom.arm9,current,code_patches)
    a=bytearray(current)
    for _,_,off,want,_ in cps:a[off:off+len(want)]=want
    if digest(a)!=REVIEWED_BASE_ARM9_SHA256:raise ValueError('Unreviewed ARM9 image')
    if digest(code.sections[1].data)!=REVIEWED_ITCM_SHA256:
        raise ValueError('Unreviewed ITCM image')
    if struct.unpack_from('<H',current,HEAP_FIX[0])[0]!=HEAP_FIX[1]:raise ValueError('Text speed requires the demand-loading heap fix')
    arm9_ranges=[]
    ov=rom.loadArm9Overlays()[50];original=bytes(ov.data)
    if digest(original)!=OVHASH or ov.bssSize or ov.ramAddress!=OVBASE:raise ValueError('Options overlay changed')
    o=bytearray(original);edits=[]
    def patch(buf,base,addr,old,new):
        off=addr-base
        if bytes(buf[off:off+len(old)])!=old:raise ValueError(f'Unexpected code at {addr:08x}')
        if len(old)!=len(new):raise ValueError('In-place size changed')
        buf[off:off+len(old)]=new;edits.append({'address':hex(addr),'before':old.hex(),'after':new.hex()})
        if buf is a:arm9_ranges.append((off,off+len(old)))
    def hw(addr,old,new):patch(o,OVBASE,addr,struct.pack('<H',old),struct.pack('<H',new))
    def call(addr,old_target,name):patch(o,OVBASE,addr,bl(addr,old_target),bl(addr,payload['symbols'][name]))
    def append(blob):
        while len(o)%4:o.append(0)
        ptr=OVBASE+len(o);o.extend(blob);return ptr
    def redirect(old,new):
        found=[]
        for off in range(0,len(original)-3,4):
            if struct.unpack_from('<I',original,off)[0]==old:
                patch(o,OVBASE,OVBASE+off,struct.pack('<I',old),struct.pack('<I',new));found.append(off)
        if not found:raise ValueError(f'No pointer to {old:x}')
    # Reserve original-code extension in ITCM, using the SDK arena boundary.
    itcm=code.sections[1]
    if itcm.ramAddress!=0x01ff8000 or len(itcm.data)!=0x620 or itcm.bssSize:raise ValueError('ITCM layout changed')
    blob=bytes.fromhex(payload['code']);end=(BASE+len(blob)+31)&~31
    if end>0x01ffa000:raise ValueError('Native code exceeds reserved budget')
    patch(a,0x2000000,0x20d1a28,struct.pack('<I',BASE),struct.pack('<I',end))
    patch(a,0x2000000,0x2020a18,struct.pack('<I',0x2020a1d),struct.pack('<I',payload['symbols']['print_task']))
    # Allocate/initialize private fractional-speed state; never reuse game-owned fields.
    patch(a,0x2000000,0x20208ea,struct.pack('<H',0x2134),struct.pack('<H',0x2138))
    patch(a,0x2000000,0x2020962,bl(0x2020962,0x2020be8),bl(0x2020962,payload['symbols']['init_printer']))
    # Options_Init already cleared both bytes. Set MEDIUM (bits2..3=1), music remains0.
    patch(a,0x2000000,0x202b176,struct.pack('<HH',0x200f,0x4381),struct.pack('<HH',0x2004,0x4301))
    # Music accesses mask only low two bits; its setter preserves the new bits.
    for addr,old,new in [(0x202b1c6,0x0700,0x0780),(0x202b1c8,0x0f00,0x0f80),(0x202b1d2,0x220f,0x2203),(0x202b1da,0x210f,0x2103)]:
        patch(a,0x2000000,addr,struct.pack('<H',old),struct.pack('<H',new))
    # Expand seven records to eight, shifting only the following metadata.
    # Original overlay SHA is mandatory before decoding these fixed instructions.
    moved=[]
    for off in range(0,0x121c,2):
        ins,nxt=struct.unpack_from('<HH',original,off)
        if ins&0xf800==0x2000 and nxt&0xf800==0 and (nxt>>3)&7==(ins>>8)&7:
            value=(ins&255)<<((nxt>>6)&31)
            if 0x2d0<=value<=0x324:
                new=value+0x54
                if new%4 or new//4>255:raise ValueError('Metadata offset cannot be encoded')
                hw(OVBASE+off,ins,(ins&0xff00)|(new//4))
                hw(OVBASE+off+2,nxt,(nxt&63)|(2<<6));moved.append(OVBASE+off)
    if len(moved)!=32:raise ValueError('Metadata relocation inventory changed')
    for addr in [0x21e57e6,0x21e5854,0x21e58f8]:
        hw(addr,0x2032,0x20dd);hw(addr+4,0x0100,0x0080)
    for addr,shift_addr,oldimm,oldshift,newimm,newshift in [
        (0x21e5aa6,0x21e5aaa,0x212d,0x0109,0x21c9,0x0089),
        (0x21e5ac0,0x21e5ac4,0x20b5,0x0080,0x20ca,0x0080),
        (0x21e5ad8,0x21e5adc,0x202d,0x0100,0x20c9,0x0080),
        (0x21e5ada,0x21e5ade,0x21b5,0x0089,0x21ca,0x0089),
        (0x21e5b56,0x21e5b5c,0x20b6,0x0080,0x20cb,0x0080)]:
        hw(addr,oldimm,newimm);hw(shift_addr,oldshift,newshift)
    for addr in [0x21e4994,0x21e49a0]:
        old=struct.unpack_from('<H',original,addr-OVBASE)[0];hw(addr,old,(old&0xff00)|0xde)
    for addr,old,new in [
        (0x21e4e24,0x2f06,0x2f07),(0x21e528e,0x2c06,0x2c07),
        (0x21e52fa,0x2c07,0x2c08),(0x21e538c,0x2806,0x2807),
        (0x21e55a0,0x2906,0x2907),(0x21e56c8,0x2906,0x2907),
        (0x21e5746,0x2906,0x2907),(0x21e594a,0x2c06,0x2c07),
        (0x21e59dc,0x2806,0x2807),(0x21e5658,0x2107,0x2108),
        (0x21e565e,0x1d80,0x1dc0),(0x21e568e,0x2107,0x2108),
        (0x21e5268,0x2018,0x2014),(0x21e53f6,0x2018,0x2014)]:hw(addr,old,new)
    patch(o,OVBASE,0x21e53e8,struct.pack('<I',0x27e),struct.pack('<I',0x2d2))
    redirect(0x21e5c14,append(struct.pack('<8I',3,2,2,2,3,20,3,2)))
    redirect(0x21e5bf8,append(struct.pack('<8i',-8,-28,-48,-68,-88,-108,-128,-156)))
    boxes=[list(v) for v in struct.iter_unpack('<4B',original[0x1334:0x1378])][:-1]
    mapping=[list(v) for v in struct.iter_unpack('<II',original[0x1378:0x13f8])]
    for box,(row,choice) in zip(boxes,mapping):
        if row<6:box[0]-=row*4;box[1]-=row*4
    mapping[14][0]=mapping[15][0]=7
    boxes.extend([[146,166,108,154],[146,166,156,202],[146,166,204,252],[255,0,0,0]])
    mapping.extend([[6,0],[6,1],[6,2]])
    redirect(0x21e5cb4,append(b''.join(struct.pack('<4B',*v) for v in boxes)))
    mapping_ptr=append(b''.join(struct.pack('<II',*v) for v in mapping))
    redirect(0x21e5cf8,mapping_ptr)
    redirect(0x21e5cfc,mapping_ptr+4)
    # Reuse the existing button graphics; move their Y coordinates only.
    for i in range(7):
        off=0x1484+i*40+6
        y=struct.unpack_from('<H',original,off)[0]
        new=24+20*i if i<5 else 124
        patch(o,OVBASE,OVBASE+off,struct.pack('<H',y),struct.pack('<H',new))
    # Opaque inherited palette background keeps seven compact rows legible.
    hw(0x21e512e,0x2100,0x2122)
    hw(0x21e540e,0x2100,0x2122)
    patch(o,OVBASE,0x21e5534,struct.pack('<I',0x00010200),struct.pack('<I',0x00030200))
    patch(o,OVBASE,0x21e553c,struct.pack('<I',0x000f0200),struct.pack('<I',0x00010200))
    patch(o,OVBASE,0x21e5bae,b'\x00',b'\xfd')
    call(0x21e5284,0x2020834,'draw_label')
    matches=[off for off in range(0,0x121c,2) if original[off:off+4]==bl(OVBASE+off,0x21e5acc)]
    if len(matches)!=1:raise ValueError('Sprite setup callers changed')
    call(OVBASE+matches[0],0x21e5acc,'setup_sprites')
    call(0x21e5366,0x200bb40,'load_choice')
    call(0x21e5264,0x200bb0c,'load_label')
    # Locate the single setup call to the original row loader.
    matches=[off for off in range(0,0x121c,2) if original[off:off+4]==bl(OVBASE+off,0x21e5334)]
    if len(matches)!=1:raise ValueError('Row loader callers changed')
    call(OVBASE+matches[0],0x21e5334,'load_rows')
    call(0x21e4b5a,0x20071b0,'exit_free')
    # No code patch may touch a byte text speed edits, nor the reviewed routines and
    # data it calls or depends on (DEPENDENCIES). The heap-fix halfword is the one
    # intended dependency on a code patch; it is only read, and must already hold
    # that patch's value (checked above). Other ARM9 bytes are covered only by the
    # base digest, which code patches elsewhere are normalised out of.
    clash=overlapping(cps,arm9_ranges)
    if clash:raise ValueError('Code patches overlap text-speed ARM9 edits: '+', '.join(clash))
    clash=overlapping(cps,dependency_ranges(len(a)))
    if clash:raise ValueError('Code patches overlap original ARM9 code text speed depends on: '+', '.join(clash))
    # Restore the code patches (none overlaps an edit) on top of the edited base.
    for _,_,off,want,_ in cps:a[off:off+len(want)]=current[off:off+len(want)]
    # Commit only after all guards and preparation succeeded.
    code.sections[0].data=a;itcm.data=bytearray(itcm.data)+blob+bytes(end-BASE-len(blob))
    rom.arm9=code.save(compress=False)
    table=bytearray(rom.arm9OverlayTable)
    for off in range(0,len(table),32):
        if struct.unpack_from('<I',table,off)[0]==50:struct.pack_into('<I',table,off+8,len(o));break
    rom.arm9OverlayTable=bytes(table);rom.files[ov.fileID]=bytes(o)
    return {'itcm_start':hex(BASE),'itcm_end':hex(end),'payload_sha256':digest(blob),'overlay_sha256':digest(o),'arm9_sha256':digest(rom.arm9),'source_code_sha256':source_digest(),'edits':edits,'labels':4,
            'arm9_code_patches':{'normalised_to_expect':[c[0] for c in cps],
                                 'held_value':[c[0] for c in cps if bytes(current[c[2]:c[2]+len(c[4])])==c[4]]}}

def verify(rom,report,code_patches=None):
    payload=load_payload()
    if report['source_code_sha256']!=source_digest():raise ValueError('Patch source changed')
    if digest(rom.arm9)!=report['arm9_sha256']:raise ValueError('Patched ARM9 changed')
    ov=rom.loadArm9Overlays()[50]
    if digest(ov.data)!=report['overlay_sha256']:raise ValueError('Patched Options overlay changed')
    if ov.ramAddress!=OVBASE or ov.ramSize!=len(ov.data) or ov.bssSize:
        raise ValueError('Patched Options overlay layout changed')
    sections=rom.loadArm9().sections
    blob=bytes.fromhex(payload['code'])
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
        0x020208ea:struct.pack('<H',0x2138),
        0x02020962:bl(0x02020962,payload['symbols']['init_printer']),
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
    return {'status':'passed','native_bytes':len(blob),'options_rows':7,'new_game_default':'MEDIUM','legacy_save_default':'SLOW','speeds':['SLOW','MEDIUM','FAST']}

if __name__=='__main__':
    import argparse,ndspy.rom
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check-payload',action='store_true',help='Required RC gate: reproduce the reviewed payload with clang')
    ap.add_argument('--rom',type=Path);ap.add_argument('--out',type=Path);args=ap.parse_args()
    if args.check_payload:
        if args.rom or args.out:ap.error('--check-payload cannot be combined with ROM output')
        print(json.dumps(verify_reproducible_payload()));raise SystemExit(0)
    if not args.rom or not args.out:ap.error('--rom and --out are required unless checking the payload')
    if not args.out.resolve().is_relative_to((WORK/'build').resolve()):ap.error('Output must be in this worktree work/build')
    if args.out.resolve()==args.rom.resolve():ap.error('Refusing source overwrite')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    payload=compile_payload(args.out.parent/'native.o');(args.out.parent/'payload.json').write_text(json.dumps(payload,indent=2))
    rom=ndspy.rom.NintendoDSRom.fromFile(str(args.rom));report=apply(rom,payload);rom.saveToFile(str(args.out))
    report['source_sha256']=digest(args.rom.read_bytes());report['rom_sha256']=digest(args.out.read_bytes());(args.out.parent/'patch-report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='edits'}))
