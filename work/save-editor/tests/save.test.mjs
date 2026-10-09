import test from 'node:test';
import assert from 'node:assert/strict';
import {crc16, readSave, patchPartyRecord} from '../dist/save.js';
import {saveFixture, pokemonFixture} from '../../save-core/tests/fixtures.mjs';
import {patchPokemonMoves, decodePokemon} from '../dist/pokemon.js';
function changedBox(record) { const moves=decodePokemon(record).moves; moves[0]={id:900,pp:1,ppUps:0}; return patchPokemonMoves(record,moves); }

const MIRROR = 0x40000;
const GENERAL = 0xf7cc;
const STORAGE = 0xf800;
const STORAGE_SIZE = 0x18408;
const dataView = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
function updateCrc(bytes, base, offset = 0, size = GENERAL) {
  const footer = base + offset + size - 16;
  dataView(bytes).setUint16(footer + 14, crc16(bytes.subarray(base + offset, footer)), true);
}
function fixture(counters = [10, 9]) { return saveFixture({counters}); }

test('CRC matches the independent standard check vector', () => {
  assert.equal(crc16(new TextEncoder().encode('123456789')), 0x29b1);
  assert.equal(crc16(new Uint8Array()), 0xffff);
});

for (const counters of [[10, 9], [9, 10]]) {
  const active = counters[0] > counters[1] ? 0 : MIRROR;
  test(`selects higher coherent counter at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    const save = readSave(bytes);
    assert.equal(save.generalOffset, active);
    assert.equal(save.counter, 10);
    assert.equal(save.tied, false);
    assert.equal(save.partyCount, 2);
    assert.deepEqual(save.party[1], bytes.slice(active + 0x98 + 236, active + 0x98 + 236 + 136));
    assert.deepEqual(save.bytes, bytes);
    assert.deepEqual(patchPartyRecord(bytes, 1, save.party[1]), bytes);
  });

  test(`party edit preserves backup, tail and every unrelated byte at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    const original = bytes.slice();
    const record = readSave(bytes).party[1];
    record.set(changedBox(record));
    const edited = patchPartyRecord(bytes, 1, record);
    const offset = active + 0x98 + 236;
    const crcOffset = active + GENERAL - 2;
    let changes = 0;
    for (let i = 0; i < bytes.length; i++) {
      if (edited[i] === bytes[i]) continue;
      changes++;
      assert.ok((i >= offset && i < offset + 136) || i === crcOffset || i === crcOffset + 1,
        `Unexpected change at ${i.toString(16)}`);
    }
    assert.ok(changes >= 2);
    assert.deepEqual(bytes, original, 'caller input unchanged');
    assert.deepEqual(edited.slice(offset + 136, offset + 236), bytes.slice(offset + 136, offset + 236));
    const backup = active === 0 ? MIRROR : 0;
    assert.deepEqual(edited.slice(backup, backup + MIRROR), bytes.slice(backup, backup + MIRROR));
    const reparsed = readSave(edited);
    assert.equal(reparsed.counter, 10);
    assert.deepEqual(reparsed.party[1], record);
  });
}

test('copies input and party records, including Buffer and nonzero-offset views', () => {
  for (const input of [fixture(), Buffer.from(fixture()), Buffer.concat([Buffer.alloc(7), Buffer.from(fixture())]).subarray(7)]) {
    const save = readSave(input);
    const original = input[0x98];
    save.party[0][0] ^= 255;
    assert.equal(save.bytes[0x98], original);
    assert.equal(input[0x98], original);
    save.bytes[0x98] ^= 127;
    assert.equal(input[0x98], original);
    const noop = patchPartyRecord(input, 0, readSave(input).party[0]);
    noop[0] ^= 255;
    assert.notEqual(noop[0], input[0]);
  }
});

test('rejects unsupported length and saves with no intact general block', () => {
  assert.throws(() => readSave(new Uint8Array(0x80001)), /512 KiB/);
  const both = fixture();
  both[42] ^= 1;
  both[MIRROR + 42] ^= 1;
  assert.throws(() => readSave(both), /checksum|coherent/);
  for (const field of [4, 8, 12]) {
    const badFooters = fixture();
    badFooters[GENERAL - 16 + field] ^= 1;
    badFooters[MIRROR + GENERAL - 16 + field] ^= 1;
    assert.throws(() => readSave(badFooters), /footer|coherent/);
  }
  assert.throws(() => readSave(new Uint8Array(0x80000).fill(0xff)), /coherent|intact/);
});

for (const counters of [[10, 9], [9, 10]]) {
  const active = counters[0] > counters[1] ? 0 : MIRROR;
  const backup = active === 0 ? MIRROR : 0;

  test(`damaged backup remains usable; damaged/mismatched selected storage falls back from ${active.toString(16)}`, () => {
    const damages = [
      [bytes => { bytes[backup + 42] ^= 1; }, active],
      [bytes => { bytes[backup + GENERAL - 16 + 8] ^= 1; }, active],
      [bytes => { bytes.fill(0xff, backup, backup + MIRROR); }, active],
      [bytes => { bytes[active + STORAGE + 42] ^= 1; }, backup],
      [bytes => { dataView(bytes).setUint32(active + STORAGE + STORAGE_SIZE - 16, 3, true); }, backup],
    ];
    for (const [damage, expected] of damages) {
      const bytes = fixture(counters); damage(bytes);
      const save = readSave(bytes); assert.equal(save.generalOffset, expected);
      const record = changedBox(save.party[0]); const edited = patchPartyRecord(bytes, 0, record);
      const unselected = expected === 0 ? MIRROR : 0;
      assert.deepEqual(edited.slice(unselected, unselected + MIRROR), bytes.slice(unselected, unselected + MIRROR));
      assert.deepEqual(edited.slice(expected + STORAGE, expected + STORAGE + STORAGE_SIZE), bytes.slice(expected + STORAGE, expected + STORAGE + STORAGE_SIZE));
      assert.deepEqual(readSave(edited).party[0], record);
    }
  });

  test(`a damaged newest general block falls back to the older copy at ${active.toString(16)}`, () => {
    const bytes = fixture(counters);
    bytes[active + 42] ^= 1;
    const save = readSave(bytes);
    assert.equal(save.generalOffset, backup);
    assert.equal(save.counter, 9);
  });
}

test('native selection uses mirror zero on ties and special rollover comparison', () => {
  const tied = fixture([10, 10]); tied[0x300] ^= 1; updateCrc(tied, 0);
  assert.equal(readSave(tied).generalOffset, 0);
  assert.equal(readSave(fixture([0xffffffff, 0])).generalOffset, MIRROR);
  assert.equal(readSave(fixture([0, 0xffffffff])).generalOffset, 0);
  assert.equal(readSave(fixture([0, 0x80000000])).generalOffset, MIRROR);
  const tiedDamaged = fixture([10, 10]); tiedDamaged[MIRROR + 42] ^= 1;
  assert.equal(readSave(tiedDamaged).generalOffset, 0);
});

test('equal-counter mirrors are inspectable but editor writes and no-ops require an in-game save', () => {
  const tied = fixture([10, 10]), save = readSave(tied);
  assert.equal(save.tied, true);
  for (const record of [save.party[0], changedBox(save.party[0])]) {
    assert.throws(() => patchPartyRecord(tied, 0, record), /Editing equal-counter mirrors is unsupported; save once in-game first/);
  }
});

test('validates active party header and patch arguments', () => {
  for (const [offset, value] of [[0x90, 5], [0x94, 7], [0x94, 0xffffffff]]) {
    const bad = fixture();
    dataView(bad).setUint32(offset, value, true);
    updateCrc(bad, 0);
    assert.throws(() => readSave(bad), /party header/);
  }
  const empty = fixture();
  dataView(empty).setUint32(0x94, 0, true);
  updateCrc(empty, 0);
  assert.deepEqual(readSave(empty).party, []);
  const bytes = fixture();
  for (const slot of [-1, 2, 0.5, NaN, Infinity]) {
    assert.throws(() => patchPartyRecord(bytes, slot, new Uint8Array(136)), /Party slot/);
  }
  assert.throws(() => patchPartyRecord(bytes, 0, new Uint8Array(135)), /136-byte/);
});


test('full party stat edit preserves all other records, mirror, storage and gap bytes', () => {
  for (const active of [0, MIRROR]) {
    const bytes = fixture(active === 0 ? [10, 9] : [9, 10]);
    const before = bytes.slice();
    const save = readSave(bytes);
    assert.equal(save.partyRecords[0].length, 236);
    assert.deepEqual(patchPartyRecord(bytes, 0, save.partyRecords[0]), bytes);
    const record = save.partyRecords[1].slice();
    record.set(pokemonFixture(1, 236, 95));
    const edited = patchPartyRecord(bytes, 1, record);
    const start = active + 0x98 + 236;
    const crc = active + GENERAL - 2;
    for (let i = 0; i < bytes.length; i++) {
      if (edited[i] !== bytes[i]) assert.ok((i >= start && i < start + 236) || i === crc || i === crc + 1);
    }
    assert.deepEqual(readSave(edited).partyRecords[1], record);
    assert.deepEqual(bytes, before);
    save.partyRecords[0].fill(0);
    assert.deepEqual(bytes, before);
    assert.deepEqual(save.party[0], readSave(bytes).party[0]);
  }
});
