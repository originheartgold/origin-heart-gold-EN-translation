import nodeTest from 'node:test';
import assert from 'node:assert/strict';
import {fixture as save} from './fixture.mjs';
const test = (name, fn) => nodeTest(name, {skip: !save}, fn);
import {readSave,readStorage,patchPartyRecord,patchBoxRecord} from '../dist/core/save.js';
import {decodePokemon,patchPokemonOT} from '../dist/core/pokemon.js';
const record=save && readSave(save).partyRecords[0];
for(const size of [136,236])test(`OT edits round-trip without changing other Pokémon fields (${size} bytes)`,()=>{
 const input=record.slice(0,size), before=decodePokemon(input);
 const edited=patchPokemonOT(input,{name:'Ash',tid:12345,sid:54321}),after=decodePokemon(edited);
 assert.equal(after.otName,'Ash');assert.equal(after.tid,12345);assert.equal(after.sid,54321);
 for(const key of ['pid','speciesId','moves','ivs','evs','experience','nature','ability','party','nickname','shinyOverride'])assert.deepEqual(after[key],before[key]);
 assert.deepEqual(edited.subarray(136),input.subarray(136));
 assert.deepEqual(patchPokemonOT(input,{tid:before.tid,sid:before.sid}),input);
 assert.equal(decodePokemon(patchPokemonOT(edited,{name:'Éclair'})).otName,'Éclair');
 if(size===236) assert.equal(decodePokemon(readSave(patchPartyRecord(save,0,edited)).partyRecords[0]).tid,12345);
 else assert.equal(decodePokemon(readStorage(patchBoxRecord(save,0,0,edited)).boxes[0][0]).otName,'Ash');
 assert.deepEqual(record.slice(0,size),input);
});
test('OT input rejects invalid IDs, long or unsupported names',()=>{
 for(const changes of [{tid:-1},{tid:65536},{sid:1.5},{sid:NaN},{name:''},{name:'12345678'},{name:'Ash🔥'},{name:' Ash'}])assert.throws(()=>patchPokemonOT(record,changes));
});
test('OT name edit preserves IDs and IDs determine natural shiny status',()=>{
 const original=decodePokemon(record);
 assert.equal(decodePokemon(patchPokemonOT(record,{name:'Red'})).tid,original.tid);
 const tid=1234,sid=(original.pid>>>16)^(original.pid&65535)^tid;
 assert.equal(decodePokemon(patchPokemonOT(record,{tid,sid})).naturalShiny,true);
});
