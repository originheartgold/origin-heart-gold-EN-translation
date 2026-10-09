import { STORAGE_OFFSET, STORAGE_FOOTER, STORAGE_CHUNK_SIZE, GENERAL_CHUNKS, BOX_COUNT, BOX_CAPACITY, BOX_STRIDE, BOX_MODIFIED_OFFSET, TRAINER_NAME_OFFSET, TRAINER_TID_OFFSET, TRAINER_SID_OFFSET, TRAINER_GENDER_OFFSET, TRAINER_LANGUAGE_OFFSET, BADGES_OFFSET, BADGES_2_OFFSET, COINS_OFFSET, PLAY_TIME_OFFSET, DEX_OFFSET, DEX_MARKER, DEX_MAX, DEX_CAUGHT, DEX_SEEN, MG_OFFSET, MG_GIFTS, MG_GIFT_STRIDE, MG_GIFT_COUNT, MG_CARDS, MG_CARD_SIZE, MG_CARD_COUNT, MG_RECEIPTS } from './layout.js';
import { SAVED_FLAG_COUNT, SAVED_VAR_BASE, SAVED_VAR_COUNT, FLAGS_OFFSET as FLAGS, VARS_OFFSET as VARS, LOCATION_OFFSET as LOCATION, OBJECTS_OFFSET as OBJECTS, GENERAL_FOOTER, POCKET_NAMES, PARTY_OFFSET, PARTY_STRIDE, BOXED_SIZE, PARTY_COUNT_OFFSET, LOCATION_COUNT, LOCATION_STRIDE, OBJECT_COUNT, OBJECT_STRIDE } from './layout.js';
import { EditorError } from './errors.js';
import { readSave, crc16 } from './save.js';
import { decodePokemon, patchPokemonFixture, emptyPokemonFixture, encodeName, decodeName } from './pokemon.js';
import type { PokemonFixtureChanges } from './pokemon.js';
import { POCKETS, MONEY_MAX, MONEY_OFFSET, REGISTERED_OFFSET } from './inventory.js';
import type { PocketId, ItemStack, InventoryData } from './inventory.js';

export { SAVED_FLAG_COUNT, SAVED_VAR_BASE, SAVED_VAR_COUNT } from './layout.js';
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
export const COINS_MAX = 50_000, HOURS_MAX = 999;
export interface TrainerProfileChanges { name?: string; gender?: 'male' | 'female'; tid?: number; sid?: number; language?: number }
export type EditorOperation =
  | {type:'replacePartyRecord';slot:number;record:Uint8Array}
  | {type:'appendPartyRecord';record:Uint8Array}
  | {type:'removePartyRecord';slot:number}
  | {type:'replaceBoxRecord';box:number;slot:number;record:Uint8Array}
  | {type:'setMoney';money:number}
  | {type:'replacePocket';pocket:PocketId;items:readonly ItemStack[];data:InventoryData}
  | {type:'setCoins';coins:number}
  | {type:'setPlayTime';hours:number;minutes:number;seconds:number}
  | {type:'setBadge';bank:number;bit:number;earned:boolean}
  | ({type:'setTrainerProfile'} & TrainerProfileChanges)
  | {type:'setPokedex';species:number;seen?:boolean;caught?:boolean}
  | {type:'completePokedex'}
  | {type:'setGiftReceived';id:number;received:boolean}
  | {type:'removePendingGift';slot:number}
  | {type:'removeWonderCard';slot:number}
  | {type:'storeWonderCard';card:Uint8Array};
function fieldKeys(op: FixtureOperation | EditorOperation, policy: 'fixture' | 'editor'): void {
  const fixtureFields: Record<FixtureOperation['type'],string[]> = {
    setFlag:['flag','value'],setVar:['var','value'],setLocation:['map','x','y','direction','warp','which'],
    placePlayer:['map','x','z','direction','height'],setPocket:['name','items'],editPartyMon:['slot','changes','tailPolicy'],setPartyCount:['count'],
  };
  const editorFields: Record<EditorOperation['type'],string[]> = {replacePartyRecord:['slot','record'],appendPartyRecord:['record'],removePartyRecord:['slot'],
    replaceBoxRecord:['box','slot','record'],setMoney:['money'],replacePocket:['pocket','items','data'],setCoins:['coins'],setPlayTime:['hours','minutes','seconds'],
    setBadge:['bank','bit','earned'],setTrainerProfile:['name','gender','tid','sid','language'],setPokedex:['species','seen','caught'],completePokedex:[],
    setGiftReceived:['id','received'],removePendingGift:['slot'],removeWonderCard:['slot'],storeWonderCard:['card']};
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

function boolean(value: unknown, label: string): asserts value is boolean {
  if (typeof value !== 'boolean') throw new EditorError('invalid-input', `${label} must be true or false.`);
}
const giftValid = (tag: number) => tag > 0 && tag < 16;
function record(value: unknown, sizes: readonly number[], label: string): asserts value is Uint8Array {
  if (!(value instanceof Uint8Array) || !sizes.includes(value.length)) throw new EditorError('invalid-pokemon', `Expected a ${label} Pokémon record.`);
}
/** Mark changed byte positions [start,end) of `bytes` against `source` within one block. */
function changedRanges(bytes: Uint8Array, source: Uint8Array, start: number, end: number, ranges: {start:number;end:number}[]): void {
  for(let i=start;i<end;i++) if(bytes[i]!==source[i]) {const last=ranges.at(-1);if(last?.end===i)last.end++;else ranges.push({start:i,end:i+1});}
}
/** Keep an inner chunk CRC current, but only where the source already held a valid one.
 * Native saves maintain some chunk CRCs and leave others zero; neither is invented. */
function maintainChunkCrc(bytes: Uint8Array, source: Uint8Array, start: number, size: number): void {
  const at = start + size, data = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (data.getUint16(at, true) !== crc16(source.subarray(start, at))) return;
  for (let i = start; i < at; i++) if (bytes[i] !== source[i]) { data.setUint16(at, crc16(bytes.subarray(start, at)), true); return; }
}

/** One bounded transaction engine owns all writes and repairs the selected CRC once.
 * No bytes or partial audit results escape on failure. Raw offsets are private. */
function applyTransaction(input: Uint8Array, operations: readonly (FixtureOperation | EditorOperation)[], policy: 'fixture' | 'editor') {
  if(!Array.isArray(operations) || operations.length>10000) throw new EditorError('invalid-input','Expected at most 10000 save operations.');
  const save=readSave(input), bytes=save.bytes, base=save.generalOffset, data=new DataView(bytes.buffer);
  if (policy === 'editor' && save.tied) throw new EditorError('invalid-save', 'Editing equal-counter mirrors is unsupported; save once in-game first');
  const source=Uint8Array.from(bytes), storage=base+STORAGE_OFFSET, gifts=base+MG_OFFSET;
  let partyCount=save.partyCount;
  function location(map:unknown,x:unknown,y:unknown,dir:unknown,warp:unknown,which:unknown) {
    integer(map,0,65535,'Map');integer(x,-0x80000000,0x7fffffff,'X');integer(y,-0x80000000,0x7fffffff,'Y');integer(warp,-1,0x7fffffff,'Warp');integer(which,0,LOCATION_COUNT-1,'Location index');
    const at=base+LOCATION+LOCATION_STRIDE*which;
    [map,warp,x,y,direction(dir)].forEach((n,i)=>data.setInt32(at+4*i,n,true));
  }
  Array.from(operations).forEach((op,index)=> {
    try {
      fieldKeys(op, policy);
      for(const key of Object.keys(op)) if (policy==='fixture' && (op as unknown as Record<string,unknown>)[key] === null) throw new EditorError('invalid-input', `Null operation field: ${key}.`);
      switch(op.type) {
        case 'replacePartyRecord': {
          if (!Number.isInteger(op.slot) || op.slot<0 || op.slot>=partyCount) throw new EditorError('invalid-save','Party slot is outside the current party.');
          if (!(op.record instanceof Uint8Array) || (op.record.length !== BOXED_SIZE && op.record.length !== PARTY_STRIDE)) throw new EditorError('invalid-save','Expected a 136-byte boxed or 236-byte party Pokémon record.');
          const at=base+PARTY_OFFSET+op.slot*PARTY_STRIDE, original=decodePokemon(bytes.subarray(at,at+PARTY_STRIDE)), replacement=decodePokemon(op.record);
          if (op.record.length===BOXED_SIZE && replacement.pid!==original.pid) throw new EditorError('invalid-pokemon','A boxed replacement must preserve PID because the existing party tail uses it as its encryption key.');
          bytes.set(op.record,at);break;
        }
        case 'appendPartyRecord': {
          if (partyCount>=6) throw new EditorError('invalid-save','The party is full. Remove a Pokémon first.');
          record(op.record,[PARTY_STRIDE],'236-byte party');decodePokemon(op.record);
          bytes.set(op.record,base+PARTY_OFFSET+partyCount*PARTY_STRIDE);partyCount++;data.setUint32(base+PARTY_COUNT_OFFSET,partyCount,true);break;
        }
        case 'removePartyRecord': {
          if (!Number.isInteger(op.slot) || op.slot<0 || op.slot>=partyCount) throw new EditorError('invalid-save','Party slot is outside the current party.');
          if (partyCount<=1) throw new EditorError('invalid-save','The party needs at least one Pokémon.');
          const start=base+PARTY_OFFSET, kept=Uint8Array.from(bytes.subarray(start+(op.slot+1)*PARTY_STRIDE,start+partyCount*PARTY_STRIDE));
          bytes.set(kept,start+op.slot*PARTY_STRIDE);bytes.set(emptyPokemonFixture(),start+(partyCount-1)*PARTY_STRIDE);
          partyCount--;data.setUint32(base+PARTY_COUNT_OFFSET,partyCount,true);break;
        }
        case 'replaceBoxRecord': {
          if (!Number.isInteger(op.box)||op.box<0||op.box>=BOX_COUNT||!Number.isInteger(op.slot)||op.slot<0||op.slot>=BOX_CAPACITY) throw new EditorError('invalid-input','PC box or slot is outside storage.');
          record(op.record,[BOXED_SIZE],'136-byte boxed');decodePokemon(op.record);
          const at=storage+op.box*BOX_STRIDE+op.slot*BOXED_SIZE;
          if (op.record.some((byte:number,i:number)=>byte!==bytes[at+i])) {
            bytes.set(op.record,at);
            // The game marks a changed box the same way.
            data.setUint32(storage+BOX_MODIFIED_OFFSET,(data.getUint32(storage+BOX_MODIFIED_OFFSET,true)|(1<<op.box))>>>0,true);
          }
          break;
        }
        case 'setCoins':integer(op.coins,0,COINS_MAX,'Coins');data.setUint16(base+COINS_OFFSET,op.coins,true);break;
        case 'setPlayTime':
          integer(op.hours,0,HOURS_MAX,'Hours');integer(op.minutes,0,59,'Minutes');integer(op.seconds,0,59,'Seconds');
          data.setUint16(base+PLAY_TIME_OFFSET,op.hours,true);bytes[base+PLAY_TIME_OFFSET+2]=op.minutes;bytes[base+PLAY_TIME_OFFSET+3]=op.seconds;break;
        case 'setBadge': {
          integer(op.bank,0,1,'Badge bank');integer(op.bit,0,7,'Badge bit');boolean(op.earned,'Badge state');
          const at=base+(op.bank===0?BADGES_OFFSET:BADGES_2_OFFSET), mask=1<<op.bit;bytes[at]=op.earned?bytes[at]!|mask:bytes[at]!&~mask;break;
        }
        case 'setTrainerProfile': {
          if(op.name!==undefined){
            if(typeof op.name!=='string'||!op.name||[...op.name].length>7)throw new EditorError('invalid-input','Trainer name must have 1–7 characters.');
            const encoded=encodeName(op.name).slice(0,16);
            if(decodeName(new DataView(encoded.buffer),0,8)!==op.name)throw new EditorError('invalid-input','Unsupported trainer name.');
            bytes.set(encoded,base+TRAINER_NAME_OFFSET);
          }
          if(op.tid!==undefined){integer(op.tid,0,65535,'Trainer ID');data.setUint16(base+TRAINER_TID_OFFSET,op.tid,true);}
          if(op.sid!==undefined){integer(op.sid,0,65535,'Secret ID');data.setUint16(base+TRAINER_SID_OFFSET,op.sid,true);}
          if(op.gender!==undefined){if(op.gender!=='male'&&op.gender!=='female')throw new EditorError('invalid-input','Invalid gender.');bytes[base+TRAINER_GENDER_OFFSET]=op.gender==='female'?1:0;}
          if(op.language!==undefined){integer(op.language,1,8,'Language');bytes[base+TRAINER_LANGUAGE_OFFSET]=op.language;}
          break;
        }
        case 'setPokedex': case 'completePokedex': {
          if(data.getUint32(base+DEX_OFFSET,true)!==DEX_MARKER)throw new EditorError('invalid-save','Origin Pokédex marker is missing.');
          const flag=(offset:number,index:number,value:boolean)=>{const at=base+DEX_OFFSET+offset+(index>>3),mask=1<<(index&7);bytes[at]=value?bytes[at]!|mask:bytes[at]!&~mask;};
          if(op.type==='completePokedex'){for(let i=0;i<DEX_MAX;i++){flag(DEX_CAUGHT,i,true);flag(DEX_SEEN,i,true);}break;}
          integer(op.species,1,DEX_MAX,'Pokédex species');
          if(op.seen!==undefined)boolean(op.seen,'Seen');if(op.caught!==undefined)boolean(op.caught,'Caught');
          const index=op.species-1;
          if(op.seen!==undefined)flag(DEX_SEEN,index,op.seen);if(op.caught!==undefined)flag(DEX_CAUGHT,index,op.caught);
          if(op.caught===true)flag(DEX_SEEN,index,true);if(op.seen===false)flag(DEX_CAUGHT,index,false);break;
        }
        case 'setGiftReceived': {
          integer(op.id,0,MG_RECEIPTS-1,'Gift receipt ID');boolean(op.received,'Receipt');
          const at=gifts+(op.id>>3),mask=1<<(op.id&7);bytes[at]=op.received?bytes[at]!|mask:bytes[at]!&~mask;break;
        }
        case 'removePendingGift': {
          integer(op.slot,0,MG_GIFT_COUNT-1,'Pending gift slot');const at=gifts+MG_GIFTS+op.slot*MG_GIFT_STRIDE;
          data.setUint16(at,0,true);data.setUint16(at+2,data.getUint16(at+2,true)&~3,true);break;
        }
        case 'removeWonderCard': {
          integer(op.slot,0,MG_CARD_COUNT-1,'Wonder Card slot');const at=gifts+MG_CARDS+op.slot*MG_CARD_SIZE,id=data.getUint16(at+0x150,true);
          data.setUint16(at,0,true);if(id<MG_RECEIPTS-1)bytes[gifts+(id>>3)]=bytes[gifts+(id>>3)]!&~(1<<(id&7));
          for(let i=0;i<MG_GIFT_COUNT;i++){const gift=gifts+MG_GIFTS+i*MG_GIFT_STRIDE;if(giftValid(data.getUint16(gift,true))&&(data.getUint16(gift+2,true)&3)===op.slot){data.setUint16(gift,0,true);data.setUint16(gift+2,data.getUint16(gift+2,true)&~3,true);}}
          break;
        }
        case 'storeWonderCard': {
          if(!(op.card instanceof Uint8Array)||op.card.length!==MG_CARD_SIZE)throw new EditorError('invalid-input','Expected a Wonder Card.');
          const card=new DataView(op.card.buffer,op.card.byteOffset,op.card.byteLength),tag=card.getUint16(0,true),id=card.getUint16(0x150,true);
          if(!giftValid(tag))throw new EditorError('invalid-input','Unsupported Wonder Card type.');
          if(id>=MG_RECEIPTS-1)throw new EditorError('invalid-input','Unsupported Wonder Card ID.');
          const cards=Array.from({length:MG_CARD_COUNT},(_,slot)=>gifts+MG_CARDS+slot*MG_CARD_SIZE);
          const free=cards.findIndex(at=>!giftValid(data.getUint16(at,true)));
          if(free<0)throw new EditorError('invalid-input','All three Wonder Card slots are occupied.');
          if(cards.some(at=>giftValid(data.getUint16(at,true))&&data.getUint16(at+0x150,true)===id))throw new EditorError('invalid-input','This Wonder Card is already stored.');
          if((bytes[gifts+(id>>3)]!&(1<<(id&7)))&&(op.card[0x152]!&1))throw new EditorError('invalid-input','This unique gift was already received. Clear its receipt flag first if you intend to receive it again.');
          bytes.set(op.card,cards[free]!);
          if(op.card[0x152]!&8){
            const gift=Array.from({length:MG_GIFT_COUNT},(_,slot)=>gifts+MG_GIFTS+slot*MG_GIFT_STRIDE).find(at=>!giftValid(data.getUint16(at,true)));
            if(gift===undefined)throw new EditorError('invalid-input','All eight pending gift slots are occupied.');
            bytes.set(op.card.subarray(0,MG_GIFT_STRIDE),gift);data.setUint16(gift+2,(data.getUint16(gift+2,true)&~3)|free,true);
          }
          bytes[gifts+(id>>3)]=bytes[gifts+(id>>3)]!|(1<<(id&7));break;
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
          for(let slot=0;slot<OBJECT_COUNT;slot++) {
            const at=base+OBJECTS+OBJECT_STRIDE*slot;if(!data.getUint32(at,true))continue;const id=bytes[at+8];
            if(id===255||id===253) {const z=op.z-(id===253?1:0);[op.x,h,z,op.x,h,z].forEach((n,i)=>data.setInt16(at+32+i*2,n,true));
              // Non-zero height also sets the saved fx32 y (+0x2C, height * 8 world units); zero leaves it as saved.
              if(h)data.setInt32(at+0x2c,h*8*0x1000,true);}
            else bytes.fill(0,at,at+OBJECT_STRIDE);
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
          integer(op.slot,0,partyCount-1,'Active party slot');const at=base+PARTY_OFFSET+op.slot*PARTY_STRIDE;
          bytes.set(patchPokemonFixture(bytes.subarray(at,at+PARTY_STRIDE),op.changes,{tailPolicy:op.tailPolicy}),at);break;
        }
        case 'setPartyCount':integer(op.count,1,partyCount,'Shrunken party count');partyCount=op.count;data.setUint32(base+PARTY_COUNT_OFFSET,partyCount,true);break;
      }
    } catch(error) {throw new SaveTransactionError(error instanceof Error?error.message:'Save operation failed.',index,{cause:error});}
  });
  for (const [offset,size] of GENERAL_CHUNKS) maintainChunkCrc(bytes,source,base+offset,size);
  maintainChunkCrc(bytes,source,storage,STORAGE_CHUNK_SIZE);
  const ranges:{start:number;end:number}[]=[];
  changedRanges(bytes,source,base,base+GENERAL_FOOTER,ranges);
  if(ranges.length) {
    data.setUint16(base+GENERAL_FOOTER+14,crc16(bytes.subarray(base,base+GENERAL_FOOTER)),true);
    changedRanges(bytes,source,base+GENERAL_FOOTER+14,base+GENERAL_FOOTER+16,ranges);
  }
  const storageChanged=ranges.length;
  changedRanges(bytes,source,storage,storage+STORAGE_FOOTER,ranges);
  if(ranges.length>storageChanged) {
    data.setUint16(storage+STORAGE_FOOTER+14,crc16(bytes.subarray(storage,storage+STORAGE_FOOTER)),true);
    changedRanges(bytes,source,storage+STORAGE_FOOTER+14,storage+STORAGE_FOOTER+16,ranges);
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
