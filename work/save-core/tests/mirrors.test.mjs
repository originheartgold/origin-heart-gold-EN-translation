import test from 'node:test';
import assert from 'node:assert/strict';
import {readSave} from '../dist/save.js';
import {patchMoney} from '../dist/inventory.js';
import {saveFixture,view} from './fixtures.mjs';
// Independently recorded Chinese ARM9 branch expectations (native_evidence.md),
// Representative rows also boot-checked by native_loader_probe.py on CN/EN.
const matrix=[
 ['ordinary first',[10,9],[10,9],[],0],['ordinary second',[9,10],[9,10],[],1],
 ['equal divergent',[10,10],[10,10],[],0],['rollover second',[0xffffffff,0],[0xffffffff,0],[],1],
 ['rollover first',[0,0xffffffff],[0,0xffffffff],[],0],['wide gap unsigned',[1,0x90000000],[1,0x90000000],[],1],
 ['newest storage mismatch',[10,9],[8,9],[],1],['other newest storage mismatch',[9,10],[9,8],[],0],
 ['crossed generations',[10,9],[9,10],[],null],['neither generation coherent',[10,9],[8,7],[],null],
 ['bad newest storage',[10,9],[10,9],['s0'],1],['bad newest general',[10,9],[10,9],['g0'],1],
 ['bad backup general',[10,9],[10,9],['g1'],0],['both storage bad',[10,9],[10,9],['s0','s1'],null],
 ['both general bad',[10,9],[10,9],['g0','g1'],null],['only one coherent pair',[10,9],[10,9],['g1','s1'],0],
 ['single copies on opposite mirrors',[10,9],[10,9],['g1','s0'],null],
 ['single same-mirror mismatch',[10,9],[8,9],['g1','s1'],null],
 ['invalid zero counter is not coherence',[0,9],[0,8],['s0'],null],
 ['unsafe newest zero cannot fallback to coherent max counter',[0,0xffffffff],[0,0xffffffff],['s0'],null],
 ['unsafe reversed newest zero cannot fallback',[0xffffffff,0],[0xffffffff,0],['s1'],null],
 ['unsafe tied first zero cannot fallback to coherent second',[0,0],[0,0],['s0'],null],
 ['safe tied first zero wins before invalid second zero',[0,0],[0,0],['s1'],0],
];
for(const [name,counters,storageCounters,corrupt,expected]of matrix)test(`mirror recovery: ${name}`,()=>{
 const source=saveFixture({counters,storageCounters});source[0x40000+0x78]^=17;
 // marker lies in checksum: independently refresh only mirror general.
 refreshBlock(source,0x40000);
 for(const block of corrupt)source[(block[1]==='1'?0x40000:0)+(block[0]==='s'?0xf800:0)+42]^=1;
 if(expected===null){assert.throws(()=>readSave(source),/coherent|intact|unsafe/);assert.throws(()=>patchMoney(source,1));return;}
 const original=source.slice(),save=readSave(source);assert.equal(save.generalOffset,expected*0x40000);
 if(save.tied){assert.throws(()=>patchMoney(source,121),/Editing equal-counter mirrors is unsupported; save once in-game first/);assert.deepEqual(source,original);return;}
 const result=patchMoney(source,121);assert.equal(readSave(result).generalOffset,save.generalOffset);
 assert.equal(view(result).getUint32(save.generalOffset+0xf7bc,true),counters[expected]);
 assert.deepEqual(result.slice(save.generalOffset+0xf800,save.generalOffset+0xf800+0x18408),source.slice(save.generalOffset+0xf800,save.generalOffset+0xf800+0x18408));
 const other=expected?0:0x40000;assert.deepEqual(result.slice(other,other+0x40000),source.slice(other,other+0x40000));assert.deepEqual(source,original);
});
import {refreshBlock} from './fixtures.mjs';

test('complete block-validity matrix against independent literal native branch oracle',()=>{
  function expected(g,s){
    const validG=[0,1].filter(i=>g[i]!==null),validS=[0,1].filter(i=>s[i]!==null);
    if(!validG.length||!validS.length)return null;
    if(validG.length===1&&validS.length===1)return validG[0]===validS[0]&&g[validG[0]]===s[validG[0]]?validG[0]:null;
    const rank=validG.slice();
    if(rank.length===2){
      const a=g[0],b=g[1];
      if(a===0xffffffff&&b===0 || !(a===0&&b===0xffffffff)&&b>a)rank.reverse();
    }
    // Literal native 2/1 branch sees an invalid storage counter as zero;
    // the safe editor rejects when that branch would select invalid storage.
    for(const i of rank)if(g[i]===(s[i]??0))return s[i]===null?null:i;
    return null;
  }
  const counterSets=[[[10,9],[10,9]],[[9,10],[9,10]],[[10,9],[8,9]],[[10,9],[9,10]],[[0,0xffffffff],[0,0xffffffff]],[[0xffffffff,0],[0xffffffff,0]],[[0,0],[0,0]],[[10,10],[10,10]]];
  for(const [counters,storageCounters]of counterSets)for(let mask=0;mask<16;mask++){
    const source=saveFixture({counters,storageCounters}),g=counters.slice(),s=storageCounters.slice();
    for(let i=0;i<2;i++){
      if(!(mask&(1<<(i*2)))){g[i]=null;source[i*0x40000+42]^=1;}
      if(!(mask&(1<<(i*2+1)))){s[i]=null;source[i*0x40000+0xf800+42]^=1;}
    }
    const selected=expected(g,s),label=JSON.stringify({g,s});
    if(selected===null)assert.throws(()=>readSave(source),undefined,label);
    else assert.equal(readSave(source).generalOffset,selected*0x40000,label);
  }
});
