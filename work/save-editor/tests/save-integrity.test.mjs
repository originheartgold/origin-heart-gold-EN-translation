import test from 'node:test';
import assert from 'node:assert/strict';
import { syntheticSave, sealBlock, GENERAL_SIZE, STORAGE_SIZE, MIRROR, STORAGE } from './fixture.mjs';
import { readSave, readStorage, patchPartyRecord, addPartyRecord, removePartyRecord, patchBoxRecord, crc16 } from '../dist/core/save.js';
import { patchPokemonShiny } from '../dist/core/pokemon.js';
import { patchBadge, patchCoins, patchPlayTime, patchTrainerProfile } from '../dist/core/trainer.js';
import { patchPokedex, completePokedex } from '../dist/core/pokedex.js';
import { patchGiftReceived, removePendingGift, removeWonderCard } from '../dist/core/mystery-gift.js';
import { transferPokemon, sortBox, batchBox } from '../dist/core/operations.js';
import { loadBundledOriginData } from '../dist/core/bundled-data.js';

import { patchMoney, patchInventoryPocket, fillBag } from '../dist/core/inventory.js';

const blocks = [
  {name: 'general', offset: 0, size: GENERAL_SIZE, id: 0, read: bytes => readSave(bytes).generalOffset},
  {name: 'storage', offset: STORAGE, size: STORAGE_SIZE, id: 1, read: bytes => readStorage(bytes).offset},
];
function tie(bytes, block) {
  bytes.set(bytes.subarray(block.offset, block.offset + block.size), MIRROR + block.offset);
}
for (const block of blocks) {
 test(`${block.name}: corruption rejects this generation and falls back coherently`,()=>{
  const bytes=syntheticSave();bytes[block.offset+17]^=1;
  assert.equal(readSave(bytes).generalOffset,MIRROR);
  assert.equal(readStorage(bytes).offset,MIRROR+STORAGE);
  bytes[MIRROR+block.offset+17]^=1;assert.throws(()=>block.read(bytes));
 });
 test(`${block.name}: invalid footer size, magic and block ID are never selected`,()=>{
  for(const field of [4,8,12]){const bytes=syntheticSave();for(const base of [0,MIRROR])bytes[base+block.offset+block.size-16+field]^=1;assert.throws(()=>block.read(bytes));}
 });
}

test('equal-counter coherent generations reject every editor write, even no-ops',()=>{
 const bytes=syntheticSave();for(const block of blocks)tie(bytes,block);
 const before=bytes.slice(),record=readSave(bytes).partyRecords[0];
 const edits=[b=>patchPartyRecord(b,0,record),b=>patchCoins(b,0),b=>patchBadge(b,0,0,false),
  b=>patchTrainerProfile(b,{tid:0,sid:0,gender:'male'}),b=>patchPlayTime(b,{hours:0,minutes:0,seconds:0}),
  b=>patchPokedex(b,1,{seen:false,caught:false}),b=>patchGiftReceived(b,10,false),b=>removePendingGift(b,0),b=>removeWonderCard(b,0),
  b=>addPartyRecord(b,record),b=>removePartyRecord(b,0),b=>completePokedex(b),b=>patchBoxRecord(b,0,0,record.slice(0,136))];
 for(const change of edits){assert.throws(()=>change(bytes),/equal-counter/i);assert.deepEqual(bytes,before);}
});

test('failed cross-block move leaves the input unchanged',()=>{
 const bytes=syntheticSave(),data=loadBundledOriginData();
 for(const block of blocks)tie(bytes,block);
 const before=bytes.slice();
 assert.throws(()=>transferPokemon(bytes,{kind:'party',slot:0},{kind:'pc',box:0,slot:0},'move',data),/equal-counter/i);
 assert.deepEqual(bytes,before);
});

test('party writes reject corrupt records and preserve both checksum layers and all unrelated bytes', () => {
  const bytes = syntheticSave(), before = bytes.slice();
  const record = readSave(bytes).partyRecords[0];
  const corrupt = record.slice(); corrupt[10] ^= 1;
  for (const change of [b => patchPartyRecord(b, 0, corrupt), b => addPartyRecord(b, corrupt)]) {
    assert.throws(() => change(bytes)); assert.deepEqual(bytes, before);
  }
  const changed = patchPartyRecord(bytes, 0, patchPokemonShiny(record, true));
  const view = new DataView(changed.buffer);
  assert.equal(view.getUint16(0x640, true), crc16(changed.subarray(0x90, 0x640)));
  assert.equal(view.getUint16(GENERAL_SIZE - 2, true), crc16(changed.subarray(0, GENERAL_SIZE - 16)));
  for (let i = 0; i < bytes.length; i++) {
    if (changed[i] !== bytes[i]) assert.ok((i >= 0x98 && i < 0x98 + 236) || i === 0x640 || i === 0x641 || i >= GENERAL_SIZE - 2 && i < GENERAL_SIZE);
  }
  assert.deepEqual(bytes, before);
  assert.equal(readSave(changed).counter, readSave(bytes).counter);
});


test('tied mirrors reject writes; empty batches preserve the input', () => {
  const data = loadBundledOriginData();
  const bytes = syntheticSave();
  tie(bytes, blocks[0]); tie(bytes, blocks[1]);
  const before = bytes.slice();
  assert.throws(()=>patchMoney(bytes, 0), /equal-counter/);
  assert.throws(()=>patchInventoryPocket(bytes, 'balls', [], data.inventory), /equal-counter/);
  assert.throws(()=>sortBox(bytes, 0), /equal-counter/);
  assert.deepEqual(batchBox(bytes, 0, () => assert.fail('empty slots must be skipped')), before);
  for (const change of [
    b => patchMoney(b, 100),
    b => patchInventoryPocket(b, 'balls', [{id: 4, quantity: 1}], data.inventory),
    b => fillBag(b, data.inventory),
  ]) {
    assert.throws(() => change(bytes), /equal-counter/i);
    assert.deepEqual(bytes, before);
  }
});
