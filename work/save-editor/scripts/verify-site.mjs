// Static native Starlight integration checks; no browser or save files are read.
import assert from 'node:assert/strict';
import {readFile,readdir,stat} from 'node:fs/promises';
import {resolve,sep} from 'node:path';
const [directory,rawBase='/']=process.argv.slice(2);
if(!directory)throw Error('Usage: node work/save-editor/scripts/verify-site.mjs SITE_DIST [BASE]');
const root=resolve(directory),base=rawBase.replace(/\/*$/,'/'),pageUrl=`${base}save-editor/`;
assert.ok(base.startsWith('/')&&!base.startsWith('//'));
const page=await readFile(resolve(root,'save-editor/index.html'),'utf8'),home=await readFile(resolve(root,'index.html'),'utf8');
assert.ok(home.includes('Save editor')&&[...home.matchAll(/href="([^"]+)"/g)].some(m=>new URL(m[1],`https://verification.invalid${base}`).pathname===pageUrl));
assert.ok(page.includes(`href="${pageUrl}"`),'Sidebar must expose editor route');
assert.doesNotMatch(page,/<iframe|save-editor\/app\/|fine-tuning|Open the editor on its own/);
assert.equal((page.match(/<main\b/g)??[]).length,1,'Starlight owns the only main landmark');
assert.equal((page.match(/<h1\b/g)??[]).length,1,'Starlight owns the only page heading');
assert.match(page,/<h1[^>]*>Save editor<\/h1>/);
assert.match(page,/class="save-editor not-content"/);
assert.match(page,/Content-Security-Policy[^>]*connect-src 'self'/);
assert.doesNotMatch(page,/connect-src 'none'|script-src 'self'|style-src 'self'/,'Do not block native search or required shell scripts/styles');
assert.match(page,/form-action 'none'/);
assert.equal((page.match(/type="file"/g)??[]).length,1);assert.match(page,/accept="\.sav,\.dsv"/);
for(const id of ['file-input','status','save-details','party-list','editor','inventory-editor','export-original','export-edited'])assert.equal((page.match(new RegExp(`id="${id}"`,'g'))??[]).length,1,`Unique editor control: ${id}`);
await assert.rejects(stat(resolve(root,'save-editor/app/index.html')),error=>error.code==='ENOENT');
const assets=[];
async function asset(reference,from=pageUrl){
 const url=new URL(reference,`https://verification.invalid${from}`);assert.equal(url.origin,'https://verification.invalid');
 assert.ok(url.pathname.startsWith(base),`Asset escapes Pages base: ${reference}`);
 const path=resolve(root,decodeURIComponent(url.pathname.slice(base.length)));assert.ok(path.startsWith(root+sep));assert.ok((await stat(path)).isFile());
 assets.push(url.pathname);return readFile(path,'utf8');
}
let editorBundles=0;
const externalShellScripts=[];
for(const match of page.matchAll(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>/g)){
 const scriptUrl=new URL(match[1],`https://verification.invalid${pageUrl}`);
 if(scriptUrl.origin!=='https://verification.invalid'){
  // The guide shell already includes GoatCounter. It is not an editor dependency
  // and this static verifier never fetches it; all editor module imports stay local.
  assert.equal(scriptUrl.href,'https://gc.zgo.at/count.js');
  assert.match(match[0],/data-goatcounter="https:\/\/originheartgold\.goatcounter\.com\/count"/);
  externalShellScripts.push(scriptUrl.href);continue;
 }
 const code=await asset(match[1]);
 if(code.includes('Download requested. Your original file was not changed.')){
  editorBundles++;assert.match(code,/origin-heartgold-english-v4\.0\.3/);
  assert.doesNotMatch(code,/Truncated or invalid ROM data|Unsupported ROM: expected Origin|Invalid ROM directory|readNdsFile/);
 }
 for(const dependency of code.matchAll(/\b(?:from\s*|import\s*(?:\(\s*)?)["'`]([^"'`]+)["'`]/g))await asset(dependency[1],new URL(match[1],`https://verification.invalid${pageUrl}`).pathname);
}
assert.equal(editorBundles,1,'Exactly one canonical editor entry bundle');
const css=[];
for(const tag of page.matchAll(/<link\b[^>]*>/g))if(/rel="stylesheet"/.test(tag[0]))css.push(await asset(tag[0].match(/href="([^"]+)"/)[1]));
for(const tag of page.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/g))css.push(tag[1]);
const styles=css.join('\n');assert.match(styles,/\.save-editor/);assert.match(styles,/var\(--sl-color/);assert.doesNotMatch(styles,/#f4f3eb|#21392f|#fffef9/,'Standalone theme must not ship on native page');
for(const selector of ['.party-list','.move-row','.inventory-row','.stat-preview','.iv-ev-columns'])assert.ok(styles.includes(selector));
let count=0;
async function walk(dir,relative=''){for(const entry of await readdir(dir,{withFileTypes:true})){const rel=relative+entry.name;if(entry.isDirectory()){assert.notEqual(entry.name,'local');await walk(resolve(dir,entry.name),rel+'/');}else{count++;assert.doesNotMatch(rel,/\.(nds|srl|sav|dsv)$/i);assert.doesNotMatch(rel,/(^|\/)rom\.js$/);}}}
await walk(root);
console.log(JSON.stringify({status:'passed',base,pageUrl,layout:'native Starlight; one main and h1; no iframe or duplicate app route',assets,externalShellScripts,outputFiles:count,theme:'scoped Starlight tokens; no standalone palette',csp:'same-origin connections for guide search; no form submission',privateGameInputs:'none'},null,2));
