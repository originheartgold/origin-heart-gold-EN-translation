"""Native Options -> actual in-game save -> reset/Continue for all three speeds.

No fixed-clock movie here: a reset during DeSmuME movie recording restores the
movie's starting battery, which would discard the in-game save under test. This
gate asserts stored values, not frame timing, so host-clock drift does not matter.
Each reload also checks the ITCM payload/arena and that the reopened menu shows
the stored choice in the English labels (text_speed_checks.option_label_errors).
"""
import argparse,json
from gate_common import start_game,add_arguments,identity,inputs_unchanged,itcm_errors,load_expected_payload,require,resolve
import text_speed_checks as checks

def main():
    from emu_harness import Harness
    p=argparse.ArgumentParser(description=__doc__)
    add_arguments(p)
    a=resolve(p,p.parse_args())
    payload=load_expected_payload(a)
    report={'status':'failed',**identity(a,payload),'modes':[],'errors':[]}
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            start_game(h);original=h.u16(h.array(1))
            require(original&12==0, 'requires legacy save')
            menus=[]
            h.on_exec(payload['symbols']['load_rows']&~1,lambda h:menus.append(h.reg.r0))
            for mode in (2,1,0):
                h.press('X',after=90);h.touch(124,115,after=300)
                require(menus, 'check failed: menus')
                h.touch((130,177,227)[mode],152,after=40);h.touch(149,180,after=300)
                expected=(original&~12)|(mode<<2)
                require(h.u16(h.array(1))==expected, 'check failed: h.u16(h.array(1))==expected')
                h.press('B',after=90);h.press('X',after=90)
                h.touch(123,73,after=180);h.screenshot(f'{mode}-save-prompt')
                h.press('A',after=180);h.press('A',after=600)
                h.screenshot(f'{mode}-saved')
                h.emu.reset();menus.clear()
                h.boot_to_menu();h.continue_game()
                problems=itcm_errors(h,payload);require(not problems, repr(problems))
                actual=h.u16(h.array(1));require(actual==expected, repr((mode,actual,expected)))
                h.press('X',after=90);h.touch(124,115,after=300)
                require(menus and h.u16(menus[-1]+0x27e)==mode, 'check failed: menus and h.u16(menus[-1]+0x27e)==mode')
                h.screenshot(f'{mode}-reloaded')
                problems=checks.option_label_errors(h.emu.screenshot().convert('RGB'),mode);require(not problems, repr(problems))
                h.press('B',after=300);h.press('B',after=90)
                report['modes'].append({'mode':mode,'options_after_reset':actual})
        require(len(report['modes'])==3, "check failed: len(report['modes'])==3")
        require(inputs_unchanged(report), 'input modified')
        report['status']='passed'
    except BaseException as exc:
        report['errors'].append(f'{type(exc).__name__}: {exc}');raise
    finally:(a.out/'report.json').write_text(json.dumps(report,indent=2,default=str))
if __name__=='__main__':main()
