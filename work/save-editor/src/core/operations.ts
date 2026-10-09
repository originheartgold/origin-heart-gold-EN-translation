import {clonePokemon} from './pokemon-species.js';
import {decodePokemon, readPokemonMetadata, patchPokemonShiny, toPartyPokemon, emptyPartyRecord, type DecodedPokemon,type PokemonMetadata} from './pokemon.js';
import {readSave,readStorage,patchBoxRecord,patchPartyRecord,addPartyRecord,removePartyRecord,BOX_CAPACITY,BOX_COUNT} from './save.js';
import {type BundledOriginData} from './bundled-data.js';
import {speciesInfo,personalIndex,possibleGenders} from './species-info.js';
import {editorReference} from './editor-reference.js';
import {EditorError} from './errors.js';
export type PokemonLocation = {kind:'party';slot:number}|{kind:'pc';box:number;slot:number};
export function recordAt(bytes:Uint8Array,location:PokemonLocation):Uint8Array {
 const record=location.kind==='party'?readSave(bytes).partyRecords[location.slot]:readStorage(bytes).boxes[location.box]?.[location.slot];
 if(!record)throw new EditorError('invalid-input','Invalid Pokémon slot.');return record;
}
export function placePokemon(bytes:Uint8Array,location:PokemonLocation,record:Uint8Array,data:BundledOriginData):Uint8Array {
 const mon=decodePokemon(record);if(!data.catalog.getSpecies(mon.speciesId)||!speciesInfo(mon.speciesId,mon.form)||(mon.form&&personalIndex(mon.speciesId,mon.form)===mon.speciesId))throw new EditorError('invalid-input','Unsupported Origin species or form.');
 if(data.inventory.getItem(mon.heldItem)?.pocket==='mail'&&(location.kind==='pc'||record.length===136))throw new EditorError('invalid-input','Remove held mail before transferring between party and PC.');
 if(location.kind==='pc')return patchBoxRecord(bytes,location.box,location.slot,record.slice(0,136));
 const party=toPartyPokemon(record,data.getPersonal(mon.speciesId,mon.form)),count=readSave(bytes).partyCount;
 return location.slot===count?addPartyRecord(bytes,party):patchPartyRecord(bytes,location.slot,party);
}
export function transferPokemon(bytes:Uint8Array,source:PokemonLocation,target:PokemonLocation,mode:'move'|'copy'|'clone',data:BundledOriginData):Uint8Array {
 if(source.kind===target.kind&&source.slot===target.slot&&(source.kind==='party'||target.kind==='pc'&&source.box===target.box))return Uint8Array.from(bytes);
 if(target.kind==='party'&&target.slot!==readSave(bytes).partyCount)throw new EditorError('invalid-input','Transfers append to the party.');
 if(target.kind==='pc'&&decodePokemon(recordAt(bytes,target)).speciesId)throw new EditorError('invalid-input','Choose an empty destination slot.');
 if(mode==='move'&&source.kind==='party'&&readSave(bytes).partyCount===1)throw new EditorError('invalid-input','Keep at least one party Pokémon.');
 const record=recordAt(bytes,source),copy=mode==='clone'?clonePokemon(record):record;
 if(!decodePokemon(record).speciesId)throw new EditorError('invalid-input','Choose an occupied slot.');
 let result=placePokemon(bytes,target,copy,data);
 if(mode==='move')result=source.kind==='party'?removePartyRecord(result,source.slot):patchBoxRecord(result,source.box,source.slot,emptyPartyRecord().slice(0,136));
 return result;
}
export function sortBox(bytes:Uint8Array,box:number):Uint8Array {
 const records=readStorage(bytes).boxes[box];if(!records)throw new EditorError('invalid-input','Unknown box.');
 const sorted=records.filter(r=>decodePokemon(r).speciesId).sort((a,b)=>{const x=decodePokemon(a),y=decodePokemon(b);return x.speciesId-y.speciesId||x.form-y.form;});
 while(sorted.length<BOX_CAPACITY)sorted.push(emptyPartyRecord().slice(0,136));
 let result=bytes;sorted.forEach((record,slot)=>{result=patchBoxRecord(result,box,slot,record);});return result;
}
export function fillBox(bytes:Uint8Array,box:number,template:Uint8Array):Uint8Array {
 const records=readStorage(bytes).boxes[box];if(!records)throw new EditorError('invalid-input','Unknown box.');
 const free=records.flatMap((r,slot)=>decodePokemon(r).speciesId?[]:[slot]);if(!free.length)throw new EditorError('invalid-input','Box is full.');
 const shinySlot=free[Math.floor(Math.random()*free.length)]!,pids=new Set<number>(records.filter(r=>decodePokemon(r).speciesId).map(r=>decodePokemon(r).pid));let result=bytes;
 for(const slot of free){let record:Uint8Array;for(let n=0;;n++){if(n>100)throw new EditorError('invalid-input','Could not generate distinct identities.');record=clonePokemon(template,Math.random,false).slice(0,136);if(!pids.has(decodePokemon(record).pid))break;}
 if(decodePokemon(record).naturalShiny&&slot!==shinySlot)throw new EditorError('invalid-input','Use a template without natural shininess to fill a box with exactly one shiny copy.');
 record=patchPokemonShiny(record,slot===shinySlot);pids.add(decodePokemon(record).pid);result=patchBoxRecord(result,box,slot,record);}
 return result;
}
export function batchBox(bytes:Uint8Array,box:number,change:(record:Uint8Array)=>Uint8Array):Uint8Array {
 const records=readStorage(bytes).boxes[box];if(!records)throw new EditorError('invalid-input','Unknown box.');let result=bytes;
 records.forEach((record,slot)=>{const mon=decodePokemon(record);if(mon.speciesId&&!mon.isEgg)result=patchBoxRecord(result,box,slot,change(record));});return result;
}
export function pokemonChecks(mon:DecodedPokemon,metadata?:PokemonMetadata,level?:number):string[] {
 const problems:string[]=[],info=speciesInfo(mon.speciesId,mon.form),ref=editorReference.compat[personalIndex(mon.speciesId,mon.form)];
 if(!info)return ['Unsupported species/form.'];
 if(mon.nature<0||mon.nature>24)problems.push('Invalid nature override.');
 if(!possibleGenders(info.genderRatio).includes(mon.gender))problems.push('Gender is not supported by this species.');
 if(!info.abilities.includes(mon.ability))problems.push('Ability is outside this species’ known slots.');
 if(Object.values(mon.evs).reduce((a,b)=>a+b,0)>510)problems.push('EV total exceeds 510.');
 if(!ref)problems.push('Move compatibility is not available for this form.');
 else for(const move of mon.moves.filter(m=>m.id))if(![...ref.levelup.map(x=>x[1]!),...ref.tms,...ref.tutors,...ref.egg].includes(move.id))problems.push(`Move #${move.id} is not in the recorded level-up, TM, tutor or egg-move lists. Evolution/event exceptions are not checked.`);
 if(metadata){
 if(metadata.ball<1||metadata.ball>24)problems.push('Poké Ball is outside the supported native range.');
 if(level!==undefined&&metadata.metLevel>level)problems.push('Met level exceeds current level.');
 if(metadata.metDate&&metadata.eggDate&&metadata.eggDate>metadata.metDate)problems.push('Egg date is later than the met/hatch date.');
 if(metadata.eggDate&&!metadata.eggLocation)problems.push('Egg date is set without an egg location.');
 if(mon.isEgg&&metadata.nicknamed)problems.push('Egg has a nickname flag.');
 }
 return problems;
}
export function exportPokemonFile(record:Uint8Array):string {decodePokemon(record);return JSON.stringify({format:'origin-heartgold-pokemon',version:1,bytes:[...record]},null,2);}
export function importPokemonFile(text:string,data:BundledOriginData):Uint8Array {
 const value=JSON.parse(text);if(value.format!=='origin-heartgold-pokemon'||value.version!==1||!Array.isArray(value.bytes)||![136,236].includes(value.bytes.length)||value.bytes.some((n:unknown)=>!Number.isInteger(n)||Number(n)<0||Number(n)>255))throw new EditorError('invalid-input','Choose an Origin .ohgpk4 file.');
 const record=Uint8Array.from(value.bytes),mon=decodePokemon(record);
 if(!data.catalog.getSpecies(mon.speciesId)||!speciesInfo(mon.speciesId,mon.form)||(mon.form&&personalIndex(mon.speciesId,mon.form)===mon.speciesId))throw new EditorError('invalid-input','Unsupported species/form.');
 const metadata=readPokemonMetadata(record);if(metadata.ball>24)throw new EditorError('invalid-input','Unsupported Poké Ball.');return record;
}
export function searchPokemon(bytes:Uint8Array,query:string,data:BundledOriginData):{location:PokemonLocation;name:string}[] {
 const matches:{location:PokemonLocation;name:string}[]=[],needle=query.trim().toLowerCase();
 const add=(record:Uint8Array,location:PokemonLocation)=>{const mon=decodePokemon(record);if(!mon.speciesId)return;const name=`${mon.nickname??''} · ${data.catalog.getSpecies(mon.speciesId)?.name??mon.speciesId} #${mon.speciesId}`;if(!needle||name.toLowerCase().includes(needle))matches.push({location,name});};
 readSave(bytes).partyRecords.forEach((record,slot)=>add(record,{kind:'party',slot}));const pc=readStorage(bytes);for(let box=0;box<BOX_COUNT;box++)pc.boxes[box]!.forEach((record,slot)=>add(record,{kind:'pc',box,slot}));return matches;
}
