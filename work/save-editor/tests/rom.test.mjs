import test from 'node:test';
import assert from 'node:assert/strict';
import { readNdsFile, readNarcMembers, loadOriginData } from '../dist/core/rom.js';

function narc() {
  const b = new Uint8Array(64); const v = new DataView(b.buffer);
  const text = (o,s) => b.set(new TextEncoder().encode(s),o);
  text(0,'NARC'); v.setUint16(4,0xfffe,true);v.setUint16(6,0x100,true);
  v.setUint32(8,b.length,true);v.setUint16(12,16,true);v.setUint16(14,2,true);
  text(16,'BTAF');v.setUint32(20,28,true);v.setUint16(24,2,true);
  v.setUint32(28,0,true);v.setUint32(32,4,true);v.setUint32(36,4,true);v.setUint32(40,12,true);
  text(44,'GMIF');v.setUint32(48,20,true);b.set([1,2,3,4,5,6,7,8,9,10,11,12],52);
  return b;
}
function rom() {
  const b = new Uint8Array(512); const v = new DataView(b.buffer);
  v.setUint32(0x40,128,true);v.setUint32(0x44,26,true);v.setUint32(0x48,160,true);v.setUint32(0x4c,8,true);
  v.setUint32(128,16,true);v.setUint16(134,2,true);
  v.setUint32(136,21,true);v.setUint16(142,0xf000,true);
  b.set([0x81,97,1,0xf0,0,3,102,111,111,0],144);
  v.setUint32(160,256,true);v.setUint32(164,260,true);b.set([3,1,4,1],256);
  return b;
}
test('NDS resolves nested directory and exact file bytes',()=>assert.deepEqual([...readNdsFile(rom(),'a/foo')],[3,1,4,1]));
test('NDS rejects missing paths, invalid directory ids and bad allocations',()=>{
  assert.throws(()=>readNdsFile(rom(),'a/bar'),/not found/);
  const bad=rom();bad[146]=5;assert.throws(()=>readNdsFile(bad,'a/foo'),/directory/);
  const reversed=rom();new DataView(reversed.buffer).setUint32(164,255,true);assert.throws(()=>readNdsFile(reversed,'a/foo'),/invalid/);
  const outside=rom();new DataView(outside.buffer).setUint32(164,513,true);assert.throws(()=>readNdsFile(outside,'a/foo'),/invalid/);
});
test('NDS honors byte array view offsets',()=>{
 const buffer=new Uint8Array(600);buffer.set(rom(),31);assert.equal(readNdsFile(buffer.subarray(31,543),'a/foo')[0],3);
});
test('NARC returns ordered member data',()=>assert.deepEqual(readNarcMembers(narc()).map(b=>[...b]),[[1,2,3,4],[5,6,7,8,9,10,11,12]]));
test('NARC rejects malformed sizes, overlapping members and missing data',()=>{
 const short=narc().subarray(0,60);assert.throws(()=>readNarcMembers(short));
 const zero=narc();new DataView(zero.buffer).setUint32(20,0,true);assert.throws(()=>readNarcMembers(zero),/size/);
 const overlap=narc();new DataView(overlap.buffer).setUint32(36,3,true);assert.throws(()=>readNarcMembers(overlap),/Overlapping/);
 const huge=narc();new DataView(huge.buffer).setUint32(40,999,true);assert.throws(()=>readNarcMembers(huge),/invalid/);
 const missing=narc();missing[44]=88;assert.throws(()=>readNarcMembers(missing),/Incomplete/);
});
test('loadOriginData rejects non-ROM and unsupported synthetic input',async()=>{
 await assert.rejects(loadOriginData(new Uint8Array(12)));
 await assert.rejects(loadOriginData(rom()));
});
