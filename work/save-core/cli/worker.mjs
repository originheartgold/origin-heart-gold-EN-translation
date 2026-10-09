#!/usr/bin/env node
// Node boundary only. stdout is reserved for bounded JSON-lines protocol responses.
import { createHash } from 'node:crypto';
import { PROTOCOL_VERSION as VERSION } from './protocol.mjs';
import { verifyBuildIdentity } from '../scripts/build-identity.mjs';
const buildIdentity = verifyBuildIdentity();
// Verify before importing any compiled code, so an old dist cannot process input.
const { decodePokemonDetails, decodePokemonDiagnostic, patchPokemonFixture, emptyPokemonFixture } = await import('../dist/pokemon.js');
const { applySaveTransaction, inspectSaveFixture } = await import('../dist/fixture.js');
const { calculateStats, mapStats } = await import('../dist/stats.js');
// Imports yield to the event loop. A concurrent rebuild must not load a mixed
// graph while the handshake still advertises the identity checked above.
if (verifyBuildIdentity().buildId !== buildIdentity.buildId) {
  throw Error('Shared save core changed while loading; restart after npm run build in work/save-editor completes.');
}
const MAX_LINE=2_000_000;
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
function fail(message) { const e=new Error(message);e.code='invalid-input';throw e; }
function bytes(value) {
  if(typeof value!=='string'||value.length>1_000_000||value.length%4||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value))fail('Expected canonical bounded base64 bytes.');
  const result=Buffer.from(value,'base64');if(result.toString('base64')!==value)fail('Noncanonical base64 bytes.');return result;
}
function keys(value,allowed) { for(const key of Object.keys(value))if(!allowed.includes(key))fail(`Unexpected field: ${key}.`); }
function handle(request) {
  if(!object(request))fail('Expected request object.');keys(request,['version','id','op','bytes','args']);
  if(request.version!==VERSION)fail('Unsupported protocol version.');
  if(!(typeof request.id==='string'&&request.id.length<=128)&&!(Number.isSafeInteger(request.id)&&request.id>=0))fail('Invalid request ID.');
  const args=request.args===undefined?{}:request.args;if(!object(args))fail('Expected args object.');
  const input=bytes(request.bytes===undefined?'':request.bytes);
  switch(request.op) {
    case 'handshake':keys(args,[]);if(input.length)fail('Handshake takes no input bytes.');return buildIdentity;
    case 'decodePokemon':keys(args,['diagnostic']);if(args.diagnostic!==undefined&&typeof args.diagnostic!=='boolean')fail('Diagnostic must be boolean.');return args.diagnostic?decodePokemonDiagnostic(input):decodePokemonDetails(input);
    case 'patchPokemon': {
      keys(args,['changes','tailPolicy']);const output=patchPokemonFixture(input,args.changes,{tailPolicy:args.tailPolicy});
      return {bytes:output,report:{sourceSha256:hash(input),outputSha256:hash(output),tailPolicy:args.tailPolicy}};
    }
    case 'inspectSave':keys(args,[]);return inspectSaveFixture(input);
    case 'transactSave': {
      keys(args,['operations']);const result=applySaveTransaction(input,args.operations);
      return {...result,report:{...result.report,sourceSha256:hash(input),outputSha256:hash(result.bytes)}};
    }
    case 'emptyPokemon':keys(args,[]);if(input.length)fail('Empty fixture takes no input bytes.');return {bytes:emptyPokemonFixture()};
    case 'calculateStats': {
      keys(args,['base','ivs','evs','level','nature','species']);
      for(const key of ['base','ivs','evs'])if(!Array.isArray(args[key])||args[key].length!==6)fail(`${key} requires six numbers.`);
      const stats=calculateStats(args.base,mapStats((_,i)=>args.ivs[i]),mapStats((_,i)=>args.evs[i]),args.level,args.nature,args.species??1);
      return Object.values(stats);
    }
    default:fail('Unknown operation.');
  }
}
function send(request) {
  let response;
  try {response={version:VERSION,id:request?.id??null,result:handle(request)};}
  catch(error) {response={version:VERSION,id:request?.id??null,error:{code:error.code??'invalid-input',message:error.message, ...(error.operationIndex===undefined?{}:{operationIndex:error.operationIndex})}};}
  process.stdout.write(JSON.stringify(response,(_,value)=>value instanceof Uint8Array?Buffer.from(value).toString('base64'):value)+'\n');
}
let pending=Buffer.alloc(0),discard=false;
process.stdin.on('data',chunk=> {
  // Never accumulate an arbitrarily large line, even if a sender omits its newline.
  let start=0;
  for(let i=0;i<chunk.length;i++)if(chunk[i]===10) {
    const part=chunk.subarray(start,i);start=i+1;
    if(discard){discard=false;pending=Buffer.alloc(0);continue;}
    if(pending.length+part.length>MAX_LINE){process.stdout.write(JSON.stringify({version:VERSION,id:null,error:{code:'invalid-input',message:'Request exceeds line limit.'}})+'\n');pending=Buffer.alloc(0);continue;}
    const line=Buffer.concat([pending,part]);pending=Buffer.alloc(0);
    try{send(JSON.parse(line.toString('utf8')));}catch{process.stdout.write(JSON.stringify({version:VERSION,id:null,error:{code:'invalid-input',message:'Invalid JSON.'}})+'\n');}
  }
  if(!discard) {
    const tail=chunk.subarray(start);
    if(pending.length+tail.length>MAX_LINE){pending=Buffer.alloc(0);discard=true;process.stdout.write(JSON.stringify({version:VERSION,id:null,error:{code:'invalid-input',message:'Request exceeds line limit.'}})+'\n');}
    else pending=Buffer.concat([pending,tail]);
  }
});
process.stdin.on('end',()=> {if(pending.length)process.stdout.write(JSON.stringify({version:VERSION,id:null,error:{code:'invalid-input',message:'Truncated request: newline required.'}})+'\n');});
