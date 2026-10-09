import test from 'node:test';
import assert from 'node:assert/strict';
import {decodePokemon, patchPokemonShiny, patchPokemonPokerus, patchPokemonMoves, patchPokemonStats} from '../dist/core/pokemon.js';
function permutations(v) { return v.length ? v.flatMap(x => permutations(v.filter(y => y !== x)).map(t => [x, ...t])) : [[]]; }
const orders = permutations([0, 1, 2, 3]);
function crypt(bytes, seed) {
  const out = Uint8Array.from(bytes), view = new DataView(out.buffer); let state = BigInt(seed);
  for (let i = 0; i < out.length; i += 2) {
    state = (state * 1103515245n + 24691n) & 0xffffffffn;
    view.setUint16(i, view.getUint16(i, true) ^ Number(state >> 16n), true);
  }
  return out;
}
function logical(record) {
  const v = new DataView(record.buffer, record.byteOffset), pid = v.getUint32(0, true);
  const plain = crypt(record.subarray(8, 136), v.getUint16(6, true));
  return [0,1,2,3].map(id => plain.slice(orders[((pid >>> 13) & 31) % 24].indexOf(id) * 32, orders[((pid >>> 13) & 31) % 24].indexOf(id) * 32 + 32));
}
function fixture(selector, {xor = 8, override = false, pokerus = 0, length = 236} = {}) {
  const pid = ((selector << 13) | 0x5a000031) >>> 0;
  const r = new Uint8Array(length), header = new DataView(r.buffer); header.setUint32(0, pid, true);
  const blocks = Array.from({length: 4}, (_, b) => Uint8Array.from({length: 32}, (_, i) => (b * 63 + i * 7) & 255));
  const a = new DataView(blocks[0].buffer), b = new DataView(blocks[1].buffer);
  for (let i=16;i<22;i++) a.setUint8(i,0);
  b.setUint32(16,0x12345678,true);
  a.setUint32(4, ((pid >>> 16) ^ (pid & 65535) ^ xor) >>> 0, true);
  b.setUint32(20, (0x01123456 | (14 << 25) | (override ? 0x80000000 : 0)) >>> 0, true);
  blocks[3][26] = pokerus;
  const plain = new Uint8Array(128); orders[selector % 24].forEach((id, i) => plain.set(blocks[id], i * 32));
  let sum = 0; const data = new DataView(plain.buffer);
  for (let i = 0; i < 128; i += 2) sum = (sum + data.getUint16(i, true)) & 65535;
  header.setUint16(6, sum, true); r.set(crypt(plain, sum), 8);
  if (length === 236) { const tail=Uint8Array.from({length: 100}, (_, i) => (i * 11 + 7) & 255); tail[4]=50; r.set(crypt(tail,pid),136); }
  return r;
}
for (let selector = 0; selector < 32; selector++) test(`traits selector ${selector}: native override and disease preserve every unrelated byte`, () => {
  const record = fixture(selector), original = record.slice(), before = decodePokemon(record);
  const shiny = patchPokemonShiny(record, true), after = decodePokemon(shiny);
  assert.equal(after.shiny, true); assert.equal(after.naturalShiny, false); assert.equal(after.shinyOverride, true);
  assert.deepEqual({...after, shiny: before.shiny, shinyOverride: before.shinyOverride}, before);
  const plainBefore = logical(record), plainAfter = logical(shiny);
  plainAfter[1][23] ^= 128; assert.deepEqual(plainAfter, plainBefore);
  assert.deepEqual(shiny.slice(0, 6), record.slice(0, 6)); assert.deepEqual(shiny.slice(136), record.slice(136));
  assert.deepEqual(patchPokemonShiny(shiny, true), shiny); assert.deepEqual(patchPokemonShiny(shiny, false), record);
  for (const status of ['infected', 'cured', 'none']) {
    const changed = patchPokemonPokerus(shiny, status), decoded = decodePokemon(changed);
    assert.equal(decoded.pokerus.status, status);
    assert.deepEqual({...decoded, pokerus: after.pokerus}, after);
    const plain = logical(changed), expected = logical(shiny); plain[3][26] = expected[3][26]; assert.deepEqual(plain, expected);
    assert.deepEqual(changed.slice(136), shiny.slice(136)); assert.deepEqual(changed.slice(0,6), shiny.slice(0,6));
    assert.deepEqual(patchPokemonPokerus(changed, status), changed);
    assert.deepEqual(patchPokemonPokerus(changed, 'none'), shiny);
  }
  assert.deepEqual(record, original);
});
test('native shininess threshold is XOR <8, override independent of trainer ID and PID', () => {
  for (const xor of [0,1,7,8,15,16,65535]) for (const override of [false,true]) {
    const record = fixture(31, {xor, override}); const decoded = decodePokemon(record);
    assert.equal(decoded.naturalShiny, xor < 8); assert.equal(decoded.shiny, xor < 8 || override);
    if (xor < 8) { assert.throws(() => patchPokemonShiny(record, false), /naturally shiny/); assert.deepEqual(patchPokemonShiny(record, true), record); }
    else assert.equal(decodePokemon(patchPokemonShiny(record, false)).shiny, false);
  }
});
test('all disease bytes decode native active/cured tests; state no-ops preserve unusual existing values', () => {
  for (let raw = 0; raw <= 255; raw++) {
    const record = fixture(raw % 32, {pokerus: raw}), decoded = decodePokemon(record);
    const status = (raw & 15) ? 'infected' : (raw >>> 4) ? 'cured' : 'none';
    assert.deepEqual(decoded.pokerus, {raw, strain: raw >>> 4, days: raw & 15, status});
    assert.deepEqual(patchPokemonPokerus(record, status), record);
    const cured = decodePokemon(patchPokemonPokerus(record, 'cured')).pokerus;
    assert.equal(cured.raw, (raw >>> 4 || 1) << 4);
    assert.equal(decodePokemon(patchPokemonPokerus(record, 'none')).pokerus.raw, 0);
    if (status !== 'infected') assert.equal(decodePokemon(patchPokemonPokerus(record, 'infected')).pokerus.raw, ((raw >>> 4 || 1) << 4) | 1);
  }
});
test('trait edits compose with moves and reject invalid requests without mutation', () => {
  const record = fixture(4), original = record.slice();
  for (const value of [null, undefined, 0, 1, 'true', {}, []]) assert.throws(() => patchPokemonShiny(record, value));
  for (const value of [null, undefined, 0, 'active', {}, []]) assert.throws(() => patchPokemonPokerus(record, value));
  const moved = patchPokemonMoves(record, Array.from({length:4}, () => ({id:0,pp:0,ppUps:0})));
  const a = patchPokemonPokerus(patchPokemonShiny(moved, true), 'infected');
  const b = patchPokemonMoves(patchPokemonShiny(patchPokemonPokerus(record, 'infected'), true), decodePokemon(moved).moves);
  assert.deepEqual(a,b); assert.deepEqual(record,original);
  const corrupt = record.slice(); corrupt[8] ^= 1; assert.throws(() => patchPokemonShiny(corrupt,true), /checksum/);
  assert.throws(() => patchPokemonPokerus(corrupt,'infected'), /checksum/);
});
test('traits support nonzero byte offsets and independent buffers', () => {
  const original = fixture(2); const holder = new Uint8Array(250); holder.set(original,7);
  const slice = holder.subarray(7,243), before = holder.slice();
  assert.equal(decodePokemon(patchPokemonShiny(slice,true)).shiny,true);
  assert.equal(decodePokemon(patchPokemonPokerus(Buffer.from(original),'cured')).pokerus.status,'cured');
  assert.deepEqual(holder,before);
});

test('nature editing preserves the shiny bit and trait edits compose with stat changes', () => {
 const record=fixture(7), personal={baseStats:[50,60,70,80,90,100],growthRate:0};
 const traits=r=>patchPokemonPokerus(patchPokemonShiny(r,true),'infected');
 const stats=r=>patchPokemonStats(r,{nature:3},personal);
 assert.deepEqual(stats(traits(record)),traits(stats(record)));
 const decoded=decodePokemon(stats(traits(record)));
 assert.equal(decoded.shiny,true);assert.equal(decoded.nature,3);assert.equal(decoded.pokerus.status,'infected');
});
