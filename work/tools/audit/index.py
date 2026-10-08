"""Build the flag/var/item/mon/warp index from all scripts + events."""
import pickle, os, collections
import core, sdis as dis
D=core.D
N=dis.NAME
def reach(d):
    """pc -> set of entry numbers (1-based)"""
    ins=d['ins']; owner=collections.defaultdict(set)
    for ei,e in enumerate(d['entries']):
        st=[e]; seen=set()
        while st:
            pc=st.pop()
            if pc in seen or pc not in ins: continue
            seen.add(pc); owner[pc].add(ei+1)
            op,a,n,t=ins[pc]
            if t is not None: st.append(t)
            if not (op in dis.TERM or (op in dis.JUMPS and dis.JUMPS[op])): st.append(n)
    return owner
def const_prop(d):
    """For each pc, known const values of special vars (0x8000-0x800F) and temps set by SetVar in the same linear run."""
    ins=d['ins']; targets=set(t for (_,_,_,t) in ins.values() if t is not None)|set(d['entries'])
    known={}; cur={}; prev_next=None
    for pc in sorted(ins):
        if pc in targets or pc!=prev_next: cur={}
        known[pc]=dict(cur)
        op,a,n,t=ins[pc]
        if op in (41,43):  # SetVar, SetOrCopyVar
            if op==41 or a[1]<0x4000: cur[a[0]]=a[1]
            else: cur.pop(a[0],None)
        elif op in (39,40,42): cur.pop(a[0],None)
        elif op in (22,2,27): cur={}
        prev_next=n
    return known
def val(v,known):
    if v<0x4000: return v
    return known.get(v,('var',v))
def build():
    A=dis.all_files(); Z=core.zones(); r=core.raw()
    file_zones=collections.defaultdict(list)
    for z in Z: file_zones[z['scripts_bank']].append(z['zone_id'])
    stdmap=core.std_mapping()
    rec=[]  # dicts
    for f,d in A.items():
        if d['kind']!='script': continue
        own=reach(d); kn=const_prop(d)
        for pc,(op,a,n,t) in d['ins'].items():
            k=kn[pc]; base=dict(file=f,pc=pc,entries=sorted(own.get(pc,())),op=N[op])
            def add(**kw): x=dict(base); x.update(kw); rec.append(x)
            if op==30: add(kind='flag_set',id=a[0])
            elif op==31: add(kind='flag_clear',id=a[0])
            elif op==32: add(kind='flag_check',id=a[0])
            elif op in (33,34,35):
                v=val(a[0],k); add(kind={33:'flag_set',34:'flag_clear',35:'flag_check'}[op],id=v,viavar=a[0])
            elif op in (36,37,38): add(kind={36:'trflag_set',37:'trflag_clear',38:'trflag_check'}[op],id=val(a[0],k))
            elif op==41: add(kind='var_set',id=a[0],v=a[1])
            elif op==43: add(kind='var_set' if a[1]<0x4000 else 'var_copy',id=a[0],v=a[1])
            elif op==42: add(kind='var_copy',id=a[0],v=a[1])
            elif op==39: add(kind='var_add',id=a[0],v=a[1])
            elif op==40: add(kind='var_sub',id=a[0],v=a[1])
            elif op==17: add(kind='var_cmp',id=a[0],v=a[1])
            elif op==18: add(kind='var_cmpvar',id=a[0],v=a[1])
            elif op==125: add(kind='item_give',id=val(a[0],k),qty=val(a[1],k))
            elif op==126: add(kind='item_take',id=val(a[0],k),qty=val(a[1],k))
            elif op==128: add(kind='item_has',id=val(a[0],k),qty=val(a[1],k))
            elif op==127: add(kind='item_space',id=val(a[0],k))
            elif op==20:
                add(kind='callstd',id=a[0],v8004=k.get(0x8004),v8005=k.get(0x8005),v8008=k.get(0x8008))
            elif op==137: add(kind='mon_give',id=val(a[0],k),lvl=val(a[1],k),item=val(a[2],k))
            elif op==138: add(kind='egg_give',id=val(a[0],k))
            elif op==362: add(kind='loan_give',id=a[2])
            elif op in (389,632,647): add(kind='mon_check',id=val(a[0],k))
            elif op==589: add(kind='wild',id=val(a[0],k),lvl=val(a[1],k))
            elif op==294: add(kind='badge_check',id=val(a[0],k))
            elif op==295: add(kind='badge_give',id=val(a[0],k))
            elif op==296: add(kind='badge_count')
            elif op==176: add(kind='warp',id=val(a[0],k),args=a)
            elif op==240: add(kind='dynwarp',id=a[0],args=a)
            elif op==213: add(kind='trainer',id=val(a[0],k))
            elif op in (100,101,375): add(kind={100:'show',101:'hide',375:'visible'}[op],id=val(a[0],k))
            elif op==131: add(kind='starter_set',id=val(a[0],k))
            elif op==206: add(kind='starter_get',id=a[0])
            elif op==281: add(kind='gender_get',id=a[0])
    ev={}
    for z in Z:
        b=z['events_bank']
        if b not in ev: ev[b]=core.parse_events(r['ev'][b])
    lv={}
    for f,d in A.items():
        if d['kind']=='level': lv[f]=d['levels']
    out=dict(rec=rec,ev=ev,lv=lv,file_zones=dict(file_zones),std=stdmap)
    pickle.dump(out,open(D+'/index%s.pkl'%core.SUF,'wb'))
    return out
def load():
    p=D+'/index%s.pkl'%core.SUF
    return pickle.load(open(p,'rb')) if os.path.exists(p) else build()
if __name__=='__main__':
    o=build(); c=collections.Counter(x['kind'] for x in o['rec']); print(c)
