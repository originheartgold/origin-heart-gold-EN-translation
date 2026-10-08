import collections, json
import core, sdis as dis, dump as DU, index
A=dis.all_files(); Z=core.zones(); o=index.load()
fz=collections.defaultdict(list)
for z in Z: fz[z['scripts_bank']].append(z)
own={f:index.reach(d) for f,d in A.items() if d['kind']=='script'}
res=[]
for f,d in A.items():
    if d['kind']!='script': continue
    zs=fz.get(f)
    if not zs:
        b=DU.msgbank_of(f); zs=[dict(zone_id=None,msg_bank=b,events_bank=None)] if b is not None else []
    for z in zs:
        b=z['msg_bank']; n=len(DU.bank(b))
        if n==0: continue
        # which entries does this zone reference?
        refs=None
        if z.get('events_bank') is not None:
            e=o['ev'][z['events_bank']]; refs=set()
            for ob in e['obj']: refs.add(ob['script'])
            for bg in e['bg']: refs.add(bg['script'])
            for c in e['coord']: refs.add(c['script'])
            for t,v in o['lv'].get(z['script_header_bank'],[]):
                if t==1: refs|=set(s for a,bb,s in v)
                else: refs.add(v)
        for pc,(op,a,nx,t) in d['ins'].items():
            if op in (44,45,46,47) and a[0]<0x4000 and a[0]>=n:
                ents=own[f].get(pc,set())
                live = refs is None or bool(ents & refs)
                res.append((f,z['zone_id'],z.get('map_name_en'),pc,a[0],b,n,sorted(ents),live))
live=[r for r in res if r[-1]]
print('msg id beyond bank:',len(res),'live (entry referenced by that zone):',len(live))
for r in live: print(r)
json.dump(res,open('badmsg.json','w'))
