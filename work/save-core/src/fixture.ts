import { readSave } from './save.js';
import { decodePokemonDetails } from './pokemon.js';
import { POCKETS } from './inventory.js';
import { SAVED_FLAG_COUNT, SAVED_VAR_COUNT } from './transaction.js';
export { SAVED_FLAG_COUNT, SAVED_VAR_BASE, SAVED_VAR_COUNT, SaveTransactionError, applyFixtureTransaction as applySaveTransaction } from './transaction.js';
export type { FixtureOperation } from './transaction.js';
const FLAGS = 0x118c, VARS = 0xeac, LOCATION = 0x1324, OBJECTS = 0x2480;
const POCKET_NAMES = ['items','key','tm','mail','medicine','berries','balls','battle'] as const;

function readLocation(data: DataView, base: number, which: number) {
  const at=base+LOCATION+which*20;
  return {map:data.getInt32(at,true),warp:data.getInt32(at+4,true),x:data.getInt32(at+8,true),y:data.getInt32(at+12,true),dir:data.getInt32(at+16,true)};
}
/** Inspection does not turn checksum validity into a playability guarantee. */
export function inspectSaveFixture(input: Uint8Array) {
  const save=readSave(input), data=new DataView(save.bytes.buffer), base=save.generalOffset;
  const pockets: Record<string,number[][]>={};
  POCKETS.forEach((p,index) => {
    const entries:number[][]=[];
    for (let slot=0;slot<p.capacity;slot++) { const at=base+p.offset+slot*4; const id=data.getUint16(at,true); if(id) entries.push([id,data.getUint16(at+2,true)]); }
    pockets[POCKET_NAMES[index]!] = entries;
  });
  const mapObjects=[];
  for(let slot=0;slot<64;slot++) {
    const at=base+OBJECTS+slot*80;
    if(data.getUint32(at,true)) mapObjects.push({slot,id:data.getUint8(at+8),map:data.getUint16(at+16,true),sprite:data.getUint16(at+18,true),x:data.getInt16(at+38,true),z:data.getInt16(at+42,true)});
  }
  return {base,counter:save.counter,tied:save.tied,partyCount:save.partyCount,
    party:save.partyRecords.map(decodePokemonDetails),locations:Array.from({length:5},(_,i)=>readLocation(data,base,i)),pockets,mapObjects,
    flags:save.bytes.slice(base+FLAGS,base+FLAGS+SAVED_FLAG_COUNT/8),vars:Array.from({length:SAVED_VAR_COUNT},(_,i)=>data.getUint16(base+VARS+i*2,true))};
}
