"""Load the untouched CN ROM: script files, events, zones, std mapping. Cached."""
import os, pickle, struct, json, re
D=os.path.dirname(os.path.abspath(__file__))
REPO=os.path.abspath(os.path.join(D, '..', '..', '..'))
KEY=os.environ.get('PA2_ROM','cn')
ROM=REPO+('/work/rom/origin_v4.0.3_cn.nds' if KEY=='cn' else '/work/rom/Pokemon - HeartGold Version (USA).nds')
SUF='' if KEY=='cn' else '_'+KEY
PHG=D+'/../phg/include/constants'
def raw():
    c=D+'/raw%s.pkl'%SUF
    if os.path.exists(c): return pickle.load(open(c,'rb'))
    import ndspy.rom, ndspy.narc
    rom=ndspy.rom.NintendoDSRom.fromFile(ROM)
    scr=ndspy.narc.NARC(rom.getFileByName('a/0/1/2')).files
    ev=ndspy.narc.NARC(rom.getFileByName('a/0/3/2')).files
    arm9=rom.arm9
    if KEY!='cn':
        import ndspy.codeCompression as cc; arm9=cc.decompress(arm9)
    out=dict(scr=scr,ev=ev,arm9=arm9)
    pickle.dump(out,open(c,'wb')); return out
def zones():
    if KEY!='cn': return us_zones()
    return json.load(open(REPO+'/work/translate/bank_maps.json'))['_zones']
def us_zones():
    # pret map header: 24 bytes each; parse from US arm9 table
    a=raw()['arm9']; off=US_HDR
    out=[]
    for i in range(540):
        b=a[off+24*i:off+24*i+24]
        v=struct.unpack_from('<BBHHHHHHHH',b,0)
        out.append(dict(zone_id=i,scripts_bank=v[4],script_header_bank=v[5],msg_bank=v[6],events_bank=v[9]))
    return out
US_HDR=1010656
US_MAP=1025188
def std_mapping():
    r=raw(); a=r['arm9']
    # try to decompress check: arm9 may be compressed? assume offset valid in decompressed code
    off=1011936 if KEY=='cn' else US_MAP
    m=[]
    for i in range(30):
        lo,sb,mb=struct.unpack_from('<HHH',a,off+6*i); m.append((lo,sb,mb))
    return m
def parse_events(b):
    p=0
    n=struct.unpack_from('<I',b,p)[0]; p+=4; bgs=[]
    for i in range(n):
        sid,typ,x,z,y,d=struct.unpack_from('<HHiiiH',b,p); p+=20; bgs.append(dict(script=sid,type=typ,x=x,z=z,y=y,dir=d))
    n=struct.unpack_from('<I',b,p)[0]; p+=4; objs=[]
    for i in range(n):
        v=struct.unpack_from('<HHHHHHhHHHhhHHi',b,p); p+=32
        objs.append(dict(id=v[0],sprite=v[1],move=v[2],type=v[3],flag=v[4],script=v[5],face=v[6],param=v[7:10],xr=v[10],yr=v[11],x=v[12],z=v[13],y=v[14]))
    n=struct.unpack_from('<I',b,p)[0]; p+=4; warps=[]
    for i in range(n):
        x,z,h,a,y=struct.unpack_from('<HHHHI',b,p); p+=12; warps.append(dict(x=x,z=z,dest=h,anchor=a,y=y))
    n=struct.unpack_from('<I',b,p)[0]; p+=4; coords=[]
    for i in range(n):
        v=struct.unpack_from('<HhhHHHHH',b,p); p+=16
        coords.append(dict(script=v[0],x=v[1],z=v[2],w=v[3],h=v[4],y=v[5],val=v[6],var=v[7]))
    return dict(bg=bgs,obj=objs,warp=warps,coord=coords)
def parse_levelscripts(b):
    """returns list of (type, value) ; type1 -> list of (var,val,script)"""
    out=[]; p=0
    while p<len(b) and b[p]!=0:
        t=b[p]; v=struct.unpack_from('<I',b,p+1)[0]
        if t==1:
            q=p+5+v; tab=[]
            while q+2<=len(b):
                v1=struct.unpack_from('<H',b,q)[0]
                if v1==0: break
                v2,s=struct.unpack_from('<HH',b,q+2); tab.append((v1,v2,s)); q+=6
            out.append((t,tab))
        else: out.append((t,v&0xFFFF))
        p+=5
    return out
def consts(fname,prefix):
    d={}
    for l in open(PHG+'/'+fname):
        m=re.match(r'#define\s+(%s\w+)\s+(0x[0-9A-Fa-f]+|\d+)\s*(//.*)?$'%prefix,l)
        if m: d.setdefault(int(m.group(2),0),m.group(1))
    return d
