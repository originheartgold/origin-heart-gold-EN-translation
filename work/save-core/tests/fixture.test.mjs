import test from 'node:test';
import assert from 'node:assert/strict';
import {applySaveTransaction, inspectSaveFixture, SAVED_FLAG_COUNT} from '../dist/fixture.js';
import {patchPokemonFixture, decodePokemonDiagnostic, decodePokemon} from '../dist/pokemon.js';
import {saveFixture, pokemonFixture, decodeOracle, refreshBlock, view} from './fixtures.mjs';
const policy = {tailPolicy:'preserve'};
const transact = (bytes, ...ops) => applySaveTransaction(bytes, ops);

for (const base of [0, 0x40000]) test(`saved flag/variable exact native boundary and preservation, mirror ${base}`, () => {
  const source = saveFixture({counters:base ? [9,10] : [10,9]}), before = source.slice();
  assert.equal(SAVED_FLAG_COUNT, 0xca0);
  const result = transact(source, {type:'setFlag',flag:1,value:true}, {type:'setFlag',flag:0xc9f,value:true}, {type:'setVar',var:0x4000,value:65535}, {type:'setVar',var:0x416f,value:513});
  const data = view(result.bytes);
  assert.equal(result.bytes[base+0x118c], 2); assert.equal(result.bytes[base+0x131f],128);
  assert.equal(data.getUint16(base+0xeac,true),65535); assert.equal(data.getUint16(base+0x118a,true),513);
  const allowed = new Set([0xeac,0xead,0x118a,0x118b,0x118c,0x131f,0xf7ca,0xf7cb].map(x=>base+x));
  for(let i=0;i<source.length;i++)if(source[i]!==result.bytes[i])assert.ok(allowed.has(i),i.toString(16));
  assert.deepEqual(source,before); assert.equal(result.report.generalOffset,base);
  assert.equal(result.report.nativeLoadVerified,false);
  const inspection=inspectSaveFixture(result.bytes); assert.equal(inspection.flags.length,0x194);assert.equal(inspection.vars.length,0x170);
});

test('all unsafe flag and var IDs/types reject; no neighboring-byte damage', () => {
  const source=saveFixture(), before=source.slice();
  for(const flag of [-1,0,0xca0,0xcbf,0xcc0,0x4000,0.5,NaN,Infinity,'1',true,null]) assert.throws(()=>transact(source,{type:'setFlag',flag,value:true}));
  for(const value of [0,1,'true',null])assert.throws(()=>transact(source,{type:'setFlag',flag:1,value}));
  for(const variable of [0x3fff,0x4170,-1,0.5,NaN,Infinity,'16384',null])assert.throws(()=>transact(source,{type:'setVar',var:variable,value:0}));
  for(const value of [-1,65536,0.5,NaN,Infinity,'1',null])assert.throws(()=>transact(source,{type:'setVar',var:0x4000,value}));
  assert.deepEqual(source,before);
});

test('failed later operation rolls back all earlier edits with operation index', () => {
  const source=saveFixture(), before=source.slice();
  assert.throws(()=>transact(source,{type:'setFlag',flag:99,value:true},{type:'setPocket',name:'items',items:[[51,2],[52,-1]]}),error=>error.operationIndex===1 && /Quantity/.test(error.message));
  assert.deepEqual(source,before);
  assert.throws(()=>transact(source,{type:'setPartyCount',count:1},{type:'editPartyMon',slot:1,changes:{species:900},...policy}),error=>error.operationIndex===1);
  assert.deepEqual(source,before);
});

test('exact no-ops and operations that cancel preserve every original byte', () => {
  const source=saveFixture();
  for(const ops of [[],[{type:'setFlag',flag:1,value:false}],[{type:'setFlag',flag:1,value:true},{type:'setFlag',flag:1,value:false}],[{type:'editPartyMon',slot:0,changes:{},...policy}]]) {
    const result=applySaveTransaction(source,ops);assert.deepEqual(result.bytes,source);assert.equal(result.report.changed,false);assert.deepEqual(result.report.changedRanges,[]);
    result.bytes[0]^=1;assert.notEqual(result.bytes[0],source[0]);
  }
});

test('party shrink cannot activate empty slots or edit inactive records', () => {
  const source=saveFixture();
  for(const count of [0,3,6,7,-1,1.5,NaN,null,'1'])assert.throws(()=>transact(source,{type:'setPartyCount',count}));
  const result=transact(source,{type:'setPartyCount',count:1});assert.equal(inspectSaveFixture(result.bytes).partyCount,1);
  assert.deepEqual(result.bytes.slice(0x98,0x98+6*236),source.slice(0x98,0x98+6*236));
  for(const slot of [-1,2,6,0.5,NaN,null,'0'])assert.throws(()=>transact(source,{type:'editPartyMon',slot,changes:{item:1},...policy}));
});

const capacities={items:165,key:50,tm:151,mail:12,medicine:40,berries:64,balls:24,battle:30};
for(const [name,capacity] of Object.entries(capacities))test(`fixture pocket ${name} empty/full/order and capacity`,()=>{
  const source=saveFixture(),items=Array.from({length:capacity},(_,i)=>[65535-i,i+1]);
  const full=transact(source,{type:'setPocket',name,items});assert.deepEqual(inspectSaveFixture(full.bytes).pockets[name],items);
  assert.throws(()=>transact(source,{type:'setPocket',name,items:[...items,[7,1]]}));
  const cleared=transact(full.bytes,{type:'setPocket',name,items:[]});assert.deepEqual(cleared.bytes,source);
});

test('reject malformed and unknown operations, including sparse arrays',()=>{
  const source=saveFixture();
  for(const op of [null,[],{}, {type:'patchGeneralRegion',offset:0,bytes:[]},{type:'setFlag',flag:1,value:true,extra:0}])assert.throws(()=>transact(source,op));
  for(const ops of [null,{},'x',new Array(1),new Array(10001).fill({type:'setFlag',flag:1,value:false})])assert.throws(()=>applySaveTransaction(source,ops));
});

for(let selector=0;selector<32;selector++)test(`fixture fields independent plaintext oracle, shuffle ${selector}`,()=>{
  const record=pokemonFixture(selector),before=decodeOracle(record),expected=before.logical.slice(),data=view(expected);
  const changes={species:65535,item:60000,ability:500,form:31,fateful:true,moves:[1000,2000],pp:[0,255],exp:0xffffffff,otId:0xfefdfcfb,currentHp:65535};
  data.setUint16(0,65535,true);data.setUint16(2,60000,true);data.setUint32(4,0xfefdfcfb,true);data.setUint32(8,0xffffffff,true);
  data.setUint16(58,500,true);expected[56]=(expected[56]&6)|249;
  data.setUint16(32,1000,true);data.setUint16(34,2000,true);expected[40]=0;expected[41]=255;
  const edited=patchPokemonFixture(record,changes,policy),oracle=decodeOracle(edited),tail=before.tail.slice();view(tail).setUint16(6,65535,true);
  assert.deepEqual(oracle.logical,expected);assert.deepEqual(oracle.tail,tail);assert.equal(oracle.checksumOk,true);assert.equal(oracle.pid,before.pid);
  assert.deepEqual(patchPokemonFixture(record,{},policy),record);
  const partial=decodeOracle(patchPokemonFixture(record,{moves:[900]},policy));assert.equal(partial.logical[40],10);assert.deepEqual(partial.logical.slice(44,48),before.logical.slice(44,48));
});

test('fixture edits require explicit tail policy and validate all field numeric boundaries',()=>{
  const record=pokemonFixture(),before=record.slice();
  for(const option of [undefined,{}, {tailPolicy:'recalculate'}])assert.throws(()=>patchPokemonFixture(record,{},option));
  for(const [key,max] of Object.entries({species:65535,item:65535,ability:65535,form:31,exp:0xffffffff,otId:0xffffffff,currentHp:65535}))for(const value of [-1,max+1,0.5,NaN,Infinity,'1',null])assert.throws(()=>patchPokemonFixture(record,{[key]:value},policy),key);
  for(const changes of [{typo:1},{fateful:1},{moves:[1,2,3,4,5]},{moves:[1],pp:[]},{moves:[1],pp:[256]},{moves:new Array(1)},{pp:new Array(1)},[],null])assert.throws(()=>patchPokemonFixture(record,changes,policy));
  assert.throws(()=>patchPokemonFixture(pokemonFixture(0,136),{currentHp:1},policy));assert.deepEqual(record,before);
});

test('diagnostic open records follow separate box/tail encryption flags; mutations always reject',()=>{
  const closed=pokemonFixture(17),before=decodePokemon(closed),logical=decodeOracle(closed);
  for(const flags of [2,3]){
    const record=closed.slice();view(record).setUint16(4,flags,true);
    // Native context functions produce box-open2 and full-party-open3.
    if(flags&2){const key=view(closed).getUint16(6,true); record.set(xorWords(record.subarray(8,136),key),8);}
    if(flags&1)record.set(logical.tail,136);
    const diagnostic=decodePokemonDiagnostic(record);assert.equal(diagnostic.checksumOk,true);assert.equal(diagnostic.speciesId,before.speciesId);assert.deepEqual(diagnostic.party,before.party);
    assert.throws(()=>patchPokemonFixture(record,{},policy),/flags/);
  }
});
import {xorWords} from './fixtures.mjs';

test('five native locations own exactly20 bytes each and validate scalar bounds',()=>{
  const source=saveFixture();
  for(let which=0;which<5;which++){
    const result=transact(source,{type:'setLocation',which,map:65535,warp:-1,x:-2147483648,y:2147483647,direction:'RIGHT'}),start=0x1324+which*20;
    assert.deepEqual(inspectSaveFixture(result.bytes).locations[which],{map:65535,warp:-1,x:-2147483648,y:2147483647,dir:3});
    for(let i=0;i<source.length;i++)if(source[i]!==result.bytes[i])assert.ok(i>=start&&i<start+20 || i>=0xf7ca&&i<0xf7cc);
  }
  const valid={type:'setLocation',map:1,x:2,y:3,direction:'DOWN'};
  for(const [field,values]of Object.entries({which:[-1,5,0.5,null],map:[-1,65536,null],x:[-2147483649,2147483648,null],y:[-2147483649,2147483648,null],warp:[-2,2147483648,null],direction:['NOPE',-1,4,null]}))for(const value of values)assert.throws(()=>transact(source,{...valid,[field]:value}));
});

test('placePlayer edits only active player/follower coordinates and removes active NPCs',()=>{
  const source=saveFixture(),data=view(source);
  for(const [slot,id]of [[0,255],[1,253],[2,15]]){
    const start=0x2480+slot*80;source.fill(0x66,start,start+80);data.setUint32(start,1,true);source[start+8]=id;
  }
  source.fill(0x55,0x2480+3*80+4,0x2480+4*80);refreshBlock(source);
  const result=transact(source,{type:'placePlayer',map:10,x:-3,z:7,height:12,direction:'UP'}),edited=view(result.bytes);
  assert.deepEqual(inspectSaveFixture(result.bytes).locations[0],{map:10,warp:-1,x:-3,y:7,dir:0});
  for(const [slot,z]of [[0,7],[1,6]]){
    const start=0x2480+slot*80;assert.deepEqual(Array.from({length:6},(_,i)=>edited.getInt16(start+32+i*2,true)),[-3,12,z,-3,12,z]);
    assert.deepEqual(result.bytes.slice(start,start+32),source.slice(start,start+32));assert.equal(edited.getInt32(start+44,true),12*8*0x1000);assert.deepEqual(result.bytes.slice(start+48,start+80),source.slice(start+48,start+80));
  }
  // Height 0 leaves the saved fx32 y as it was.
  const flat=transact(source,{type:'placePlayer',map:10,x:-3,z:7,height:0,direction:'UP'});
  assert.deepEqual(flat.bytes.slice(0x2480+44,0x2480+80),source.slice(0x2480+44,0x2480+80));
  assert.deepEqual(result.bytes.slice(0x2480+2*80,0x2480+3*80),new Uint8Array(80));
  assert.deepEqual(result.bytes.slice(0x2480+3*80,0x2480+4*80),source.slice(0x2480+3*80,0x2480+4*80));
  for(const changes of [{x:32768},{x:-32769},{z:-32768},{z:32768},{height:32768},{height:null}])assert.throws(()=>transact(source,{type:'placePlayer',map:10,x:2,z:3,direction:0,...changes}));
});

test('diagnostic corruption is reported and cannot pass any fixture mutation',()=>{
  const original=pokemonFixture();
  for(const offset of [8,57,135]){
    const record=original.slice();record[offset]^=1;
    assert.equal(decodePokemonDiagnostic(record).checksumOk,false);
    assert.throws(()=>patchPokemonFixture(record,{item:1},policy),/checksum/);
  }
  for(const flags of [4,8,0x8000]){
    const record=original.slice();view(record).setUint16(4,flags,true);
    const diagnostic=decodePokemonDiagnostic(record);assert.equal(diagnostic.flags,flags);assert.equal(diagnostic.badEgg,(flags&4)!==0);assert.equal(diagnostic.checksumOk,true);
    assert.throws(()=>patchPokemonFixture(record,{},policy),/flags/);
  }
});
