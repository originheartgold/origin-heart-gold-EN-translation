import test from 'node:test';
import assert from 'node:assert/strict';
import {readSave} from '../dist/save.js';
import {decodePokemon} from '../dist/pokemon.js';
import {applySaveTransaction} from '../dist/fixture.js';
import {saveFixture, pokemonFixture, crcOracle, view} from './fixtures.mjs';

// Small independent sentinels for the mutation runner. Each proposed mutation
// must compile and fail its named assertion; crashes/import failures do not count.
test('mutation contract: save block CRC rejection', () => {
  const source = saveFixture();
  source[0x20] ^= 1; source[0x40020] ^= 1;
  assert.throws(() => readSave(source), /intact|checksum/);
});
test('mutation contract: Pokemon checksum rejection', () => {
  const source = pokemonFixture(); source[81] ^= 1;
  assert.throws(() => decodePokemon(source), /checksum/);
});
test('mutation contract: native saved flag upper boundary', () => {
  assert.throws(() => applySaveTransaction(saveFixture(), [{type: 'setFlag', flag: 0xca0, value: true}]), /Saved flag/);
});
test('mutation contract: shrunken inactive party slot rejection', () => {
  assert.throws(() => applySaveTransaction(saveFixture(), [
    {type: 'setPartyCount', count: 1},
    {type: 'editPartyMon', slot: 1, changes: {item: 41}, tailPolicy: 'preserve'},
  ]), error => error.operationIndex === 1 && /Active party slot/.test(error.message));
});
test('mutation contract: ordinary native mirror ranking', () => {
  let save;
  assert.doesNotThrow(() => { save = readSave(saveFixture({counters: [9, 10]})); });
  assert.equal(save.generalOffset, 0x40000);
});
test('mutation contract: exact native counter rollover', () => {
  let save;
  assert.doesNotThrow(() => { save = readSave(saveFixture({counters: [0xffffffff, 0]})); });
  assert.equal(save.generalOffset, 0x40000);
});
test('mutation contract: transaction writes independent CRC', () => {
  let result;
  assert.doesNotThrow(() => { result = applySaveTransaction(saveFixture(), [{type: 'setVar', var: 0x4000, value: 77}]); });
  assert.equal(view(result.bytes).getUint16(0xf7ca, true), crcOracle(result.bytes.subarray(0, 0xf7bc)));
});
test('mutation contract: caller ownership after transaction', () => {
  const source = saveFixture(), before = source.slice();
  assert.doesNotThrow(() => applySaveTransaction(source, [{type: 'setVar', var: 0x4000, value: 77}]));
  assert.ok(source.every((byte, index) => byte === before[index]), 'Transaction changed caller-owned bytes');
});
