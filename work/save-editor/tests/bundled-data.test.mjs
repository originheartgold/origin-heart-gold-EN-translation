import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {loadBundledOriginData,validateBundledReference} from '../dist/core/bundled-data.js';
import {bundledReference} from '../dist/core/generated-reference.js';
import {loadOriginData} from '../dist/core/rom.js';
test('bundled metadata has verified deterministic content hash and complete English catalogs',()=>{
 validateBundledReference(bundledReference);
 assert.equal(createHash('sha256').update(JSON.stringify(bundledReference.payload)).digest('hex'),bundledReference.provenance.payloadSha256);
 const d=loadBundledOriginData();assert.deepEqual(d.catalog.readiness,{moves:902,species:1025,items:768});assert.equal(d.inventory.items.length,790);
 assert.equal(d.catalog.getSpecies(1).name,'Bulbasaur'); assert.equal(d.catalog.getMove(1).name,'Pound');
 for(const args of [[0,0],[1026,0],[1,-1],[1,256],[1.5,0]])assert.throws(()=>d.getPersonal(...args));
 assert.equal(d.catalog.getMove(-1),undefined);assert.equal(d.catalog.getMove(921),undefined);
});
test('bundled metadata rejects invalid version, table counts, indices and values',()=>{
 for(const mutate of [r=>r.extra='not allowed',r=>r.payload.extra=[],r=>r.payload=null,r=>r.provenance.sources.extra='0'.repeat(64),r=>r.payload.species[0].extra='not allowed',r=>r.payload.species[0].name=123,r=>r.payload.moves[1].name={},r=>r.payload.items[0].extra=0,r=>r.schemaVersion=2,r=>r.gameVersion='other',r=>r.provenance.romSha256='bad',r=>r.payload.personal.pop(),r=>r.payload.personal[1][6]=8,r=>r.payload.forms[0][1]=1441,r=>r.payload.growth[0].pop(),r=>r.payload.moves[1].id=2,r=>r.payload.moves[1].basePp=-1,r=>r.payload.species[0].id=0,r=>r.payload.items[0].pocket='unknown',r=>r.payload.readiness.moves=0]) {
 const r=structuredClone(bundledReference);mutate(r);assert.throws(()=>validateBundledReference(r),/Invalid bundled/);
 }
});
test('bundled provider protects returned catalogs and isolates editable stats',()=>{
 const d=loadBundledOriginData();assert.throws(()=>d.catalog.moves[0].name='changed');assert.throws(()=>d.inventory.items[0].name='changed');
 const stats=d.getPersonal(1,0);stats.baseStats[0]=0;assert.notEqual(d.getPersonal(1,0).baseStats[0],0);assert.throws(()=>stats.growthThresholds[1]=99);
});
test('optional local English ROM parity: every species/form, growth threshold, move and item', {skip:!process.env.ORIGIN_EN_ROM},async()=>{
 const rom=new Uint8Array(await readFile(process.env.ORIGIN_EN_ROM)), expected=await loadOriginData(rom),actual=loadBundledOriginData();
 assert.equal(createHash('sha256').update(rom).digest('hex'),bundledReference.provenance.romSha256);
 assert.deepEqual(actual.catalog.moves,expected.catalog.moves);assert.deepEqual(actual.catalog.species,expected.catalog.species);assert.deepEqual(actual.catalog.readiness,expected.catalog.readiness);assert.deepEqual(actual.inventory.items,expected.inventory.items);
 for(let id=0;id<921;id++)assert.deepEqual(actual.catalog.getMove(id),expected.catalog.getMove(id));
 for(let id=1;id<=1025;id++)for(let form=0;form<=255;form++)assert.deepEqual(actual.getPersonal(id,form),expected.getPersonal(id,form));
});
