import test from 'node:test';
import assert from 'node:assert/strict';
import { readItemNames } from '../dist/core/item-names.js';

// Synthetic strings only: exercise the Nintendo DS name-bank framing and cipher.
function bank(records, seed = 0x1234) {
  const bytes = new Uint8Array(4 + records.length * 8 + records.reduce((sum, codes) => sum + codes.length * 2, 0));
  const view = new DataView(bytes.buffer);
  view.setUint16(0, records.length, true); view.setUint16(2, seed, true);
  let offset = 4 + records.length * 8;
  records.forEach((codes, i) => {
    const half = (seed * 0x2fd * (i + 1)) & 0xffff;
    const key = (half | half << 16) >>> 0;
    view.setUint32(4 + i * 8, (offset ^ key) >>> 0, true);
    view.setUint32(8 + i * 8, (codes.length ^ key) >>> 0, true);
    let cipher = (0x91bd3 * (i + 1)) & 0xffff;
    codes.forEach(code => { view.setUint16(offset, code ^ cipher, true); offset += 2; cipher = (cipher + 0x493d) & 0xffff; });
  });
  return bytes;
}
function tableValue(bytes, entry, field, value) {
  const view = new DataView(bytes.buffer);
  const half = (view.getUint16(2, true) * 0x2fd * (entry + 1)) & 0xffff;
  const key = (half | half << 16) >>> 0;
  view.setUint32(4 + entry * 8 + field * 4, (value ^ key) >>> 0, true);
}
test('item names decrypt independent records, Latin glyphs, digits and punctuation', () => {
  const bytes = bank([
    [0x12b, 0x144, 0x145, 0x15e, 0x121, 0x12a, 0xffff],
    [0x15f, 0x188, 0x19e, 0x1de, 0x1ac, 0x1ae, 0x1be, 0x1b3, 0x1b1, 0x1bd, 0x1c2, 0x1b9, 0x1ba, 0xffff],
  ]);
  assert.deepEqual(readItemNames(bytes), ['AZaz09', 'Àéÿ ?.-’/+&()']);
});
test('unsupported glyph or control rejects the whole display name, never a partial label', () => {
  assert.deepEqual(readItemNames(bank([[0x12b, 0x8001, 0x145, 0xffff], [0xf100, 0xffff], [0x12c, 0xffff]])), [undefined, undefined, 'B']);
});
test('blank names remain undefined and zero-record banks are valid', () => {
  assert.deepEqual(readItemNames(bank([[0xffff], [0x1de, 0x1de, 0xffff]])), [undefined, undefined]);
  assert.deepEqual(readItemNames(bank([])), []);
});
test('item-name decoder honors nonzero byte offsets and leaves input unchanged', () => {
  const bytes = bank([[0x12b, 0xffff]]); const snapshot = bytes.slice();
  const padded = new Uint8Array(bytes.length + 21); padded.set(bytes, 11);
  assert.deepEqual(readItemNames(padded.subarray(11, 11 + bytes.length)), ['A']);
  assert.deepEqual(bytes, snapshot);
});
test('item-name decoder rejects truncated headers and table counts', () => {
  for (let length = 0; length < 4; length++) assert.throws(() => readItemNames(new Uint8Array(length)), /Truncated/);
  const huge = bank([]); new DataView(huge.buffer).setUint16(0, 4097, true);
  assert.throws(() => readItemNames(huge), /table/);
  const short = bank([[0xffff]]).subarray(0, 11); assert.throws(() => readItemNames(short), /table/);
});
test('item-name decoder rejects overlaps, gaps, empty/oversized records and out-of-bounds lengths', () => {
  for (const [field, value] of [[0, 0], [0, 13], [0, 0xffffffff], [1, 0], [1, 257], [1, 0xffffffff]]) {
    const bytes = bank([[0x12b, 0xffff]]); tableValue(bytes, 0, field, value);
    assert.throws(() => readItemNames(bytes), /record/);
  }
  assert.throws(() => readItemNames(bank([[0x12b, 0xffff]]).subarray(0, 15)), /record/);
  const overlap = bank([[0xffff], [0xffff]]); tableValue(overlap, 1, 0, 20);
  assert.throws(() => readItemNames(overlap), /record/);
});
test('item-name decoder requires an explicit terminator', () => {
  assert.throws(() => readItemNames(bank([[0x12b]])), /Unterminated/);
});

test('species gender symbols and colon decode without collapsing distinct names', () => {
  assert.deepEqual(readItemNames(bank([[0x12b,0x1bb,0xffff],[0x12b,0x1bc,0xffff],[0x12b,0x1c4,0x12c,0xffff]])), ['A♂','A♀','A:B']);
});
