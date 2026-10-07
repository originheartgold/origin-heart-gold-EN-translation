import test from 'node:test';
import assert from 'node:assert/strict';
import {createPokemon, emptyPartyRecord, decodePokemon, patchPokemonSpecies} from '../dist/core/pokemon.js';
import {loadBundledOriginData} from '../dist/core/bundled-data.js';
import {speciesInfo} from '../dist/core/species-info.js';
import {crc16, readSave, patchPartyRecord} from '../dist/core/save.js';
import {fillBag, POCKETS, readInventory, patchInventoryPocket} from '../dist/core/inventory.js';
const data = loadBundledOriginData();
function fixture() {
 const bytes = new Uint8Array(0x80000), dv = new DataView(bytes.buffer);
 for (const base of [0, 0x40000]) {
  dv.setUint32(base + 0x90, 6, true); dv.setUint32(base + 0x94, 1, true);
  const footer = base + 0xf7cc - 16;
  dv.setUint32(footer, base ? 1 : 2, true); dv.setUint32(footer + 4, 0xf7cc, true);
  dv.setUint32(footer + 8, 0x20060623, true);
  dv.setUint16(footer + 14, crc16(bytes.subarray(base, footer)), true);
 }
 return bytes;
}
const ivs = {hp:31, attack:20, defense:19, speed:18, spAttack:17, spDefense:16};
function pokemon() {
 const info = speciesInfo(1, 0);
 return createPokemon(emptyPartyRecord(), {speciesId:1, level:50, nature:3, shiny:true,
  gender:'male', ability:info.abilities[0], abilitySlot:0, ivs, moves:[{id:33,pp:35}], name:'Bulbasaur',
  genderRatio:info.genderRatio, baseFriendship:info.baseFriendship, personal:data.getPersonal(1,0)});
}
for (const size of [136,236]) test(`species change preserves identity and training (${size})`, () => {
 const record = pokemon().slice(0,size), before = decodePokemon(record);
 const changed = patchPokemonSpecies(record,445,'Garchomp',data.getPersonal(445,0),data.getPersonal(1,0).growthThresholds,speciesInfo(445,0).genderRatio);
 const after = decodePokemon(changed);
 assert.equal(after.speciesId,445); assert.equal(after.form,0); assert.equal(after.nickname,'Garchomp');
 for (const key of ['pid','tid','sid','otName','ivs','evs','nature','shiny','moves','heldItem','ability','abilitySlot','pokerus']) assert.deepEqual(after[key],before[key]);
 assert.equal(after.experience,data.getPersonal(445,0).growthThresholds[50]);
 if (size===236) { assert.equal(after.party.level,50); assert.notDeepEqual(after.party.stats,before.party.stats); }
 assert.deepEqual(decodePokemon(record),before);
 assert.deepEqual(patchPokemonSpecies(record,1,'Bulbasaur',data.getPersonal(1,0),data.getPersonal(1,0).growthThresholds,31),record);
 assert.throws(()=>patchPokemonSpecies(record,0,'Bad',data.getPersonal(1,0),[],31));
 const save = patchPartyRecord(fixture(),0,pokemon());
 const result = patchPartyRecord(save,0,changed.length===236?changed:patchPokemonSpecies(pokemon(),445,'Garchomp',data.getPersonal(445,0),data.getPersonal(1,0).growthThresholds,speciesInfo(445,0).genderRatio));
 assert.equal(decodePokemon(readSave(result).partyRecords[0]).speciesId,445);
});
test('fill bag respects capacity, quantity limits, existing items and key item bytes', () => {
 const key=data.inventory.items.find(i=>i.pocket==='keyItems');
 const existing=data.inventory.items.filter(i=>i.pocket==='items'&&!i.name.startsWith('Item #')).at(-1);
 let input=patchInventoryPocket(fixture(),'keyItems',[{id:key.id,quantity:1}],data.inventory);
 input=patchInventoryPocket(input,'items',[{id:existing.id,quantity:2}],data.inventory);
 const before=input.slice(), result=fillBag(input,data.inventory), inv=readInventory(result.bytes);
 assert.ok(result.omitted>0); assert.deepEqual(input,before);
 assert.deepEqual(inv.pockets.keyItems,[{id:key.id,quantity:1}]);
 const kp=POCKETS.find(p=>p.id==='keyItems'), base=readSave(input).generalOffset;
 assert.deepEqual(result.bytes.slice(base+kp.offset,base+kp.offset+kp.capacity*4),input.slice(base+kp.offset,base+kp.offset+kp.capacity*4));
 for (const p of POCKETS.filter(p=>p.id!=='keyItems')) {
  assert.ok(inv.pockets[p.id].length<=p.capacity);
  assert.ok(inv.pockets[p.id].every(i=>i.quantity===p.maxQuantity));
 }
 assert.ok(inv.pockets.items.some(i=>i.id===existing.id));
 assert.deepEqual(fillBag(result.bytes,data.inventory).bytes,result.bytes);
});

test('all Hisuian choices create native base-species/form records in party and PC', async () => {
 const {HISUI_CHOICES, speciesSelection, selectionId, defaultMoves} = await import('../dist/core/species-info.js');
 assert.equal(HISUI_CHOICES.length,16);
 for (const choice of HISUI_CHOICES) {
  const info=speciesInfo(choice.speciesId,choice.form), personal=data.getPersonal(choice.speciesId,choice.form);
  const record=createPokemon(emptyPartyRecord(),{speciesId:choice.speciesId,form:choice.form,level:50,nature:3,shiny:true,
   gender:info.genderRatio===255?'genderless':info.genderRatio===254?'female':'male',ability:info.abilities[0],abilitySlot:0,
   ivs,moves:defaultMoves(info,50).map(id=>({id,pp:data.catalog.getMove(id).basePp})),name:data.catalog.getSpecies(choice.speciesId).name,
   genderRatio:info.genderRatio,baseFriendship:info.baseFriendship,personal});
  for(const size of [136,236]) {const mon=decodePokemon(record.slice(0,size));assert.equal(mon.speciesId,choice.speciesId);assert.equal(mon.form,choice.form);assert.equal(mon.ability,info.abilities[0]);assert.equal(selectionId(mon.speciesId,mon.form),choice.id);}
  assert.equal(speciesSelection(choice.id).speciesId,choice.speciesId);
 }
 const original=pokemon();const changed=patchPokemonSpecies(original,571,'Zoroark',data.getPersonal(571,1),data.getPersonal(1,0).growthThresholds,speciesInfo(571,1).genderRatio,1);
 assert.equal(decodePokemon(changed).form,1);assert.equal(decodePokemon(changed).speciesId,571);
 const normal=patchPokemonSpecies(changed,571,'Zoroark',data.getPersonal(571,0),data.getPersonal(571,1).growthThresholds,speciesInfo(571,0).genderRatio);
 assert.equal(decodePokemon(normal).form,0);
});

test('Iron Moth can be created without a level-up learnset', async () => {
 const {defaultMoves} = await import('../dist/core/species-info.js');
 const info=speciesInfo(994,0), moves=defaultMoves(info,50);
 assert.deepEqual(moves,[]);
 const record=createPokemon(emptyPartyRecord(),{speciesId:994,level:50,nature:3,shiny:false,gender:'genderless',
  ability:info.abilities[0],abilitySlot:0,ivs,moves:[],name:'Iron Moth',genderRatio:info.genderRatio,
  baseFriendship:info.baseFriendship,personal:data.getPersonal(994,0)});
 for(const size of [136,236]) {
  const mon=decodePokemon(record.slice(0,size));assert.equal(mon.speciesId,994);
  assert.ok(mon.moves.every(m=>m.id===0&&m.pp===0&&m.ppUps===0));assert.equal(mon.ability,info.abilities[0]);
 }
 const save=patchPartyRecord(fixture(),0,record);
 assert.equal(decodePokemon(readSave(save).partyRecords[0]).speciesId,994);
});

test('gender changes preserve every other decoded field and party tail', async () => {
 const {patchPokemonGender} = await import('../dist/core/pokemon.js');
 for(const size of [136,236]) {
  const record=pokemon().slice(0,size), before=decodePokemon(record);
  const changed=patchPokemonGender(record,'female'), after=decodePokemon(changed);
  assert.equal(after.gender,'female');assert.deepEqual({...after,gender:before.gender},before);
  assert.deepEqual(changed.slice(136),record.slice(136));
  assert.deepEqual(patchPokemonGender(changed,'male'),record);
  assert.throws(()=>patchPokemonGender(record,'genderless'));
 }
});
