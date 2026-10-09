import test from 'node:test';
import assert from 'node:assert/strict';
import {decodePokemon, patchPokemonMoves} from '../dist/pokemon.js';
import {readSave, patchPartyRecord, crc16} from '../dist/save.js';
import {unwrapSave, wrapSave} from '../dist/save-container.js';
import {pokemonFixture, saveFixture, view, decodeOracle, crcOracle, rng} from './fixtures.mjs';

for (let selector = 0; selector < 32; selector++) {
  test(`independent seeded plaintext oracle: shuffle ${selector}, boxed and party`, () => {
    const next = rng(0x1000 + selector);
    for (const length of [136, 236]) for (let round = 0; round < 8; round++) {
      const source = pokemonFixture(selector, length, next()), before = source.slice(), oracle = decodeOracle(source);
      const moves = Array.from({length: 4}, () => ({id: next() & 65535, pp: next() & 255, ppUps: next() & 3}));
      const result = patchPokemonMoves(source, moves), edited = decodeOracle(result), expected = oracle.logical.slice(), data = view(expected);
      moves.forEach((move, i) => {data.setUint16(32 + i * 2, move.id, true); expected[40 + i] = move.pp; expected[44 + i] = move.ppUps;});
      assert.equal((oracle.pid >>> 13) & 31, selector);
      assert.equal(edited.checksumOk, true); assert.deepEqual(edited.logical, expected);
      assert.deepEqual(edited.tail, oracle.tail); assert.equal(edited.pid, oracle.pid);
      assert.deepEqual(decodePokemon(result).moves, moves); assert.deepEqual(source, before);
      assert.deepEqual(patchPokemonMoves(result, decodePokemon(source).moves), source);
    }
  });
}

test('CRC oracle agrees for seeded lengths and nonzero-offset byte views', () => {
  const next = rng();
  for (const length of [0, 1, 2, 3, 127, 128, 129, 0x1000, 0xf7bc]) {
    const backing = Uint8Array.from({length: length + 19}, () => next() & 255), bytes = backing.subarray(13, 13 + length);
    assert.equal(crc16(bytes), crcOracle(bytes));
  }
});

test('every header flag bit is rejected for mutation, including exact no-op', () => {
  const record = pokemonFixture();
  for (let bit = 0; bit < 16; bit++) {
    const flagged = record.slice(); view(flagged).setUint16(4, 1 << bit, true);
    assert.throws(() => patchPokemonMoves(flagged, decodePokemon(record).moves), /flags/);
  }
});

test('source and replacement corruption cannot be repaired by party replacement', () => {
  const source = saveFixture(), before = source.slice(), valid = pokemonFixture(7);
  for (const offset of [6, 8, 67, 135]) {
    const corrupt = valid.slice(); corrupt[offset] ^= 0x80;
    assert.throws(() => patchPartyRecord(source, 0, corrupt), /checksum/);
  }
  for (let bit = 0; bit < 16; bit++) {
    const corrupt = valid.slice(); view(corrupt).setUint16(4, 1 << bit, true);
    assert.throws(() => patchPartyRecord(source, 0, corrupt), /flags/);
  }
  assert.deepEqual(source, before);
});

function footer() {
  const notice='|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:', cookie='|-DESMUME SAVE-|';
  const result=new Uint8Array(122); result.set(new TextEncoder().encode(notice));
  [0x40001,0x80000,6,3,0x80000,0].forEach((value,i)=>view(result).setUint32(notice.length+4*i,value,true));
  result.set(new TextEncoder().encode(cookie),notice.length+24); return result;
}

test('raw and DSV Buffer/offset inputs own all returned byte arrays', () => {
  const raw = saveFixture(), dsv = new Uint8Array(raw.length + 122); dsv.set(raw); dsv.set(footer(), raw.length);
  for (const source of [raw, dsv]) for (const isBuffer of [false, true]) for (const offset of [0, 1, 17]) {
    const backing = isBuffer ? Buffer.alloc(source.length + offset + 9, 0xb7) : new Uint8Array(source.length + offset + 9).fill(0xb7);
    backing.set(source, offset); const input = backing.subarray(offset, offset + source.length), before = Uint8Array.from(backing);
    const parsed = unwrapSave(input), wrapped = wrapSave(parsed.bytes, parsed.container);
    assert.deepEqual(Uint8Array.from(wrapped), source);
    parsed.bytes[0] ^= 1; wrapped[1] ^= 1;
    if (parsed.container.kind === 'desmume') parsed.container.footer[0] ^= 1;
    assert.deepEqual(Uint8Array.from(backing), before);
  }
});

test('save replacement owns input Buffer and offset view, preserves every unrelated byte', () => {
  for (const counters of [[12, 11], [11, 12]]) {
    const raw = saveFixture({counters}), active = counters[0] > counters[1] ? 0 : 0x40000;
    const backing = Buffer.alloc(raw.length + 29, 0xaa); backing.set(raw, 13);
    const source = backing.subarray(13, raw.length + 13), before = Uint8Array.from(backing);
    const replacement = pokemonFixture(31), result = patchPartyRecord(source, 1, replacement), start = active + 0x98 + 236;
    for (let i=0;i<raw.length;i++) if (result[i] !== source[i]) assert.ok(i >= start && i < start + 236 || i >= active + 0xf7ca && i < active + 0xf7cc, `offset ${i.toString(16)}`);
    assert.deepEqual(readSave(result).partyRecords[1], replacement); assert.deepEqual(Uint8Array.from(backing), before);
    replacement.fill(0); assert.notEqual(result[start], 0);
  }
});

test('party replacement accepts only byte arrays; rejects array-shaped inputs',()=>{
  const source=saveFixture();
  for(const replacement of [[],[1],{length:1,0:1},null,new Uint16Array([1])])assert.throws(()=>patchPartyRecord(source,0,replacement));
});

test('stat calculation rejects sparse or malformed base-stat arrays before producing NaN',()=>{
  const stats={hp:0,attack:0,defense:0,speed:0,spAttack:0,spDefense:0};
  for(const base of [new Array(6),[10,10,,10,10,10],null,{},'123456'])assert.throws(()=>calculateStats(base,stats,stats,5,0,25));
});
import {calculateStats} from '../dist/stats.js';

test('stat mutation rejects explicit nulls rather than silently accepting a no-op',()=>{
  const record=pokemonFixture(),personal={baseStats:[30,30,30,30,30,30],growthRate:0};
  for(const key of ['ivs','evs','level','nature'])assert.throws(()=>patchPokemonStats(record,{[key]:null},personal));
});
import {patchPokemonStats} from '../dist/pokemon.js';

test('valid replacement cannot silently legitimize a corrupt active source record',()=>{
  const source=saveFixture(),valid=pokemonFixture();source[0x98+8]^=1;refreshBlock(source);
  assert.throws(()=>patchPartyRecord(source,0,valid),/checksum/);
});

test('boxed PID change rejects rather than corrupting the unchanged encrypted party tail',()=>{
  const source=saveFixture(),replacement=pokemonFixture(0,136,9001);
  assert.throws(()=>patchPartyRecord(source,0,replacement),/PID/);
});
import {refreshBlock} from './fixtures.mjs';
