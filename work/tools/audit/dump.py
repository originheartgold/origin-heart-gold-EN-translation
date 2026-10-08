import json, os, sys
import core, sdis as dis
D=core.D; N=dis.NAME
FL=core.consts('flags.h','FLAG_'); VA=core.consts('vars.h','VAR_')
IT=core.consts('items.h','ITEM_'); SP=core.consts('species.h','SPECIES_')
MP=core.consts('maps.h','MAP_'); STD=core.consts('std_script.h','std_')
_banks={}
def bank(b):
    if b not in _banks:
        p=core.REPO+'/work/translate/banks/a027/%04d.json'%b
        _banks[b]=json.load(open(p))['strings'] if os.path.exists(p) else []
    return _banks[b]
def msgbank_of(f):
    Z=core.zones()
    for z in Z:
        if z['scripts_bank']==f: return z['msg_bank']
    for lo,sb,mb in core.std_mapping():
        if sb==f: return mb
    return None
def txt(b,i,n=70):
    s=bank(b) if b is not None else []
    if i<len(s):
        e=(s[i].get('en') or '').replace('{NEWLINE}',' ').replace('{CLEAR}',' ').replace('{SCROLL}',' ')
        z=(s[i].get('zh') or '').replace('{NEWLINE}','').replace('{CLEAR}','').replace('{SCROLL}','')
        return '«%s» «%s»'%(z[:40],e[:n])
    return ''
def nm(v,tab=None):
    if tab is FL and v in FL: return '%s(0x%X)'%(FL[v],v)
    if v>=0x4000 and v in VA: return VA[v]
    if tab and v in tab: return tab[v]
    return hex(v) if v>=0x4000 else str(v)
ARGTAB={30:[FL],31:[FL],32:[FL],17:[VA],41:[VA],39:[VA],40:[VA],42:[VA,VA],43:[VA],125:[IT],126:[IT],128:[IT],127:[IT],137:[SP],589:[SP],389:[SP],176:[MP],20:[STD]}
def dump(f,out=None):
    A=dis.all_files(); d=A[f]
    b=msgbank_of(f)
    L=['# file %d msgbank %s zones %s'%(f,b,[z['zone_id'] for z in core.zones() if z['scripts_bank']==f])]
    if d['kind']=='level': L.append('LEVEL '+str(d['levels'])); return '\n'.join(L)
    ent={e:i+1 for i,e in enumerate(d['entries'])}
    tg=set(t for (_,_,_,t) in d['ins'].values() if t is not None)
    for pc in sorted(d['ins']):
        if pc in ent: L.append('\n== script %d (@%d)'%(ent[pc],pc))
        elif pc in tg: L.append(' L%d:'%pc)
        op,a,n,t=d['ins'][pc]; s=N[op]
        tabs=ARGTAB.get(op,[])
        args=[nm(x,tabs[j] if j<len(tabs) else None) for j,x in enumerate(a)]
        if op in dis.JUMPS: args[-1]='->L%d'%t
        if op in (28,29): args[0]=dis.COND.get(a[0],a[0])
        extra=''
        if op in (44,45,46,47) : extra=txt(b,a[0])
        if op==440 or op==439: extra='(ext bank %s #%s)'%(a[0],a[1])
        if op in (64,65,68,69) : pass
        if op==66: extra=txt(b,a[0],30)
        if op==751: extra=txt(b,a[0],30)
        L.append('  %5d %s %s %s'%(pc,s,' '.join(args),extra))
    if d['errs']: L.append('ERRS '+str(d['errs']))
    return '\n'.join(L)
if __name__=='__main__':
    os.makedirs(D+'/dump',exist_ok=True)
    A=dis.all_files()
    for f in (sys.argv[1:] and map(int,sys.argv[1:]) or A):
        open(D+'/dump/%04d.txt'%f,'w').write(dump(f))
