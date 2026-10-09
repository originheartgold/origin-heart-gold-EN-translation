import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorError} from '../dist/core/errors.js';
import {importSave} from '../dist/core/save-import.js';
import {crc16} from '../dist/core/save.js';
import {DESMUME_FOOTER_SIZE, RAW_SAVE_SIZE, containerLabel, saveExtension, unwrapSave, wrapSave} from '../dist/core/save-container.js';

function fixture() {
  // Invented empty-party data, not a playable game save.
  const bytes=new Uint8Array(RAW_SAVE_SIZE), view=new DataView(bytes.buffer);
  for(const [index,base] of [0,0x40000].entries()) {
    view.setUint32(base+0x90,6,true);
    for(const [offset,size,id] of [[0,0xf7cc,0],[0xf800,0x18408,1]]) {
      const footer=base+offset+size-16;
      view.setUint32(footer,10-index,true);view.setUint32(footer+4,size,true);
      view.setUint32(footer+8,0x20060623,true);view.setUint16(footer+12,id,true);
      view.setUint16(footer+14,crc16(bytes.subarray(base+offset,footer)),true);
    }
  }
  return bytes;
}
// DeSmuME 0.9.x footer layout: notice, six u32 (written size, pad size, type, address bytes, memory size, version), cookie.
function desmumeFooter({padSize=RAW_SAVE_SIZE,cookie='|-DESMUME SAVE-|'}={}) {
  const notice='|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:';
  const footer=new Uint8Array(notice.length+24+cookie.length), view=new DataView(footer.buffer);
  footer.set([...notice].map(c=>c.charCodeAt(0)));
  [0x40001,padSize,6,3,RAW_SAVE_SIZE,0].forEach((value,i)=>view.setUint32(notice.length+i*4,value,true));
  footer.set([...cookie].map(c=>c.charCodeAt(0)),notice.length+24);
  return footer;
}
const join=(a,b)=>{const out=new Uint8Array(a.length+b.length);out.set(a);out.set(b,a.length);return out;};
const file=(name,bytes)=>({name,size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});

test('DeSmuME footer is the documented 122 bytes',()=>{
  assert.equal(DESMUME_FOOTER_SIZE,122);assert.equal(desmumeFooter().length,122);
});
test('raw saves pass through unchanged and export as .sav',()=>{
  const raw=fixture(),{bytes,container}=unwrapSave(raw);
  assert.deepEqual(container,{kind:'raw'});assert.deepEqual(bytes,raw);assert.notEqual(bytes.buffer,raw.buffer);
  assert.deepEqual(wrapSave(bytes,container),raw);assert.equal(saveExtension(container),'.sav');assert.equal(containerLabel(container),'raw .sav');
});
test('DeSmuME .dsv splits into raw data and footer and round-trips byte for byte',()=>{
  const raw=fixture(),footer=desmumeFooter(),dsv=join(raw,footer),{bytes,container}=unwrapSave(dsv);
  assert.equal(container.kind,'desmume');assert.deepEqual(bytes,raw);assert.deepEqual(container.footer,footer);
  assert.deepEqual(wrapSave(bytes,container),dsv);assert.equal(saveExtension(container),'.dsv');
});
test('edits keep the original DeSmuME footer',()=>{
  const footer=desmumeFooter(),{bytes,container}=unwrapSave(join(fixture(),footer));
  bytes[0x78]=42;const out=wrapSave(bytes,container);
  assert.equal(out.length,RAW_SAVE_SIZE+122);assert.equal(out[0x78],42);assert.deepEqual(out.subarray(RAW_SAVE_SIZE),footer);
});
test('detection uses content: a raw save named .dsv stays raw',async()=>{
  const imported=await importSave(file('drastic.dsv',fixture()));
  assert.deepEqual(imported.container,{kind:'raw'});
});
test('.dsv-sized files without a valid DeSmuME footer are rejected',()=>{
  for(const footer of [desmumeFooter({cookie:'|-NOT DESMUME!!-|'}),desmumeFooter({padSize:0x40000}),new Uint8Array(122)]) {
    assert.throws(()=>unwrapSave(join(fixture(),footer)),error=>error instanceof EditorError&&error.code==='invalid-save');
  }
});
test('other sizes are rejected, and wrapping requires 512 KiB of data',()=>{
  for(const size of [0,RAW_SAVE_SIZE-1,RAW_SAVE_SIZE+1,RAW_SAVE_SIZE+121,RAW_SAVE_SIZE+123,RAW_SAVE_SIZE*2]) {
    assert.throws(()=>unwrapSave(new Uint8Array(size)),error=>error.code==='invalid-save');
  }
  assert.throws(()=>wrapSave(new Uint8Array(10),{kind:'raw'}),error=>error.code==='invalid-save');
});
test('importSave accepts a .dsv and validates the inner save',async()=>{
  const raw=fixture(),dsv=join(raw,desmumeFooter()),imported=await importSave(file('origin.dsv',dsv));
  assert.equal(imported.filename,'origin.dsv');assert.equal(imported.container.kind,'desmume');assert.deepEqual(imported.bytes,raw);
  const broken=dsv.slice();broken[20]^=1;broken[0x40000+20]^=1;
  await assert.rejects(importSave(file('broken.dsv',broken)),error=>error.code==='invalid-save'&&/checksum/.test(error.message));
});
