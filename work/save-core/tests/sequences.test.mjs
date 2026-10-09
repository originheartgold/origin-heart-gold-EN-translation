import test from 'node:test';
import assert from 'node:assert/strict';
import {applySaveTransaction} from '../dist/fixture.js';
import {saveFixture, rng, view, decodeOracle, encodeOracle, crcOracle} from './fixtures.mjs';

// Deliberately literal format constants: this model must not share the writer's
// offsets, pocket metadata, encryption, checksum, or transaction implementation.
const pockets = [
  ['items', 0x644, 165], ['key', 0x8d8, 50], ['tm', 0x9a0, 151],
  ['mail', 0xbfc, 12], ['medicine', 0xc2c, 40], ['berries', 0xccc, 64],
  ['balls', 0xdcc, 24], ['battle', 0xe2c, 30],
];
function model(source, base, operations) {
  const bytes = Uint8Array.from(source), data = view(bytes);
  for (const op of operations) {
    if (op.type === 'setFlag') {
      const at = base + 0x118c + Math.floor(op.flag / 8), mask = 2 ** (op.flag % 8);
      bytes[at] = op.value ? bytes[at] | mask : bytes[at] & ~mask;
    } else if (op.type === 'setVar') {
      data.setUint16(base + 0xeac + (op.var - 0x4000) * 2, op.value, true);
    } else if (op.type === 'setPartyCount') {
      data.setUint32(base + 0x94, op.count, true);
    } else if (op.type === 'setPocket') {
      const [, offset, capacity] = pockets.find(([name]) => name === op.name);
      bytes.fill(0, base + offset, base + offset + capacity * 4);
      op.items.forEach(([id, quantity], i) => {
        data.setUint16(base + offset + i * 4, id, true);
        data.setUint16(base + offset + i * 4 + 2, quantity, true);
      });
    } else if (op.type === 'editPartyMon') {
      const at = base + 0x98 + op.slot * 236;
      const {pid, logical, tail} = decodeOracle(bytes.subarray(at, at + 236));
      const logicalView = view(logical), changes = op.changes;
      if (changes.item !== undefined) logicalView.setUint16(2, changes.item, true);
      if (changes.exp !== undefined) logicalView.setUint32(8, changes.exp, true);
      if (changes.currentHp !== undefined) view(tail).setUint16(6, changes.currentHp, true);
      changes.moves?.forEach((id, i) => {
        logicalView.setUint16(32 + i * 2, id, true);
        logical[40 + i] = changes.pp?.[i] ?? 10;
      });
      bytes.set(encodeOracle(logical, pid, tail), at);
    } else assert.fail(`Oracle missing operation ${op.type}`);
  }
  data.setUint16(base + 0xf7ca, crcOracle(bytes.subarray(base, base + 0xf7bc)), true);
  return bytes;
}
function changedRanges(before, after) {
  const ranges = [];
  for (let i = 0; i < before.length; i++) if (before[i] !== after[i]) {
    const previous = ranges.at(-1);
    if (previous?.end === i) previous.end++;
    else ranges.push({start: i, end: i + 1});
  }
  return ranges;
}

for (const seed of [1, 0x1eafcafe, 0xffffffff, 0x80000000, 29, 0x61b6, 0xc001d00d, 12345]) {
  test(`mixed transaction state machine, independent full-byte oracle; seed=0x${seed.toString(16)}`, () => {
    const next = rng(seed), base = seed & 1 ? 0x40000 : 0;
    let source = saveFixture({count: 6, counters: base ? [11, 12] : [12, 11]}), count = 6;
    for (let step = 0; step < 12; step++) {
      const label = `seed=0x${seed.toString(16)} step=${step} mirror=0x${base.toString(16)}`;
      const before = source.slice(), operations = [];
      const [name] = pockets[(step + seed) % pockets.length];
      operations.push({type: 'setFlag', flag: 1 + next() % 3231, value: Boolean(next() & 1)});
      operations.push({type: 'setVar', var: 0x4000 + next() % 368, value: next() % 65536});
      operations.push({type: 'setPocket', name, items: Array.from({length: step % 4}, () => [1 + next() % 65535, 1 + next() % 65535])});
      const moves = Array.from({length: step % 5}, () => next() % 65536);
      operations.push({type: 'editPartyMon', slot: next() % count, tailPolicy: 'preserve', changes: {
        item: next() % 65536, exp: next(), currentHp: next() % 65536,
        moves, ...(step % 2 ? {pp: moves.map(() => next() % 256)} : {}),
      }});
      if (step === 3 || step === 7) operations.push({type: 'setPartyCount', count: --count});
      const originalOperations = structuredClone(operations);

      // Failure after valid mutations (and sometimes a shrink) must leave the
      // caller's bytes untouched, then permit the exact same successful retry.
      const invalid = step % 2
        ? {type: 'editPartyMon', slot: count, changes: {item: 7}, tailPolicy: 'preserve'}
        : {type: 'setPocket', name, items: [[7, 1], [8, 65536]]};
      assert.throws(() => applySaveTransaction(source, [...operations, invalid]), error => error.operationIndex === operations.length, label);
      assert.deepEqual(source, before, `${label}: failed transaction mutated input`);
      const expected = model(source, base, operations), result = applySaveTransaction(source, operations);
      assert.deepEqual(result.bytes, expected, `${label}: complete binary oracle, including unrelated bytes`);
      assert.deepEqual(source, before, `${label}: successful transaction mutated input`);
      assert.deepEqual(operations, originalOperations, `${label}: caller operations changed`);
      assert.deepEqual(result.report.changedRanges, changedRanges(before, expected), `${label}: audit ranges`);
      assert.equal(result.report.generalOffset, base, label);
      assert.equal(result.report.counter, 12, label);
      // A separate no-op transaction and output alias cannot change committed state.
      const noOp = applySaveTransaction(result.bytes, []);
      assert.deepEqual(noOp.bytes, result.bytes, label);
      noOp.bytes[base + 0x94] ^= 1;
      assert.deepEqual(result.bytes, expected, `${label}: outputs alias`);
      source = result.bytes;
    }
  });
}

test('offset Buffer transaction isolates surrounding allocation, rollback, and retained inactive records', () => {
  const fixture = saveFixture({count: 6}), allocation = Buffer.alloc(fixture.length + 79, 0xa7);
  const input = allocation.subarray(31, 31 + fixture.length); input.set(fixture);
  const before = Buffer.from(allocation);
  const operations = [{type: 'setPartyCount', count: 1}, {type: 'editPartyMon', slot: 0, changes: {item: 42}, tailPolicy: 'preserve'}];
  assert.throws(() => applySaveTransaction(input, [...operations, {type: 'editPartyMon', slot: 1, changes: {item: 9}, tailPolicy: 'preserve'}]));
  const result = applySaveTransaction(input, operations);
  assert.deepEqual(result.bytes, model(fixture, 0, operations));
  assert.deepEqual(allocation, before);
  assert.deepEqual(result.bytes.subarray(0x98 + 236, 0x98 + 6 * 236), fixture.subarray(0x98 + 236, 0x98 + 6 * 236));
  result.bytes[0] ^= 1;
  assert.deepEqual(allocation, before);
});
