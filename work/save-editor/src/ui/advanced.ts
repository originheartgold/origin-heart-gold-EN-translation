import {h} from './dom.js';
import {combobox} from './combobox.js';
import {readPokemonMetadata,patchPokemonMetadata,patchPokemonExperience,decodePokemon,type PokemonMetadata} from '../core/pokemon.js';
import {editorReference} from '../core/editor-reference.js';
import {recordAt,fillBox,sortBox,batchBox,searchPokemon,type PokemonLocation} from '../core/operations.js';
import {patchPokemonStats} from '../core/pokemon.js';
import {type BundledOriginData} from '../core/bundled-data.js';
export interface EditorContext {
 bytes:Uint8Array;location:PokemonLocation;data:BundledOriginData;
 commit:(change:(bytes:Uint8Array)=>Uint8Array,message:string)=>void;
 navigate:(location:PokemonLocation)=>void;error:(message:string)=>void;
}
function download(text:string,name:string):void {const url=URL.createObjectURL(new Blob([text],{type:'application/json'})),a=h('a',{href:url,download:name});a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function field(label:string,input:HTMLElement):HTMLElement{return h('label',{class:'field'},label,input);}
function numeric(value:number,min:number,max:number,change:(n:number)=>void):HTMLInputElement {const input=h('input',{type:'number',value,min,max,step:1});input.addEventListener('change',()=>{if(input.value!==''&&Number.isInteger(Number(input.value)))change(Number(input.value));});return input;}
export function metadataFields(metadata:PokemonMetadata,change:(changes:Partial<PokemonMetadata>)=>void,isEgg=false):HTMLElement {
 const fields=h('div',{class:'editor-fields'});
 const addNumber=(label:string,key:'friendship'|'language'|'originGame'|'metLevel'|'metLocation'|'eggLocation'|'encounterType',max:number)=>fields.append(field(label,numeric(metadata[key],0,max,n=>change({[key]:n}))));
 addNumber(isEgg?'Hatch cycles':'Friendship','friendship',255);addNumber('Language ID','language',8);addNumber('Origin game ID','originGame',255);addNumber('Met level','metLevel',100);addNumber('Met location ID','metLocation',65535);addNumber('Egg location ID (0 = not hatched)','eggLocation',65535);addNumber('Encounter type ID','encounterType',255);
 const balls=['Master Ball','Ultra Ball','Great Ball','Poké Ball','Safari Ball','Net Ball','Dive Ball','Nest Ball','Repeat Ball','Timer Ball','Luxury Ball','Premier Ball','Dusk Ball','Heal Ball','Quick Ball','Cherish Ball','Fast Ball','Level Ball','Lure Ball','Heavy Ball','Love Ball','Friend Ball','Moon Ball','Sport Ball'];
 const ball=h('select',{},...balls.map((name,i)=>h('option',{value:i+1},name)));ball.value=String(metadata.ball||4);ball.addEventListener('change',()=>change({ball:Number(ball.value)}));fields.append(field('Caught in',ball));
 const gender=h('select',{},h('option',{value:'male'},'Male'),h('option',{value:'female'},'Female'));gender.value=metadata.otGender;gender.addEventListener('change',()=>change({otGender:gender.value as 'male'|'female'}));fields.append(field('OT gender',gender));
 for(const key of ['metDate','eggDate'] as const){const date=h('input',{type:'date',value:metadata[key],min:'2000-01-01',max:'2255-12-31'});date.addEventListener('change',()=>change({[key]:date.value}));fields.append(field(key==='metDate'?'Met date':'Egg date',date));}
 const fateful=h('input',{type:'checkbox',checked:metadata.fateful});fateful.addEventListener('change',()=>change({fateful:fateful.checked}));fields.append(field('Fateful encounter',fateful));return fields;
}
export function advancedPokemon(ctx:EditorContext):DocumentFragment {
 const record=recordAt(ctx.bytes,ctx.location),mon=decodePokemon(record),metadata=readPokemonMetadata(record);
 const patch=(changes:Partial<PokemonMetadata>)=>ctx.commit(bytes=>{
 const current=recordAt(bytes,ctx.location),next=patchPokemonMetadata(current,changes);
 return ctx.location.kind==='party'?patchParty(bytes,ctx.location.slot,next):patchBox(bytes,ctx.location.box,ctx.location.slot,next);
 },'Pokémon details updated');
 const nickname=h('input',{type:'text',value:metadata.nickname??'',maxlength:10,'aria-label':'Nickname'});nickname.addEventListener('change',()=>patch({nickname:nickname.value,nicknamed:true}));
 const named=h('input',{type:'checkbox',checked:metadata.nicknamed});named.addEventListener('change',()=>patch(named.checked?{nicknamed:true}:{nickname:ctx.data.catalog.getSpecies(mon.speciesId)!.name.slice(0,10),nicknamed:false}));
 const personal=ctx.data.getPersonal(mon.speciesId,mon.form),exp=numeric(mon.experience,personal.growthThresholds[1]!,personal.growthThresholds[100]!,experience=>ctx.commit(bytes=>{
 const next=patchPokemonExperience(recordAt(bytes,ctx.location),experience,personal);return ctx.location.kind==='party'?patchParty(bytes,ctx.location.slot,next):patchBox(bytes,ctx.location.box,ctx.location.slot,next);
 },'Experience updated'));
 const encounter=metadataFields(metadata,patch,mon.isEgg);
 const friendship=encounter.firstElementChild!;friendship.remove();
 const identity=h('section',{class:'tile span-2 pokemon-identity'},h('h2',{},'Nickname & friendship'),
   h('div',{class:'editor-fields identity-fields'},field('Nickname',nickname),field('Nicknamed',named),friendship,field('Experience',exp)));
 const origin=h('section',{class:'tile span-4 pokemon-origin'},h('h2',{},'Origin & encounter'),encounter);
 const cards=document.createDocumentFragment();cards.append(identity,origin);return cards;
}
import {patchPartyRecord as patchParty,patchBoxRecord as patchBox} from '../core/save.js';
export function boxTools(ctx:EditorContext,box:number):HTMLElement {
 const section=h('details',{class:'editor-advanced'},h('summary',{},'Box tools'),h('div',{class:'editor-tools'},
 h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>sortBox(bytes,box),'Box sorted')},'Sort by species'),
 h('button',{type:'button',class:'btn small',disabled:!decodePokemon(recordAt(ctx.bytes,ctx.location)).speciesId,onclick:()=>ctx.commit(bytes=>fillBox(bytes,box,recordAt(bytes,ctx.location)),'Free slots filled with distinct Pokémon')},'Fill free slots'),
 h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>batchBox(bytes,box,record=>{const mon=decodePokemon(record),personal=ctx.data.getPersonal(mon.speciesId,mon.form);return patchPokemonStats(record,{ivs:{hp:31,attack:31,defense:31,speed:31,spAttack:31,spDefense:31}},personal,personal.growthThresholds);}), 'Box IVs maxed')},'Max box IVs'),
 h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>batchBox(bytes,box,record=>patchPokemonMetadata(record,{friendship:255})),'Box friendship maxed')},'Max box friendship')));
 const search=h('input',{type:'search',placeholder:'Search party & all boxes','aria-label':'Search Pokémon database'}),list=h('div',{class:'editor-tools'});
 search.addEventListener('input',()=>{try{list.replaceChildren(...searchPokemon(ctx.bytes,search.value,ctx.data).slice(0,40).map(match=>h('button',{type:'button',class:'btn small',onclick:()=>ctx.navigate(match.location)},`${match.name} · ${match.location.kind==='party'?`Party ${match.location.slot+1}`:`Box ${match.location.box+1}/${match.location.slot+1}`}`)));}catch(error){ctx.error(String(error));}});section.append(search,list);return section;
}
export function itemReference(ctx:EditorContext):HTMLElement {
 const display=h('div',{}),picker=combobox({id:'reference-item',label:'Find any item',value:undefined,choices:ctx.data.inventory.items.filter(i=>!i.name.startsWith('Item #')),onSelect:id=>{
 const item=ctx.data.inventory.getItem(id)!,ref=editorReference.items[id];if(!ref)return;
 display.replaceChildren(h('h3',{},item.name),h('p',{class:'note'},`#${id} · ${item.pocket} · Price ${ref.price} · Held effect ${ref.hold} (${ref.holdParameter}) · Fling ${ref.flingPower} / effect ${ref.flingEffect} · Field use ${ref.fieldUse} · Battle use ${ref.battleUse} · Party use ${ref.partyUse}`),h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>{const inventory=readInventory(bytes),pocket=POCKETS.find(p=>p.id===item.pocket)!,items=inventory.pockets[item.pocket].map(i=>({...i})),existing=items.find(i=>i.id===id);if(existing)existing.quantity=Math.min(pocket.maxQuantity,existing.quantity+1);else items.push({id,quantity:1});return patchInventoryPocket(bytes,item.pocket,items,ctx.data.inventory);},'Item added')},'Add ×1 to bag'));
 }});
 return h('details',{class:'editor-advanced'},h('summary',{},'Item reference'),picker,display);
}
import {POCKETS,readInventory,patchInventoryPocket} from '../core/inventory.js';
import {readPokedex,patchPokedex,completePokedex} from '../core/pokedex.js';
let selectedDexSpecies=1;
export function pokedexTile(ctx:EditorContext):HTMLElement {
 const tile=h('section',{class:'tile span-2 pokedex-tile'},h('h2',{},'Pokédex',h('span',{class:'aside'},'1,025 species')));
 try {
   const dex=readPokedex(ctx.bytes),display=h('div',{class:'dex-selection'});
   const metric=(label:string,count:number)=>h('div',{class:'dex-metric'},
     h('div',{class:'dex-metric-label'},h('span',{},label),h('strong',{class:'num'},count.toLocaleString())),
     h('progress',{max:1025,value:count,'aria-label':`${label} Pokémon`}),h('span',{class:'dex-percent num'},`${Math.round(count/1025*100)}%`));
   const showSpecies=(id:number)=>{
     const species=ctx.data.catalog.getSpecies(id)!;
     display.replaceChildren(h('div',{class:'dex-species-heading'},img(miniSpriteUrl(id,false),species.name),
       h('div',{},h('span',{class:'dex-number num'},`No. ${String(id).padStart(4,'0')}`),h('h3',{},species.name))),
       h('div',{class:'dex-flags'},...(['seen','caught'] as const).map(key=>h('button',{type:'button',class:'dex-flag','aria-pressed':String(dex[key][id-1]),
         onclick:()=>ctx.commit(bytes=>patchPokedex(bytes,id,{[key]:!dex[key][id-1]}),'Pokédex flag updated')},
         h('span',{'aria-hidden':'true'},dex[key][id-1]?'✓':'○'),key==='seen'?'Seen':'Caught'))));
   };
   const picker=combobox({id:'dex-species',label:'Pokédex species',value:selectedDexSpecies,choices:[...ctx.data.catalog.species],onSelect:id=>{selectedDexSpecies=id;showSpecies(id);}});
   showSpecies(selectedDexSpecies);
   tile.append(h('div',{class:'dex-metrics'},metric('Seen',dex.seenCount),metric('Caught',dex.caughtCount)),
     h('div',{class:'dex-browser'},picker,display),h('button',{type:'button',class:'btn ghost dex-complete',onclick:()=>ctx.commit(completePokedex,'All base species marked seen and caught')},'Mark all seen & caught'));
 } catch(error){tile.append(h('p',{class:'note'},String(error)));}
 return tile;
}
import {img,miniSpriteUrl} from './sprites.js';

import {readMysteryGifts,patchGiftReceived,removePendingGift,removeWonderCard,exportWonderCard,importWonderCard} from '../core/mystery-gift.js';
export function mysteryGiftTile(ctx:EditorContext):HTMLElement {
 const state=readMysteryGifts(ctx.bytes),tile=h('section',{class:'tile span-2'},h('h2',{},'Mystery Gift'));
 const enabled=h('input',{type:'checkbox',checked:state.received[2047]});enabled.addEventListener('change',()=>ctx.commit(bytes=>patchGiftReceived(bytes,2047,enabled.checked),'Special receipt flag updated'));tile.append(field('Special receipt flag (2047)',enabled));
 const tags=['Empty','Pokémon','Egg','Item','Battle rules','Decoration','Pokémon decoration','Manaphy Egg','Member Card','Oak’s Letter','Azure Flute','Pokétch','Secret Key','Movie Pokémon','Pokéwalker','Photo'];
 for(const card of state.cards){const occupied=card.tag>0&&card.tag<16;tile.append(h('details',{class:'editor-advanced'},h('summary',{},`Card ${card.slot+1} · ${occupied?(card.title??`#${card.id}`):'Empty'}`),occupied?h('div',{class:'editor-tools'},h('span',{class:'note'},`ID ${card.id} · ${tags[card.tag]}`),h('button',{class:'btn small',type:'button',onclick:()=>download(exportWonderCard(ctx.bytes,card.slot),`card-${card.id}.ohgwc4`)},'Export card'),h('button',{class:'btn small',type:'button',onclick:()=>ctx.commit(bytes=>removeWonderCard(bytes,card.slot),'Card and associated pending gifts removed')},'Remove card & gift')):null));}
 const pending=state.gifts.filter(g=>g.tag>0&&g.tag<16);tile.append(h('details',{class:'editor-advanced'},h('summary',{},`Pending gifts · ${pending.length}/8`),...pending.map(g=>h('div',{class:'editor-tools'},h('span',{},`${g.slot+1}. ${tags[g.tag]} · card ${g.cardSlot+1}`),h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>removePendingGift(bytes,g.slot),'Pending gift removed')},'Remove pending gift')))));
 let flagID=0;const status=h('p',{class:'note'},'Receipt 0: '+(state.received[0]?'Received':'Available')),id=numeric(0,0,2046,n=>{flagID=n;status.textContent=`Receipt ${n}: ${state.received[n]?'Received':'Available'}`;});tile.append(h('details',{class:'editor-advanced'},h('summary',{},'Receipt flags'),field('Gift ID',id),status,h('div',{class:'editor-tools'},...([true,false] as const).map(received=>h('button',{type:'button',class:'btn small',onclick:()=>ctx.commit(bytes=>patchGiftReceived(bytes,flagID,received),'Gift receipt updated')},received?'Mark received':'Allow again')))));
 const importFile=h('input',{type:'file',accept:'.ohgwc4,application/json','aria-label':'Import Origin Wonder Card'});importFile.addEventListener('change',()=>{void (async()=>{try{const input=importFile.files?.[0];if(!input)return;const text=await input.text();ctx.commit(bytes=>importWonderCard(bytes,text,ctx.data),'Wonder Card imported');}catch(error){ctx.error(String(error));}})();});
 tile.append(h('details',{class:'editor-advanced'},h('summary',{},'Import Origin card'),importFile,h('p',{class:'note'},'Import native Pokémon, Egg or Item .ohgwc4 cards exported from Origin. Special cards and unrelated event flags are preserved. No online event database is used.')));return tile;
}
