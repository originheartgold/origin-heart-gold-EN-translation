import {readFile, writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {loadOriginData, readNdsFile, readNarcMembers} from '../dist/core/rom.js';
const args=process.argv.slice(2), check=args.includes('--check'), romPath=args.find(a=>a!=='--check');
if(!romPath) throw new Error('Usage: node work/save-editor/scripts/generate-reference.mjs [--check] <English Origin v4.0.3 ROM>');
const rom=new Uint8Array(await readFile(romPath)), data=await loadOriginData(rom);
if(data.catalog.readiness.species!==1025 || data.catalog.readiness.moves<800 || data.catalog.readiness.items<700) throw new Error('A verified English Origin ROM is required.');
const sha=b=>createHash('sha256').update(b).digest('hex');
const personal=readNarcMembers(readNdsFile(rom,'a/0/0/2')).map(r=>[...r.slice(0,6),r[19]]);
const growth=readNarcMembers(readNdsFile(rom,'a/0/0/3')).map(r=>Array.from({length:101},(_,i)=>new DataView(r.buffer,r.byteOffset,r.byteLength).getUint32(i*4,true)));
const view=new DataView(rom.buffer,rom.byteOffset,rom.byteLength), offset=view.getUint32(0x20,true)+0xfedc0;
const forms=Array.from({length:415},(_,i)=>[view.getUint16(offset+i*6,true),view.getUint16(offset+i*6+2,true),rom[offset+i*6+4]]);
const payload={personal,growth,forms,moves:Array.from({length:921},(_,i)=>data.catalog.getMove(i)),species:data.catalog.species,items:data.inventory.items,readiness:data.catalog.readiness};
const nameBanks=readNarcMembers(readNdsFile(rom,'a/0/2/7'));
const sources=Object.fromEntries(['a/0/0/2','a/0/0/3','a/0/1/7','extra/new_move_data.narc'].map(path=>[path,sha(readNdsFile(rom,path))]));
for(const id of [219,232,739])sources[`a/0/2/7#${id}`]=sha(nameBanks[id]);
sources['arm9#forms']=sha(rom.subarray(offset,offset+415*6));
const record={schemaVersion:1,gameVersion:'origin-heartgold-english-v4.0.3',provenance:{romSha256:sha(rom),payloadSha256:sha(JSON.stringify(payload)),sources},payload};
const output='/** Generated minimal editor reference data. Regenerate with scripts/generate-reference.mjs; do not hand edit. */\nexport const bundledReference = '+JSON.stringify(record)+';\n';
const target=new URL('../src/core/generated-reference.ts',import.meta.url);
if(check){if(await readFile(target,'utf8')!==output)throw new Error('Bundled reference differs from the supplied English ROM.');console.log('Bundled reference matches every extracted field and provenance hash.');}
else {await writeFile(target,output);console.log('Generated '+Buffer.byteLength(output)+' bytes of editor reference metadata.');}
