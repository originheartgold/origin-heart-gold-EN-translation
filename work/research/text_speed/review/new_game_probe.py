"""Read-only emulator observation of native text speed on a fresh save."""
import os,json,sys
from pathlib import Path
out=Path('work/build/text-speed/review/new-game').resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
from desmume.emulator import DeSmuME
from desmume.controls import Keys,keymask
rom=Path('work/build/text-speed/full-build/origin_hg_v4.0.3_en_wip.nds').resolve()
game=out/'game.nds'
if not game.exists():game.symlink_to(rom)
e=DeSmuME();e.open(str(game));u=e.memory.unsigned
frame=0;report=[]
def step(n):
 global frame
 for _ in range(n):e.cycle(with_joystick=False);frame+=1
def press(k,n=6):
 m=keymask(getattr(Keys,'KEY_'+k));e.input.keypad_add_key(m);step(n);e.input.keypad_rm_key(m)
def shot(name):
 e.screenshot().save(str(out/(name+'.png')))
 save=u.read_long(0x021106c8)
 d={'name':name,'frame':frame,'save':hex(save),'save_flag':u.read_long(save+4) if save else None}
 report.append(d);print(d,flush=True)
for cmd in sys.argv[1].split(';'):
 q=cmd.split()
 if q[0]=='wait':step(int(q[1]))
 elif q[0]=='press':press(q[1],int(q[2]) if len(q)>2 else 6)
 elif q[0]=='shot':shot(q[1])
 elif q[0]=='touch':e.input.touch_set_pos(int(q[1]),int(q[2]));step(6);e.input.touch_release()
 elif q[0]=='state':e.savestate.save_file(str(out/(q[1]+'.dst')))
 elif q[0]=='load':e.savestate.load_file(str(out/(q[1]+'.dst')))
 else:raise ValueError(cmd)
(out/'report.json').write_text(json.dumps(report,indent=2));e.destroy()
