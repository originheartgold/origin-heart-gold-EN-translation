// Clean player guide: complete gameplay lists, no research panels, source retention and no-JS.
import assert from 'node:assert/strict';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base=process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4327/poke/';
const out='work/build/website-qa/plain-player-guide';mkdirSync(out,{recursive:true});
const read=n=>JSON.parse(readFileSync(`site/src/data/${n}.json`,'utf8'));
const moves=read('moves'),tutors=read('tutors');
const browser=await chromium.launch({headless:true});
const errors=[],layouts=[];let assertions=0;
const ok=(v,msg)=>{assert.ok(v,msg);assertions++;};
const block=async ctx=>ctx.route('**/*',r=>new URL(r.request().url()).origin===new URL(base).origin?r.continue():r.abort());
const ctx=await browser.newContext({viewport:{width:1440,height:1000}});await block(ctx);
const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));
const go=async path=>{const r=await page.goto(base+path,{waitUntil:'domcontentloaded'});ok(r.status()===200,path);return page.locator('main').innerText();};
const clean=async path=>{
 const text=await go(path), main=page.locator('main');
 ok(await main.locator('.reference-provenance, pre, .evidence').count()===0,path+' no visible or collapsed research');
 const full=await main.textContent();ok(!/emu_harness|Battle test details|effect field|source comparison|configured theft source|HP loss\/cost field|not universally verified|Not confirmed/.test(full),path+' clean whole page');
 return text;
};
try{
 for(const [slug,expected] of [['blast-burn','Attack again on the next turn—no recharge needed'],['volt-tackle','No recoil when knocking out a wild Pokémon'],['lunar-dance','stays in battle without fainting'],['bounce','Attacks on the same turn']]){
  const text=await clean(`moves/${slug}/`);ok(text.includes(expected),slug+' practical effect');
  ok(!/other situations|recorded|observed|tested/i.test(text),slug+' no audit commentary');
  if(slug==='blast-burn'){
   ok((text.match(/10% chance to burn/g)??[]).length===2,'Blast Burn full effect and added effect comparison');
   for(const change of ['Compared with Pokémon HeartGold.','Category: Special → Physical.','Power: 150 → 100.','Accuracy: 90% → 100%.','PP: 5 → 10.','Recharge turn removed.','Adds a 10% chance to burn the target.'])ok(text.includes(change),'Blast Burn comparison '+change);
   ok(!text.includes('0 known learners')&&text.includes('Learn this move from the tutor below'),'Blast Burn tutor first');
   ok(await page.locator('#learners-tutor .tutor-details').count()===0 || await page.locator('.tutor-details').count()>0,'Blast Burn tutor present');
  }
 }
 for(const [slug,change] of [['bounce','Attacks in one turn instead of spending the first turn bouncing up.'],['lunar-dance','instead of sacrificing the user to restore its replacement'],['luster-purge','Power: 70 → 95.'],['dragon-claw','The advertised critical-hit boost is not confirmed.'],['play-rough','Accuracy changed to 100%.']]){
  const text=await clean(`moves/${slug}/`);ok(text.includes(change),slug+' comparison');
 }
 await go('moves/?changed=yes');await page.waitForFunction(()=>document.querySelector('.filter-reset'));
 for(const slug of ['blast-burn','lunar-dance','luster-purge','dragon-claw','play-rough'])ok(await page.locator(`#move-${moves.find(m=>m.slug===slug).id}`).isVisible(),slug+' changed filter');
 ok(!(await page.locator('#move-55').isVisible()),'Water Gun stale description is not a move change');
 await page.reload();ok(await page.locator('#move-295').isVisible(),'comparison filter survives reload');
 for(const [slug,expected] of [['water-gun','Does not burn the target'],['luster-purge','30% chance to lower the target’s Sp. Def']]){
  const text=await clean(`moves/${slug}/`);ok(text.includes(expected)&&text.includes('in-game description is outdated'),slug+' correct current effect');
  const original=moves.find(m=>m.slug===slug).description.text;ok(!(await page.locator('main').textContent()).includes(original),slug+' no stale instructions');
 }
 for(const slug of ['frenzy-plant','hydro-cannon','rock-wrecker']){const text=await clean(`moves/${slug}/`);ok(!text.includes('may not work'),slug+' no speculative failure');}
 for(const t of tutors.filter(t=>t.species==='restricted')){
  const m=moves.find(m=>m.id===t.move),text=await clean(`moves/${m.slug}/`);
  ok(await page.locator('.tutor-details').count()>0,m.name+' actual tutor');
  ok(text.includes('the full compatible list is not known'),m.name+' honest eligibility');
  ok(!text.includes('0 known learners'),m.name+' no false empty learner message');
  for(const q of t.quests)ok(await page.locator(`.tutor-details a[href="${new URL(base).pathname.replace(/\/$/,'')}${q.href}"]`).count()>0,m.name+' requirements link');
  if(t.cost?.length===0)ok(text.includes('Cost: Free'),m.name+' free cost');
  if(m.id===268)ok(text.includes('₽10000'),m.name+' real cost');
 }
 await go('moves/?method=tutor');await page.waitForFunction(()=>document.querySelector('.filter-reset'));
 for(const t of tutors.filter(t=>t.species==='restricted'))ok(await page.locator(`#move-${t.move}`).isVisible(),'restricted tutor filter '+t.move);
 await page.reload();for(const t of tutors.filter(t=>t.species==='restricted'))ok(await page.locator(`#move-${t.move}`).isVisible(),'restricted tutor reload '+t.move);
 for(const [slug,who] of [['salac-berry','Pinsir'],['petaya-berry','Empoleon']]){
  const text=await clean(`items/${slug}/`);ok(text.includes(who)&&text.includes('steal it with Thief or Covet')&&text.includes('keeps holding it after the battle'),slug+' practical theft route');
  ok(!text.includes('No confirmed way to get it'),slug+' not unavailable');
 }
 for(const slug of ['qualot-berry','tamato-berry'])ok((await clean(`items/${slug}/`)).includes('Scratch-Off'),slug+' prize route');
 const ursaring=await clean('pokemon/ursaring/');ok(ursaring.includes('holding Moon Stone')&&ursaring.includes('at night'),'Ursaring actual evolution');ok(!ursaring.includes('Use a Moon Stone at Night'),'no contradictory stone use');
 const sharp=await clean('abilities/sharpness/');ok(sharp.includes('23 moves')&&sharp.includes('these 9 moves')&&sharp.includes('may also affect'),'Sharpness separates possible moves');
 ok(sharp.includes('Added in this hack'),'Sharpness additions retained');
 for(const m of moves.filter(m=>m.flags.includes('slicing')))ok(await page.locator(`main a[href$="/moves/${m.slug}/"]`).count()>0,'Sharpness retains '+m.name);
 await go('reference-sources/');
 for(const slug of ['blast-burn','volt-tackle','lunar-dance','bounce','struggle','clangorous-soul','chloroblast']){
  const m=moves.find(m=>m.slug===slug),row=page.locator(`#move-source-${m.id}`);ok(await row.count()===1,slug+' central research');
  await row.locator('summary').click();const text=await row.innerText();
  if(m.testedNotes.length){ok(text.includes(m.testedNotes[0].text)&&text.includes(m.testedNotes[0].limitation),slug+' full original tests');ok(await row.locator('a[href$="#moves-that-work-differently"]').count()>0,slug+' source report');}
  if(m.effects.heal<0)ok(text.includes(`HP loss/cost field: ${m.effects.heal}`),slug+' signed HP fields');
  await row.locator('summary').click();
 }
 const paths=['','moves/','moves/blast-burn/','moves/bounce/','moves/water-gun/','moves/luster-purge/','moves/lunar-dance/','moves/dragon-claw/','moves/play-rough/','abilities/','abilities/sharpness/','abilities/mega-launcher/','abilities/water-veil/','tms/','items/tm75-swords-dance/','items/salac-berry/','items/qualot-berry/','pokemon/','pokemon/ursaring/','pokemon/mew/','pokemon/hoopa-unbound/','locations/pallet-town/','locations/fuchsia-city/','trainers/records/105/','tutors/','mechanics/','calendar/','faq/','reference-sources/'];
 for(const path of paths){await go(path);ok(await page.locator('h1').count()===1,path+' title');
  for(const width of [1440,390]){await page.setViewportSize({width,height:width===390?844:1000});
   for(const theme of ['light','dark']){await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
    const sizes=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));ok(sizes.scroll<=sizes.width+1,path+' '+width+' '+theme+' containment');layouts.push({path,theme,...sizes});
    if(['moves/blast-burn/','moves/bounce/','moves/luster-purge/','moves/lunar-dance/','abilities/sharpness/','items/salac-berry/','pokemon/ursaring/'].includes(path))await page.screenshot({path:`${out}/${path.replaceAll('/','-').replace(/-$/,'')}-${width}-${theme}.png`,fullPage:false});
   }
  }
 }
 const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});await block(nojs);const np=await nojs.newPage();
 for(const [path,id,n] of [['pokemon/','mon-table',1440],['moves/','move-table',920],['abilities/','ability-table',327],['tms/','tm-table',138]]){await np.goto(base+path,{waitUntil:'domcontentloaded'});ok(await np.locator(`#${id} tbody tr`).count()===n,'no-JS complete '+path);}
 await np.goto(base+'moves/blast-burn/',{waitUntil:'domcontentloaded'});ok((await np.locator('main').innerText()).includes('no recharge needed'),'no-JS practical Blast Burn');ok(await np.locator('main pre, main .reference-provenance').count()===0,'no-JS no audit panel');
 ok((await np.locator('main').innerText()).includes('Power: 150 → 100.'),'no-JS Blast Burn comparison');
 await np.goto(base+'reference-sources/',{waitUntil:'domcontentloaded'});await np.locator('#move-source-307 > summary').click();ok((await np.locator('#move-source-307').innerText()).includes('emu_harness.py'),'no-JS central evidence available');await nojs.close();
 ok(errors.length===0,JSON.stringify(errors));writeFileSync(`${out}/browser-results.json`,JSON.stringify({assertions,layouts,errors},null,2));console.log(JSON.stringify({assertions,layoutChecks:layouts.length,errors}));
}finally{await browser.close();}
