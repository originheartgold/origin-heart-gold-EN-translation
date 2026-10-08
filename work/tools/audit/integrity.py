import collections, json
import core, index, sdis as dis, dump as DU
o=index.load(); Z=core.zones(); EV=o['ev']; A=dis.all_files(); r=core.raw()
STD=core.std_mapping()
out=collections.defaultdict(list)
def std_ok(sid):
    for lo,sb,mb in STD:
        if sid>=lo:
            n=len(A[sb]['entries']) if A.get(sb,{}).get('kind')=='script' else 0
            return sid-lo < n, (sb,sid-lo,n)
    return None, None
def check_script_id(z,sid,what):
    if sid==0: return
    if sid>=2000:
        ok,info=std_ok(sid)
        if ok is False: out['bad_std_ref'].append((z['zone_id'],z['map_name_en'],what,sid,info))
        return
    f=z['scripts_bank']; n=len(A[f]['entries']) if A[f]['kind']=='script' else 0
    if sid>n: out['bad_local_ref'].append((z['zone_id'],z['map_name_en'],what,sid,n,f))
for z in Z:
    e=EV[z['events_bank']]
    for i,ob in enumerate(e['obj']):
        if ob['type']==0: check_script_id(z,ob['script'],'obj%d'%i)
    for i,b in enumerate(e['bg']): check_script_id(z,b['script'],'bg%d'%i)
    for i,c in enumerate(e['coord']): check_script_id(z,c['script'],'coord%d'%i)
    for i,w in enumerate(e['warp']):
        if w['dest']>=len(Z): out['bad_warp_dest'].append((z['zone_id'],i,w)); continue
        dz=Z[w['dest']]; n=len(EV[dz['events_bank']]['warp'])
        if w['anchor']!=0xFFFF and w['anchor']>=n: out['bad_warp_anchor'].append((z['zone_id'],z['map_name_en'],i,w,dz['zone_id'],dz['map_name_en'],n))
    lv=o['lv'].get(z['script_header_bank'],[])
    for t,v in lv:
        if t==1:
            for (a,b,s) in v: check_script_id(z,s,'scene')
        else: check_script_id(z,v,'level%d'%t)
# message ids beyond bank
for f,d in A.items():
    if d['kind']!='script': continue
    b=DU.msgbank_of(f)
    if b is None: continue
    n=len(DU.bank(b))
    for pc,(op,a,nx,t) in d['ins'].items():
        if op in (44,45,46,47) and a[0]<0x4000 and a[0]>=n: out['bad_msg'].append((f,pc,dis.NAME[op],a[0],b,n))
        if op in (751,66) and a[0]<0x4000 and a[0]>=n and a[0]!=255: out['bad_menu_msg'].append((f,pc,dis.NAME[op],a[0],b,n))
        if op==176 and a[0]<0x4000 and a[0]>=len(Z): out['bad_script_warp'].append((f,pc,a))
        if op==20:
            ok,info=std_ok(a[0])
            if ok is False: out['bad_callstd'].append((f,pc,a[0],info))
json.dump(out,open(core.D+'/integrity.json','w'),indent=0,default=str)
for k,v in out.items():
    print(k,len(v))
    for x in v[:30]: print('  ',x)
