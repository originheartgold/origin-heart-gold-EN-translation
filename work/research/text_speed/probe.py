import sys,os,json,hashlib
from pathlib import Path
sys.path.insert(0,str(Path('work/tools').resolve()))
from desmume.emulator import DeSmuME
from desmume.controls import Keys,keymask
import memcheck
name=sys.argv[1];mode=sys.argv[2];out=Path('work/build/text-speed')/f'{name}-{mode}';out.mkdir(parents=True,exist_ok=True);out=out.resolve()
root=Path('/Users/simonvergauwen/Developer/poke')
rom=root/('work/rom/origin_v4.0.3_cn.nds' if name=='cn' else 'work/build/origin_hg_v4.0.3_en_wip.nds')
save=root/'work/build/memcheck/trainer.sav'
game=out/'game.nds'
if not game.exists():game.symlink_to(rom)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
e=DeSmuME();e.open(str(game));e.backup.import_file(str(save),524288);e.reset()
p=memcheck.Probe(e);u=e.memory.unsigned;r=e.memory.register_arm9
starts=[];glyphs=[];returns={};budgets={};loops=[];enabled=False

def start(a,b):
 if enabled:starts.append({'frame':p.frame,'speed':r.r1,'callback':r.r2,'font':u.read_byte(r.r0+9)})
def glyph(a,b):
 if enabled:glyphs.append({'frame':p.frame,'ptr':r.r4,'x':u.read_short(r.r4+12),'y':u.read_short(r.r4+14)})
def task(a,b):
 if enabled:budgets[r.r1]=({'normal':1,'lazy':1,'fast':3,'instant':128}[mode])-1

def result(a,b):
 if enabled:returns[r.r4]=r.r0

def repeat(a,b):
 if not enabled or mode in ('normal','lazy'):return
 ptr=r.r4
 if r.r0!=0 or budgets.get(ptr,0)<=0:return
 if u.read_long(ptr+0x1c)!=0 or u.read_byte(ptr+0x28)!=0 or u.read_byte(ptr+0x2a)!=0:return
 next_unit=u.read_short(u.read_long(ptr))
 if next_unit in (0xffff,0xfffe,0x25bc,0x25bd):return
 budgets[ptr]-=1;loops.append(p.frame);r.r0=2
for address,fn in [(0x020208d4,start),(0x02002680,glyph),(0x02020a1c,task),(0x02020a94,repeat)]:e.memory.register_exec(address,fn)
def step(n):
 for _ in range(n):
  e.cycle(with_joystick=False);p.frame+=1
  if p.armed and p.frame%10==0 and p.corrupt is None:
   bad=p.heap_walk()
   if bad:p.corrupt=(p.frame,bad)
def press(k,n=6):
 m=keymask(getattr(Keys,'KEY_'+k));e.input.keypad_add_key(m);step(n);e.input.keypad_rm_key(m)
checkpoint=Path('work/build/text-speed/controlled-before.dst').resolve()
if name=='en' and checkpoint.exists():
 e.savestate.load_file(str(checkpoint));p.frame=3418
else:
 step(2400);press('START');step(400);press('A');step(300);press('A');step(300)
 if name=='en':e.savestate.save_file(str(checkpoint))
if mode=='lazy':
 assert u.read_short(0x0200ba9a)==0x1c05
 e.memory.write_short(0x0200ba9a,0x2501)
e.screenshot().save(str(out/'before.png'));enabled=True;p.armed=True;startframe=p.frame
for i in range(3):
 press('A',1);step(239);e.screenshot().save(str(out/f'page-{i}.png'))
report={'rom':str(rom),'sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'mode':mode,'start':startframe,'starts':starts,'glyphs':glyphs,'loops':loops,'heap_checks':p.heap_checks,'corrupt':p.corrupt,'allocation_failures':p.fails,'null_writes':p.nullw,'message_loads':p.message_loads,'text_rejections':p.text_rejections}
(out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('glyphs','loops','message_loads')}));e.destroy()
