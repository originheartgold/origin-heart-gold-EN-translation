import {readSave,patchGeneralRegion} from './save.js';
import {decodeName,decodePokemon} from './pokemon.js';
import {importPokemonFile} from './operations.js';
import {type BundledOriginData} from './bundled-data.js';
import {EditorError} from './errors.js';
// Native rc5 save table entry 27 at 0x020f327c; size getter 0x0202ddd0.
export const MG_OFFSET=0x9ee0,MG_SIZE=0x1680,CARD_SIZE=0x358;
const valid=(tag:number)=>tag>0&&tag<16;
function block(bytes:Uint8Array):Uint8Array {const save=readSave(bytes);return save.bytes.slice(save.generalOffset+MG_OFFSET,save.generalOffset+MG_OFFSET+MG_SIZE);}
function cardOffset(slot:number):number {if(!Number.isInteger(slot)||slot<0||slot>2)throw new EditorError('invalid-input','Choose Wonder Card slot 1–3.');return 0x920+slot*CARD_SIZE;}
function view(bytes:Uint8Array):DataView{return new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);}
export function readMysteryGifts(bytes:Uint8Array){const raw=block(bytes),dv=view(raw);return {received:Array.from({length:2048},(_,i)=>!!(raw[i>>3]!&(1<<(i&7)))),gifts:Array.from({length:8},(_,slot)=>{const offset=0x100+slot*0x104;return{slot,tag:dv.getUint16(offset,true),cardSlot:dv.getUint16(offset+2,true)&3};}),cards:Array.from({length:3},(_,slot)=>{const offset=cardOffset(slot);return{slot,tag:dv.getUint16(offset,true),id:dv.getUint16(offset+0x150,true),title:decodeName(dv,offset+0x104,36),bytes:raw.slice(offset,offset+CARD_SIZE)};}),specialTag:dv.getUint16(0x1328,true)};}
export function patchGiftReceived(bytes:Uint8Array,id:number,received:boolean):Uint8Array {if(!Number.isInteger(id)||id<0||id>2047||typeof received!=='boolean')throw new EditorError('invalid-input','Gift receipt ID must be 0–2047.');const raw=block(bytes),index=id>>3,mask=1<<(id&7);raw[index]=received?raw[index]!|mask:raw[index]!&~mask;return patchGeneralRegion(bytes,MG_OFFSET+index,raw.slice(index,index+1));}
export function removePendingGift(bytes:Uint8Array,slot:number):Uint8Array {if(!Number.isInteger(slot)||slot<0||slot>7)throw new EditorError('invalid-input','Choose pending gift slot 1–8.');const raw=block(bytes),offset=0x100+slot*0x104,dv=view(raw);dv.setUint16(offset,0,true);dv.setUint16(offset+2,dv.getUint16(offset+2,true)&~3,true);return patchGeneralRegion(bytes,MG_OFFSET+offset,raw.slice(offset,offset+4));}
export function removeWonderCard(bytes:Uint8Array,slot:number):Uint8Array {const raw=block(bytes),offset=cardOffset(slot),dv=view(raw),id=dv.getUint16(offset+0x150,true);dv.setUint16(offset,0,true);if(id<2047)raw[id>>3]=raw[id>>3]!&~(1<<(id&7));for(let i=0;i<8;i++){const gift=0x100+i*0x104;if(valid(dv.getUint16(gift,true))&&(dv.getUint16(gift+2,true)&3)===slot){dv.setUint16(gift,0,true);dv.setUint16(gift+2,dv.getUint16(gift+2,true)&~3,true);}}return patchGeneralRegion(bytes,MG_OFFSET,raw);}
export function exportWonderCard(bytes:Uint8Array,slot:number):string {const card=readMysteryGifts(bytes).cards[slot];if(!card||!valid(card.tag))throw new EditorError('invalid-input','Choose an occupied Wonder Card.');return JSON.stringify({format:'origin-heartgold-wonder-card',version:1,bytes:[...card.bytes]},null,2);}
export function importWonderCard(bytes:Uint8Array,text:string,data:BundledOriginData):Uint8Array {
 const value=JSON.parse(text);if(value.format!=='origin-heartgold-wonder-card'||value.version!==1||!Array.isArray(value.bytes)||value.bytes.length!==CARD_SIZE||value.bytes.some((n:unknown)=>!Number.isInteger(n)||Number(n)<0||Number(n)>255))throw new EditorError('invalid-input','Choose an Origin .ohgwc4 file.');
 const card=Uint8Array.from(value.bytes),cdv=view(card),tag=cdv.getUint16(0,true),id=cdv.getUint16(0x150,true);
 if(![1,2,3].includes(tag))throw new EditorError('invalid-input','Only native Pokémon, Egg and Item gift imports are validated.');
 if(id>=2047)throw new EditorError('invalid-input','Unsupported Wonder Card ID.');
 if(tag===3){const item=cdv.getUint32(4,true);if(!data.inventory.getItem(item)||data.inventory.getItem(item)!.name.startsWith('Item #'))throw new EditorError('invalid-input','Unknown Origin gift item.');}
 else {const offset=tag===1?8:4,record=card.slice(offset,offset+236);importPokemonFile(JSON.stringify({format:'origin-heartgold-pokemon',version:1,bytes:[...record]}),data);if(tag===2&&!decodePokemon(record).isEgg)throw new EditorError('invalid-input','Egg gift does not contain an egg.');}
 const state=readMysteryGifts(bytes),slot=state.cards.find(c=>!valid(c.tag))?.slot;if(slot===undefined)throw new EditorError('invalid-input','All three Wonder Card slots are occupied.');
 if(state.cards.some(c=>valid(c.tag)&&c.id===id))throw new EditorError('invalid-input','This Wonder Card is already stored.');
 if(state.received[id]&&(card[0x152]!&1))throw new EditorError('invalid-input','This unique gift was already received. Clear its receipt flag first if you intend to receive it again.');
 const raw=block(bytes);raw.set(card,cardOffset(slot));
 if(card[0x152]!&8){const gift=state.gifts.find(g=>!valid(g.tag));if(!gift)throw new EditorError('invalid-input','All eight pending gift slots are occupied.');const offset=0x100+gift.slot*0x104;raw.set(card.slice(0,0x104),offset);view(raw).setUint16(offset+2,(view(raw).getUint16(offset+2,true)&~3)|slot,true);}
 raw[id>>3]=raw[id>>3]!|(1<<(id&7));return patchGeneralRegion(bytes,MG_OFFSET,raw);
}
