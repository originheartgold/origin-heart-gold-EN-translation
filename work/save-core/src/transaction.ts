import { EditorError } from './errors.js';
import { readSave, crc16 } from './save.js';
import { decodePokemon, patchPokemonFixture } from './pokemon.js';
import type { PokemonFixtureChanges } from './pokemon.js';
import { POCKETS, MONEY_MAX, MONEY_OFFSET, REGISTERED_OFFSET } from './inventory.js';
import type { PocketId, ItemStack, InventoryData } from './inventory.js';

/** Native GetFlagAddr bounds: 0x194 bytes; four following padding bytes are not flags. */
export const SAVED_FLAG_COUNT = 0xca0;
export const SAVED_VAR_BASE = 0x4000;
export const SAVED_VAR_COUNT = 0x170;
const FLAGS = 0x118c, VARS = 0xeac, LOCATION = 0x1324, OBJECTS = 0x2480;
const GENERAL_FOOTER = 0xf7bc;
const POCKET_NAMES = ['items','key','tm','mail','medicine','berries','balls','battle'] as const;
export type FixtureOperation =
  | {type:'setFlag';flag:number;value:boolean}
  | {type:'setVar';var:number;value:number}
  | {type:'setLocation';map:number;x:number;y:number;direction:number|string;warp?:number;which?:number}
  | {type:'placePlayer';map:number;x:number;z:number;direction:number|string;height?:number}
  | {type:'setPocket';name:string;items:readonly (readonly [number,number])[]}
  | {type:'editPartyMon';slot:number;changes:PokemonFixtureChanges;tailPolicy:'preserve'}
  | {type:'setPartyCount';count:number};
export class SaveTransactionError extends EditorError {
  constructor(message: string, readonly operationIndex: number, options?: ErrorOptions) {
    const cause=options?.cause;
    super(cause instanceof EditorError?cause.code:'invalid-input',message,cause instanceof EditorError?cause.context:undefined,options);
  }
}
function integer(value: unknown, min: number, max: number, label: string): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < min || (value as number) > max) throw new EditorError('invalid-input',`${label} must be an integer from ${min} to ${max}.`);
}
function direction(value: unknown): number {
  const names: Record<string,number> = {UP:0,DOWN:1,LEFT:2,RIGHT:3};
  const n = typeof value === 'string' ? names[value] : value;
  integer(n,0,3,'Direction'); return n;
}
export type EditorOperation =
  | {type:'replacePartyRecord';slot:number;record:Uint8Array}
  | {type:'setMoney';money:number}
  | {type:'replacePocket';pocket:PocketId;items:readonly ItemStack[];data:InventoryData};
function fieldKeys(op: FixtureOperation | EditorOperation, policy: 'fixture' | 'editor'): void {
  const fixtureFields: Record<FixtureOperation['type'],string[]> = {
    setFlag:['flag','value'],setVar:['var','value'],setLocation:['map','x','y','direction','warp','which'],
    placePlayer:['map','x','z','direction','height'],setPocket:['name','items'],editPartyMon:['slot','changes','tailPolicy'],setPartyCount:['count'],
  };
  const editorFields: Record<EditorOperation['type'],string[]> = {replacePartyRecord:['slot','record'],setMoney:['money'],replacePocket:['pocket','items','data']};
  const fields: Record<string,string[]> = policy==='fixture'?fixtureFields:editorFields;
  if (!op || typeof op !== 'object' || Array.isArray(op) || typeof op.type!=='string' || !Object.hasOwn(fields,op.type)) throw new EditorError('invalid-input',`Unknown ${policy} operation.`);
  for (const key of Object.keys(op)) if (key !== 'type' && !fields[op.type]!.includes(key)) throw new EditorError('invalid-input',`Unexpected operation field: ${key}.`);
}

function replacePocket(bytes: Uint8Array, base: number, pocketId: PocketId, items: readonly ItemStack[], data: InventoryData): void {
  const pocket = POCKETS.find(p => p.id === pocketId);
  if (!pocket) throw new EditorError('invalid-input', 'Unknown inventory pocket.');
  if (!Array.isArray(items) || items.length > pocket.capacity) throw new EditorError('invalid-input', `${pocket.label} holds at most ${pocket.capacity} different items.`);
  if (!data || typeof data.getItem !== 'function') throw new EditorError('invalid-input', 'Reference data unavailable. Reload the editor before editing inventory.');
  const current=new DataView(bytes.buffer);
  const existing: ItemStack[]=[];
  for(let i=0;i<pocket.capacity;i++) {const at=base+pocket.offset+i*4,id=current.getUint16(at,true),quantity=current.getUint16(at+2,true);if(id||quantity)existing.push({id,quantity});}
  const before={pockets:{[pocket.id]:existing},registeredItems:[current.getUint16(base+REGISTERED_OFFSET,true),current.getUint16(base+REGISTERED_OFFSET+2,true)]};
  const previousIds = new Set(before.pockets[pocket.id]!.map(item => item.id));
  const validated=Array.from(items);
  const seen = new Set<number>();
  validated.forEach(item => {
    if (!item || typeof item !== 'object') throw new EditorError('invalid-input', 'Invalid item stack.');
    integer(item.id,1,790,'Item ID'); integer(item.quantity,1,pocket.maxQuantity,'Quantity');
    const metadata = data.getItem(item.id);
    if (!metadata || metadata.pocket !== pocket.id) throw new EditorError('invalid-input', `Item #${item.id} does not belong in ${pocket.label}.`, {kind: 'wrong-pocket', itemId: item.id, pocketLabel: pocket.label});
    if (seen.has(item.id)) throw new EditorError('invalid-input', `Item #${item.id} occurs more than once. Change its quantity instead.`, {kind: 'duplicate-item', itemId: item.id});
    seen.add(item.id);
  });
  // Native insertion sorts TMs/HMs and berries; quantity-only edits preserve order.
  const ordered = (pocket.nativeId === 3 || pocket.nativeId === 4) && validated.some(item => !previousIds.has(item.id))
    ? validated.sort((a,b) => a.id - b.id) : validated;
  const replacement = new Uint8Array(pocket.capacity * 4), view = new DataView(replacement.buffer);
  ordered.forEach((item,index) => {view.setUint16(index * 4,item.id,true);view.setUint16(index * 4+2,item.quantity,true);});
  // Exact no-op preserves unusual but harmless slot gaps rather than compacting.
  if (items.length === existing.length && items.every((item,index) => item.id === existing[index]!.id && item.quantity === existing[index]!.quantity)) return;
  bytes.set(replacement,base+pocket.offset);
  // Clear only shortcuts for items actually removed from this pocket.
  const removed = new Set(before.pockets[pocket.id]!.filter(item => !seen.has(item.id)).map(item => item.id));
  const registered = before.registeredItems.some(id => removed.has(id))
    ? before.registeredItems.filter(id => id && !removed.has(id)) : [...before.registeredItems];
  while (registered.length < 2) registered.push(0);
  if (registered.some((id,index) => id !== before.registeredItems[index])) {
    const replacement = new Uint8Array(4), shortcuts = new DataView(replacement.buffer);
    registered.forEach((id,index) => shortcuts.setUint16(index * 2,id,true));
    bytes.set(replacement,base+REGISTERED_OFFSET);
  }
}

/** One bounded transaction engine owns all writes and repairs the selected CRC once.
 * No bytes or partial audit results escape on failure. Raw offsets are private. */
function applyTransaction(input: Uint8Array, operations: readonly (FixtureOperation | EditorOperation)[], policy: 'fixture' | 'editor') {
  if(!Array.isArray(operations) || operations.length>10000) throw new EditorError('invalid-input','Expected at most 10000 save operations.');
  const save=readSave(input), bytes=save.bytes, base=save.generalOffset, data=new DataView(bytes.buffer);
  const source=Uint8Array.from(bytes);
  let partyCount=save.partyCount;
  function location(map:unknown,x:unknown,y:unknown,dir:unknown,warp:unknown,which:unknown) {
    integer(map,0,65535,'Map');integer(x,-0x80000000,0x7fffffff,'X');integer(y,-0x80000000,0x7fffffff,'Y');integer(warp,-1,0x7fffffff,'Warp');integer(which,0,4,'Location index');
    const at=base+LOCATION+20*which;
    [map,warp,x,y,direction(dir)].forEach((n,i)=>data.setInt32(at+4*i,n,true));
  }
  Array.from(operations).forEach((op,index)=> {
    try {
      fieldKeys(op, policy);
      for(const key of Object.keys(op)) if (policy==='fixture' && (op as unknown as Record<string,unknown>)[key] === null) throw new EditorError('invalid-input', `Null operation field: ${key}.`);
      switch(op.type) {
        case 'replacePartyRecord': {
          if (!Number.isInteger(op.slot) || op.slot<0 || op.slot>=partyCount) throw new EditorError('invalid-save','Party slot is outside the current party.');
          if (!(op.record instanceof Uint8Array) || (op.record.length !== 136 && op.record.length !== 236)) throw new EditorError('invalid-save','Expected a 136-byte boxed or 236-byte party Pokémon record.');
          const at=base+0x98+op.slot*236, original=decodePokemon(bytes.subarray(at,at+236)), replacement=decodePokemon(op.record);
          if (op.record.length===136 && replacement.pid!==original.pid) throw new EditorError('invalid-pokemon','A boxed replacement must preserve PID because the existing party tail uses it as its encryption key.');
          bytes.set(op.record,at);break;
        }
        case 'setMoney': integer(op.money,0,MONEY_MAX,'Money');data.setUint32(base+MONEY_OFFSET,op.money,true);break;
        case 'replacePocket': replacePocket(bytes,base,op.pocket,op.items,op.data);break;
        case 'setFlag': {
          integer(op.flag,1,SAVED_FLAG_COUNT-1,'Saved flag');if(typeof op.value!=='boolean') throw new EditorError('invalid-input','Flag value must be boolean.');
          const at=base+FLAGS+(op.flag>>>3), mask=1<<(op.flag&7); bytes[at]=op.value ? bytes[at]!|mask : bytes[at]!&~mask;break;
        }
        case 'setVar':integer(op.var,SAVED_VAR_BASE,SAVED_VAR_BASE+SAVED_VAR_COUNT-1,'Saved variable');integer(op.value,0,65535,'Variable value');data.setUint16(base+VARS+2*(op.var-SAVED_VAR_BASE),op.value,true);break;
        case 'setLocation':location(op.map,op.x,op.y,op.direction,op.warp??-1,op.which??0);break;
        case 'placePlayer': {
          integer(op.x,-32768,32767,'Object X');integer(op.z,-32767,32767,'Object Z');const h=op.height??0;integer(h,-32768,32767,'Object height');
          location(op.map,op.x,op.z,op.direction,-1,0);
          for(let slot=0;slot<64;slot++) {
            const at=base+OBJECTS+80*slot;if(!data.getUint32(at,true))continue;const id=bytes[at+8];
            if(id===255||id===253) {const z=op.z-(id===253?1:0);[op.x,h,z,op.x,h,z].forEach((n,i)=>data.setInt16(at+32+i*2,n,true));}
            else bytes.fill(0,at,at+80);
          }break;
        }
        case 'setPocket': {
          const pindex=POCKET_NAMES.indexOf(op.name as typeof POCKET_NAMES[number]); const pocket=POCKETS[pindex];
          if(!pocket || !Array.isArray(op.items)||op.items.length>pocket.capacity)throw new EditorError('invalid-input','Unknown pocket or too many entries.');
          const replacement=new Uint8Array(pocket.capacity*4), rv=new DataView(replacement.buffer);
          Array.from(op.items).forEach((entry,i)=> {if(!Array.isArray(entry)||entry.length!==2)throw new EditorError('invalid-input','Expected item/quantity pairs.');integer(entry[0],1,65535,'Item');integer(entry[1],1,65535,'Quantity');rv.setUint16(i*4,entry[0],true);rv.setUint16(i*4+2,entry[1],true);});
          bytes.set(replacement,base+pocket.offset);break;
        }
        case 'editPartyMon': {
          integer(op.slot,0,partyCount-1,'Active party slot');const at=base+0x98+op.slot*236;
          bytes.set(patchPokemonFixture(bytes.subarray(at,at+236),op.changes,{tailPolicy:op.tailPolicy}),at);break;
        }
        case 'setPartyCount':integer(op.count,1,partyCount,'Shrunken party count');partyCount=op.count;data.setUint32(base+0x94,partyCount,true);break;
      }
    } catch(error) {throw new SaveTransactionError(error instanceof Error?error.message:'Save operation failed.',index,{cause:error});}
  });
  const ranges:{start:number;end:number}[]=[];
  for(let i=base;i<base+GENERAL_FOOTER;i++) if(bytes[i]!==source[i]) {const last=ranges.at(-1);if(last?.end===i)last.end++;else ranges.push({start:i,end:i+1});}
  if(ranges.length) {
    data.setUint16(base+GENERAL_FOOTER+14,crc16(bytes.subarray(base,base+GENERAL_FOOTER)),true);
    for(let i=base+GENERAL_FOOTER+14;i<base+GENERAL_FOOTER+16;i++) if(bytes[i]!==source[i]) {const last=ranges.at(-1);if(last?.end===i)last.end++;else ranges.push({start:i,end:i+1});}
  }
  readSave(bytes);
  return {bytes,report:{profile:'origin-v4.0.3',policy,generalOffset:base,counter:save.counter,changed:ranges.length>0,operations:operations.length,changedRanges:ranges,tailPolicy:policy==='fixture'?'preserve' as const:'caller-supplied' as const,nativeLoadVerified:false}};
}

/** Normal editor operations enforce inventory metadata and closed Pokémon records.
 * Record transformations must recompute cached stats when their inputs change. */
export function applyEditorTransaction(input: Uint8Array, operations: readonly EditorOperation[]) {
  return applyTransaction(input,operations,'editor');
}
/** Fixture policy explicitly permits scenario-only values and stale party tails. */
export function applyFixtureTransaction(input: Uint8Array, operations: readonly FixtureOperation[]) {
  return applyTransaction(input,operations,'fixture');
}
