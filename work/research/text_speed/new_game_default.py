"""Read-only blank-battery Options initialization and publication-order check."""
import argparse,json,os,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();a.rom,a.out=a.rom.resolve(),a.out.resolve()
    if not a.out.is_relative_to(ROOT/'work/build') or a.out==ROOT/'work/build':p.error('Use work/build')
    a.out.mkdir(parents=True,exist_ok=True)
    identity=hashlib.sha256(a.rom.read_bytes()).hexdigest()
    report={'status':'failed','rom_sha256':identity,'read_only':True,'events':[]}
    try:
        with tempfile.TemporaryDirectory(dir=a.out) as td:
            out=Path(td);os.environ['XDG_CONFIG_HOME']=str(out/'config')
            from desmume.emulator import DeSmuME
            game=out/'game.nds';game.symlink_to(a.rom)
            e=DeSmuME()
            try:
                e.open(str(game));u=e.memory.unsigned;r=e.memory.register_arm9;callbacks=[]
                for address,label in [(0x02027624,'constructor-entry'),(0x020282d4,'metadata-init'),(0x02027920,'new-game-init'),(0x0202770c,'constructor-ready'),(0x02000cda,'before-publication'),(0x02000cdc,'after-publication')]:
                    def cb(addr,size,label=label):
                        runtime=u.read_long(0x021106c8)
                        save=runtime if label=='after-publication' else r.r0 if label in ('constructor-ready','before-publication') else None
                        event={'event':label,'runtime':runtime}
                        if save:event.update(save=save,flag=u.read_long(save+4),options=u.read_short(save+0x10+u.read_long(save+0x2e02c)),block1_id=u.read_long(save+0x2e024),block1_offset=u.read_long(save+0x2e02c))
                        report['events'].append(event)
                    callbacks.append(cb);e.memory.register_exec(address,cb)
                for _ in range(2400):e.cycle(with_joystick=False)
                log=report['events']
                assert [x['event'] for x in log]==['constructor-entry','metadata-init','new-game-init','constructor-ready','before-publication','after-publication'],log
                assert all(x['runtime']==0 for x in log[:-1])
                assert all(x['block1_id']==1 and x['block1_offset']>0 and x['options']==516 for x in log if 'save' in x),log
                last=log[-1];assert last['runtime']==last['save'] and last['flag']==0
            finally:e.destroy()
        assert hashlib.sha256(a.rom.read_bytes()).hexdigest()==identity
        report['status']='passed'
    finally:(a.out/'report.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
