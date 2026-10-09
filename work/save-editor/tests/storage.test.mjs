import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture as original} from './fixture.mjs';
import {readStorage, patchBoxRecord, readSave, crc16} from '../dist/core/save.js';
import {decodePokemon, patchPokemonStats, patchPokemonAbility, patchPokemonMoves, emptyPartyRecord} from '../dist/core/pokemon.js';
import {loadBundledOriginData} from '../dist/core/bundled-data.js';
const template = readSave(original).partyRecords[0].slice(0,136);
function rewriteCounter(bytes, base, counter) { new DataView(bytes.buffer).setUint32(base+0x18408-16, counter, true); }
test('Origin storage decodes all 24 boxes and all 720 slots', () => {
 const pc=readStorage(original);
 assert.equal(pc.boxes.length,24);assert.equal(pc.boxes[23].length,30);
 for(const box of pc.boxes)for(const r of box) assert.ok(Number.isInteger(decodePokemon(r).speciesId));
 assert.ok([0xf800,0x4f800].includes(pc.offset));
 assert.equal(pc.wallpapers.length,24);
});
test('editing the final PC slot preserves general blocks, backup storage and other records', () => {
 const pc=readStorage(original), result=patchBoxRecord(original,23,29,template);
 assert.deepEqual(readSave(result).partyRecords,readSave(original).partyRecords);
 for(const base of [0,0x40000]) assert.deepEqual(result.subarray(base,base+0xf7cc),original.subarray(base,base+0xf7cc));
 const backup = pc.offset === 0xf800 ? 0x4f800 : 0xf800;
 assert.deepEqual(result.subarray(backup,backup+0x18408),original.subarray(backup,backup+0x18408));
 assert.deepEqual(readStorage(result).boxes[23][29],template);
 const allowed=new Set(Array.from({length:136},(_,i)=>pc.offset+23*0x1000+29*136+i));
 for(const off of [0x18004,0x18005,0x18006,0x18007,0x183f4,0x183f5,0x18406,0x18407])allowed.add(pc.offset+off);
 for(let i=0;i<original.length;i++)if(result[i]!==original[i])assert.ok(allowed.has(i));
 assert.deepEqual(patchBoxRecord(result,23,29,template),result);
 assert.equal(decodePokemon(readStorage(patchBoxRecord(result,23,29,emptyPartyRecord().slice(0,136))).boxes[23][29]).speciesId,0);
});
test('PC selection follows coherent native generations; corruption falls back as a pair', () => {
 const bytes=original.slice();
 assert.equal(readStorage(bytes).offset,readSave(bytes).generalOffset+0xf800);
 const active=readSave(bytes).generalOffset, backup=active?0:0x40000;
 bytes[active+0xf800+17]^=1;
 assert.equal(readStorage(bytes).offset,backup+0xf800);
 assert.equal(readSave(bytes).generalOffset,backup);
 bytes[backup+0xf800+17]^=1;
 assert.throws(()=>readStorage(bytes));
 const tied=original.slice();tied.set(tied.subarray(0,0x27c08),0x40000);
 assert.ok(readStorage(tied).tied);
 assert.throws(()=>patchBoxRecord(tied,0,0,template),/equal-counter/);
 assert.throws(()=>patchBoxRecord(tied,0,0,readStorage(tied).boxes[0][0]),/equal-counter/);
});
test('PC stats, abilities and moves edit a 136-byte record and round-trip through storage', () => {
 const mon=decodePokemon(template), data=loadBundledOriginData(), personal=data.getPersonal(mon.speciesId,mon.form);
 const ivs={hp:31,attack:31,defense:31,speed:31,spAttack:31,spDefense:31};
 const trained=patchPokemonStats(template,{level:50,nature:13,ivs},personal,personal.growthThresholds);
 assert.equal(trained.length,136);
 const changed=patchPokemonAbility(trained,22);
 const moves=decodePokemon(changed).moves.map(()=>({id:33,pp:35,ppUps:0}));
 const moved=patchPokemonMoves(changed,moves);
 const result=decodePokemon(readStorage(patchBoxRecord(original,12,4,moved)).boxes[12][4]);
 assert.equal(result.ability,22);assert.equal(result.nature,13);assert.deepEqual(result.ivs,ivs);
 assert.equal(result.experience,personal.growthThresholds[50]);assert.deepEqual(result.moves,moves);
 assert.equal(result.party,undefined);
 assert.deepEqual(patchPokemonStats(trained,{},personal,personal.growthThresholds),trained);
 for(const args of [[24,0,template],[0,30,template],[-1,0,template],[0,0,new Uint8Array(136)],[0,0,new Uint8Array(236)]])assert.throws(()=>patchBoxRecord(original,...args));
});
