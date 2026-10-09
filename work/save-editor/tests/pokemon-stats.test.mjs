import test from 'node:test';
import assert from 'node:assert/strict';
import { decodePokemon, patchPokemonStats } from '../dist/core/pokemon.js';
const keys=['hp','attack','defense','speed','spAttack','spDefense'];
const values=(a)=>Object.fromEntries(keys.map((k,i)=>[k,a[i]]));
const ivs=values([10,11,12,13,14,15]);
const evs=values([8,12,16,20,24,28]);
const personal={baseStats:[50,60,70,80,90,100],growthRate:0};
function permutations(v){return v.length?v.flatMap(x=>permutations(v.filter(y=>y!==x)).map(t=>[x,...t])):[[]];}
const orders=permutations([0,1,2,3]);
function crypt(bytes, seed){const r=Uint8Array.from(bytes);const v=new DataView(r.buffer);let s=BigInt(seed);for(let i=0;i<r.length;i+=2){s=(s*1103515245n+24691n)&0xffffffffn;v.setUint16(i,v.getUint16(i,true)^Number(s>>16n),true);}return r;}
function seal(record,plain){const v=new DataView(plain.buffer);let sum=0;for(let i=0;i<128;i+=2)sum=(sum+v.getUint16(i,true))&65535;new DataView(record.buffer).setUint16(6,sum,true);record.set(crypt(plain,sum),8);return record;}
function fixture(selector=0,{egg=false,override=0,currentHp=40}={}){
 const r=new Uint8Array(236),h=new DataView(r.buffer);const pid=(selector<<13)|123;h.setUint32(0,pid,true);
 const logical=Array.from({length:4},(_,b)=>Uint8Array.from({length:32},(_,i)=>(b*13+i*3)&255));
 const a=new DataView(logical[0].buffer),b=new DataView(logical[1].buffer);
 a.setUint16(0,1018,true);a.setUint32(8,99999,true);keys.forEach((k,i)=>a.setUint8(16+i,evs[k]));
 let packed=0x80000000|(egg?0x40000000:0);keys.forEach((k,i)=>packed|=ivs[k]<<(i*5));b.setUint32(16,packed>>>0,true);
 b.setUint32(20,(0x80123456|(override<<25))>>>0,true);b.setUint8(24,(3<<3)|5);
 const plain=new Uint8Array(128);orders[selector%24].forEach((id,i)=>plain.set(logical[id],i*32));seal(r,plain);
 const tail=Uint8Array.from({length:100},(_,i)=>(i*7+11)&255),t=new DataView(tail.buffer);t.setUint32(0,8,true);t.setUint8(4,50);t.setUint16(6,currentHp,true);[115,75,85,95,105,115].forEach((x,i)=>t.setUint16(8+i*2,x,true));r.set(crypt(tail,pid),136);return r;
}
function plain(record){return crypt(record.slice(8,136),new DataView(record.buffer,record.byteOffset).getUint16(6,true));}
function tail(record){return crypt(record.slice(136),new DataView(record.buffer,record.byteOffset).getUint32(0,true));}
for(let selector=0;selector<32;selector++)test(`stats selector ${selector}: decode, separate IV/EV edit, unknown bytes intact`,()=>{
 const r=fixture(selector),snapshot=r.slice(),d=decodePokemon(r);assert.deepEqual(d.ivs,ivs);assert.deepEqual(d.evs,evs);assert.equal(d.nature,d.pid%25);assert.equal(d.form,3);assert.equal(d.experience,99999);assert.equal(d.party.level,50);assert.equal(d.party.currentHp,40);assert.equal(d.party.status,8);
 assert.deepEqual(patchPokemonStats(r,{},personal),r);assert.deepEqual(patchPokemonStats(r,{ivs,evs,level:50,nature:d.nature},personal),r);
 for(const group of ['ivs','evs']){
  const edits={...d[group],attack:group==='ivs'?31:252};const patched=patchPokemonStats(r,{[group]:edits},personal),after=decodePokemon(patched);assert.deepEqual(after[group],edits);assert.deepEqual(after[group==='ivs'?'evs':'ivs'],d[group==='ivs'?'evs':'ivs']);assert.equal(after.experience,d.experience);assert.equal(after.nature,d.nature);assert.equal(after.pid,d.pid);
  const beforePlain=plain(r),afterPlain=plain(patched),physicalA=orders[selector%24].indexOf(0)*32,physicalB=orders[selector%24].indexOf(1)*32;
  for(let i=0;i<128;i++)if(!(i>=physicalA+16&&i<physicalA+22)&&!(i>=physicalB+16&&i<physicalB+20))assert.equal(afterPlain[i],beforePlain[i]);
  assert.equal(new DataView(afterPlain.buffer).getUint32(physicalB+16,true)>>>30,2);
  assert.deepEqual(tail(patched).slice(20),tail(r).slice(20));assert.deepEqual(tail(patched).slice(0,6),tail(r).slice(0,6));
 }
 assert.deepEqual(r,snapshot);
});
test('nature override changes effective nature without PID, flags or other ribbon bits',()=>{
 const r=fixture(0,{override:4}),before=plain(r);assert.equal(decodePokemon(r).nature,3);
 const out=patchPokemonStats(r,{nature:12},personal),after=plain(out);assert.equal(decodePokemon(out).nature,12);assert.deepEqual(out.slice(0,6),r.slice(0,6));assert.equal(new DataView(after.buffer).getUint32(52,true)&0x81ffffff,new DataView(before.buffer).getUint32(52,true)&0x81ffffff);
});
test('changing level uses supplied growth thresholds and updates encrypted level',()=>{
 const thresholds=Array.from({length:101},(_,i)=>i<2?0:i*i*i),r=fixture();const out=patchPokemonStats(r,{level:60},personal,thresholds);assert.equal(decodePokemon(out).experience,216000);assert.equal(decodePokemon(out).party.level,60);assert.equal(decodePokemon(r).experience,99999);
});
test('fainted stays fainted; eggs, bad values and boxed edits without growth data fail without mutations',()=>{
 const r=fixture(0,{currentHp:0}),snapshot=r.slice();assert.equal(decodePokemon(patchPokemonStats(r,{ivs:{...ivs,hp:31}},personal)).party.currentHp,0);
 assert.throws(()=>patchPokemonStats(fixture(0,{egg:true}),{ivs:{...ivs,hp:31}},personal),/Egg/);
 assert.throws(()=>patchPokemonStats(r.slice(0,136),{ivs},personal),/growth data/);
 for(const changes of [{ivs:{...ivs,hp:32}},{evs:{...evs,hp:256}},{evs:values([255,255,1,0,0,0])},{level:0},{level:101},{nature:25},{ivs:{hp:1}}])assert.throws(()=>patchPokemonStats(r,changes,personal));
 assert.throws(()=>patchPokemonStats(fixture(0,{override:63}),{ivs:{...ivs,hp:31}},personal),/nature/);assert.deepEqual(r,snapshot);
});
test('Buffer and offset-backed inputs do not alias edited outputs',()=>{const r=fixture(11);for(const input of [Buffer.from(r),Buffer.concat([Buffer.alloc(7),r]).subarray(7)]){const snapshot=Uint8Array.from(input);const out=patchPokemonStats(input,{ivs:{...ivs,hp:31}},personal);out.fill(0);assert.deepEqual(Uint8Array.from(input),snapshot);}});
