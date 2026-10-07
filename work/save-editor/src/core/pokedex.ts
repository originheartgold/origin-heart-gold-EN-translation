import {readSave,patchGeneralRegion} from './save.js';
import {EditorError} from './errors.js';
/** Origin rc5 native readers 0x0202a508/0x0202a554: caught +4, seen +0xcc,
 * species (id-1) bit. Save marker at general+0x13a8. Max native ID is 1025.
 * Only these verified flags are edited; gender/form/language records are preserved. */
export const DEX_OFFSET=0x13a8,DEX_MAX=1025,DEX_CAUGHT=4,DEX_SEEN=0xcc;
function dex(bytes:Uint8Array){const save=readSave(bytes);if(new DataView(save.bytes.buffer).getUint32(save.generalOffset+DEX_OFFSET,true)!==0xbeefcafe)throw new EditorError('invalid-save','Origin Pokédex marker is missing.');return save;}
export function readPokedex(bytes:Uint8Array):{seen:boolean[];caught:boolean[];seenCount:number;caughtCount:number}{
 const save=dex(bytes),flag=(offset:number)=>Array.from({length:DEX_MAX},(_,i)=>!!(save.bytes[save.generalOffset+DEX_OFFSET+offset+(i>>3)]!&(1<<(i&7))));
 const seen=flag(DEX_SEEN),caught=flag(DEX_CAUGHT);return{seen,caught,seenCount:seen.filter(Boolean).length,caughtCount:caught.filter(Boolean).length};
}
export function patchPokedex(bytes:Uint8Array,species:number,changes:{seen?:boolean;caught?:boolean}):Uint8Array {
 if(!Number.isInteger(species)||species<1||species>DEX_MAX)throw new EditorError('invalid-input','Choose a base species from 1–1025.');
 for(const value of Object.values(changes))if(typeof value!=='boolean')throw new EditorError('invalid-input','Invalid Pokédex flag.');
 const save=dex(bytes),index=(species-1)>>3,mask=1<<((species-1)&7);let result=bytes;
 const edit=(offset:number,value:boolean)=>{const current=save.bytes[save.generalOffset+DEX_OFFSET+offset+index]!;result=patchGeneralRegion(result,DEX_OFFSET+offset+index,Uint8Array.of(value?current|mask:current&~mask));};
 if(changes.seen!==undefined)edit(DEX_SEEN,changes.seen);if(changes.caught!==undefined)edit(DEX_CAUGHT,changes.caught);
 if(changes.caught===true)edit(DEX_SEEN,true);if(changes.seen===false)edit(DEX_CAUGHT,false);return result;
}
export function completePokedex(bytes:Uint8Array):Uint8Array {
 const save=dex(bytes),count=Math.ceil(DEX_MAX/8),mask=new Uint8Array(count).fill(255);mask[count-1]=(1<<(DEX_MAX%8))-1;
 let result=bytes;for(const offset of [DEX_CAUGHT,DEX_SEEN]){const before=save.bytes.slice(save.generalOffset+DEX_OFFSET+offset,save.generalOffset+DEX_OFFSET+offset+count);before.forEach((n,i)=>{before[i]=n|mask[i]!;});result=patchGeneralRegion(result,DEX_OFFSET+offset,before);}return result;
}
