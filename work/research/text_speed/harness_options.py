"""Native Options input boundaries, cancellation and repeated entry via emu_harness.

Every time the menu is reopened after a commit (and for the reserved value), the
screenshot's TEXT SPEED row must show three separate English labels, each inside
its own touch column, only the stored choice in the selected colour, and nothing
spilling out of the row (text_speed_checks.option_label_errors).
"""
import argparse
import json
import sys as _sys  # noqa: E402
from pathlib import Path as _Path  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))   # python -I adds no script directory
from gate_common import (CLOCK, start_game, add_arguments, attach_probe, identity, inputs_unchanged, itcm_errors,
                         load_expected_payload, memory_errors, memory_summary, require, resolve)
import text_speed_checks as checks


def main():
    from emu_harness import Harness
    p=argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    a=resolve(p,p.parse_args())
    payload=load_expected_payload(a)
    report={'status':'failed',**identity(a,payload),'checks':[],'errors':[]}
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False, rtc=CLOCK) as h:
            start_game(h)
            start=itcm_errors(h,payload);require(not start, repr(start))
            probe=attach_probe(h)
            menus=[];exits=[]
            h.on_exec(payload['symbols']['load_rows']&~1,lambda h:menus.append(h.reg.r0))
            h.on_exec(payload['symbols']['exit_free']&~1,lambda h:exits.append(h.frame))
            def open_menu():
                count=len(menus)
                h.press('X',after=90);h.touch(124,115,after=300)
                require(len(menus)==count+1, 'check failed: len(menus)==count+1')
                return menus[-1]
            def leave(key):
                count=len(exits)
                h.press(key,after=300)
                require(len(exits)==count+1, 'Options did not exit')
                h.press('B',after=90)
            labels=report['labels']=[]
            def check_labels(name,shown):
                img=h.emu.screenshot().convert('RGB')
                img.save(a.out/f'labels-{name}.png')
                problems=checks.option_label_errors(img,shown)
                labels.append({'case':name,'shown':shown,'errors':problems})
                require(not problems, repr((name,problems)))
            original=h.u16(h.array(1))
            d=open_menu()
            check_labels('legacy-open',0)
            row=lambda:(h.u32(d+16)>>2)&7
            require(row()==0, 'check failed: row()==0')
            h.press('UP',after=30);require(row()==7, 'check failed: row()==7')
            h.press('DOWN',after=30);require(row()==0, 'check failed: row()==0')
            report['checks'].append('row wrap 0 <-> 7')
            h.touch(130,152,after=30);require(row()==6, 'check failed: row()==6')
            # Text values cycle in both directions; A on a setting stays in Options.
            for key,value in (('LEFT',2),('RIGHT',0),('RIGHT',1),('RIGHT',2),('RIGHT',0)):
                h.press(key,after=30);require(h.u16(d+0x27e)==value, 'check failed: h.u16(d+0x27e)==value')
            count=len(exits);h.press('A',after=60);require(len(exits)==count, 'check failed: len(exits)==count')
            report['checks'].append('text values wrap both directions; A does not close settings row')
            h.touch(227,152,after=30)
            leave('B');require(h.u16(h.array(1))==original, 'check failed: h.u16(h.array(1))==original')
            report['checks'].append('B discards FAST')
            d=open_menu();require(h.u16(d+0x27e)==0, 'check failed: h.u16(d+0x27e)==0')
            h.touch(177,152,after=30);h.press('DOWN',after=30)
            require(row()==7 and h.u16(d+0x2d2)==0, 'check failed: row()==7 and h.u16(d+0x2d2)==0')
            h.press('LEFT',after=30);require(h.u16(d+0x2d2)==1, 'check failed: h.u16(d+0x2d2)==1')
            h.press('RIGHT',after=30);require(h.u16(d+0x2d2)==0, 'check failed: h.u16(d+0x2d2)==0')
            leave('A');require(h.u16(h.array(1))==original, 'check failed: h.u16(h.array(1))==original')
            report['checks'].append('Quit default and LEFT/RIGHT; A on Quit discards MEDIUM')
            for mode,x in ((2,227),(1,177),(0,130)):
                d=open_menu()
                before=h.u16(h.array(1))
                require(h.u16(d+0x27e)==(before>>2)&3, 'check failed: h.u16(d+0x27e)==(before>>2)&3')
                check_labels(f'reopen-{(before>>2)&3}',(before>>2)&3)
                h.touch(x,152,after=30)
                require(h.u16(d+0x27e)==mode and h.u16(h.array(1))==before, 'check failed: h.u16(d+0x27e)==mode and h.u16(h.array(1))==before')
                h.press('DOWN',after=30);h.press('LEFT',after=30)
                leave('A')
                require(h.u16(h.array(1))==(original&~12)|(mode<<2), f'Confirm did not store the chosen text speed (Options {h.u16(h.array(1)):#x}, expected {(original&~12)|(mode<<2):#x})')
                report['checks'].append(f'commit mode {mode}, reopen and preserve other bits')
            # Reserved raw value 3 is a controlled corrupt/unknown-setting case.
            h.w16(h.array(1),(original&~12)|12)
            d=open_menu();require(h.u16(d+0x27e)==1, f'reserved value 3 is not shown as MEDIUM (row value {h.u16(d+0x27e)})')
            check_labels('reserved-3',1)
            leave('B');require(h.u16(h.array(1))==(original&~12)|12, 'check failed: h.u16(h.array(1))==(original&~12)|12')
            d=open_menu();require(h.u16(d+0x27e)==1, f'reserved value 3 is not shown as MEDIUM (row value {h.u16(d+0x27e)})')
            h.touch(149,180,after=300);h.press('B',after=90)
            require(h.u16(h.array(1))==(original&~12)|4, 'check failed: h.u16(h.array(1))==(original&~12)|4')
            report['checks'].append('reserved value displays MEDIUM; Cancel preserves it, Confirm normalizes it')
            d=open_menu();check_labels('final-1',1);leave('B')
            require(len(labels)==6, repr(labels))
            report['checks'].append('English labels render inside their columns at every value (6 screenshots)')
            report['itcm']=itcm_errors(h,payload)
            require(not report['itcm'], repr(report['itcm']))
            report['memory']=memory_summary(probe)
            problems=memory_errors(report['memory']);require(not problems, repr(problems))
        require(inputs_unchanged(report), 'input modified')
        report['status']='passed'
    except BaseException as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2,default=str))


if __name__=='__main__':main()
