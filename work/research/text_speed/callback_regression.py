"""Controlled callback fallback, busy callback retries and held-input comparisons.

Uses a same-candidate checkpoint and an existing, byte-verified return-zero code
sequence as a benign callback. Only the callback's return value is overridden to
simulate four busy retries. No injected executable code or source save changes.
These are renderer branch tests, not a natural callback-scene certification.
"""
import argparse,json,sys
from pathlib import Path
from harness_regression import ROOT,digest
sys.path.insert(0,str(ROOT/'work/tools'))


def main():
    from emu_harness import Harness
    from text_speed_patch import load_payload
    from memcheck import Probe
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','save','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.rom,a.save,a.out=a.rom.resolve(),a.save.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out==ROOT/'work/build':p.error('Use work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    report={'status':'failed','inputs':{str(x):digest(x) for x in (a.rom,a.save)},'cases':{}}
    payload=load_payload();stub=0x0200107a
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.boot_to_menu();h.continue_game()
            checkpoint=a.out/'candidate.dst';h.save_state(checkpoint)
            for kind in ('callback','busy','held-A','held-B'):
                for mode in (3,0,1,2):
                    h.load_state(checkpoint)
                    assert h.read(payload['base'],len(bytes.fromhex(payload['code'])))==bytes.fromhex(payload['code'])
                    assert h.read(stub,4)==bytes.fromhex('00207047')
                    opts=h.array(1);value=(h.u16(opts)&~12)|(mode<<2);h.w16(opts,value)
                    trace={'glyphs':[],'callbacks':[],'native':0,'original':0,'injected':0}
                    def native(h):
                        if h.u8(h.reg.r1+9)==1:trace['native']+=1
                    def original(h):
                        if h.u8(h.reg.r1+9)==1:trace['original']+=1
                    def constructor(h):
                        if kind in ('callback','busy') and h.u8(h.reg.r0+9)==1:
                            assert h.reg.r2==0,'fixture already has a callback'
                            h.reg.r2=stub|1;trace['injected']+=1
                    def callback(h):
                        if h.reg.lr not in (0x02020a67,0x02020a7f):return
                        assert h.u8(h.reg.r0+9)==1
                        trace['callbacks'].append({'event':h.reg.r1,'glyphs':len(trace['glyphs'])})
                    def callback_return(h):
                        if h.reg.lr in (0x02020a67,0x02020a7f):
                            h.reg.r0=int(kind=='busy' and len(trace['callbacks'])<=4)
                    def glyph(h):
                        ptr=h.reg.r4
                        if h.u8(ptr+9)==1:
                            trace['glyphs'].append((trace['native'],h.u16(ptr+12),h.u16(ptr+14)))
                    h.on_exec(payload['symbols']['print_task']&~1,native)
                    h.on_exec(0x02020a1c,original);h.on_exec(0x020208d4,constructor)
                    h.on_exec(stub,callback);h.on_exec(stub+2,callback_return)
                    h.on_exec(0x02002680,glyph)
                    if kind=='held-A':
                        h.hold('A');h.step(406);h.release()
                    elif kind=='held-B':
                        h.hold('B');h.press('A',after=400);h.release()
                    else:h.press('A',after=400)
                    assert trace['native']>0 and len(trace['glyphs'])==54,trace
                    assert h.u16(opts)==value
                    if kind in ('callback','busy'):
                        assert trace['injected']>0 and trace['original']==trace['native']
                        assert len(trace['callbacks'])>=54
                        if kind=='busy':assert [x['glyphs'] for x in trace['callbacks'][:5]]==[1]*5
                    else:
                        assert not trace['callbacks'] and not trace['injected']
                        assert bool(trace['original'])==(mode==3)
                    first=trace['glyphs'][0][0]
                    trace['glyphs']=[(task-first,x,y) for task,x,y in trace['glyphs']]
                    trace['pixels']=__import__('hashlib').sha256(h.emu.screenshot().crop((8,153,236,182)).tobytes()).hexdigest()
                    probe=Probe(h.emu);probe.armed=True;probe.frame=h.frame
                    assert not probe.heap_walk() and probe.heap_checks
                    trace['heap_checks']=probe.heap_checks
                    report['cases'][f'{kind}-{mode}']=trace
                base=report['cases'][f'{kind}-3']
                for mode in range(3):
                    case=report['cases'][f'{kind}-{mode}']
                    assert case['pixels']==base['pixels']
                    assert [x[1:] for x in case['glyphs']]==[x[1:] for x in base['glyphs']]
                    if kind in ('callback','busy'):
                        assert case['callbacks']==base['callbacks']
                        assert case['glyphs']==base['glyphs'],'callback task cadence changed'
        assert all(digest(Path(path))==sha for path,sha in report['inputs'].items())
        report['status']='passed'
    finally:(a.out/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
