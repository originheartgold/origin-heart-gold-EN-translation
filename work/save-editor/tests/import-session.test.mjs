import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {SaveImportRequest} from '../dist/core/save-import.js';
import {readSave} from '../dist/core/save.js';
import {syntheticSave} from './fixture.mjs';

// Exercise the actual compiled open handler, with its surrounding UI supplied as
// a small adapter. Real browser appearance is checked separately by the site gate.
const code=readFileSync(new URL('../dist/ui/app.js',import.meta.url),'utf8');
const start=code.indexOf('async function open(file)');
const end=code.indexOf("fileInput.addEventListener('change'",start);
assert.ok(start>=0&&end>start,'actual editor import handler must be tested');
class Element {
 constructor(){this.childNodes=[{value:'pending draft'}];this.attrs=new Map([['class','old'],['hidden','']]);}
 get attributes(){return [...this.attrs].map(([name,value])=>({name,value}));}
 querySelectorAll(){return [];}
 replaceChildren(...children){this.childNodes=children;}
 removeAttribute(name){this.attrs.delete(name);}
 setAttribute(name,value){this.attrs.set(name,value);}
}
function setup(){
 const bytes=syntheticSave(),old={original:bytes,working:bytes.slice(),filename:'original.sav',history:[bytes.slice()]};
 const elements=Object.fromEntries(['app','fileMeta','exportButton','undoButton','dockUndo','dockExport','viewSwitch','dock'].map(name=>[name,new Element()]));
 const originalNode=elements.app.childNodes[0],messages=[];
 const context=vm.createContext({...elements,SaveImportRequest,readSave,initial:old,messages,failRender:false,
   toast:(message,error)=>messages.push({message,error}),errorText:error=>String(error),});
 vm.runInContext(`let session=initial,selected=2,pcBox=3,pcSlot=4; const saveImport=new SaveImportRequest();
 function render(){ app.replaceChildren({value:'new session'});fileMeta.setAttribute('class','new'); if(failRender)throw Error('render failed'); }
 ${code.slice(start,end)}
 globalThis.api={open,state:()=>({session,selected,pcBox,pcSlot}),invalidate:()=>saveImport.invalidate()};`,context);
 return {context,elements,old,originalNode,messages,api:context.api};
}
const file=(name,bytes=syntheticSave())=>({name,size:bytes.length,arrayBuffer:async()=>bytes.buffer.slice(0)});
function assertPreserved(ui){assert.equal(ui.api.state().session,ui.old);assert.equal(ui.old.history.length,1);assert.equal(ui.elements.app.childNodes[0],ui.originalNode);assert.equal(ui.originalNode.value,'pending draft');}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}

test('actual open preserves prior session for invalid or unreadable replacement',async()=>{
 for(const replacement of [file('size.sav',new Uint8Array(10)),file('crc.sav',new Uint8Array(524288)),{name:'unreadable',size:524288,arrayBuffer:async()=>{throw Error('read failed');}}]){
  const ui=setup();await ui.api.open(replacement);assertPreserved(ui);assert.equal(ui.messages.at(-1).error,true);
 }
});
test('actual open rolls back session, selections, DOM drafts and chrome on render failure',async()=>{
 const ui=setup();ui.context.failRender=true;await ui.api.open(file('replacement.sav'));
 assertPreserved(ui);assert.equal(ui.api.state().selected,2);assert.equal(ui.api.state().pcBox,3);assert.equal(ui.api.state().pcSlot,4);
 assert.equal(ui.elements.fileMeta.attrs.get('class'),'old');assert.match(ui.messages.at(-1).message,/render failed/);
 ui.context.failRender=false;await ui.api.open(file('recovered.sav'));assert.equal(ui.api.state().session.filename,'recovered.sav');assert.equal(ui.api.state().session.history.length,0);
});
test('actual open latest selection wins over older success and stale failure',async()=>{
 for(const rejects of [false,true]){
  const ui=setup(),slow=deferred();const pending=ui.api.open({name:'slow.sav',size:524288,arrayBuffer:()=>slow.promise});
  await ui.api.open(file('latest.sav'));const count=ui.messages.length;
  if(rejects)slow.reject(Error('stale failure'));else slow.resolve(syntheticSave().buffer);
  await pending;assert.equal(ui.api.state().session.filename,'latest.sav');assert.equal(ui.messages.length,count);
 }
});
test('edits made during a pending actual open invalidate its result',async()=>{
 const ui=setup(),slow=deferred();const pending=ui.api.open({name:'slow.sav',size:524288,arrayBuffer:()=>slow.promise});
 ui.api.invalidate();slow.resolve(syntheticSave().buffer);await pending;assertPreserved(ui);
});
