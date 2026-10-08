"""Inspect untouched CN facility code; dump disassembly only to ignored work/build."""
from pathlib import Path
import struct
import ndspy.rom
import capstone
ROOT=Path.cwd(); OUT=ROOT/'work/build/trainer_verification/facilities'
ROM=ROOT/'work/rom/origin_v4.0.3_cn.nds'
def load():
 r=ndspy.rom.NintendoDSRom.fromFile(str(ROM))
 return r,{'arm9':(r.arm9RamAddress,bytes(r.arm9)),**{f'ov{k}':(v.ramAddress,bytes(v.data)) for k,v in r.loadArm9Overlays().items()}}
def disasm(data,base):
 m=capstone.Cs(capstone.CS_ARCH_ARM,capstone.CS_MODE_THUMB);m.skipdata=True
 for i in m.disasm(data,base):
  extra=''
  if i.mnemonic=='ldr' and '[pc' in i.op_str:
   s=i.op_str.split('#')[-1].split(']')[0] if '#' in i.op_str else '0'
   a=((i.address+4)&~3)+int(s,0)
   if base<=a<=base+len(data)-4:extra=f' ; [{a:08x}]={struct.unpack_from("<I",data,a-base)[0]:08x}'
  yield i,f'{i.address:08x} {i.mnemonic} {i.op_str}{extra}'
def main():
 OUT.mkdir(parents=True,exist_ok=True);r,images=load();hits=[]
 for name,(base,data) in images.items():
  ins=list(disasm(data,base));lines=[s for i,s in ins]
  # NARC read wrappers, general archive resolver, known facility consumers.
  for n,(i,s) in enumerate(ins):
   if i.mnemonic in ('bl','b') and i.op_str in {f'#{x:#x}' for x in (0x2007424,0x2007440,0x2007838,0x204b19c,0x204b18c,0x204ad50,0x204af14)}:
    hits.append(name+'\n'+'\n'.join(lines[max(0,n-10):n+3]))
  if name=='arm9' or 60<=int(name[2:])<=90:
   (OUT/f'{name}.txt').write_text('\n'.join(lines)+'\n')
 (OUT/'calls.txt').write_text('\n\n'.join(hits)+'\n')
 print(f'Scanned {len(images)} images, found {len(hits)} candidate call sites')
if __name__=='__main__':main()
