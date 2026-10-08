"""Compare effects of gender / starter branches."""
import collections, json
import core, sdis as dis, index
A=dis.all_files(); o=index.load()
EFF={}
for x in o['rec']:
    k=x['kind']
    if k in ('flag_set','flag_clear','var_set','item_give','mon_give','egg_give','show','hide','visible','warp','trainer','callstd','badge_give','trflag_set','wild','var_add'):
        if k=='callstd':
            if x['id'] not in (2033,2008,2007): continue
            e=('give_std',x.get('v8004'))
        elif k=='var_set': e=(k,x['id'],x['v'])
        elif k=='warp': e=(k,x['id'])
        else: e=(k,x['id'])
        if k in ('var_set',) and x['id']>=0x8000: continue
        if k=='var_set' and x['id']<0x4020: continue
        EFF.setdefault((x['file'],x['pc']),[]).append(e)
def succ(f,pc):
    op,a,n,t=A[f]['ins'][pc]; s=[]
    if t is not None: s.append(t)
    if not (op in dis.TERM or (op in dis.JUMPS and dis.JUMPS[op])): s.append(n)
    return s
def reach(f,start,stop=None):
    ins=A[f]['ins']; seen=set(); st=[start]
    while st:
        p=st.pop()
        if p in seen or p not in ins: continue
        seen.add(p); st.extend(succ(f,p))
    return seen
def compare(f,pa,pb):
    RA=reach(f,pa); RB=reach(f,pb)
    ea=collections.Counter(e for p in RA-RB for e in EFF.get((f,p),[]))
    eb=collections.Counter(e for p in RB-RA for e in EFF.get((f,p),[]))
    return ea-eb, eb-ea
def branch_points(getop):
    out=[]
    for f,d in A.items():
        if d['kind']!='script': continue
        ins=d['ins']
        for pc,(op,a,n,t) in ins.items():
            if op!=getop: continue
            var=a[0]; p=n; found=False
            for _ in range(6):
                if p not in ins: break
                op2,a2,n2,t2=ins[p]
                if op2==17 and a2[0]==var and n2 in ins and ins[n2][0]==28:
                    c=ins[n2]; out.append((f,pc,p,a2[1],c[1][0],c[3],c[2]))
                    p=c[2]; found=True; continue
                if found: break
                if op2 in (2,22,27,28,29) or (op2 in (41,42,43) and a2[0]==var) or op2==getop: break
                p=n2
    return out
if __name__=='__main__':
    res=[]
    for name,getop in (('gender',281),('starter',206)):
        for (f,pc,cpc,val,cond,tgt,ft) in branch_points(getop):
            a,b=compare(f,tgt,ft)
            if a or b:
                res.append(dict(kind=name,file=f,pc=pc,cmp=cpc,val=val,cond=dis.COND[cond],taken=tgt,fall=ft,only_taken=[list(map(str,k))+[v] for k,v in a.items()],only_fall=[list(map(str,k))+[v] for k,v in b.items()]))
    json.dump(res,open(core.D+'/branches.json','w'),indent=1)
    print(len(res))
    for r in res: print(r['kind'],r['file'],r['pc'],'var==%s %s'%(r['val'],r['cond']),'\n   T:',r['only_taken'][:8],'\n   F:',r['only_fall'][:8])
