"""Native Options -> actual in-game save -> reset/Continue for all three speeds."""
import argparse,json,sys
from pathlib import Path
from harness_regression import ROOT,digest
sys.path.insert(0,str(ROOT/'work/tools'))

def main():
    from emu_harness import Harness
    from text_speed_patch import load_payload
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','save','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.rom,a.save,a.out=a.rom.resolve(),a.save.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out==ROOT/'work/build':p.error('Use work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    report={'status':'failed','inputs':{str(x):digest(x) for x in (a.rom,a.save)},'modes':[]}
    payload=load_payload()
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.boot_to_menu();h.continue_game();original=h.u16(h.array(1))
            assert original&12==0,'requires legacy save'
            menus=[]
            h.on_exec(payload['symbols']['load_rows']&~1,lambda h:menus.append(h.reg.r0))
            for mode in (2,1,0):
                h.press('X',after=90);h.touch(124,115,after=300)
                assert menus
                h.touch((130,177,227)[mode],152,after=40);h.touch(149,180,after=300)
                expected=(original&~12)|(mode<<2)
                assert h.u16(h.array(1))==expected
                h.press('B',after=90);h.press('X',after=90)
                h.touch(123,73,after=180);h.screenshot(f'{mode}-save-prompt')
                h.press('A',after=180);h.press('A',after=600)
                h.screenshot(f'{mode}-saved')
                h.emu.reset();menus.clear()
                h.boot_to_menu();h.continue_game()
                assert h.read(payload['base'],len(bytes.fromhex(payload['code'])))==bytes.fromhex(payload['code'])
                actual=h.u16(h.array(1));assert actual==expected,(mode,actual,expected)
                h.press('X',after=90);h.touch(124,115,after=300)
                assert menus and h.u16(menus[-1]+0x27e)==mode
                h.screenshot(f'{mode}-reloaded');h.press('B',after=300);h.press('B',after=90)
                report['modes'].append({'mode':mode,'options_after_reset':actual})
        assert all(digest(Path(path))==sha for path,sha in report['inputs'].items())
        report['status']='passed'
    finally:(a.out/'report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
