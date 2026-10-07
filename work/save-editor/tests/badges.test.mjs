import test from 'node:test';
import assert from 'node:assert/strict';
import {crc16, readSave} from '../dist/core/save.js';
import {patchBadge, readTrainer} from '../dist/core/trainer.js';
function fixture(base = 0) {
  const bytes = new Uint8Array(0x80000), dv = new DataView(bytes.buffer);
  for (const offset of [0, 0x40000]) {
    dv.setUint32(offset + 0x90, 6, true);
    bytes[offset + 0x7e] = 0xff; bytes[offset + 0x7f] = 0xff;
    bytes[offset + 0x80] = 0x55; bytes[offset + 0x83] = 0xaa;
    dv.setUint16(offset + 0x8c,crc16(bytes.subarray(offset+0x60,offset+0x8c)),true);
    const footer = offset + 0xf7cc - 16;
    dv.setUint32(footer, offset === base ? 2 : 1, true);
    dv.setUint32(footer + 4, 0xf7cc, true);
    dv.setUint32(footer + 8, 0x20060623, true);
    dv.setUint16(footer + 14, crc16(bytes.subarray(offset, footer)), true);
  }
  return bytes;
}
for (const base of [0, 0x40000]) test(`all badge bits preserve unrelated data, active mirror ${base}`, () => {
  const input = fixture(base);
  for (let bank = 0; bank < 2; bank++) for (let bit = 0; bit < 8; bit++) {
    const before = readTrainer(input), earned = !(before.badges[bank] & (1 << bit));
    const output = patchBadge(input, bank, bit, earned);
    assert.equal(readSave(output).generalOffset, base);
    const expected = [...before.badges]; expected[bank] ^= 1 << bit;
    assert.deepEqual(readTrainer(output).badges, expected);
    assert.equal(readTrainer(output).badgeCount, before.badgeCount + (earned ? 1 : -1));
    assert.deepEqual(patchBadge(output, bank, bit, !earned), input);
    assert.deepEqual(patchBadge(output, bank, bit, earned), output);
    const allowed = new Set([base + (bank === 0 ? 0x80 : 0x83), base + 0x8c, base + 0x8d, base + 0xf7cc - 2, base + 0xf7cc - 1]);
    for (let i = 0; i < input.length; i++) if (output[i] !== input[i]) assert.ok(allowed.has(i), `unexpected change at ${i}`);
  }
  assert.deepEqual(input, fixture(base));
});
test('invalid badge arguments rejected', () => {
  for (const args of [[-1, 0, true], [2, 0, true], [0.5, 0, true], [0, -1, true], [0, 8, true], [0, NaN, true], [0, 0, 1]]) assert.throws(() => patchBadge(fixture(), ...args));
});
test('equal-counter mirrors allow no-op and reject edits', () => {
  const bytes = fixture(); bytes.set(bytes.subarray(0, 0xf7cc), 0x40000);
  assert.equal(readSave(bytes).tied, true);
  assert.deepEqual(patchBadge(bytes, 0, 0, true), bytes);
  assert.throws(() => patchBadge(bytes, 0, 0, false));
});

function repairGeneral(bytes, base) {
  const footer = base + 0xf7cc - 16;
  new DataView(bytes.buffer).setUint16(footer + 14, crc16(bytes.subarray(base, footer)), true);
}
for (const base of [0, 0x40000]) {
  test(`unrelated profile bytes and older mirror never light badges, active mirror ${base}`, () => {
    const bytes = fixture(base);
    bytes[base + 0x80] = 0;
    bytes[base + 0x83] = 0;
    // Neighboring fields can contain any value, including all bits set.
    for (const offset of [0x7e, 0x7f, 0x81, 0x82]) bytes[base + offset] = 0xff;
    repairGeneral(bytes, base);
    const older = base === 0 ? 0x40000 : 0;
    bytes[older + 0x80] = 0xff;
    bytes[older + 0x83] = 0xff;
    repairGeneral(bytes, older);
    const before = bytes.slice();
    assert.deepEqual(readTrainer(bytes).badges, [0, 0]);
    assert.equal(readTrainer(bytes).badgeCount, 0);
    assert.deepEqual(bytes, before, 'reading the trainer must not mutate the save');
    const result = patchBadge(bytes, 0, 1, true);
    assert.equal(result[base + 0x80], 2);
    assert.deepEqual(readTrainer(result).badges, [2, 0]);
    for (const offset of [0x7e, 0x7f, 0x81, 0x82]) assert.equal(result[base + offset], 0xff);
    assert.deepEqual(result.subarray(older, older + 0xf7cc), bytes.subarray(older, older + 0xf7cc));
  });
  test(`each native badge bit maps independently, active mirror ${base}`, () => {
    for (const offset of [0x80, 0x83]) for (let bit = 0; bit < 8; bit++) {
      const bytes = fixture(base);
      bytes[base + 0x80] = 0;
      bytes[base + 0x83] = 0;
      bytes[base + offset] = 1 << bit;
      repairGeneral(bytes, base);
      assert.deepEqual(readTrainer(bytes).badges, offset === 0x80 ? [1 << bit, 0] : [0, 1 << bit]);
      assert.equal(readTrainer(bytes).badgeCount, 1);
    }
  });
}
