import test from 'node:test';
import assert from 'node:assert/strict';
import {decodePokemon, decodePokemonDetails, patchPokemonGender} from '../../save-core/dist/pokemon.js';
import {pokemonFixture, decodeOracle, encodeOracle, saveFixture} from '../../save-core/tests/fixtures.mjs';
import {readSave} from '../../save-core/dist/save.js';
import {applyEditorTransaction} from '../../save-core/dist/transaction.js';
const pokemonGender=(pid,ratio)=>ratio===255?'genderless':ratio===254?'female':(pid&255)<ratio?'female':'male';

for (const length of [136,236]) test(`gender edits preserve all unrelated plaintext (${length} bytes, all shuffles)`, () => {
  for (let selector=0;selector<32;selector++) for (const ratio of [31,63,127,191,225]) for (const shiny of [false,true]) for (const override of [false,true]) {
    const fixture=decodeOracle(pokemonFixture(selector,length,selector+1));
    const data=new DataView(fixture.logical.buffer);
    data.setUint32(4,(fixture.pid >>> 16) ^ (fixture.pid & 65535) ^ (shiny ? 0 : 8),true);
    // Both PID-derived and overridden natures; nonzero forms and fateful bit.
    data.setUint32(52,((selector%2 ? 14 << 25 : 0) | (override ? 0x80000000 : 0)) >>> 0,true);
    fixture.logical[56]=0xf9;
    const input=encodeOracle(fixture.logical,fixture.pid,fixture.tail), original=input.slice();
    const before=decodePokemonDetails(input);
    const requested=pokemonGender(before.pid,ratio)==='male' ? 'female' : 'male';
    const edited=patchPokemonGender(input,requested,ratio), after=decodePokemonDetails(edited), oracle=decodeOracle(edited);
    assert.equal(pokemonGender(after.pid,ratio),requested);
    assert.equal((oracle.logical[56] >>> 1) & 3, requested==='female' ? 1 : 0);
    assert.equal(after.pid%25,before.pid%25); assert.equal(after.pid&1,before.pid&1);
    for (const key of ['nature','ability','form','fateful','otId','shiny','naturalShiny','shinyOverride','party','ivs','evs','moves','pokerus','nickname','otName']) assert.deepEqual(after[key],before[key],key);
    assert.ok(oracle.checksumOk); assert.deepEqual(oracle.tail,fixture.tail);
    oracle.logical[56]=fixture.logical[56]; assert.deepEqual(oracle.logical,fixture.logical);
    assert.deepEqual(input,original); assert.deepEqual(patchPokemonGender(edited,requested,ratio),edited);
    assert.equal(pokemonGender(decodePokemonDetails(patchPokemonGender(edited,pokemonGender(before.pid,ratio),ratio)).pid,ratio),pokemonGender(before.pid,ratio));
  }
});
test('native ratio boundaries, fixed genders, and invalid edits',()=>{
 const record=pokemonFixture();
 for(const [ratio,gender] of [[0,'male'],[254,'female'],[255,'genderless']]) {
   assert.equal(pokemonGender(0,ratio),gender);assert.equal(pokemonGender(255,ratio),gender);
   const edited=patchPokemonGender(record,gender,ratio); assert.equal(decodePokemon(edited).gender,gender); assert.deepEqual(patchPokemonGender(edited,gender,ratio),edited);
   for(const other of ['male','female','genderless'].filter(x=>x!==gender)) assert.throws(()=>patchPokemonGender(record,other,ratio),/species/);
 }
 assert.equal(pokemonGender(126,127),'female');assert.equal(pokemonGender(127,127),'male');
 for(const ratio of [-1,256,NaN,undefined,1.5])assert.throws(()=>patchPokemonGender(record,'female',ratio));
 for(const gender of [null,undefined,0,'invalid'])assert.throws(()=>patchPokemonGender(record,gender,127));
 const corrupt=record.slice();corrupt[8]^=1;assert.throws(()=>patchPokemonGender(corrupt,'female',127),/checksum/);
 const holder=new Uint8Array(250);holder.set(record,7);const before=holder.slice();
 patchPokemonGender(holder.subarray(7,243),'female',127);assert.deepEqual(holder,before);
});
test('gender survives edited save export and reopen in either active generation',()=>{
 for(const counters of [[10,9],[9,10]]) {
  const bytes=saveFixture({counters}),original=bytes.slice(),save=readSave(bytes),record=save.partyRecords[0];
  const ratio=127, gender=pokemonGender(decodePokemonDetails(record).pid,ratio)==='male'?'female':'male';
  const patched=patchPokemonGender(record,gender,ratio);
  const edited=applyEditorTransaction(bytes,[{type:'replacePartyRecord',slot:0,record:patched}]).bytes;
  assert.deepEqual(readSave(edited).partyRecords[0],patched);
  assert.equal(pokemonGender(decodePokemonDetails(readSave(edited).partyRecords[0]).pid,ratio),gender);
  const offset=save.generalOffset+0x98,crc=save.generalOffset+0xf7cc-2;
  for(let i=0;i<bytes.length;i++)if(bytes[i]!==edited[i])assert.ok((i>=offset&&i<offset+236)||i===crc||i===crc+1,`unexpected byte ${i}`);
  assert.deepEqual(bytes,original);
 }
});
test('repairs stale cached gender even when the requested cached value is unchanged',()=>{
 for(const requested of ['male','female']) {
  const fixture=decodeOracle(pokemonFixture()),ratio=127;
  const pid=(fixture.pid & 0xffffff00) | (requested==='female'?200:20);
  fixture.logical[56]=(fixture.logical[56]&~6)|(requested==='female'?2:0);
  const record=encodeOracle(fixture.logical,pid>>>0,fixture.tail);
  assert.equal(decodePokemon(record).gender,requested);
  const edited=patchPokemonGender(record,requested,ratio),mon=decodePokemon(edited);
  assert.equal(mon.gender,requested);assert.equal(pokemonGender(mon.pid,ratio),requested);
  assert.notEqual(mon.pid,pid>>>0);
 }
});
test('PC gender edit survives export/reopen and preserves party and backup storage',async()=>{
 const {readStorage}=await import('../../save-core/dist/save.js');
 for(const counters of [[10,9],[9,10]]) {
  const original=saveFixture({counters}),record=pokemonFixture(17,136),ratio=127;
  const input=applyEditorTransaction(original,[{type:'replaceBoxRecord',box:23,slot:29,record}]).bytes;
  const gender=pokemonGender(decodePokemon(record).pid,ratio)==='male'?'female':'male';
  const edited=patchPokemonGender(record,gender,ratio);
  const output=applyEditorTransaction(input,[{type:'replaceBoxRecord',box:23,slot:29,record:edited}]).bytes;
  const pc=readStorage(output);assert.deepEqual(pc.boxes[23][29],edited);
  assert.equal(pokemonGender(decodePokemon(pc.boxes[23][29]).pid,ratio),gender);
  assert.deepEqual(readSave(output).partyRecords,readSave(input).partyRecords);
  const backup=pc.offset===0xf800?0x4f800:0xf800;
  assert.deepEqual(output.slice(backup,backup+0x18408),input.slice(backup,backup+0x18408));
 }
});
