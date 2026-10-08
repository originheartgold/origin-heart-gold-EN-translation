"""Script disassembler for a/0/1/2 (pret command table, 853 cmds; hack table has 843)."""
import json, struct, os, pickle
import core
D=core.D
C={int(k):v for k,v in json.load(open(D+'/cmds.json')).items()}
NAME={k:v['name'] for k,v in C.items()}
OP={v:k for k,v in NAME.items()}
JUMPS={22:True,26:False,23:False,24:False,25:False,28:False,29:False,225:False}  # True=unconditional goto
CALLS={26,29}
TERM={2,27}
COND={0:'<',1:'==',2:'>',3:'<=',4:'>=',5:'!='}
def argsizes(op,data,p):
    if op in (400,401,402):
        return [1,2] if data[p]==2 else [1]
    if op==465:
        a=struct.unpack_from('<H',data,p)[0]
        return [2,2,2] if a<=3 else ([2] if a==6 else [2,2])
    if op==489:
        a=struct.unpack_from('<H',data,p)[0]
        return [2,2] if 1<=a<=3 else ([2,2,2] if a in (5,6) else [2])
    return C[op]['args']
def header(data):
    entries=[];p=0
    while p+4<=len(data):
        if struct.unpack_from('<H',data,p)[0]==0xFD13: break
        off=struct.unpack_from('<i',data,p)[0]; entries.append(p+4+off); p+=4
    return entries
def disasm(data, entries=None):
    if entries is None: entries=header(data)
    todo=[(e,) for e in entries]; ins={}; errs=[]; movs=set()
    todo=list(entries)
    while todo:
        pc=todo.pop()
        while True:
            if pc in ins: break
            if pc<0 or pc+2>len(data): errs.append(('eof',pc)); break
            op=struct.unpack_from('<H',data,pc)[0]
            if op not in C or op>=(843 if core.KEY=='cn' else 853): errs.append(('badop',pc,op)); break
            q=pc+2; args=[]; bad=False
            for s in argsizes(op,data,q):
                if q+s>len(data): errs.append(('trunc',pc)); bad=True; break
                args.append(int.from_bytes(data[q:q+s],'little',signed=(s==4))); q+=s
            if bad: break
            tgt=None
            if op in JUMPS:
                tgt=q+args[-1]; todo.append(tgt)
            if op==94: movs.add(q+args[-1])
            ins[pc]=(op,args,q,tgt)
            if op in JUMPS and JUMPS[op]: break
            if op in TERM: break
            pc=q
    return dict(entries=entries,ins=ins,errs=errs,movs=movs)
def all_files():
    c=D+'/dis%s.pkl'%core.SUF
    if os.path.exists(c): return pickle.load(open(c,'rb'))
    r=core.raw(); z=core.zones()
    hdr=set(x['script_header_bank'] for x in z)-set(x['scripts_bank'] for x in z)
    out={}
    for i,f in enumerate(r['scr']):
        if i in hdr:
            out[i]=dict(kind='level',levels=core.parse_levelscripts(f),size=len(f)); continue
        try: d=disasm(f)
        except Exception as e: d=dict(entries=[],ins={},errs=[('exc',str(e))],movs=set())
        d['kind']='script'; d['size']=len(f); out[i]=d
    pickle.dump(out,open(c,'wb')); return out
if __name__=='__main__':
    A=all_files()
    ns=sum(1 for v in A.values() if v['kind']=='script'); nl=len(A)-ns
    print('files',len(A),'script',ns,'level',nl,'cmds',sum(len(v.get('ins',{})) for v in A.values()))
    for k,v in A.items():
        if v.get('errs'): print(k,v['size'],len(v['entries']),v['errs'][:4])
