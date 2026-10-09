import test from 'node:test';
import assert from 'node:assert/strict';
import {cpSync, existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, symlinkSync, writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

const editor=fileURLToPath(new URL('..',import.meta.url));
function isolatedSource(fn) {
  const root=mkdtempSync(join(tmpdir(),'save-typecheck-regression-'));
  try {
    for(const [from,to] of [
      [join(editor,'src'),'save-editor/src'],[join(editor,'scripts/build.mjs'),'save-editor/scripts/build.mjs'],
      [join(editor,'tsconfig.json'),'save-editor/tsconfig.json'],[join(editor,'package.json'),'save-editor/package.json'],
      [join(editor,'../save-core/src'),'save-core/src'],[join(editor,'../save-core/tsconfig.json'),'save-core/tsconfig.json'],
      [join(editor,'../save-core/package.json'),'save-core/package.json'],
    ]) cpSync(from,join(root,to),{recursive:true});
    symlinkSync(join(editor,'node_modules'),join(root,'save-editor/node_modules'),'dir');
    fn(root);
  } finally {rmSync(root,{recursive:true,force:true});}
}
function check(root) {
  const result=spawnSync(process.execPath,[join(root,'save-editor/scripts/build.mjs'),'--check'],{encoding:'utf8',timeout:30000});
  assert.equal(result.error,undefined);
  return result;
}
function snapshot(path) {
  if(!existsSync(path))return null;
  return Object.fromEntries(readdirSync(path,{recursive:true}).sort().map(name=>{
    const file=join(path,name),info=statSync(file,{bigint:true});
    return [name,{mtime:info.mtimeNs,bytes:info.isFile()?readFileSync(file):null}];
  }));
}
for(const built of [false,true])test(`typecheck checks current source with ${built?'poisoned':'absent'} dist and never changes emitted files`,()=>isolatedSource(root=>{
  if(built)for(const part of ['save-core','save-editor']) {
    const dist=join(root,part,'dist');mkdirSync(dist);
    writeFileSync(join(dist,'build-identity.json'),'preserve fingerprint byte-for-byte');
    writeFileSync(join(dist,'save.d.ts'),'this is deliberately invalid TypeScript');
    writeFileSync(join(dist,'save.js'),'throw Error("must never execute")');
  }
  const paths=['save-core','save-editor'].map(part=>join(root,part,'dist')),before=paths.map(snapshot);
  const result=check(root);assert.equal(result.status,0,result.stdout+result.stderr);
  assert.deepEqual(paths.map(snapshot),before);
}));

test('typecheck rejects editor API mismatch even when generated declarations claim it is valid',()=>isolatedSource(root=>{
  const dist=join(root,'save-core/dist');mkdirSync(dist);
  writeFileSync(join(dist,'save.d.ts'),'export declare function readSave(input: string): unknown;');
  writeFileSync(join(root,'save-editor/src/typecheck-regression.ts'),"import {readSave} from '../../save-core/dist/save.js';\nreadSave('not bytes');\n");
  const before=snapshot(dist),result=check(root);
  assert.notEqual(result.status,0);assert.match(result.stdout,/typecheck-regression.ts.*TS2345/);
  assert.deepEqual(snapshot(dist),before);
}));
