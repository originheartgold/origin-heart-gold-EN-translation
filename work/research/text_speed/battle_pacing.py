"""Measure actual battle turns without holding A/B or using emulator fast-forward.

Printer lifetime/last-glyph measurements are not a guarantee of screen dwell:
other scene drawing can clear a window. Screenshots accompany the observations.
"""
import argparse,json,sys
from pathlib import Path
from datetime import datetime
from harness_regression import ROOT,digest
sys.path.insert(0,str(ROOT/'work/tools'))


def main():
    from emu_harness import Harness,BATTLE_BUTTONS,MOVE_BUTTONS
    from memcheck import Probe
    import msgtool
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','save','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--mode',type=int,choices=range(3),required=True)
    p.add_argument('--payload',type=Path,default=ROOT/'work/patches/text_speed/payload.json')
    a=p.parse_args();a.rom,a.save,a.out=a.rom.resolve(),a.save.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out==ROOT/'work/build':p.error('Use worktree work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    report={'status':'failed','mode':a.mode,'rom_sha256':digest(a.rom),'save_sha256':digest(a.save),'messages':[],'turns':[]}
    payload=json.loads(a.payload.read_text());cm=msgtool.Charmap.load([str(ROOT/'work/tools/charmap_en.tsv')])
    active={};battle=[False];screens={}
    try:
        with Harness(a.rom,a.save,out=a.out,verbose=False) as h:
            h.set_clock(datetime(2026,10,9,12));h.boot_to_menu();h.continue_game()
            code=bytes.fromhex(payload['code']);assert h.read(payload['base'],len(code))==code
            probe=Probe(h.emu);probe.armed=True
            def frame(h):
                probe.frame=h.frame
                if h.frame%10==0 and probe.corrupt is None:
                    bad=probe.heap_walk()
                    if bad:probe.corrupt=(h.frame,bad)
                for i,row in enumerate(report['messages']):
                    if not row['glyph_frames'] or 'visible_change' in row:continue
                    last=row['glyph_frames'][-1]
                    if h.frame==last+3:
                        # Allow display transfer to complete after the final glyph.
                        screens[i]=(last,h.emu.screenshot().crop((8,153,248,184)).tobytes())
                        h.screenshot(f'message-{i}')
                    elif i in screens and screens[i][0]==last and h.frame>last+3:
                        if h.emu.screenshot().crop((8,153,248,184)).tobytes()!=screens[i][1]:
                            row['visible_change']=h.frame
                            row['stable_after_final_glyph']=h.frame-last-3
            h.on_frame(frame)
            def task(h):
                ptr=h.reg.r1
                if not battle[0] or ptr in active:return
                addr=h.u32(ptr);units=[]
                for n in range(1024):
                    u=h.u16(addr+2*n)
                    if u==65535:break
                    units.append(u)
                row={'start':h.frame,'text':msgtool.decode_units(units,cm),'font':h.u8(ptr+9),'id':h.u8(ptr+0x2c),'callback':h.u32(ptr+0x1c),'delay':h.u8(ptr+0x29)&127,'glyph_frames':[],'window':h.u32(ptr+4)}
                active[ptr]=row;report['messages'].append(row)
            def glyph(h):
                row=active.get(h.reg.r4)
                if row is not None:
                    row['glyph_frames'].append(h.frame)
                    row.pop('visible_change',None);row.pop('stable_after_final_glyph',None)
            def destroy(h):
                for ptr,row in list(active.items()):
                    if row['id']==h.reg.r0:
                        row['end']=h.frame
                        if row['glyph_frames']:
                            row['glyph_span']=row['glyph_frames'][-1]-row['glyph_frames'][0]
                        del active[ptr]
            h.on_exec(payload['symbols']['print_task']&~1,task)
            h.on_exec(0x02002680,glyph);h.on_exec(0x0202075c,destroy)
            menus=[]
            h.on_exec(payload['symbols']['load_rows']&~1,lambda h:menus.append(h.reg.r0))
            h.press('X',after=90);h.touch(124,115,after=300);assert menus
            d=menus[-1];opts=h.u32(d+0x24);before=h.u16(opts)
            h.touch((130,177,227)[a.mode],152,after=40)
            h.touch(149,180,after=300);h.press('B',after=90)
            assert h.u16(opts)==(before&~12)|(a.mode<<2)
            # Controlled battle through the game's trainer script command.
            battle[0]=True
            h.trainer_battle(1)
            ready=h.wait_screen('battle_menu',1500)
            h.screenshot('battle-entry')
            assert ready, 'battle did not start'
            h.screenshot('battle-start')
            for turn in range(3):
                start=h.frame;mark=len(report['messages'])
                h.touch(*BATTLE_BUTTONS['fight'],frames=10,after=40)
                h.touch(*MOVE_BUTTONS[0],frames=10,after=90)
                reached=h.run_until(lambda h:h.on_screen('battle_menu') or h.in_field(),3000,every=10)
                h.screenshot(f'turn-{turn+1}')
                assert reached,'turn stuck without A/B; inspect screenshot'
                report['turns'].append({'turn':turn+1,'frames':h.frame-start,'messages':len(report['messages'])-mark,'returned_to_field':h.in_field()})
                if h.in_field():break
            rows=[r for r in report['messages'] if r['glyph_frames']]
            assert len(rows)>=4 and any('used' in r['text'] for r in rows), 'no actual move messages'
            report['memory']={k:getattr(probe,k) for k in ('heap_checks','corrupt','fails','nullw','text_rejections','heap_table_errors','text_probe_errors')}
            assert probe.heap_checks and not any(v for k,v in report['memory'].items() if k!='heap_checks')
        assert digest(a.rom)==report['rom_sha256'] and digest(a.save)==report['save_sha256']
        report['status']='passed'
    finally:
        (a.out/'report.json').write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
