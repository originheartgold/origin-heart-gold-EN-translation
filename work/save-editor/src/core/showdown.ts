import {createPokemon,decodePokemon,patchPokemonHeldItem,patchPokemonStats,readPokemonMetadata,patchPokemonMetadata,type DecodedPokemon} from './pokemon.js';
import {FORM_CHOICES,selectionId,speciesSelection,speciesInfo,defaultMoves,possibleGenders,ABILITIES,getAbility} from './species-info.js';
import {type BundledOriginData} from './bundled-data.js';
import {EditorError} from './errors.js';
import {type StatValues} from './stats.js';
const NATURES=['Hardy','Lonely','Brave','Adamant','Naughty','Bold','Docile','Relaxed','Impish','Lax','Timid','Hasty','Serious','Jolly','Naive','Modest','Mild','Quiet','Bashful','Rash','Careful','Quirky'];
const keys:Record<string,keyof StatValues>={HP:'hp',Atk:'attack',Def:'defense',SpA:'spAttack',SpD:'spDefense',Spe:'speed'};
const normalize=(name:string)=>name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
export function exportShowdown(record:Uint8Array,data:BundledOriginData):string {
 const mon=decodePokemon(record),choice=FORM_CHOICES.find(c=>c.id===selectionId(mon.speciesId,mon.form)),name=choice?.name??data.catalog.getSpecies(mon.speciesId)?.name??String(mon.speciesId),held=data.inventory.getItem(mon.heldItem)?.name;
 const gender=mon.gender==='genderless'?'':` (${mon.gender==='female'?'F':'M'})`,meta=readPokemonMetadata(record);
 const format=(stats:StatValues)=>Object.entries(keys).map(([key,field])=>`${stats[field]} ${key}`).join(' / ');
 const personal=data.getPersonal(mon.speciesId,mon.form);let level=mon.party?.level??1;if(!mon.party)for(let n=2;n<=100;n++)if(mon.experience>=personal.growthThresholds[n]!)level=n;
 return [`${meta.nicknamed&&mon.nickname?`${mon.nickname} (${name})`:name}${gender}${held?` @ ${held}`:''}`,`Ability: ${getAbility(mon.ability)?.name??mon.ability}`,`Level: ${level}`,`Shiny: ${mon.shiny?'Yes':'No'}`,`Happiness: ${meta.friendship}`,`EVs: ${format(mon.evs)}`,`${NATURES[mon.nature]} Nature`,`IVs: ${format(mon.ivs)}`,...mon.moves.filter(m=>m.id).map(m=>`- ${data.catalog.getMove(m.id)?.name??m.id}`)].join('\n');
}
export function importShowdown(text:string,template:Uint8Array,data:BundledOriginData):Uint8Array[] {
 const sets=text.trim().split(/\n\s*\n/).filter(Boolean);if(!sets.length||sets.length>30)throw new EditorError('invalid-input','Import one to thirty sets.');
 return sets.map(set=>{
 const lines=set.split(/\r?\n/).map(s=>s.trim()).filter(Boolean),header=lines.shift()!,parts=header.split(' @ '),held=parts[1];let title=parts[0]!,gender:'male'|'female'|'genderless'|undefined;
 if(/\s\([MF]\)$/.test(title)){gender=title.endsWith('(F)')?'female':'male';title=title.slice(0,-4);}
 let nickname:string|undefined;const named=title.match(/^(.*) \(([^()]+)\)$/);if(named){nickname=named[1];title=named[2]!;}
 const choices=[...data.catalog.species,...FORM_CHOICES];const choice=choices.find(c=>normalize(c.name)===normalize(title)||normalize(c.name.replace(/^Hisuian (.*)$/,'$1-Hisui').replace(/^Alolan (.*)$/,'$1-Alola').replace(/^Galarian (.*)$/,'$1-Galar'))===normalize(title));
 if(!choice)throw new EditorError('invalid-input',`Unknown Origin species/form: ${title}`);
 const selected=speciesSelection(choice.id),info=speciesInfo(selected.speciesId,selected.form)!;
 let level=100,nature=0,shiny=false,friendship=info.baseFriendship,ability=info.abilities[0],slot=0;
 const evs:StatValues={hp:0,attack:0,defense:0,speed:0,spAttack:0,spDefense:0},ivs:StatValues={hp:31,attack:31,defense:31,speed:31,spAttack:31,spDefense:31},moves:number[]=[];
 for(const line of lines){
 if(line.startsWith('- ')){const raw=line.slice(2);if(/ \[[^\]]+\]$/.test(raw))throw new EditorError('invalid-input','Set Hidden Power type with the editor’s IV control before exporting; typed Hidden Power imports are unsupported.');const name=raw;const move=data.catalog.moves.find(m=>normalize(m.name)===normalize(name));if(!move)throw new EditorError('invalid-input',`Unknown move: ${name}`);moves.push(move.id);}
 else if(line.endsWith(' Nature')){nature=NATURES.findIndex(n=>normalize(n)===normalize(line.slice(0,-7)));if(nature<0)throw new EditorError('invalid-input','Unknown nature.');}
 else if(line.startsWith('Ability: ')){const name=line.slice(9);const found=ABILITIES.find(a=>normalize(a.name)===normalize(name));if(!found)throw new EditorError('invalid-input',`Unknown ability: ${name}`);ability=found.id;slot=Math.max(0,info.abilities.indexOf(ability));}
 else if(line.startsWith('Level: '))level=Number(line.slice(7));
 else if(line.startsWith('Shiny: ')){if(!['Yes','No'].includes(line.slice(7)))throw new EditorError('invalid-input','Shiny must be Yes or No.');shiny=line.slice(7)==='Yes';}
 else if(line.startsWith('Happiness: '))friendship=Number(line.slice(11));
 else if(line.startsWith('EVs: ')||line.startsWith('IVs: ')){const values=line.startsWith('EVs')?evs:ivs;for(const stat of line.slice(5).split(' / ')){const match=stat.match(/^(\d+) (HP|Atk|Def|SpA|SpD|Spe)$/);if(!match)throw new EditorError('invalid-input',`Invalid stat: ${stat}`);values[keys[match[2]!]!]=Number(match[1]);}}
 else throw new EditorError('invalid-input',`Unsupported set field: ${line}`);
 }
 const finalMoves=moves.length?moves:defaultMoves(info,level),personal=data.getPersonal(selected.speciesId,selected.form),allowed=possibleGenders(info.genderRatio);
 let record=createPokemon(template,{speciesId:selected.speciesId,form:selected.form,level,nature,shiny,gender:gender??allowed[0]!,ability,abilitySlot:slot,ivs,moves:finalMoves.map(id=>({id,pp:data.catalog.getMove(id)!.basePp})),name:data.catalog.getSpecies(selected.speciesId)!.name,genderRatio:info.genderRatio,baseFriendship:info.baseFriendship,personal});
 record=patchPokemonStats(record,{evs},personal,personal.growthThresholds);record=patchPokemonMetadata(record,{friendship,...(nickname?{nickname,nicknamed:true}:{})});
 if(held){const item=data.inventory.items.find(i=>normalize(i.name)===normalize(held));if(!item)throw new EditorError('invalid-input',`Unknown item: ${held}`);record=patchPokemonHeldItem(record,item.id);}return record;
 });
}
export function setLevel(mon:DecodedPokemon,data:BundledOriginData):number {const personal=data.getPersonal(mon.speciesId,mon.form);let level=mon.party?.level??1;if(!mon.party)for(let n=2;n<=100;n++)if(mon.experience>=personal.growthThresholds[n]!)level=n;return level;}
