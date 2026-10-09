import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { deflateRawSync } from 'node:zlib';
import { Crc32, Sha1 } from '../public/patch-tool/hash.js';
import { isZip, listZip, ndsEntries, readEntry } from '../public/patch-tool/zip.js';

for (const length of [0, 1, 55, 56, 63, 64, 65, 127, 128, 4097]) {
  test(`streaming SHA-1 matches Node across padding/chunk boundaries (${length} bytes)`, () => {
    const data = Uint8Array.from({length}, (_, i) => i * 37 & 255);
    for (const chunk of [1, 7, 64, 129]) {
      const hash = new Sha1();
      for (let offset = 0; offset < length; offset += chunk) hash.update(data.subarray(offset, offset + chunk));
      assert.equal(hash.hex(), createHash('sha1').update(data).digest('hex'));
    }
  });
}
test('CRC32 known vector and incremental updates', () => {
  const bytes = new TextEncoder().encode('123456789');
  assert.equal(new Crc32().hex(), '00000000');
  assert.equal(new Crc32().update(bytes).hex(), 'CBF43926');
  assert.equal(new Crc32().update(bytes.subarray(0, 4)).update(bytes.subarray(4)).hex(), 'CBF43926');
});
function archive({method = 0, zip64 = false, comment = ''} = {}) {
  const name = new TextEncoder().encode('game.nds');
  const data = new TextEncoder().encode('synthetic content, not a ROM'.repeat(100));
  const packed = method === 8 ? deflateRawSync(data) : data;
  const local = new Uint8Array(30 + name.length + packed.length), lv = new DataView(local.buffer);
  lv.setUint32(0, 0x04034b50, true); lv.setUint16(8, method, true); lv.setUint16(26, name.length, true);
  local.set(name, 30); local.set(packed, 30 + name.length);
  const central = new Uint8Array(46 + name.length + (zip64 ? 28 : 0)), cv = new DataView(central.buffer);
  cv.setUint32(0, 0x02014b50, true); cv.setUint16(10, method, true);
  cv.setUint32(16, parseInt(new Crc32().update(data).hex(), 16), true);
  cv.setUint32(20, zip64 ? 0xffffffff : packed.length, true); cv.setUint32(24, zip64 ? 0xffffffff : data.length, true);
  cv.setUint16(28, name.length, true); cv.setUint16(30, zip64 ? 28 : 0, true);
  cv.setUint32(42, zip64 ? 0xffffffff : 0, true); central.set(name, 46);
  if (zip64) {
    const e = 46 + name.length;
    cv.setUint16(e, 1, true); cv.setUint16(e + 2, 24, true);
    cv.setBigUint64(e + 4, BigInt(data.length), true); cv.setBigUint64(e + 12, BigInt(packed.length), true);
    cv.setBigUint64(e + 20, 0n, true);
  }
  const trailer = new Uint8Array(zip64 ? 76 : 0);
  if (zip64) {
    const zv = new DataView(trailer.buffer);
    zv.setUint32(0, 0x06064b50, true); zv.setBigUint64(4, 44n, true);
    zv.setBigUint64(24, 1n, true); zv.setBigUint64(32, 1n, true);
    zv.setBigUint64(40, BigInt(central.length), true); zv.setBigUint64(48, BigInt(local.length), true);
    zv.setUint32(56, 0x07064b50, true); zv.setBigUint64(64, BigInt(local.length + central.length), true); zv.setUint32(72, 1, true);
  }
  const text = new TextEncoder().encode(comment);
  const end = new Uint8Array(22 + text.length), ev = new DataView(end.buffer);
  ev.setUint32(0, 0x06054b50, true); ev.setUint16(8, zip64 ? 65535 : 1, true); ev.setUint16(10, zip64 ? 65535 : 1, true);
  ev.setUint32(12, zip64 ? 0xffffffff : central.length, true); ev.setUint32(16, zip64 ? 0xffffffff : local.length, true);
  ev.setUint16(20, text.length, true); end.set(text, 22);
  return {blob: new Blob([local, central, trailer, end]), data, central: local.length, end: local.length + central.length + trailer.length};
}
for (const method of [0, 8]) for (const zip64 of [false, true]) test(`ZIP round-trip: method ${method}, Zip64 ${zip64}`, async () => {
  const {blob, data} = archive({method, zip64});
  assert.equal(await isZip(blob), true);
  const entries = await listZip(blob); assert.equal(entries.length, 1);
  assert.equal(entries[0].name, 'game.nds');
  const chunks = []; await readEntry(blob, entries[0], chunk => chunks.push(chunk));
  assert.deepEqual(new Uint8Array(await new Blob(chunks).arrayBuffer()), data);
});
test('ZIP comments may contain a false end-of-directory signature', async () => {
  const {blob} = archive({comment: 'PK\x05\x06' + 'x'.repeat(24)});
  assert.equal((await listZip(blob)).length, 1);
});
test('ZIP rejects truncated directories, invalid bounds and incomplete Zip64 fields', async () => {
  for (const mutate of [
    (v, a) => v.setUint32(a.end + 12, 10, true),
    (v, a) => v.setUint32(a.end + 16, 0xfffffff0, true),
    (v, a) => v.setUint16(a.central + 28, 65535, true),
    (v, a) => v.setUint16(a.end + 4, 1, true),
  ]) {
    const a = archive({zip64: false}), bytes = new Uint8Array(await a.blob.arrayBuffer());
    mutate(new DataView(bytes.buffer), a);
    await assert.rejects(listZip(new Blob([bytes])), {kind: 'zip'});
  }
});
test('truncated Zip64 extra fields are rejected', async () => {
  const a = archive({zip64: true}), bytes = new Uint8Array(await a.blob.arrayBuffer());
  new DataView(bytes.buffer).setUint16(a.central + 46 + 8 + 2, 1, true);
  await assert.rejects(listZip(new Blob([bytes])), {kind: 'zip'});
});
test('ZIP extraction rejects oversized output before delivering it and reports damaged headers', async () => {
  const {blob} = archive({method: 8}); const [entry] = await listZip(blob);
  await assert.rejects(readEntry(blob, {...entry, size: 1}, () => assert.fail('oversized chunk delivered')), {kind: 'zip'});
  await assert.rejects(readEntry(blob, {...entry, localOffset: blob.size - 2}, () => {}), {kind: 'zip'});
  await assert.rejects(readEntry(blob, {...entry, csize: blob.size}, () => {}), {kind: 'zip'});
  await assert.rejects(readEntry(blob, {...entry, encrypted: true}, () => {}), /password/);
  await assert.rejects(readEntry(blob, {...entry, method: 99}, () => {}), /compression/);
  assert.equal(await isZip(new Blob([new Uint8Array(2)])), false);
  assert.equal(await isZip(new Blob([Uint8Array.of(0x50, 0x4b, 3, 6)])), false);
  assert.deepEqual(ndsEntries([{name: '__MACOSX/game.nds'}, {name: '._game.nds'}, {name: 'folder/game.NDS'}]), [{name: 'folder/game.NDS'}]);
});
