import json, collections
import sdis as dis
A=dis.all_files()
L=json.load(open('lockcheck.json'))
prevmap={}
def prev(f,pc):
    ins=A[f]['ins']
    for p,(op,a,n,t) in ins.items():
        if n==pc: return op
    return None
out=collections.Counter(); keep=[]
for x in L:
    if x[0]!='END_LOCKED': keep.append(x); continue
    f,e,pc=x[1],x[2],x[3]
    po=prev(f,pc)
    nm=dis.NAME.get(po,'label')
    out[nm]+=1
    if po not in (28,): keep.append(x+[nm])
print(out.most_common(40))
json.dump(keep,open('lock_suspects.json','w'))
print(len(keep))
