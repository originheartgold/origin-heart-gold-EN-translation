// Assemble an ignored integration fixture when this worktree lacks the guide site.
// Copy site code/config only; borrow existing generated content/assets read-only.
import {cp,mkdir,readdir,readFile,symlink,writeFile} from 'node:fs/promises';
import {resolve,join,sep} from 'node:path';
import {createHash} from 'node:crypto';
const [canonicalRepo,output]=process.argv.slice(2);
if(!canonicalRepo||!output)throw Error('Usage: node work/save-editor/scripts/prepare-site-preview.mjs CANONICAL_REPO NEW_IGNORED_OUTPUT');
const source=resolve(canonicalRepo),out=resolve(output),local=resolve('work/save-editor/local');
if(!out.startsWith(local+sep))throw Error('Output must be a new directory under ignored work/save-editor/local/');
await readFile(join(source,'site/package.json'));
await mkdir(out,{recursive:false});const site=join(out,'site');await mkdir(site);
for(const name of ['package.json','package-lock.json','site.config.mjs','astro.config.mjs'])await cp(join(source,'site',name),join(site,name));
await mkdir(join(site,'src'),{recursive:true});
for(const name of ['components','lib','pages','styles'])await cp(join(source,'site/src',name),join(site,'src',name),{recursive:true});
await cp(join(source,'site/src/content.config.ts'),join(site,'src/content.config.ts'));
await symlink(join(source,'site/src/data'),join(site,'src/data'),'dir');
await mkdir(join(site,'src/content/docs'),{recursive:true});
for(const entry of await readdir(join(source,'site/src/content/docs'),{withFileTypes:true})){
 const from=join(source,'site/src/content/docs',entry.name),to=join(site,'src/content/docs',entry.name);
 if(entry.isDirectory())await symlink(from,to,'dir');else await cp(from,to);
}
await mkdir(join(site,'public'));
await cp(join(source,'site/public/ohg.js'),join(site,'public/ohg.js'));
await cp(join(source,'site/public/patch-tool'),join(site,'public/patch-tool'),{recursive:true});
await symlink(join(source,'site/public/vendor'),join(site,'public/vendor'),'dir');
for(const target of [join(site,'node_modules'),join(out,'node_modules')])await symlink(join(source,'site/node_modules'),target,'dir');
await mkdir(join(out,'work'));await symlink(resolve('work/save-editor'),join(out,'work/save-editor'),'dir');
await symlink(resolve('work/save-core'),join(out,'work/save-core'),'dir');
// Only changed/new site overlay files exist in this worktree.
await cp(resolve('site'),site,{recursive:true});
const hashes=[];
for(const name of ['site/astro.config.mjs','site/src/content/docs/index.mdx','.github/workflows/site.yml'])hashes.push({file:name,original_sha256:createHash('sha256').update(await readFile(join(source,name))).digest('hex')});
await writeFile(join(out,'provenance.json'),JSON.stringify(hashes,null,2)+'\n');
console.log(site);
