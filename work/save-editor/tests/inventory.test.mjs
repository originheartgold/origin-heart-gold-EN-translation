import test from 'node:test';
import assert from 'node:assert/strict';
import {crc16,readSave} from '../dist/core/save.js';
import {POCKETS,MONEY_MAX,MONEY_OFFSET,REGISTERED_OFFSET,readInventory,patchMoney,patchInventoryPocket} from '../dist/core/inventory.js';
const M=0x40000,G=0xf7cc,S=0xf800,Z=0x18408;
const v=b=>new DataView(b.buffer,b.byteOffset,b.byteLength);
function crc(b,base,o=0,size=G){const f=base+o+size-16;v(b).setUint16(f+14,crc16(b.subarray(base+o,f)),true);}
function fixture(c=[10,9]){const b=Uint8Array.from({length:0x80000},(_,i)=>(i*17+43)&255);[0,M].forEach((base,index)=>{
 v(b).setUint32(base+0x90,6,true);v(b).setUint32(base+0x94,0,true);v(b).setUint32(base+MONEY_OFFSET,123,true);
 for(const p of POCKETS)b.fill(0,base+p.offset,base+p.offset+p.capacity*4);b.fill(0,base+REGISTERED_OFFSET,base+REGISTERED_OFFSET+4);
 for(const[o,size,id]of[[0,G,0],[S,Z,1]]){const f=base+o+size-16;v(b).setUint32(f,c[index],true);v(b).setUint32(f+4,size,true);v(b).setUint32(f+8,0x20060623,true);v(b).setUint16(f+12,id,true);crc(b,base,o,size);}
 });return b;}
let next=1;const items=POCKETS.flatMap(p=>Array.from({length:p.capacity+1},()=>({id:next++,name:'Synthetic item',pocket:p.id})));
const data={items,getItem:id=>items.find(i=>i.id===id)},ids=p=>items.filter(i=>i.pocket===p).map(i=>i.id);
function stacks(b,id,entries){const base=readSave(b).generalOffset,p=POCKETS.find(p=>p.id===id);b.fill(0,base+p.offset,base+p.offset+p.capacity*4);entries.forEach((s,i)=>{if(s){v(b).setUint16(base+p.offset+i*4,s.id,true);v(b).setUint16(base+p.offset+i*4+2,s.quantity,true);}});crc(b,base);return b;}
function registrations(b,a,c){const base=readSave(b).generalOffset;v(b).setUint16(base+REGISTERED_OFFSET,a,true);v(b).setUint16(base+REGISTERED_OFFSET+2,c,true);crc(b,base);return b;}
function allowed(b,a,ranges){assert.equal(a.length,b.length);const base=readSave(b).generalOffset;ranges=[...ranges,[base+G-2,2]];for(let i=0;i<b.length;i++)if(a[i]!==b[i])assert.ok(ranges.some(([s,n])=>i>=s&&i<s+n),`Unexpected byte ${i.toString(16)}`);readSave(a);assert.equal(v(a).getUint16(base+G-2,true),crc16(a.subarray(base,base+G-16)));}
for(const counters of [[10,9],[9,10]]){const base=counters[0]>counters[1]?0:M;
 test(`money bounds, byte preservation and CRC mirror ${base}`,()=>{const b=fixture(counters),copy=b.slice();for(const money of [0,1,MONEY_MAX]){const a=patchMoney(b,money);assert.equal(readInventory(a).money,money);allowed(b,a,[[base+MONEY_OFFSET,4]]);}assert.deepEqual(b,copy);assert.deepEqual(patchMoney(b,123),b);});
 for(const p of POCKETS)test(`${p.id} cap, capacity, validation and preservation mirror ${base}`,()=>{const b=fixture(counters),copy=b.slice(),entries=ids(p.id).slice(0,p.capacity).map(id=>({id,quantity:p.maxQuantity}));const a=patchInventoryPocket(b,p.id,entries,data);assert.deepEqual(readInventory(a).pockets[p.id],entries);allowed(b,a,[[base+p.offset,p.capacity*4]]);assert.deepEqual(b,copy);assert.deepEqual(readInventory(patchInventoryPocket(a,p.id,[],data)).pockets[p.id],[]);
 assert.throws(()=>patchInventoryPocket(b,p.id,[...entries,{id:ids(p.id).at(-1),quantity:1}],data),/at most/);
 for(const quantity of [0,-1,p.maxQuantity+1,.5,NaN,Infinity,'1',null])assert.throws(()=>patchInventoryPocket(b,p.id,[{id:entries[0].id,quantity}],data),/Quantity/);
 assert.throws(()=>patchInventoryPocket(b,p.id,[{id:items.find(i=>i.pocket!==p.id).id,quantity:1}],data),/does not belong/);assert.throws(()=>patchInventoryPocket(b,p.id,[entries[0],entries[0]],data),/more than once/);assert.throws(()=>patchInventoryPocket(b,p.id,[{id:790,quantity:1}],data),/does not belong/);});
}
test('malformed money and pocket arguments are rejected',()=>{const b=fixture();for(const money of [-1,MONEY_MAX+1,.5,NaN,Infinity,'1',null,undefined])assert.throws(()=>patchMoney(b,money),/Money/);assert.throws(()=>patchInventoryPocket(b,'missing',[],data),/Unknown/);assert.throws(()=>patchInventoryPocket(b,'items',null,data),/at most/);assert.throws(()=>patchInventoryPocket(b,'items',[],undefined),/Reference data unavailable/);for(const item of [null,undefined,42])assert.throws(()=>patchInventoryPocket(b,'items',[item],data),/Invalid item/);for(const id of [0,-1,791,.5,NaN,Infinity,'1'])assert.throws(()=>patchInventoryPocket(b,'items',[{id,quantity:1}],data),/Item ID/);});
test('Buffer and nonzero-offset inputs are copied and never aliased',()=>{const b=fixture();for(const input of [b,Buffer.from(b),Buffer.concat([Buffer.alloc(13),Buffer.from(b)]).subarray(13)]){const copy=Uint8Array.from(input);assert.equal(readInventory(input).money,123);const a=patchInventoryPocket(patchMoney(input,234),'items',[{id:ids('items')[0],quantity:2}],data);assert.equal(readInventory(a).money,234);assert.deepEqual(Uint8Array.from(input),copy);const noop=patchMoney(input,123);noop[0]^=255;assert.deepEqual(Uint8Array.from(input),copy);}});
test('exact no-op preserves gaps and independent money/pocket updates compose',()=>{const id=ids('items')[0],b=stacks(fixture(),'items',[null,{id,quantity:2}]);assert.deepEqual(patchInventoryPocket(b,'items',readInventory(b).pockets.items,data),b);const a=patchInventoryPocket(patchMoney(b,54321),'items',[{id,quantity:3}],data);assert.equal(readInventory(a).money,54321);assert.deepEqual(readInventory(a).pockets.items,[{id,quantity:3}]);assert.deepEqual(a,patchMoney(patchInventoryPocket(b,'items',[{id,quantity:3}],data),54321));});
test('equal counters remain readable but reject inventory writes and no-ops',()=>{
 const b=fixture([10,10]),copy=b.slice();assert.equal(readInventory(b).money,123);
 for(const edit of [()=>patchMoney(b,123),()=>patchMoney(b,124),()=>patchInventoryPocket(b,'items',[],data),()=>patchInventoryPocket(b,'items',[{id:ids('items')[0],quantity:1}],data)])assert.throws(edit,/equal-counter mirrors/);
 assert.deepEqual(b,copy);
});
test('removed registered item clears shortcut and moves slot2 into slot1',()=>{const[a,c]=ids('keyItems'),b=registrations(stacks(fixture(),'keyItems',[{id:a,quantity:1},{id:c,quantity:1}]),a,c);const after=patchInventoryPocket(b,'keyItems',[{id:c,quantity:1}],data);assert.deepEqual(readInventory(after).registeredItems,[c,0]);const p=POCKETS.find(p=>p.id==='keyItems');allowed(b,after,[[p.offset,p.capacity*4],[REGISTERED_OFFSET,4]]);assert.deepEqual(readInventory(patchInventoryPocket(b,'items',[{id:ids('items')[0],quantity:1}],data)).registeredItems,[a,c]);assert.deepEqual(readInventory(patchInventoryPocket(b,'keyItems',[],data)).registeredItems,[0,0]);});
for(const id of ['tmHm','berries'])test(`${id} insertion sorts but quantity changes preserve order`,()=>{const[a,c,d]=ids(id),b=stacks(fixture(),id,[{id:d,quantity:2},{id:a,quantity:1}]);assert.deepEqual(readInventory(patchInventoryPocket(b,id,[{id:d,quantity:3},{id:a,quantity:1}],data)).pockets[id].map(s=>s.id),[d,a]);assert.deepEqual(readInventory(patchInventoryPocket(b,id,[{id:d,quantity:2},{id:a,quantity:1},{id:c,quantity:1}],data)).pockets[id].map(s=>s.id),[a,c,d]);});
test('public save API does not expose raw-offset mutation',async()=>{assert.equal('patchGeneralRegion' in await import('../dist/core/save.js'),false);});

test('unrelated second-slot-only registration remains byte-for-byte unchanged',()=>{
 const registered=ids('keyItems')[0],b=registrations(fixture(),0,registered);
 const after=patchInventoryPocket(b,'items',[{id:ids('items')[0],quantity:1}],data);
 assert.deepEqual(readInventory(after).registeredItems,[0,registered]);
 const p=POCKETS.find(p=>p.id==='items');allowed(b,after,[[p.offset,p.capacity*4]]);
});
test('sparse stack arrays are rejected rather than silently clearing pocket',()=>{
 const b=stacks(fixture(),'items',[{id:ids('items')[0],quantity:2}]);
 assert.throws(()=>patchInventoryPocket(b,'items',new Array(1),data),/Invalid item/);
});
