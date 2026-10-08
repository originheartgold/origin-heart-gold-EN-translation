"""Controlled RAM cases using a checkpoint booted from this exact fixed ROM.

Not natural fresh-game playback or heap certification. Only isolated live RAM
is changed, never the source ROM, checkpoint, or imported battery save.
"""
import hashlib, json, os, sys
from pathlib import Path
case=sys.argv[1]
root=Path('work/build/text-speed/save-readiness-fix').resolve()
out=root/case;out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
from desmume.emulator import DeSmuME
from desmume.controls import Keys,keymask
rom=root/'game.nds';game=out/'game.nds'
if not game.exists():game.symlink_to(rom)
payload=json.loads((root/'payload.json').read_text())
e=DeSmuME();e.open(str(game));e.savestate.load_file(str(root/'checkpoint/before-talk.dst'))
u=e.memory.unsigned;r=e.memory.register_arm9
save=u.read_long(0x021106c8);options=save+0x10+u.read_long(save+0x2e02c)
assert save and u.read_short(options)==512
assert bytes(u.read_byte(payload['base']+i) for i in range(len(bytes.fromhex(payload['code']))))==bytes.fromhex(payload['code']), 'Checkpoint must contain fixed native code'
mode={'normal':0,'fast':1,'instant':2,'invalid':3,'null':2}.get(case,0)
flag=1 if case.startswith('old-music-') else 0
music=int(case[-1]) if case.startswith('old-music-') else 0
value=512 | (mode<<2) | music
e.memory.write_long(save+4,flag);e.memory.write_short(options,value)
frame=[0];native=[];original=[];glyphs=[];masked=[False];getter_calls=[]
def restore():
 if masked[0]:e.memory.write_long(0x021106c8,save);masked[0]=False
def task(a,b):
 p=r.r1;native.append({'frame':frame[0],'callback':u.read_long(p+0x1c),'delay':u.read_byte(p+0x29)&127})
 if case=='null':e.memory.write_long(0x021106c8,0);masked[0]=True
def old(a,b):restore();original.append(frame[0])
def render(a,b):restore()
def getter(a,b):
 if masked[0]:getter_calls.append(frame[0])
def glyph(a,b):glyphs.append(frame[0])
e.memory.register_exec(payload['symbols']['print_task']&~1,task)
e.memory.register_exec(0x02020a1c,old);e.memory.register_exec(0x02020a88,render)
e.memory.register_exec(0x02029348,getter);e.memory.register_exec(0x02002680,glyph)
for i in range(240):
 if i==0:e.input.keypad_add_key(keymask(Keys.KEY_A))
 if i==1:e.input.keypad_rm_key(keymask(Keys.KEY_A))
 frame[0]=i;e.cycle(with_joystick=False)
 assert not masked[0]
assert native and glyphs
assert u.read_short(options)==value and u.read_long(save+4)==flag
if case in ('fast','instant'):assert not original
else:assert original
assert not getter_calls, 'Null runtime must bypass Options lookup'
span=max(glyphs)-min(glyphs)
if case=='fast':assert span<54
elif case=='instant':assert span<=3
else:assert span>=54
report={'case':case,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest(),'controlled_ram':{'save_exists':flag,'options':value,'null_runtime_only_during_mode':case=='null'},'native_calls':len(native),'original_calls':len(original),'glyph_count':len(glyphs),'glyph_span':span,'glyph_frames':glyphs,'passed':True}
e.screenshot().save(str(out/'dialogue.png'));(out/'report.json').write_text(json.dumps(report,indent=2));print(report,flush=True);e.destroy()
