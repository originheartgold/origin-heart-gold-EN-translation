"""Native Options input boundaries, cancellation and repeated entry via emu_harness."""
import argparse
import json
from pathlib import Path
import sys
from harness_regression import ROOT, digest
sys.path.insert(0,str(ROOT/'work/tools'))


def main():
    from emu_harness import Harness
    from text_speed_patch import load_payload
    from memcheck import Probe
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','save','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    a.rom,a.save,a.out=a.rom.resolve(),a.save.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out==ROOT/'work/build':p.error('Use this worktree work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    report={'status':'failed','inputs':{str(x):digest(x) for x in (a.rom,a.save)},'checks':[]}
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.boot_to_menu();h.continue_game()
            payload=load_payload();code=bytes.fromhex(payload['code'])
            assert h.read(payload['base'],len(code))==code
            probe=Probe(h.emu);probe.armed=True
            def frame(h):
                probe.frame=h.frame
                if h.frame%10==0 and probe.corrupt is None:
                    bad=probe.heap_walk()
                    if bad:probe.corrupt=(h.frame,bad)
            h.on_frame(frame)
            menus=[];exits=[]
            h.on_exec(payload['symbols']['load_rows']&~1,lambda h:menus.append(h.reg.r0))
            h.on_exec(payload['symbols']['exit_free']&~1,lambda h:exits.append(h.frame))
            def open_menu():
                count=len(menus)
                h.press('X',after=90);h.touch(124,115,after=300)
                assert len(menus)==count+1
                return menus[-1]
            def leave(key):
                count=len(exits)
                h.press(key,after=300)
                assert len(exits)==count+1, 'Options did not exit'
                h.press('B',after=90)
            original=h.u16(h.array(1))
            d=open_menu()
            row=lambda:(h.u32(d+16)>>2)&7
            assert row()==0
            h.press('UP',after=30);assert row()==7
            h.press('DOWN',after=30);assert row()==0
            report['checks'].append('row wrap 0 <-> 7')
            h.touch(130,152,after=30);assert row()==6
            # Text values cycle in both directions; A on a setting stays in Options.
            for key,value in (('LEFT',2),('RIGHT',0),('RIGHT',1),('RIGHT',2),('RIGHT',0)):
                h.press(key,after=30);assert h.u16(d+0x27e)==value
            count=len(exits);h.press('A',after=60);assert len(exits)==count
            report['checks'].append('text values wrap both directions; A does not close settings row')
            h.touch(227,152,after=30)
            leave('B');assert h.u16(h.array(1))==original
            report['checks'].append('B discards FAST')
            d=open_menu();assert h.u16(d+0x27e)==0
            h.touch(177,152,after=30);h.press('DOWN',after=30)
            assert row()==7 and h.u16(d+0x2d2)==0
            h.press('LEFT',after=30);assert h.u16(d+0x2d2)==1
            h.press('RIGHT',after=30);assert h.u16(d+0x2d2)==0
            leave('A');assert h.u16(h.array(1))==original
            report['checks'].append('Quit default and LEFT/RIGHT; A on Quit discards MEDIUM')
            for mode,x in ((2,227),(1,177),(0,130)):
                d=open_menu()
                before=h.u16(h.array(1))
                assert h.u16(d+0x27e)==(before>>2)&3
                h.touch(x,152,after=30)
                assert h.u16(d+0x27e)==mode and h.u16(h.array(1))==before
                h.press('DOWN',after=30);h.press('LEFT',after=30)
                leave('A')
                assert h.u16(h.array(1))==(original&~12)|(mode<<2)
                report['checks'].append(f'commit mode {mode}, reopen and preserve other bits')
            # Reserved raw value 3 is a controlled corrupt/unknown-setting case.
            h.w16(h.array(1),(original&~12)|12)
            d=open_menu();assert h.u16(d+0x27e)==1
            leave('B');assert h.u16(h.array(1))==(original&~12)|12
            d=open_menu();assert h.u16(d+0x27e)==1
            h.touch(149,180,after=300);h.press('B',after=90)
            assert h.u16(h.array(1))==(original&~12)|4
            report['checks'].append('reserved value displays MEDIUM; Cancel preserves it, Confirm normalizes it')
            report['memory']={k:getattr(probe,k) for k in ('heap_checks','corrupt','fails','nullw','text_rejections','heap_table_errors','text_probe_errors')}
            assert probe.heap_checks and not any(v for k,v in report['memory'].items() if k!='heap_checks')
        assert all(digest(Path(path))==sha for path,sha in report['inputs'].items())
        report['status']='passed'
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
