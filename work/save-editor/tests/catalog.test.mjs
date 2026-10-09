import test from 'node:test';
import assert from 'node:assert/strict';
import {createNameCatalog, maxMovePp, validateMoveChoice} from '../dist/core/catalog.js';
function fixture() {
 const moves=Array(921), species=Array(1439), items=Array(791);
 moves[1]='Test Alpha'; moves[2]='Test Alpha'; moves[3]='---'; moves[4]='Empty PP'; species[1]='Test Species'; items[1]='Test Item';
 const records=Array.from({length:921},()=>new Uint8Array(40)); records[1].set([12,0,2,80,95,15]); records[2][5]=1; records[3][5]=10;
 return {moves,species,items,records,catalog:createNameCatalog(moves,species,items,records)};
}
test('catalog aligns IDs without deduplicating equal labels and uses live PP byte 5',()=>{
 const {catalog}=fixture(); assert.deepEqual(catalog.moves.map(m=>m.id),[1,2]);
 assert.deepEqual(catalog.getMove(1),{id:1,name:'Test Alpha',basePp:15,type:12,power:80,accuracy:95});
 assert.equal(catalog.getMove(3).name,undefined); assert.equal(catalog.getMove(1.2),undefined); assert.equal(catalog.getMove(99999),undefined);
 assert.equal(catalog.getSpecies(1).name,'Test Species'); assert.deepEqual(catalog.readiness,{moves:2,species:1,items:1});
});
test('catalog rejects incorrect name and live move archive layouts',()=>{
 const {moves,species,items,records}=fixture();
 assert.throws(()=>createNameCatalog(moves,species,items,records.slice(1)),/records/);
 records[0]=new Uint8Array(16); assert.throws(()=>createNameCatalog(moves,species,items,records),/records/);
 records[0]=new Uint8Array(40); assert.throws(()=>createNameCatalog(moves.slice(1),species,items,records),/sizes/);
});
test('catalog stays usable with undecodable Chinese names without inventing English choices',()=>{
 const {records}=fixture();const catalog=createNameCatalog(Array(921),Array(1439),Array(791),records);
 assert.deepEqual(catalog.readiness,{moves:0,species:0,items:0});assert.equal(catalog.getMove(1).basePp,15);
});
test('PP limits and move selections reject invalid input while retaining explicit empty slots',()=>{
 const {catalog}=fixture();assert.deepEqual([0,1,2,3].map(v=>maxMovePp(catalog.getMove(1),v)),[15,18,21,24]);
 assert.equal(maxMovePp(catalog.getMove(2),3),1);
 for(const v of [-1,4,1.5,NaN])assert.throws(()=>maxMovePp(catalog.getMove(1),v),/PP Ups/);
 validateMoveChoice(catalog,1,24,3);validateMoveChoice(catalog,0,0,0);
 for(const args of [[0,1,0],[0,0,1],[1,25,3],[1,-1,0],[1,1.5,0],[1,NaN,0],[3,5,0],[4,0,0],[10000,1,0]])assert.throws(()=>validateMoveChoice(catalog,...args));
});
