"""Run a native patched-ROM menu scenario; instrumentation is read-only."""
import os,sys,json,hashlib
from pathlib import Path
TOOLS=Path(__file__).resolve().parents[2]/'tools'
sys.path.insert(0,str(TOOLS))
out=Path(sys.argv[1]).resolve()
if not out.is_relative_to(TOOLS.parent/'build'):
 raise ValueError('Artifacts must stay in this worktree work/build')
out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
from desmume.emulator import DeSmuME
from desmume.controls import Keys,keymask
import memcheck
rom=Path(sys.argv[2]).resolve();save=Path(sys.argv[3]).resolve();script=sys.argv[4]
game=out/'game.nds'
if game.exists() and game.resolve()!=rom:
 raise ValueError('Output already belongs to a different ROM')
if not game.exists():game.symlink_to(rom)
e=DeSmuME();e.open(str(game));assert e.backup.import_file(str(save),524288);e.reset();p=memcheck.Probe(e)
u=e.memory.unsigned;r=e.memory.register_arm9;menus=[];snapshots=[];glyphs=[];starts=[];menu_live=[False];options_ptr=[None]
payload_path=rom.parent/'payload.json'
if not payload_path.exists():payload_path=Path('work/patches/text-speed/payload.json')
payload=json.loads(payload_path.read_text())
def menu(a,b):
 menus.append(r.r0);menu_live[0]=True;options_ptr[0]=u.read_long(r.r0+0x24)
def closing(a,b):menu_live[0]=False
def glyph(a,b):
 if p.armed:glyphs.append({'frame':p.frame,'printer':r.r4,'x':u.read_short(r.r4+12),'y':u.read_short(r.r4+14),'font':u.read_byte(r.r4+9)})
def start(a,b):
 if p.armed:starts.append({'frame':p.frame,'speed':r.r1,'callback':r.r2,'font':u.read_byte(r.r0+9)})
e.memory.register_exec(payload['symbols']['load_rows']&~1,menu)
e.memory.register_exec(payload['symbols']['exit_free']&~1,closing)
e.memory.register_exec(0x02002680,glyph);e.memory.register_exec(0x020208d4,start)
def step(n):
 for _ in range(n):
  e.cycle(with_joystick=False);p.frame+=1
  if p.armed and p.frame%10==0 and p.corrupt is None:
   bad=p.heap_walk()
   if bad:p.corrupt=(p.frame,bad)
def press(k,n=6):
 mask=keymask(getattr(Keys,'KEY_'+k));e.input.keypad_add_key(mask);step(n);e.input.keypad_rm_key(mask)
for cmd in script.split(';'):
 q=cmd.strip().split()
 if not q:continue
 if q[0] in ('boot','fieldboot'):
  step(2400);press('START');step(400)
  for _ in range(4 if q[0]=='boot' else 2):press('A');step(300)
  if q[0]=='boot':step(600)
  p.armed=True
 elif q[0]=='wait':step(int(q[1]))
 elif q[0]=='press':press(q[1],int(q[2]) if len(q)>2 else 6)
 elif q[0]=='touch':
  e.input.touch_set_pos(int(q[1]),int(q[2]));step(6);e.input.touch_release()
 elif q[0]=='shot':
  e.screenshot().save(str(out/(q[1]+'.png')))
  s={'name':q[1],'frame':p.frame,'palette13':[u.read_short(0x05000000+13*32+2*i) for i in range(16)]}
  if options_ptr[0]:s['saved_options']=u.read_short(options_ptr[0])
  if menus and menu_live[0]:
   ptr=menus[-1];s.update(menu=ptr,selection=(u.read_long(ptr+16)>>2)&7,rows=[{'count':u.read_short(ptr+0x84+i*84),'value':u.read_short(ptr+0x86+i*84)} for i in range(8)],saved_options=u.read_short(u.read_long(ptr+0x24)))
  snapshots.append(s);print(s,flush=True)
 elif q[0]=='export':assert e.backup.export_file(str(out/(q[1]+'.sav')))
 elif q[0]=='reset':e.reset();menus.clear();menu_live[0]=False;options_ptr[0]=None;p.armed=False
 elif q[0]=='state':e.savestate.save_file(str(out/(q[1]+'.dst')))
 elif q[0]=='load':
  checkpoint=Path(q[1]).resolve();e.savestate.load_file(str(checkpoint));p.armed=True
  prior=json.loads((checkpoint.parent/'report.json').read_text())
  menus.extend([row['menu'] for row in prior['snapshots'] if 'menu' in row][:1])
  if menus:menu_live[0]=True;options_ptr[0]=u.read_long(menus[-1]+0x24)
 else:raise ValueError(cmd)
report={'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'snapshots':snapshots,'starts':starts,'glyphs':glyphs,'heap_checks':p.heap_checks,'heap_table_errors':p.heap_table_errors,'text_probe_errors':p.text_probe_errors,'minimum_spare':p.minspare,'corrupt':p.corrupt,'failures':p.fails,'null_writes':p.nullw,'text_rejections':p.text_rejections,'message_loads':p.message_loads}
report['memory_status']='passed' if p.heap_checks and not any([p.corrupt,p.fails,p.nullw,p.text_rejections,p.heap_table_errors,p.text_probe_errors]) else 'failed'
(out/'report.json').write_text(json.dumps(report,indent=2));e.destroy()
if report['memory_status']!='passed':raise SystemExit('Native memory checks failed; inspect report.json')
