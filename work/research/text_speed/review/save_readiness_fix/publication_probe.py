"""Read-only publication-order observation; no battery import or RAM writes."""
import json,os
from pathlib import Path
root=Path('work/build/text-speed/save-readiness-fix').resolve();out=root/'publication';out.mkdir(parents=True,exist_ok=True)
os.environ['XDG_CONFIG_HOME']=str(out/'config')
from desmume.emulator import DeSmuME
rom=root/'game.nds';game=out/'game.nds'
if not game.exists():game.symlink_to(rom)
e=DeSmuME();e.open(str(game));u=e.memory.unsigned;r=e.memory.register_arm9
log=[];callbacks=[]
for address,label in [(0x02027624,'constructor-entry'),(0x020282d4,'metadata-init'),(0x02027920,'new-game-init'),(0x0202770c,'constructor-ready'),(0x02000cda,'before-publication'),(0x02000cdc,'after-publication')]:
 def cb(a,b,label=label):
  runtime=u.read_long(0x021106c8);save=runtime if label=='after-publication' else r.r0 if label in ('constructor-ready','before-publication') else None
  event={'event':label,'runtime':runtime}
  if save:
   event.update(save=save,flag=u.read_long(save+4),options=u.read_short(save+0x10+u.read_long(save+0x2e02c)),block1_id=u.read_long(save+0x2e024),block1_offset=u.read_long(save+0x2e02c))
  log.append(event)
 callbacks.append(cb);e.memory.register_exec(address,cb)
for _ in range(2400):e.cycle(with_joystick=False)
assert [x['event'] for x in log]==['constructor-entry','metadata-init','new-game-init','constructor-ready','before-publication','after-publication'],log
assert all(x['runtime']==0 for x in log[:-1])
assert all(x['block1_id']==1 and x['block1_offset']>0 and x['options']==512 for x in log if 'save' in x),log
a=log[-1];assert a['runtime']==a['save'] and a['flag']==0 and a['block1_id']==1 and (a['options']&15)==0,a
(out/'report.json').write_text(json.dumps({'read_only':True,'events':log,'passed':True},indent=2));print(log,flush=True);e.destroy()
