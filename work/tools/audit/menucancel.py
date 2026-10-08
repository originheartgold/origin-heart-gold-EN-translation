"""For cancellable menus, follow the B-press (0xFFFE) result and see whether the script ends while still locked."""
import json
import core, sdis as dis, lockcheck as LC
A=dis.all_files()
INIT={64,65,68,69,749,750}; EXEC={67,71,752}
def cmp_eval(v,c,cond):
    return {0:v<c,1:v==c,2:v>c,3:v<=c,4:v>=c,5:v!=c}[cond]
def explore(f,start,locked,tracked):
    ins=A[f]['ins']; res=set(); st=[(start,locked,frozenset(tracked.items()),None,0,())]; seen=set()
    while st:
        pc,l,tv,lastcmp,steps,stack=st.pop()
        key=(pc,l,tv,lastcmp,stack)
        if key in seen or steps>3000: continue
        seen.add(key)
        if pc not in ins: res.add(('abort',pc,l)); continue
        op,a,n,t=ins[pc]; tvd=dict(tv)
        if op==96: l=True
        elif op==97: l=False
        elif op==176: l=None
        if op==2: res.add(('end',pc,l)); continue
        if op==27:
            if stack: st.append((stack[-1],l,tv,lastcmp,steps+1,stack[:-1]))
            continue
        if op in (42,43) and a[1] in tvd: tvd[a[0]]=tvd[a[1]]
        elif op in (41,42,43,39,40) and a[0] in tvd: tvd.pop(a[0])
        if op==17: lastcmp=(a[0],a[1]) if a[0] in tvd else None
        elif op in (18,11,12,13,14,15,16,19,21): lastcmp=None
        tv=frozenset(tvd.items())
        if op in (28,29):
            nexts=[]
            if lastcmp:
                taken=cmp_eval(tvd[lastcmp[0]],lastcmp[1],a[0])
                nexts=[taken]
            else: nexts=[True,False]
            for tk in nexts:
                if tk:
                    if op==29: st.append((t,l,tv,lastcmp,steps+1,stack+(n,)))
                    else: st.append((t,l,tv,lastcmp,steps+1,stack))
                else: st.append((n,l,tv,lastcmp,steps+1,stack))
            continue
        if op==26: st.append((t,l,tv,lastcmp,steps+1,stack+(n,))); continue
        if op==22: st.append((t,l,tv,lastcmp,steps+1,stack)); continue
        if op==20:
            LC.std_target(a[0])
            # assume std calls return with same lock state
        if op in (23,24,25,225): st.append((t,l,tv,lastcmp,steps+1,stack))
        st.append((n,l,tv,lastcmp,steps+1,stack))
    return res
out=[]
for f,d in A.items():
    if d['kind']!='script': continue
    ins=d['ins']
    for pc,(op,a,n,t) in ins.items():
        if op in INIT and a[3]==1:
            var=a[4]
            # find the exec after init (linear)
            p=n; ex=None
            for _ in range(60):
                if p not in ins: break
                o2=ins[p]
                if o2[0] in EXEC: ex=p; break
                if o2[0] in (2,22,27): break
                p=o2[2]
            if ex is None: continue
            r=explore(f,ins[ex][2],True,{var:0xFFFE})
            bad=[x for x in r if (x[0]=='end' and x[2]) or x[0]=='abort']
            if bad: out.append((f,pc,ex,var,sorted(bad)[:3]))
json.dump(out,open(core.D+'/menucancel.json','w'))
print('cancellable menus whose B-press path ends locked:',len(out))
for x in out: print(x)
