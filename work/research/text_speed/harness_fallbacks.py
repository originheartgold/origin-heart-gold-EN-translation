"""Controlled runtime regressions for fallback paths on an exact-ROM checkpoint.

Uses the shared emulator harness. Deliberate RAM changes are limited to Options,
cartridge-save flag, a transient null runtime pointer, and requested printer delay.
These are branch tests, not natural gameplay claims. Inputs are never modified.
"""
import argparse
import json
from pathlib import Path
import sys

from harness_regression import ROOT, digest
sys.path.insert(0, str(ROOT/'work/tools'))


def main():
    from emu_harness import Harness
    from text_speed_patch import load_payload
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True, type=Path)
    p.add_argument('--save', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    a.rom,a.save,a.out = a.rom.resolve(),a.save.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out == ROOT/'work/build':
        p.error('Output must be in this worktree work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    report = {'status':'failed','inputs':{str(x):digest(x) for x in (a.rom,a.save)},'cases':{}}
    payload=load_payload()
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.boot_to_menu();h.continue_game()
            checkpoint=a.out/'fresh-candidate.dst'
            h.save_state(checkpoint)
            cases=[('normal',0,0,False,0),('fast',1,0,False,0),('instant',2,0,False,0),
                   ('invalid',3,0,False,0),('null',2,0,True,0),
                   ('old-music-1',0,1,False,0),('old-music-2',0,2,False,0),
                   ('delay-normal',0,0,False,3),('delay-fast',1,0,False,3),('delay-instant',2,0,False,3)]
            for name,mode,music,null,delay in cases:
                h.load_state(checkpoint)
                code=bytes.fromhex(payload['code'])
                assert h.read(payload['base'],len(code))==code, 'stale checkpoint executable'
                save=h.u32(0x021106C8)
                opts=h.array(1)
                value=(h.u16(opts)&~15)|(mode<<2)|music
                h.w16(opts,value)
                h.w32(save+4,0)  # initialized new-game state before the first cartridge save
                trace={'native':0,'original':0,'delayed':0,'glyphs':[]}
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
                h.on_exec(0x02002680,lambda h:trace['glyphs'].append(h.frame) if h.u8(h.reg.r4+9)==1 else None)
                # Natural A interaction from the trainer fixture; only test fields above are changed.
                h.press('A',after=400)
                assert not hidden[0] and h.u32(0x021106C8)==save
                assert h.u16(opts)==value and h.u32(save+4)==0
                assert trace['native'] and len(trace['glyphs'])==54, (name,trace)
                fallback=mode in (0,3) or null or delay
                assert bool(trace['original'])==bool(fallback), (name,trace)
                if fallback:assert trace['original']==trace['native'], 'fallback skipped original task'
                if delay:assert trace['delayed'], 'delay injection not exercised'
                first=trace['glyphs'][0]
                trace['glyphs']=[f-first for f in trace['glyphs']]
                trace['span']=trace['glyphs'][-1]
                report['cases'][name]=trace
            cases=report['cases']
            for name in ('invalid','null','old-music-1','old-music-2'):
                assert cases[name]['glyphs']==cases['normal']['glyphs'], name
            assert cases['normal']['span']>cases['fast']['span']>cases['instant']['span']
            assert cases['delay-normal']['glyphs']==cases['delay-fast']['glyphs']==cases['delay-instant']['glyphs']
            assert cases['delay-normal']['span']>cases['normal']['span']
        assert all(digest(Path(path))==sha for path,sha in report['inputs'].items())
        report['status']='passed'
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
