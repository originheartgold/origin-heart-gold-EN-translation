// Run from the repository root: node work/save-editor/scripts/generate-editor-reference.mjs <local-rc5-rom>
import {existsSync,readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {readNdsFile,readNarcMembers} from '../dist/core/rom.js';
const romPath=process.argv[2];if(!romPath)throw new Error('Provide the local rc5 ROM; this script never downloads files.');
const embedded=new URL('../../../site/src/data/species.json',import.meta.url),standalone=new URL('../../origin-heart-gold-EN-translation/site/src/data/species.json',import.meta.url);
const speciesPath=process.argv[3]??(existsSync(embedded)?embedded:standalone);
const rom=new Uint8Array(readFileSync(romPath)),sp=JSON.parse(readFileSync(speciesPath));
import {bundledReference} from '../dist/core/generated-reference.js';
if(createHash('sha256').update(rom).digest('hex')!==bundledReference.provenance.romSha256)throw new Error('Use the verified English Origin rc5 ROM for this reference.');
const items=readNarcMembers(readNdsFile(rom,'a/0/1/7')).map((r,id)=>({id,price:r[0]|r[1]<<8,hold:r[2],holdParameter:r[3],flingPower:r[6],flingEffect:r[5],fieldUse:r[10],battleUse:r[11],partyUse:r[12]}));
const forms=Object.fromEntries(sp.filter(s=>s.id>1025).map(s=>[s.id,s.name])),list=x=>Array.isArray(x)?x:[];
const compat=Object.fromEntries(sp.map(s=>[s.id,{levelup:list(s.levelup),tms:list(s.tms).map(x=>x[1]),tutors:list(s.tutors),egg:list(s.egg),source:s.how??'No source recorded'}]));
const provenance={romSha256:createHash('sha256').update(rom).digest('hex'),guideSpeciesSha256:createHash('sha256').update(readFileSync(speciesPath)).digest('hex')};
const header='/** Generated from local rc5 item data and guide species data. See scripts/generate-editor-reference.mjs. */\nexport interface Compatibility {levelup:number[][]; tms:number[]; tutors:number[]; egg:number[]; source:string}\nexport const editorReference: {provenance:{romSha256:string;guideSpeciesSha256:string};forms:Record<number,string>;compat:Record<number,Compatibility>;items:{id:number;price:number;hold:number;holdParameter:number;flingPower:number;flingEffect:number;fieldUse:number;battleUse:number;partyUse:number}[]} = ';
writeFileSync(new URL('../src/core/editor-reference.ts',import.meta.url),header+'JSON.parse('+JSON.stringify(JSON.stringify({provenance,forms,compat,items}))+');\n');
