import test from 'node:test';
import assert from 'node:assert/strict';
import {EditorError, editorErrorMessage} from '../dist/core/errors.js';
import {importSave} from '../dist/core/save-import.js';
import {crc16, readSave} from '../dist/core/save.js';
import {mapStats} from '../dist/core/stats.js';
import {isPokerusStatus} from '../dist/core/pokemon.js';
import {isPocketId} from '../dist/core/inventory.js';

function fixture() {
  // Invented empty-party data, not a playable game save.
  const bytes=new Uint8Array(524288), view=new DataView(bytes.buffer);
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
const file=bytes=>({name:'test.sav',size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength)});

test('domain errors retain stable codes and actionable messages',()=>{
  assert.throws(()=>readSave(new Uint8Array()),error=>error instanceof EditorError&&error.code==='invalid-save');
  assert.equal(editorErrorMessage(new EditorError('invalid-input','Total EVs cannot exceed 510.')),'Total EVs cannot exceed 510.');
});
test('item error display uses typed context, not message parsing',()=>{
  const error=new EditorError('invalid-input','wording can change',{kind:'wrong-pocket',itemId:1,pocketLabel:'Medicine'});
  assert.equal(editorErrorMessage(error,()=> 'Master Ball'),'Master Ball does not belong in Medicine.');
  assert.equal(editorErrorMessage(error),'Item #1 does not belong in Medicine.');
  assert.equal(editorErrorMessage(new EditorError('invalid-input','unaltered Item #1')), 'unaltered Item #1');
});
test('unexpected thrown values use safe fallback without string coercion',()=>{
  const hostile={toString(){throw Error('must not run');}};
  for(const value of [null,undefined,'secret',new Error('internal details'),hostile]) {
    assert.match(editorErrorMessage(value),/Something went wrong/);
    assert.doesNotMatch(editorErrorMessage(value),/secret|internal details/);
  }
});
test('candidate import validates and leaves source bytes unchanged',async()=>{
  const bytes=fixture(), copy=bytes.slice();const imported=await importSave(file(bytes));
  assert.equal(imported.filename,'test.sav');assert.deepEqual(imported.bytes,copy);assert.deepEqual(bytes,copy);
});
test('candidate import rejects incorrect sizes before reading',async()=>{
  let read=false;
  await assert.rejects(importSave({name:'bad.sav',size:10,arrayBuffer:async()=>{read=true;return new ArrayBuffer(10);}}),error=>error instanceof EditorError&&error.code==='invalid-save');
  assert.equal(read,false);
});
test('candidate import reports file-read failure with cause, never raw content',async()=>{
  const cause=new Error('operating system details');
  await assert.rejects(importSave({name:'bad.sav',size:524288,arrayBuffer:async()=>{throw cause;}}),error=>error instanceof EditorError&&error.code==='read-failed'&&error.cause===cause&&!editorErrorMessage(error).includes(cause.message));
});
test('candidate import validates actual bytes, not only declared size',async()=>{
  await assert.rejects(importSave({name:'bad.sav',size:524288,arrayBuffer:async()=>new ArrayBuffer(1)}),error=>error.code==='invalid-save');
  const bytes=fixture();bytes[20]^=1;bytes[0x40000+20]^=1;
  await assert.rejects(importSave(file(bytes)),error=>error.code==='invalid-save'&&/checksum/.test(error.message));
});
test('candidate import validates party record even when save CRC is intact',async()=>{
  const bytes=fixture(),view=new DataView(bytes.buffer);
  view.setUint32(0x94,1,true);view.setUint16(0x98+4,1,true);
  view.setUint16(0xf7ca,crc16(bytes.subarray(0,0xf7bc)),true);
  await assert.rejects(importSave(file(bytes)),error=>error.code==='invalid-pokemon');
});
test('six-key stat builder preserves native Speed-before-Special index order',()=>{
  assert.deepEqual(mapStats((key,index)=>[key,index]),{hp:['hp',0],attack:['attack',1],defense:['defense',2],speed:['speed',3],spAttack:['spAttack',4],spDefense:['spDefense',5]});
});
test('DOM enum guards reject arbitrary or missing values',()=>{
  for(const value of ['none','infected','cured']) assert.equal(isPokerusStatus(value),true);
  for(const value of ['',null,undefined,'INFECTED',{},1]) assert.equal(isPokerusStatus(value),false);
  assert.equal(isPocketId('medicine'),true);assert.equal(isPocketId('other'),false);
});
