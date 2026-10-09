import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createHash} from 'node:crypto';
import {saveFixture,pokemonFixture} from './fixtures.mjs';
const worker=new URL('../cli/worker.mjs',import.meta.url);
const request=(op,bytes=new Uint8Array(),args={},id=1)=>({version:1,id,op,bytes:Buffer.from(bytes).toString('base64'),args});
function run(chunks) {
  return new Promise((resolve,reject)=>{
    const child=spawn(process.execPath,[worker.pathname],{stdio:['pipe','pipe','pipe']}),out=[],err=[];
    const deadline=setTimeout(()=>{child.kill();reject(new Error('Worker timeout'));},10000);
    child.on('error',reject);child.stdout.on('data',x=>out.push(x));child.stderr.on('data',x=>err.push(x));
    child.on('close',code=>{clearTimeout(deadline);try{assert.equal(code,0,Buffer.concat(err).toString());resolve(Buffer.concat(out).toString().trim().split('\n').filter(Boolean).map(x=>JSON.parse(x)));}catch(e){reject(e);}});
    child.stdin.on('error',reject);for(const chunk of chunks)child.stdin.write(chunk);child.stdin.end();
  });
}
const line=value=>JSON.stringify(value)+'\n';

test('worker preserves request IDs, hashes, and exact no-op full save bytes',async()=>{
  const save=saveFixture(),record=pokemonFixture(31);
  const rows=await run([line(request('decodePokemon',record,{},'first')),line(request('transactSave',save,{operations:[]},2)),line(request('decodePokemon',record,{},'last'))]);
  assert.deepEqual(rows.map(row=>row.id),['first',2,'last']);assert.ok(rows.every(row=>row.version===1&&!row.error));
  assert.deepEqual(Buffer.from(rows[1].result.bytes,'base64'),Buffer.from(save));
  const hash=createHash('sha256').update(save).digest('hex');assert.equal(rows[1].result.report.sourceSha256,hash);assert.equal(rows[1].result.report.outputSha256,hash);
});

test('worker rejects malformed protocol then continues with valid request',async()=>{
  const invalid=[null,[],{}, {...request('emptyPokemon'),version:2},{...request('emptyPokemon'),id:-1},{...request('emptyPokemon'),id:'x'.repeat(129)}, {...request('emptyPokemon'),extra:1},request('unknown'),request('emptyPokemon',new Uint8Array(),[]),request('emptyPokemon',new Uint8Array(),null),{...request('emptyPokemon'),bytes:null},request('emptyPokemon',new Uint8Array(),{extra:true}),{...request('emptyPokemon'),bytes:'AA'},{...request('emptyPokemon'),bytes:'Zh=='},{...request('emptyPokemon'),bytes:34},request('decodePokemon',pokemonFixture(),{diagnostic:1})];
  const rows=await run(['{bad json}\n',...invalid.map(line),line(request('emptyPokemon',new Uint8Array(),{},'healthy'))]);
  assert.equal(rows.length,invalid.length+2);assert.ok(rows.slice(0,-1).every(row=>row.error?.code==='invalid-input'));
  assert.equal(rows.at(-1).id,'healthy');assert.equal(Buffer.from(rows.at(-1).result.bytes,'base64').length,236);
});

test('worker rejects failed transaction with operation index, source remains reusable',async()=>{
  const source=saveFixture(),bad=request('transactSave',source,{operations:[{type:'setFlag',flag:10,value:true},{type:'setVar',var:0x4170,value:1}]},1);
  const rows=await run([line(bad),line(request('transactSave',source,{operations:[]},2))]);
  assert.equal(rows[0].error.operationIndex,1);assert.deepEqual(Buffer.from(rows[1].result.bytes,'base64'),Buffer.from(source));
});

test('worker handles split lines, oversized no-newline requests, and resynchronizes',async()=>{
  const valid=line(request('emptyPokemon',new Uint8Array(),{},'resumed'));
  const rows=await run(['x'.repeat(999999),'x'.repeat(999999),'xxxx','\n',valid.slice(0,9),valid.slice(9)]);
  assert.equal(rows.length,2);assert.match(rows[0].error.message,/line limit/);assert.equal(rows[1].id,'resumed');assert.ok(rows[1].result);
});

test('worker rejects truncated last line without executing it',async()=>{
  const rows=await run([JSON.stringify(request('emptyPokemon'))]);assert.equal(rows.length,1);assert.match(rows[0].error.message,/Truncated/);
});
