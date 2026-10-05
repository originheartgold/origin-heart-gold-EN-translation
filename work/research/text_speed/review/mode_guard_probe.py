"""Controlled RAM experiment: vary only cartridge-save-exists in a live checkpoint.

This is deliberately NOT natural new-game playback or a read-only runtime probe.
It never edits source ROMs/saves. Inputs are the existing reviewed native-v5 ROM
and its own before-talk checkpoint, with naturally confirmed INSTANT options.
"""
import os,sys,json
from pathlib import Path
flag=int(sys.argv[1]);assert flag in (0,1)
out=Path(f'work/build/text-speed/review/mode-guard-{flag}').resolve();out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
from desmume.emulator import DeSmuME
from desmume.controls import Keys,keymask
rom=Path('work/build/text-speed/native-v5/game.nds').resolve()
game=out/'game.nds'
if not game.exists():game.symlink_to(rom)
e=DeSmuME();e.open(str(game));e.savestate.load_file(str(Path('work/build/text-speed/trainer-options/before-talk.dst').resolve()))
u=e.memory.unsigned;r=e.memory.register_arm9
save=u.read_long(0x021106c8);options=save+0x10+u.read_long(save+0x2e01c+16)
assert u.read_short(options)==520,(hex(options),u.read_short(options))
e.memory.write_long(save+4,flag)
frame=[0];original=[];native=[];glyphs=[]
payload=json.loads(Path('work/patches/text_speed/payload.json').read_text())
def task(a,b):
 p=r.r1;native.append({'frame':frame[0],'callback':u.read_long(p+0x1c),'delay':u.read_byte(p+0x29)&127,'state':u.read_byte(p+0x28)})
def old(a,b):original.append(frame[0])
def glyph(a,b):glyphs.append(frame[0])
e.memory.register_exec(payload['symbols']['print_task']&~1,task)
e.memory.register_exec(0x02020a1c,old);e.memory.register_exec(0x02002680,glyph)
for i in range(240):
 if i==0:e.input.keypad_add_key(keymask(Keys.KEY_A))
 if i==1:e.input.keypad_rm_key(keymask(Keys.KEY_A))
 frame[0]=i;e.cycle(with_joystick=False)
e.screenshot().save(str(out/'dialogue.png'))
result={'controlled_memory_change':{'address':hex(save+4),'value':flag},'saved_options':u.read_short(options),'native_tasks':native,'original_task_frames':original,'glyph_frames':glyphs}
(out/'report.json').write_text(json.dumps(result,indent=2));print({'flag':flag,'saved_options':result['saved_options'],'native_calls':len(native),'original_calls':len(original),'glyphs':len(glyphs),'glyph_span':max(glyphs)-min(glyphs) if glyphs else None},flush=True);e.destroy()
