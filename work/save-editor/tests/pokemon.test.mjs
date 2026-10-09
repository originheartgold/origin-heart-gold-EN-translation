import test from 'node:test';
import assert from 'node:assert/strict';
import { decodePokemon, patchPokemonMoves } from '../dist/core/pokemon.js';

// Invented logical records. Generate the shuffle permutation independently,
// and use BigInt arithmetic instead of the implementation's Math.imul cipher.
const moves = [
  {id: 44, pp: 7, ppUps: 0}, {id: 701, pp: 11, ppUps: 1},
  {id: 12, pp: 18, ppUps: 2}, {id: 983, pp: 24, ppUps: 3},
];
function permutations(values) {
  if (!values.length) return [[]];
  return values.flatMap(v => permutations(values.filter(x => x !== v)).map(tail => [v, ...tail]));
}
const permutations24 = permutations([0, 1, 2, 3]);
function fixture(selector = 0, length = 236) {
  const record = new Uint8Array(length);
  const header = new DataView(record.buffer);
  const pid = (selector << 13) | 0x345;
  header.setUint32(0, pid, true);
  const logical = Array.from({length: 4}, (_, block) => Uint8Array.from({length: 32}, (_, i) => (block * 61 + i * 7 + 19) & 255));
  new DataView(logical[0].buffer).setUint16(0, 1018, true);
  const b = new DataView(logical[1].buffer);
  moves.forEach((move, i) => { b.setUint16(2*i, move.id, true); b.setUint8(8+i, move.pp); b.setUint8(12+i, move.ppUps); });
  const plain = new Uint8Array(128);
  // Lexicographic permutations describe physical block order. The codec uses
  // the inverse mapping (logical block to physical offset).
  permutations24[selector % 24].forEach((logicalIndex, physical) => plain.set(logical[logicalIndex], physical * 32));
  const payload = new DataView(plain.buffer);
  let sum = 0;
  for (let i = 0; i < 128; i += 2) sum = (sum + payload.getUint16(i, true)) & 65535;
  header.setUint16(6, sum, true);
  let seed = BigInt(sum);
  for (let i = 0; i < 128; i += 2) {
    seed = (seed * 1103515245n + 24691n) & 0xffffffffn;
    header.setUint16(8+i, payload.getUint16(i, true) ^ Number(seed >> 16n), true);
  }
  for (let i = 136; i < length; i++) record[i] = (i * 3 + 41) & 255;
  return record;
}

for (let selector = 0; selector < 32; selector++) {
  test(`shuffle selector ${selector}: decode, exact no-op, full slot swap and restoration`, () => {
    const record = fixture(selector);
    const snapshot = record.slice();
    const decoded = decodePokemon(record);
    assert.equal(decoded.pid, (selector << 13) | 0x345);
    assert.equal(decoded.speciesId, 1018);
    assert.deepEqual(decoded.moves, moves);
    assert.deepEqual(patchPokemonMoves(record, moves), record);
    const swapped = [moves[3], moves[1], moves[2], moves[0]];
    const edited = patchPokemonMoves(record, swapped);
    assert.deepEqual(decodePokemon(edited).moves, swapped);
    assert.deepEqual(edited.slice(136), record.slice(136));
    assert.deepEqual(edited.slice(0, 6), record.slice(0, 6));
    assert.deepEqual(patchPokemonMoves(edited, moves), record);
    assert.deepEqual(record, snapshot);
  });
}

test('new move ID changes checksum; boxed and party records round-trip', () => {
  for (const length of [136, 236]) {
    const record = fixture(23, length);
    const replacement = moves.map(m => ({...m}));
    replacement[0] = {id: 1024, pp: 4, ppUps: 2};
    const edited = patchPokemonMoves(record, replacement);
    assert.notDeepEqual(edited.slice(6, 8), record.slice(6, 8));
    assert.deepEqual(decodePokemon(edited).moves, replacement);
    assert.deepEqual(patchPokemonMoves(edited, moves), record);
  }
});

test('rejects truncation, unsupported size, flags, and checksum corruption', () => {
  for (const length of [0, 8, 135, 137, 235, 237]) assert.throws(() => decodePokemon(new Uint8Array(length)), /Expected/);
  assert.throws(() => decodePokemon(null), /Expected/);
  const flags = fixture(); flags[4] = 1;
  assert.throws(() => decodePokemon(flags), /flags/);
  assert.throws(() => patchPokemonMoves(flags, moves), /flags/);
  const corrupt = fixture(); corrupt[8] ^= 1;
  assert.throws(() => decodePokemon(corrupt), /checksum/);
  assert.throws(() => patchPokemonMoves(corrupt, moves), /checksum/);
});

test('rejects invalid move arrays and fields without changing input', () => {
  const record = fixture(); const snapshot = record.slice();
  for (const invalid of [null, [], moves.slice(0, 3), [...moves, moves[0]], [null,...moves.slice(1)]]) {
    assert.throws(() => patchPokemonMoves(record, invalid));
  }
  for (const [field, values] of Object.entries({id: [-1, 65536, 0.5, NaN, Infinity], pp: [-1, 256, 0.5, NaN], ppUps: [-1, 4, 0.5, NaN]})) {
    for (const value of values) assert.throws(() => patchPokemonMoves(record, [{...moves[0], [field]: value}, ...moves.slice(1)]), /Invalid/);
  }
  assert.deepEqual(record, snapshot);
});

test('Buffer and offset views remain immutable during decode and patch', () => {
  const raw = fixture(17);
  const backing = new Uint8Array(300); backing.fill(207); backing.set(raw, 19);
  for (const record of [Buffer.from(raw), backing.subarray(19, 255), Buffer.from(backing).subarray(19, 255)]) {
    const before = Uint8Array.from(record);
    decodePokemon(record);
    assert.deepEqual(Uint8Array.from(record), before);
    const edited = patchPokemonMoves(record, [moves[1], moves[0], moves[2], moves[3]]);
    assert.deepEqual(Uint8Array.from(record), before);
    assert.deepEqual(edited.slice(136), before.slice(136));
    edited.fill(0);
    assert.deepEqual(Uint8Array.from(record), before);
  }
  assert.equal(backing[18], 207); assert.equal(backing[255], 207);
});
