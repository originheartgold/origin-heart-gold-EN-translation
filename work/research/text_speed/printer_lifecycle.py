"""Check private printer initialization and reused allocations on the candidate ROM.

Poison only the new private byte before the initializer; observe the game's
constructor return and require it to reset both phase and its owned focus pointer.
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
    report={'status':'failed','inputs':{str(x):digest(x) for x in (a.rom,a.save)},'constructors':[]}
    payload=load_payload();pending=[];seen=set();reused=[];errors=[]
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.boot_to_menu();h.continue_game()
            assert h.read(payload['base'],len(bytes.fromhex(payload['code'])))==bytes.fromhex(payload['code'])
            probe=Probe(h.emu);probe.armed=True
            def begin(h):
                ptr=h.reg.r0
                pending.append(ptr)
                if ptr in seen:reused.append(ptr)
                seen.add(ptr)
                h.w8(ptr+0x34,255)
            def end(h):
                ptr=h.reg.r4
                if not pending or pending.pop()!=ptr:errors.append('constructor pairing mismatch')
                if h.u8(ptr+0x34)!=0 or h.u32(ptr+0x30)!=0:errors.append('initializer did not reset private phase/focus pointer')
                report['constructors'].append(ptr)
                probe.frame=h.frame
                bad=probe.heap_walk()
                if bad:errors.append(bad)
            h.on_exec(payload['symbols']['init_printer']&~1,begin)
            h.on_exec(0x02020966,end)
            h.w16(h.array(1),h.u16(h.array(1))&~12)
            for _ in range(3):
                h.show_message(48,20)
            report['errors']=errors
            assert len(report['constructors'])>=3 and reused and not pending and not errors,report
            report['reused_allocations']=reused
            report['heap_checks']=probe.heap_checks
            assert probe.heap_checks and not probe.corrupt
        assert all(digest(Path(path))==sha for path,sha in report['inputs'].items())
        report['status']='passed'
    finally:(a.out/'report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
