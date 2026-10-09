import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
// A small DOM fixture runs the production enhancement, without adding a browser
// dependency to CI. Real keyboard activation/layout are covered by browser-smoke.mjs.
class Element {
  constructor(text = '', dataset = {}) { this.textContent = text; this.dataset = dataset; this.childNodes = [text]; this.listeners = {}; this.attrs = {}; this.hidden = false; this.children = []; }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  fire(name, target = this) { for (const fn of this.listeners[name] ?? []) fn({target}); }
  setAttribute(k,v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  append(...children) { this.children.push(...children); }
  after(child) { this.afterElement = child; }
}
function fixture({query = '', multiple = false, names = ['Alpha', 'Beta', 'Gamma']} = {}) {
  const historyEntries = [`https://example.test/poke/pokemon/${query}`]; let cursor = 0;
  const location = {}; const setLocation = url => { const u = new URL(url); Object.assign(location,{href:u.href,search:u.search,hash:u.hash,pathname:u.pathname}); }; setLocation(historyEntries[0]);
  const make = id => {
    const input = new Element(); input.value = '';
    const type = new Element('',{key:'type'}); type.value = ''; type.options = ['', 'Water','Grass'].map(value => ({value}));
    const ability = new Element('',{key:'ability'}); ability.value = ''; ability.options = ['', '2','3'].map(value => ({value}));
    const check = new Element('',{key:'availability',showValue:'unavailable'}); check.checked = true;
    const count = new Element();
    const filter = new Element('',{table:id}); filter.querySelector = s => s.includes('search') ? input : s === '.filter-count' ? count : null;
    filter.querySelectorAll = s => s.startsWith('select') ? [type,ability] : [check];
    const rows = [[names[0],100,'Water|Grass','2|3','documented'],[names[1],20,'Water','2','unavailable'],[names[2],20,'Grass','3','documented']].map(([name,number,t,a,av]) => {
      const row = new Element(`${name} ${number}`,{type:t,ability:a,availability:av}); row.cells = [new Element(name),new Element(String(number))]; return row;
    });
    const ths = [new Element('Name'),new Element('Power',{sortType:'number'})];
    const body = new Element(); body.rows = [...rows]; body.append = (...next) => {body.rows = next;};
    const target = new Element(); target.id=id; target.tBodies=[body]; target.querySelectorAll = s => s === 'thead th' ? ths : [...rows, new Element('Nested party row')];
    return {input,type,ability,check,count,filter,rows,ths,body,target};
  };
  const lists = [make('one'), ...(multiple ? [make('two')] : [])];
  const doc = {readyState:'complete',documentElement:{dataset:{}},querySelector:()=>null,createElement:()=>new Element(),getElementById:id=>lists.find(l=>l.target.id===id)?.target,querySelectorAll:s=>s==='section.quest'?[]:s==='.table-filter'?lists.map(l=>l.filter):s==='table.sortable'?lists.map(l=>l.target):[]};
  const window = new Element();
  const history = {pushState(_,__,url){historyEntries.splice(++cursor);historyEntries.push(String(url));setLocation(url);},replaceState(_,__,url){historyEntries[cursor]=String(url);setLocation(url);}};
  const context = {document:doc,window,history,location,URL,URLSearchParams,localStorage:{getItem:()=>null,setItem(){}}};
  vm.runInNewContext(readFileSync(new URL('../public/ohg.js',import.meta.url),'utf8'),context);
  return {...lists[0],lists,location,historyEntries,back(){setLocation(historyEntries[--cursor]);window.fire('popstate');},forward(){setLocation(historyEntries[++cursor]);window.fire('popstate');},reset(){lists[0].filter.children.find(c=>c.className==='filter-reset').fire('click');}};
}
const visible = f => f.body.rows.filter(r=>!r.hidden).map(r=>r.cells[0].textContent);
const select = (f,c,value) => {c.value=value;f.filter.fire('change',c);};
test('plain keyboard spellings match accented names and either apostrophe style in shared URLs',()=>{
 const names=['Poké Ball','King’s Rock',"Farfetch'd"];
 for(const [query,expected] of [['poke ball','Poké Ball'],["king's rock",'King’s Rock'],['kings rock','King’s Rock'],['farfetchd',"Farfetch'd"]]) {
  const f=fixture({names,query:`?q=${encodeURIComponent(query)}`});assert.deepEqual(visible(f),[expected]);
  f.reset();assert.equal(visible(f).length,3);
 }
});
test('combined multivalue filters and search are AND; URL survives a fresh initialization',()=>{
 const f=fixture({query:'?tech=1#legacy'}); select(f,f.type,'Water');select(f,f.ability,'3');f.input.value='alpha';f.input.fire('input');
 assert.deepEqual(visible(f),['Alpha']); assert.equal(new URL(f.location.href).searchParams.get('ability'),'3');assert.equal(f.location.hash,'#legacy');
 const fresh=fixture({query:f.location.search+f.location.hash});assert.deepEqual(visible(fresh),['Alpha']);assert.equal(fresh.type.value,'Water');assert.equal(fresh.input.value,'alpha');
});
test('invalid select/sort parameters are harmless and Reset clears owned state only',()=>{
 const f=fixture({query:'?type=Unknown&sort=99-desc&availability=banana&tech=1&other=keep#x'});assert.deepEqual(visible(f),['Alpha','Beta','Gamma']);assert.equal(f.type.value,'');assert.equal(f.check.checked,true);
 f.input.value='no such result';f.input.fire('input');assert.equal(f.target.afterElement.hidden,false);assert.match(f.count.textContent,/0 of 3/);assert.equal(f.count.attrs.role,'status');
 f.reset();assert.deepEqual(visible(f),['Alpha','Beta','Gamma']);assert.equal(f.target.afterElement.hidden,true);assert.equal(f.location.search,'?tech=1&other=keep');assert.equal(f.location.hash,'#x');
});
test('numeric sort is stable, exposes real buttons and aria-sort; Reset restores original order',()=>{
 const f=fixture();const button=f.ths[1].children[0];assert.equal(button.type,'button');button.fire('click');assert.deepEqual(visible(f),['Beta','Gamma','Alpha']);assert.equal(f.ths[1].attrs['aria-sort'],'ascending');
 button.fire('click');assert.deepEqual(visible(f),['Alpha','Beta','Gamma']);assert.equal(f.ths[1].attrs['aria-sort'],'descending');assert.equal(new URL(f.location.href).searchParams.get('sort'),'1-desc');
 f.reset();assert.deepEqual(visible(f),['Alpha','Beta','Gamma']);assert.equal(f.ths[1].attrs['aria-sort'],'none');
});
test('typing creates one history state; Back and Forward restore rows, controls and sort',()=>{
 const f=fixture();for(const q of ['a','al','alpha']){f.input.value=q;f.input.fire('input');}assert.equal(f.historyEntries.length,2);
 select(f,f.type,'Water');f.ths[1].children[0].fire('click');f.back();assert.equal(f.ths[1].attrs['aria-sort'],'none');f.back();assert.equal(f.type.value,'');assert.equal(f.input.value,'alpha');f.back();assert.equal(f.input.value,'');assert.equal(visible(f).length,3);
 f.forward();assert.equal(f.input.value,'alpha');assert.deepEqual(visible(f),['Alpha']);
});
test('checkbox exclusion and multiple table namespaces stay independent',()=>{
 const f=fixture({multiple:true,query:'?one.type=Water&two.ability=3&tech=1'});assert.deepEqual(visible(f),['Alpha','Beta']);assert.deepEqual(visible(f.lists[1]),['Alpha','Gamma']);
 f.check.checked=false;f.filter.fire('change',f.check);assert.deepEqual(visible(f),['Alpha']);assert.match(f.location.search,/one.availability=0/);f.reset();assert.match(f.location.search,/two.ability=3/);assert.equal(f.lists[1].ability.value,'3');
});

test('table filtering owns only direct body rows and never reparents nested party rows',()=>{ const f=fixture();assert.equal(f.count.textContent,'3 of 3 shown');f.ths[1].children[0].fire('click');assert.equal(f.body.rows.length,3); });

test('leading whitespace does not replace the original history entry before meaningful typing',()=>{ const f=fixture();f.input.value=' ';f.input.fire('input');assert.equal(f.historyEntries.length,1);f.input.value=' alpha';f.input.fire('input');assert.equal(f.historyEntries.length,2);f.back();assert.equal(f.input.value,'');assert.equal(visible(f).length,3); });
