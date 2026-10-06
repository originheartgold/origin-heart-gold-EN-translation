"""Controlled runtime regressions for fallback paths on an exact-ROM checkpoint.

Uses the shared emulator harness. Deliberate RAM changes are limited to Options,
cartridge-save flag, a transient null runtime pointer, and requested printer delay.
These are branch tests, not natural gameplay claims. Inputs are never modified.
"""
import argparse
from collections import Counter
import json

from gate_common import (CLOCK, start_game, add_arguments, identity, inputs_unchanged, itcm_errors, load_expected_payload,
                         resolve)
import text_speed_checks as checks


def main():
    from emu_harness import Harness
    p = argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    a = resolve(p, p.parse_args())
    payload = load_expected_payload(a)
    report = {'status':'failed',**identity(a,payload),'cases':{},'errors':[]}
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False, rtc=CLOCK) as h:
            start_game(h)
            checkpoint=a.out/'fresh-candidate.dst'
            h.save_state(checkpoint)
            cases=[('slow',0,0,False,0),('medium',1,0,False,0),('fast',2,0,False,0),
                   ('invalid',3,0,False,0),('null',2,0,True,0),
                   ('old-music-1',0,1,False,0),('old-music-2',0,2,False,0),
                   ('delay-slow',0,0,False,3),('delay-medium',1,0,False,3),('delay-fast',2,0,False,3)]
            for name,mode,music,null,delay in cases:
                h.load_state(checkpoint)
                code=bytes.fromhex(payload['code'])
                assert h.read(payload['base'],len(code))==code, 'stale checkpoint executable'
                save=h.u32(0x021106C8)
                opts=h.array(1)
                value=(h.u16(opts)&~15)|(mode<<2)|music
                h.w16(opts,value)
                h.w32(save+4,0)  # initialized new-game state before the first cartridge save
                trace={'native':0,'original':0,'delayed':0,'glyphs':[],'glyph_tasks':[]}
                hidden=[False]
                def restore(h):
                    if hidden[0]:
                        h.w32(0x021106C8,save);hidden[0]=False
                def native(h):
                    trace['native']+=1
                    if null:
                        h.w32(0x021106C8,0);hidden[0]=True
                def original(h):
                    restore(h);trace['original']+=1
                def constructor(h):
                    if delay:
                        h.reg.r1=delay
                        trace['delayed']+=1
                h.on_exec(payload['symbols']['print_task']&~1,native)
                h.on_exec(0x02020A1C,original)
                h.on_exec(0x02020A88,restore)
                h.on_exec(0x020208D4,constructor)
                def glyph(h):
                    if h.u8(h.reg.r4+9)==1:
                        trace['glyphs'].append(h.frame)
                        trace['glyph_tasks'].append(trace['native'])
                h.on_exec(0x02002680,glyph)
                # Natural A interaction from the trainer fixture; only test fields above are changed.
                h.press('A',after=400)
                assert not hidden[0] and h.u32(0x021106C8)==save
                assert h.u16(opts)==value and h.u32(save+4)==0
                assert trace['native'] and len(trace['glyphs'])==54, (name,trace)
                fallback=mode==3 or null or delay
                assert bool(trace['original'])==bool(fallback), (name,trace)
                if fallback:assert trace['original']==trace['native'], 'fallback skipped original task'
                if delay:assert trace['delayed'], 'delay injection not exercised'
                first=trace['glyphs'][0]
                trace['glyphs']=[f-first for f in trace['glyphs']]
                trace['span']=trace['glyphs'][-1]
                report['cases'][name]=trace
            cases=report['cases']
            for name in ('old-music-1','old-music-2'):
                assert cases[name]['glyphs']==cases['slow']['glyphs'], name
            # Null-pointer injection adds instructions before the same original task.
            # Compare task cadence exactly; VBlank boundaries can differ by one frame.
            assert cases['invalid']['glyph_tasks']==cases['null']['glyph_tasks']
            assert max(abs(a-b) for a,b in zip(cases['invalid']['glyphs'],cases['null']['glyphs']))<=1
            for name in ('slow','medium','fast','invalid'):
                frames=sorted(set(cases[name]['glyphs']))
                cases[name]['lag_frames']=sum(b-a-1 for a,b in zip(frames,frames[1:]))
            names={3:'invalid',0:'slow',1:'medium',2:'fast'}
            order,warnings=checks.speed_order_with_lag({m:cases[n]['span'] for m,n in names.items()},
                                                       {m:cases[n]['lag_frames'] for m,n in names.items()})
            report['errors'].extend(f'frame order: {e}' for e in order)
            report['warnings']=warnings
            for name,budgets in (('slow',{1,2}),('medium',{2}),('fast',{3})):
                observed=set(Counter(cases[name]['glyph_tasks']).values())
                assert observed==budgets,(name,observed)

            assert cases['delay-slow']['glyphs']==cases['delay-medium']['glyphs']==cases['delay-fast']['glyphs']
            assert cases['delay-slow']['span']>cases['slow']['span']
            report['errors'].extend(itcm_errors(h,payload))
        assert inputs_unchanged(report),'input modified'
        if not report['errors']:report['status']='passed'
    except BaseException as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}');raise
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2,default=str))
    if report['status']!='passed':raise SystemExit('\n'.join(report['errors']))


if __name__=='__main__':main()
