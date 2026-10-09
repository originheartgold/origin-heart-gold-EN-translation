// Run from the repository root after the /poke/ production build + local preview:
// PLAYWRIGHT_MODULE=/absolute/existing/playwright/index.mjs node site/tests/browser-smoke.mjs
// Optional GUIDE_PREVIEW_URL (default http://127.0.0.1:4327/poke/).
// Uses synthetic saves and image failure injection; never creates or patches a ROM.
import assert from 'node:assert/strict';
import {readFileSync, mkdirSync, writeFileSync} from 'node:fs';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4327/poke/';
const output = 'work/build/website-qa';mkdirSync(output,{recursive:true});
const load = name => JSON.parse(readFileSync(`site/src/data/${name}.json`,'utf8'));
const tms=load('tms');
const species=load('species'), abilities=load('abilities'), moves=load('moves'), items=load('items');
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
// Block analytics; media is viewed normally in the browser, never saved as source assets.
await context.route(/gc\.zgo\.at|goatcounter/,r=>r.abort());
const page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
let assertions=0;const check=(actual,expected,message='browser assertion')=>{assert.deepEqual(actual,expected,message);assertions++;};
const goto=async path=>{const r=await page.goto(new URL(path,base).href,{waitUntil:'domcontentloaded'});if(r) assert.equal(r.status(),200,path);await page.waitForFunction(()=>document.readyState!=='loading');};
const shown=async(table)=>page.locator(`#${table} tbody > tr:not([hidden])`).count();
try {
 await goto('pokemon/?tech=1#mon-table');check(await shown('mon-table'),1440);
 const form=species.find(s=>s.formId!==0);check(await page.locator('#mon-table tbody > tr').count(),species.length);
 const bulba=species.find(s=>s.id===1);await page.selectOption('[data-key=type]','Grass');await page.selectOption('[data-key=ability]',String(bulba.hiddenAbilityId));
 const expected=species.filter(s=>s.types.includes('Grass')&&[...s.abilityIds,s.hiddenAbilityId].includes(bulba.hiddenAbilityId)).length;
 check(await shown('mon-table'),expected,'hidden abilities and secondary type membership');
 await page.selectOption('[data-key=region]',bulba.region);
 check(await shown('mon-table'),species.filter(s=>s.types.includes('Grass')&&[...s.abilityIds,s.hiddenAbilityId].includes(bulba.hiddenAbilityId)&&s.region===bulba.region).length);
 const shared=page.url();await page.reload();check(await page.locator('[data-key=ability]').inputValue(),String(bulba.hiddenAbilityId));check(page.url(),shared);
 const header=page.locator('#mon-table th').nth(5);await header.locator('button').focus();await page.keyboard.press('Enter');check(await header.getAttribute('aria-sort'),'ascending');await page.keyboard.press('Space');check(await header.getAttribute('aria-sort'),'descending');
 await page.locator('.filter-reset').click();check(await shown('mon-table'),1440);check(await page.locator('#mon-table tbody tr').first().locator('td').first().textContent(),'1');check(new URL(page.url()).search,'?tech=1');check(new URL(page.url()).hash,'#mon-table');
 await goto('pokemon/?type=bogus&ability=999999&sort=999-desc');check(await shown('mon-table'),1440);
 const before=await page.evaluate(()=>history.length);await page.locator('input[type=search]').pressSequentially('not-a-pokemon');check(await page.evaluate(()=>history.length),before+1);check(await shown('mon-table'),0);check(await page.locator('.filter-empty').isVisible(),true);
 await page.goBack();check(await shown('mon-table'),1440);await page.goForward();check(await shown('mon-table'),0);await page.locator('.filter-reset').click();check(await shown('mon-table'),1440);
 await goto('moves/?type=Water&category=Special&method=tm&changed=yes');check(await shown('move-table')>0,true);
 check(await page.locator('#move-table tr#move-503').isVisible(),true,'Scald retained among combined filters');
 await page.locator('.filter-reset').click();check(await shown('move-table'),920);await page.locator('#move-table th').nth(6).locator('button').click();
 const priorities=await page.locator('#move-table tbody > tr td:nth-child(7)').allTextContents();check(priorities.map(Number),priorities.map(Number).toSorted((a,b)=>a-b),'signed numeric priority sorting');
 await goto('abilities/?changed=yes&holder=hidden');check(await shown('ability-table')>0,true);check(await page.locator('#ability-table tbody tr:not([hidden])').filter({hasText:'Sharpness'}).count(),1);
 await goto('tms/');const multi=await page.locator('#tm-table tr[data-location*="|"]').first().getAttribute('data-location');if(multi){await page.selectOption('[data-key=location]',multi.split('|').at(-1));check(await shown('tm-table')>0,true);await page.selectOption('[data-key=availability]','documented');check(await shown('tm-table')>0,true);}await page.locator('.filter-reset').click();check(await shown('tm-table'),138);
 const paths=['pokemon/','moves/','abilities/','tms/','trainers/records/105/','pokemon/bulbasaur/',`pokemon/${form.slug}/`,'pokemon/mew/','abilities/sharpness/','abilities/mega-launcher/',`abilities/${abilities.find(a=>a.id===327).slug}/`,'moves/water-gun/','moves/luster-purge/',`items/${items.find(i=>i.id===tms.find(t=>t.label==='TM93').itemId).slug}/`,`items/${items.find(i=>i.id===tms.find(t=>t.label==='TM46').itemId).slug}/`,'reference-sources/',`items/${items.find(i=>i.name==='Qualot Berry').slug}/`,`items/${items.find(i=>i.name==='Tamato Berry').slug}/`,'guide/known-issues/','items/','locations/','locations/pallet-town/','tutors/','trainers/','about/','patch/'];
 const layouts=[];
 for(const path of paths){ console.log('Checking',path);
  await goto(path);check(await page.locator('h1').count(),1,path);check(await page.locator('.sl-markdown-content').innerText().then(t=>!t.includes('{SCROLL}')&&!t.includes('{CLEAR}')),true,`no control tags ${path}`);
  if(path===`items/${items.find(i=>i.name==='Qualot Berry').slug}/`||path===`items/${items.find(i=>i.name==='Tamato Berry').slug}/`) {check(await page.locator('.sl-markdown-content').innerText().then(t=>t.includes('Scratch-Off')&&t.includes('Saffron')),true,path);}
  if(path.startsWith('pokemon/')){const s=species.find(s=>path===`pokemon/${s.slug}/`);const img=page.locator('.pokemon-image-large img');if(await img.count()){await img.scrollIntoViewIfNeeded();await img.evaluate(img=>img.decode()).catch(()=>{});check(await img.evaluate(img=>img.naturalWidth>0),true,'hero image renders');check(await img.getAttribute('width'),'256');check(await img.getAttribute('src').then(src=>src.endsWith(`/${s.baseSpeciesId}.png`)),true);}}
  for(const theme of ['light','dark']){
   await page.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);await page.setViewportSize({width:390,height:844});
   const layout=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth,controls:[...document.querySelectorAll('.table-filter input,.table-filter select,.table-filter button')].map(e=>({left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right})),tables:[...document.querySelectorAll('table.compact')].map(e=>({width:e.clientWidth,scroll:e.scrollWidth}))}));
   assert.ok(layout.scroll<=layout.width+1,`page overflow ${path} ${theme}: ${JSON.stringify(layout)}`);assert.ok(layout.controls.every(c=>c.left>=0&&c.right<=391),`clipped controls ${path}`);assertions+=2;layouts.push({path,theme,...layout});
  }await page.setViewportSize({width:1440,height:1000});
 }
 await goto('abilities/sharpness/');await page.locator('.reference-provenance').first().evaluate(e=>e.open=true).catch(()=>{});await page.screenshot({path:`${output}/sharpness-desktop.png`,fullPage:false});
 await goto('pokemon/?type=Grass&ability=65');await page.setViewportSize({width:390,height:844});await page.evaluate(()=>document.documentElement.dataset.theme='light');await page.screenshot({path:`${output}/pokemon-mobile-light.png`,fullPage:false});
 await goto('moves/water-gun/');await page.evaluate(()=>document.documentElement.dataset.theme='dark');await page.screenshot({path:`${output}/water-gun-mobile-dark.png`,fullPage:false});
 console.log('Checking artwork fallback and no-JS');
 // Artwork errors are exercised with both URLs blocked; fallback must replace the broken image.
 const fail=await browser.newContext();await fail.route(/\.png(?:\?|$)/,r=>r.abort());const fp=await fail.newPage();await fp.goto(new URL('pokemon/bulbasaur/',base).href,{waitUntil:'domcontentloaded'});await fp.locator('.pokemon-image-large').scrollIntoViewIfNeeded();await fp.waitForSelector('.pokemon-image-large .art-placeholder');check(await fp.locator('.pokemon-image-large img').count(),0);check(await fp.locator('.pokemon-image-large .art-placeholder').getAttribute('aria-label').then(s=>s.includes('image unavailable')),true);await fail.close();
 // JavaScript-disabled content is complete, including hidden-holder and form lists.
 const nojs=await browser.newContext({javaScriptEnabled:false});await nojs.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());const np=await nojs.newPage();for(const [path,id,n]of[['pokemon/?type=Water','mon-table',1440],['moves/','move-table',920],['abilities/','ability-table',327],['tms/','tm-table',138]]){await np.goto(new URL(path,base).href,{waitUntil:'domcontentloaded'});check(await np.locator(`#${id} tbody > tr`).count(),n);check(await np.locator(`#${id} tbody > tr[hidden]`).count(),0);}await np.goto(new URL('abilities/sharpness/',base).href,{waitUntil:'domcontentloaded'});check(await np.locator('#holders-hidden tbody tr').count()>0,true);await nojs.close();
 await goto('moves/#move-55');check(await page.locator('#move-55').count(),1);await goto('moves/#tm-list');check(await page.locator('#tm-list').count(),1);
 console.log('Checking camera / patch / save / quest controls');
 await goto('camera-codes/');await page.locator('.camb-form').waitFor({state:'visible'});const old=await page.locator('.camb-code').textContent();await page.selectOption('.camb select','2');check(await page.locator('.camb-code').textContent()!==old,true);await page.locator('.camb input[name=flat]').check();const flat=await page.locator('.camb-code').textContent();await page.locator('.camb-reset').click();check(await page.locator('.camb-code').textContent()!==flat,true);await page.locator('.camb-copy').click();
 await context.route('**/patch/latest.json',r=>r.fulfill({json:{available:true,tag:'v0.0.0-rc1',file:'fixture.xdelta',size:1,patched_sha1:'0'.repeat(40),release_url:'https://example.test/release'}}));
 await goto('patch/');check(await page.locator('.sl-markdown-content').innerText().then(t=>t.includes('USA')),true);await page.locator('#patcher-rom').waitFor({state:'visible'});if(await page.locator('#patcher-rom').isVisible()&&await page.locator('#patcher-rom').isEnabled()){await page.locator('#patcher-rom').setInputFiles({name:'synthetic-invalid.nds',mimeType:'application/octet-stream',buffer:Buffer.from('synthetic invalid fixture')});await page.getByText("This isn't the right game file.",{exact:true}).waitFor();check(await page.getByText("This isn't the right game file.",{exact:true}).isVisible(),true,'patcher rejects synthetic invalid input');}
 await goto('save-editor/');check(await page.locator('#export').isDisabled(),true);check(await page.locator('#file-input').getAttribute('accept').then(s=>s.includes('.sav')&&s.includes('.dsv')),true);await page.locator('#theme-toggle').click();await page.locator('#file-input').setInputFiles({name:'invalid.sav',mimeType:'application/octet-stream',buffer:Buffer.from('invalid synthetic save')});await page.waitForTimeout(250);check(await page.locator('#export').isDisabled(),true);check(await page.locator('#toast').innerText().then(t=>t.length>0),true);
 // Existing quest state and technical toggle survive filter integration.
 await goto('guide/pallet-to-pewter/?tech=1');check(await page.locator('.game-setup').count(),1);await page.selectOption('.game-setup [name=starter]','Pikachu');await page.locator('.quest-tools input').first().check();await page.reload();check(await page.locator('.game-setup [name=starter]').inputValue(),'Pikachu');check(await page.locator('.quest-tools input').first().isChecked(),true);check(await page.evaluate(()=>document.documentElement.dataset.tech),'on');
 check(errors,[],'no uncaught browser errors');
 writeFileSync(`${output}/browser-results.json`,JSON.stringify({assertions,base,layouts,errors},null,2));console.log(`Browser smoke: ${assertions} assertions passed; ${layouts.length} mobile theme/page checks; ${base}`);
}finally{await browser.close();}
