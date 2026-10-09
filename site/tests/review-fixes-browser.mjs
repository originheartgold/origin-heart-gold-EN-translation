// Factual regressions remain checked after moving all technical evidence to the central source page.
import assert from 'node:assert/strict';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base=process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4327/poke/';
const read=n=>JSON.parse(readFileSync(`site/src/data/${n}.json`,'utf8'));
const moves=read('moves'),tutors=read('tutors'),species=read('species');
const browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:390,height:844}});
await context.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
const page=await context.newPage(),errors=[],layouts=[];page.on('pageerror',e=>errors.push(e.message));let assertions=0;const ok=(v,msg)=>{assert.ok(v,msg);assertions++;};
const go=async path=>{const r=await page.goto(base+path,{waitUntil:'domcontentloaded'});ok(r.status()===200,path);const size=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));ok(size.scroll<=size.width+1,path+' containment');layouts.push({path,...size});return page.locator('main').innerText();};
try{
 for(const [slug,value] of [['struggle',-25],['clangorous-soul',-33],['chloroblast',-50]]){
  const m=moves.find(m=>m.slug===slug);ok(m.effects.heal===value,slug+' signed HP preserved');const text=await go(`moves/${slug}/`);ok(!text.includes('HP loss/cost field')&&!text.includes('Configured healing'),slug+' no fake player effect');
  await go('reference-sources/');const row=page.locator(`#move-source-${m.id}`);await row.locator('summary').click();ok((await row.innerText()).includes(`HP loss/cost field: ${value}`),slug+' full signed source');
 }
 for(const slug of ['swords-dance','growl','growth','lunar-dance']){const text=await go(`moves/${slug}/`);ok(text.includes('stage'),slug+' stat changes');ok(!text.includes('0% chance'),slug+' zero sentinel not literal probability');}
 for(const path of ['pokemon/kommo-o/','pokemon/hisuian-electrode/','pokemon/bulbasaur/','items/tm75-swords-dance/']){const text=await go(path);ok(!/, 0% chance|Configured healing: (231|223|206)%/.test(text),path+' learning summary integrity');}
 for(const t of tutors.filter(t=>t.species==='restricted')){const m=moves.find(m=>m.id===t.move),text=await go(`moves/${m.slug}/`);ok(await page.locator('.tutor-details').count()>0,m.name+' tutor source');ok(text.includes('full compatible list is not known'),m.name+' list limit');if(t.cost?.length===0)ok(text.includes('Cost: Free'),m.name+' free cost');if(m.id===268)ok(text.includes('₽10000'),m.name+' correct cost');}
 await go('moves/?method=tutor');await page.waitForFunction(()=>document.querySelector('.filter-reset'));for(const t of tutors.filter(t=>t.species==='restricted'))ok(await page.locator(`#move-${t.move}`).isVisible(),'restricted tutor filter '+t.move);
 for(const slug of ['salac-berry','petaya-berry','qualot-berry','tamato-berry']){const text=await go(`items/${slug}/`);ok(!text.includes('No confirmed way to get it'),slug+' available route');ok(text.includes(slug==='salac-berry'||slug==='petaya-berry'?'steal it with Thief or Covet':'Scratch-Off'),slug+' actual route');}
 await go('reference-sources/');
 for(const slug of ['volt-tackle','blast-burn','lunar-dance','bounce']){const m=moves.find(m=>m.slug===slug),row=page.locator(`#move-source-${m.id}`);await row.locator('summary').click();const text=await row.innerText();ok(text.includes(m.testedNotes[0].text)&&text.includes(m.testedNotes[0].limitation),slug+' full test retained');await row.locator('summary').click();}
 for(const slug of ['frenzy-plant','hydro-cannon','rock-wrecker']){const m=moves.find(m=>m.slug===slug),row=page.locator(`#move-source-${m.id}`);await row.locator('summary').click();ok((await row.innerText()).includes('battle behavior needs an in-game test'),slug+' unresolved source retained');await row.locator('summary').click();}
 const ursaring=await go('pokemon/ursaring/');ok(ursaring.includes('holding Moon Stone')&&ursaring.includes('at night')&&!ursaring.includes('Use a Moon Stone at Night'),'Ursaring correct operation');
 const note=species.find(s=>s.id===217).referenceNotes.find(n=>n.comparison?.evolution);ok(note.comparison.evolution.equal===false,'source operation conflict preserved');
 const about=await go('about/');ok(about.includes('7,673 included and 401 unresolved'),'counts retained');ok(errors.length===0,JSON.stringify(errors));
 mkdirSync('work/build/website-qa/astra-fixes',{recursive:true});writeFileSync('work/build/website-qa/astra-fixes/browser-results.json',JSON.stringify({assertions,layouts,errors},null,2));console.log(JSON.stringify({assertions,layoutChecks:layouts.length,errors}));
}finally{await browser.close();}
