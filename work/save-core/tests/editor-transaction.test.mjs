import test from 'node:test';
import assert from 'node:assert/strict';
import {applyEditorTransaction, applyFixtureTransaction, SaveTransactionError} from '../dist/transaction.js';
import {patchPartyRecord, readSave} from '../dist/save.js';
import {patchMoney, patchInventoryPocket, readInventory} from '../dist/inventory.js';
import {patchPokemonMoves, decodePokemon} from '../dist/pokemon.js';
import {saveFixture, refreshBlock, view, crcOracle} from './fixtures.mjs';

const items=[{id:1,name:'Synthetic A',pocket:'keyItems'},{id:2,name:'Synthetic B',pocket:'keyItems'},{id:3,name:'Synthetic C',pocket:'keyItems'}];
const data={items,getItem:id=>items.find(item=>item.id===id)};
function fixture(counters=[10,9]) {
  const bytes=saveFixture({counters}),base=counters[0]>counters[1]?0:0x40000;
  view(bytes).setUint32(base+0x78,123,true);
  bytes.fill(0,base+0x8d8,base+0x9a0);
  view(bytes).setUint16(base+0x8d8,1,true);view(bytes).setUint16(base+0x8da,1,true);
  view(bytes).setUint16(base+0x8dc,2,true);view(bytes).setUint16(base+0x8de,1,true);
  view(bytes).setUint16(base+0xea4,1,true);view(bytes).setUint16(base+0xea6,2,true);
  refreshBlock(bytes,base);return bytes;
}
function assertAudit(source,result) {
  const actual=[];
  for(let i=0;i<source.length;i++)if(source[i]!==result.bytes[i])actual.push(i);
  const reported=result.report.changedRanges.flatMap(({start,end})=>Array.from({length:end-start},(_,i)=>start+i));
  assert.deepEqual(reported,actual);assert.equal(result.report.changed,actual.length>0);
  const base=result.report.generalOffset;
  assert.equal(view(result.bytes).getUint16(base+0xf7ca,true),crcOracle(result.bytes.subarray(base,base+0xf7bc)));
}
for(const counters of [[10,9],[9,10]])test(`editor multi-operation transaction composes and audits both mirrors ${counters}`,()=>{
  const source=fixture(counters),before=source.slice(),record=patchPokemonMoves(readSave(source).partyRecords[0],[{id:33,pp:22,ppUps:0},{id:0,pp:0,ppUps:0},{id:0,pp:0,ppUps:0},{id:0,pp:0,ppUps:0}]);
  const pocket=[{id:2,quantity:9}];
  const result=applyEditorTransaction(source,[{type:'setMoney',money:54321},{type:'replacePartyRecord',slot:0,record},{type:'replacePocket',pocket:'keyItems',items:pocket,data}]);
  assert.deepEqual(result.bytes,patchInventoryPocket(patchPartyRecord(patchMoney(source,54321),0,record),'keyItems',pocket,data));
  assert.equal(result.report.policy,'editor');assert.equal(result.report.operations,3);
  assert.equal(readInventory(result.bytes).money,54321);assert.deepEqual(readInventory(result.bytes).registeredItems,[2,0]);
  assert.equal(decodePokemon(readSave(result.bytes).partyRecords[0]).moves[0].id,33);
  assertAudit(source,result);assert.deepEqual(source,before);
  record.fill(0);assert.equal(decodePokemon(readSave(result.bytes).partyRecords[0]).moves[0].id,33);
});

test('editor transactions validate staged pocket state and shortcuts at every step',()=>{
  const source=fixture();
  const result=applyEditorTransaction(source,[
    {type:'replacePocket',pocket:'keyItems',items:[{id:2,quantity:1}],data},
    {type:'replacePocket',pocket:'keyItems',items:[{id:3,quantity:1}],data},
  ]);
  assert.deepEqual(readInventory(result.bytes).registeredItems,[0,0]);
  assert.deepEqual(readInventory(result.bytes).pockets.keyItems,[{id:3,quantity:1}]);assertAudit(source,result);
});

test('editor late failures preserve original and expose operation index and actionable context',()=>{
  const source=fixture(),before=source.slice();
  for(const bad of [
    {type:'replacePocket',pocket:'items',items:[{id:1,quantity:1}],data},
    {type:'replacePartyRecord',slot:99,record:readSave(source).partyRecords[0]},
    {type:'setMoney',money:10000000},
  ]) {
    assert.throws(()=>applyEditorTransaction(source,[{type:'setMoney',money:42},bad]),error=>{
      assert.ok(error instanceof SaveTransactionError);assert.equal(error.operationIndex,1);
      if(bad.type==='replacePocket')assert.deepEqual(error.context,{kind:'wrong-pocket',itemId:1,pocketLabel:'Items'});
      return true;
    });assert.deepEqual(source,before);
  }
  assert.equal(readInventory(applyEditorTransaction(source,[{type:'setMoney',money:42}]).bytes).money,42);
});

test('normal and fixture policies reject each other and reject raw operations',()=>{
  const source=fixture();
  assert.throws(()=>applyEditorTransaction(source,[{type:'setPocket',name:'key',items:[[65535,65535]]}]),/Unknown editor operation/);
  assert.throws(()=>applyFixtureTransaction(source,[{type:'setMoney',money:123}]),/Unknown fixture operation/);
  for(const mutate of [applyEditorTransaction,applyFixtureTransaction]){
    assert.throws(()=>mutate(source,[{type:'patchGeneralRegion',offset:0,bytes:[]}]),/Unknown/);
    for(const ops of [null,{},new Array(1),Array(10001).fill({type:'setMoney',money:1})])assert.throws(()=>mutate(source,ops));
  }
  const fixtureResult=applyFixtureTransaction(source,[{type:'setPocket',name:'key',items:[[65535,65535],[65535,1]]}]);
  assert.equal(fixtureResult.report.policy,'fixture');
  assert.deepEqual(readInventory(fixtureResult.bytes).pockets.keyItems,[{id:65535,quantity:65535},{id:65535,quantity:1}]);
});

test('empty, exact no-op, and cancelling normal transactions preserve every byte and ownership',()=>{
  const source=fixture(),before=source.slice(),money=readInventory(source).money;
  for(const operations of [[],[{type:'setMoney',money}],[{type:'setMoney',money:7},{type:'setMoney',money}]]){
    const result=applyEditorTransaction(source,operations);assert.deepEqual(result.bytes,source);assertAudit(source,result);
    result.bytes[0]^=255;assert.deepEqual(source,before);
  }
});

test('operation discriminants cannot exploit property-key coercion into silent no-ops',()=>{
  const source=fixture();
  for(const mutate of [applyEditorTransaction,applyFixtureTransaction])for(const type of [['setMoney'],['setFlag'],{toString:()=> 'setMoney'},{toString:()=> 'setFlag'}]){
    assert.throws(()=>mutate(source,[{type}]),/Unknown/);
  }
});

test('sorted pockets reject malformed mixed entries before invoking sort comparisons',()=>{
  const source=fixture();
  const tmData={items:[],getItem:id=>({id,name:'Synthetic TM',pocket:'tmHm'})};
  for(const entries of [[{id:1,quantity:1},null],[{id:1,quantity:1},undefined],[{id:1,quantity:1},42]]){
    assert.throws(()=>applyEditorTransaction(source,[{type:'replacePocket',pocket:'tmHm',items:entries,data:tmData}]),/Invalid item stack/);
  }
});
