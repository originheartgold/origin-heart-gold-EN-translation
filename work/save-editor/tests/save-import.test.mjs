import test from 'node:test';
import assert from 'node:assert/strict';
import { syntheticSave } from './fixture.mjs';
import { importSave, SaveImportRequest } from '../dist/core/save-import.js';
import { unwrapSave, wrapSave, RAW_SAVE_SIZE, DESMUME_FOOTER_SIZE } from '../dist/core/save-container.js';

const raw = syntheticSave();
function file(name, arrayBuffer = async () => raw.slice().buffer, size = raw.length) { return {name, size, arrayBuffer}; }
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}
function dsv() {
  const bytes = new Uint8Array(RAW_SAVE_SIZE + DESMUME_FOOTER_SIZE);
  bytes.set(raw);
  const notice = '|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:';
  bytes.set(new TextEncoder().encode(notice), RAW_SAVE_SIZE);
  bytes.set(new TextEncoder().encode('|-DESMUME SAVE-|'), bytes.length - 16);
  new DataView(bytes.buffer).setUint32(RAW_SAVE_SIZE + notice.length + 4, RAW_SAVE_SIZE, true);
  return bytes;
}
for (const container of ['raw', 'desmume']) test(`${container}: offset views and Node buffers round-trip without aliasing input`, () => {
  const source = container === 'raw' ? raw : dsv();
  for (const make of [n => new Uint8Array(n), n => Buffer.alloc(n)]) {
    const backing = make(source.length + 16); backing.set(source, 7);
    const input = backing.subarray(7, 7 + source.length);
    const unpacked = unwrapSave(input);
    assert.equal(unpacked.container.kind, container);
    const result = wrapSave(unpacked.bytes, unpacked.container);
    assert.deepEqual(result, source);
    unpacked.bytes[0] ^= 1;
    if (unpacked.container.kind === 'desmume') unpacked.container.footer[0] ^= 1;
    assert.deepEqual(new Uint8Array(input), source);
    assert.deepEqual(result, source);
  }
});
test('import rejects wrong sizes, unreadable files, malformed footer and corrupt party records', async () => {
  await assert.rejects(importSave(file('state', () => assert.fail('must not read'), 123)), /512 KiB/);
  await assert.rejects(importSave(file('save', async () => { throw new Error('disk'); })), /Could not read/);
  const badFooter = dsv(); badFooter[badFooter.length - 1] ^= 1;
  assert.throws(() => unwrapSave(badFooter), /footer/);
  const damaged = raw.slice(); damaged[0x98 + 10] ^= 1; damaged[0x40000 + 0x98 + 10] ^= 1;
  await assert.rejects(importSave(file('bad.sav', async () => damaged.buffer)));
  assert.equal((await importSave(file('valid.sav'))).filename, 'valid.sav');
});
test('latest selection wins even when old reads or errors arrive later', async () => {
  for (const failed of [false, true]) {
    const requests = new SaveImportRequest(), old = deferred();
    const pending = requests.load(file('old.sav', () => old.promise));
    assert.equal((await requests.load(file('new.sav'))).filename, 'new.sav');
    if (failed) old.reject(new Error('stale read error')); else old.resolve(raw.slice().buffer);
    assert.equal(await pending, undefined);
  }
});
test('editing or undo invalidates a pending import; current errors remain visible', async () => {
  const requests = new SaveImportRequest(), old = deferred();
  const pending = requests.load(file('old.sav', () => old.promise));
  requests.invalidate(); old.resolve(raw.slice().buffer);
  assert.equal(await pending, undefined);
  await assert.rejects(requests.load(file('bad.sav', async () => { throw new Error('disk'); })), /Could not read/);
  assert.equal((await requests.load(file('good.sav'))).filename, 'good.sav');
});
