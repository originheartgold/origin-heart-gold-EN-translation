import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { referenceArtwork, artworkUrl, fallbackArtworkUrl } from '../../work/save-editor/src/ui/artwork.ts';
import { buildBattleIndexes } from '../src/lib/battle-indexes.mjs';
import { playerMoveChanges } from '../src/lib/reference-format.mjs';
const json = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = json('species'), moves = json('moves'), abilities = json('abilities'), tms = json('tms'), items = json('items');
const dist = new URL('../dist/', import.meta.url);
const built = process.env.GUIDE_TEST_DIST === '1';
const read = path => readFileSync(new URL(`${path}/index.html`, dist), 'utf8');
const hasLink = (html, path) => html.includes(`href="${path}"`) || html.includes(`${path}"`);

test('integrated reference pages retain item navigation, encounter filters and evolution triggers', {skip: !built}, () => {
  const item = read('items/mystic-water');
  assert.ok(hasLink(item, '#wild-holder-118'));
  assert.ok(item.includes('data-table="wild-locations-118"'));
  assert.ok(item.includes('aria-label="Filter Goldeen locations or encounter methods"'));
  assert.ok(read('pokemon/gengar').includes('when leveled up'));
  assert.ok(read('pokemon/togepi').includes('when leveled up'));
});

test('reference artwork uses national base IDs and labels every unmapped form', () => {
  assert.equal(referenceArtwork(3, 1).src, artworkUrl(3, false));
  assert.equal(referenceArtwork(3, 1).fallback, fallbackArtworkUrl(3, false));
  assert.equal(referenceArtwork(3, 1).baseFallback, true);
  assert.equal(referenceArtwork(3, 0).baseFallback, false);
  for (const id of [0, -1, 1026, 1440, NaN, 1.5]) assert.equal(referenceArtwork(id, 0), null);
  for (const s of species) {
    const art = referenceArtwork(s.baseSpeciesId, s.formId);
    assert.ok(art, s.name);
    assert.ok(art.src.endsWith(`/${s.baseSpeciesId}.png`), s.name);
    assert.equal(art.baseFallback, s.formId !== 0, s.name);
  }
});

test('built complete references and legacy move anchors resolve', {skip: !built}, () => {
  const index = read('moves');
  for (const m of moves) {
    assert.ok(existsSync(new URL(`moves/${m.slug}/index.html`, dist)), m.name);
    assert.ok(index.includes(`id="move-${m.id}"`), m.name);
    assert.ok(hasLink(index, `/moves/${m.slug}/`), m.name);
  }
  assert.ok(index.includes('id="tm-list"'));
  for (const a of abilities) assert.ok(existsSync(new URL(`abilities/${a.slug}/index.html`, dist)), a.name);
  const tmIndex = read('tms');
  for (const t of tms) {
    const item = items.find(i => i.id === t.itemId);
    assert.ok(hasLink(tmIndex, `/items/${item.slug}/`), t.label);
    assert.ok(read(`items/${item.slug}`).includes('id="compatible-pokemon"'), t.label);
  }
});

test('player effects supersede stale descriptions and omit unknown targets', {skip: !built}, () => {
  const water=read('moves/water-gun'), luster=read('moves/luster-purge');
  assert.ok(water.includes('Does not burn the target'));
  assert.ok(luster.includes('30% chance to lower the target’s Sp. Def'));
  for(const slug of ['water-gun','luster-purge']) {
    const m=moves.find(m=>m.slug===slug),html=read(`moves/${slug}`);
    assert.ok(html.includes('The in-game description is outdated'));
    assert.ok(html.includes('id="description"'));
    assert.ok(!html.includes(m.description.text));
  }
  const unknown=moves.find(m=>m.target===null);
  assert.ok(!read(`moves/${unknown.slug}`).includes('<th>Target</th>'));
  const unnamed=abilities.find(a=>a.id===327),html=read(`abilities/${unnamed.slug}`);
  assert.ok(html.includes('Moonlight Guardian'));
  assert.ok(hasLink(html,'/pokemon/cresselia/'));
});

test('built learners retain unavailable forms, evolution levels and Mew all-TM compatibility', {skip: !built}, () => {
  const {moveLearners,tmCompatibility} = buildBattleIndexes(species,tms);
  for (const id of [15,55,175,295,503]) {
    const m = moves.find(m => m.id === id), html = read(`moves/${m.slug}`);
    for (const row of moveLearners.get(id) ?? []) {
      const s = species.find(s => s.id === row.speciesId);
      assert.ok(hasLink(html, `/pokemon/${s.slug}/`), `${m.name}: ${s.name}`);
    }
  }
  const evolved = species.find(s => s.levelup.some(([level]) => level === 0));
  assert.ok(read(`pokemon/${evolved.slug}`).includes('On evolution'));
  const mew = read('pokemon/mew');
  for (const tm of tms) {
    assert.ok(tmCompatibility.get(tm.itemId).includes(151));
    const item = items.find(i => i.id === tm.itemId);
    assert.ok(hasLink(mew, `/items/${item.slug}/`), tm.label);
  }
  const form = species.find(s => s.id !== s.baseSpeciesId);
  const html = read(`pokemon/${form.slug}`);
  assert.ok(html.includes(`home/${form.baseSpeciesId}.png`));
  assert.ok(!html.includes(`home/${form.id}.png`));
  assert.ok(html.includes('standard form'));
});

test('Sharpness keeps supported and possible move lists distinct', {skip: !built}, () => {
  const sharpness=abilities.find(a=>a.id===292),html=read(`abilities/${sharpness.slug}`);
  assert.ok(html.includes('23 moves'));
  assert.ok(html.includes('these 9 moves'));
  for(const m of moves.filter(m=>m.flags.includes('slicing'))) assert.ok(hasLink(html,`/moves/${m.slug}/`),m.name);
  assert.ok(html.includes('Added in this hack'));
  assert.ok(html.includes('may also affect'));
  const sources=read('reference-sources');
  assert.ok(sources.includes('13 Mega Launcher interactions remain author claims'));
});

test('every stored equipment reference resolves to its exact trainer detail', {skip: !built}, () => {
  const trainers = json('trainers');
  const byId = new Map(trainers.map(t => [t.id,t]));
  for (const t of trainers) {
    const html = read(`trainers/records/${t.id}`);
    assert.ok(html.includes(`id="trainer-${t.id}"`), `trainer ${t.id}`);
    assert.ok(html.includes('Check the battle locations'));
    assert.ok(!html.includes('Stored party and script references'));
    if (!t.places.length) assert.ok(html.includes('No battle location is known'));
  }
  for (const item of items.filter(i => i.trainerUses?.length)) {
    const html = read(`items/${item.slug}`);
    for (const id of item.trainerUses) {
      assert.ok(byId.has(id),`${item.name}: trainer ${id}`);
      assert.ok(hasLink(html,`/trainers/records/${id}/`),`${item.name}: trainer ${id}`);
    }
    assert.ok(!html.includes('/trainers/#trainer-'),item.name);
  }
});


test('move and ability details preserve explicit change sections with original comparisons', {skip: !built}, () => {
  for(const m of moves) assert.ok(read(`moves/${m.slug}`).includes('id="changes"'),m.name);
  for(const a of abilities) assert.ok(read(`abilities/${a.slug}`).includes('id="changes"'),a.name);
  const blast=read('moves/blast-burn');
  for(const text of ['Compared with Pokémon HeartGold.','Category: Special → Physical.','Power: 150 → 100.','Accuracy: 90% → 100%.','PP: 5 → 10.','Recharge turn removed.','Adds a 10% chance to burn the target.']) assert.ok(blast.includes(text),text);
  assert.ok(!blast.includes('before:'));
  assert.ok(read('abilities/sharpness').includes('Additional moves are marked below'));
});

test('move changes filter exactly matches displayed comparisons, including uncertain claims', {skip: !built}, () => {
 const index=read('moves');
 for(const m of moves){
  const changes=playerMoveChanges(m),row=index.match(new RegExp(`<tr id="move-${m.id}"[^>]*>`))[0];
  assert.ok(row.includes(`data-changed="${changes.length ? 'yes' : 'no'}"`),m.name);
  const html=read(`moves/${m.slug}`);
  for(const text of changes)assert.ok(html.includes(text.replaceAll('&','&amp;')),m.name+': '+text);
 }
 assert.ok(read('moves/dragon-claw').includes('Stats are unchanged.'));
 assert.ok(read('moves/dragon-claw').includes('advertised critical-hit boost is not confirmed'));
 assert.ok(read('moves/water-gun').includes('No changes listed.'));
 assert.ok(read('moves/play-rough').includes('Accuracy changed to 100%.'));
 assert.ok(!read('moves/play-rough').includes('Compared with Pokémon HeartGold.'));
});

test('signed HP and uninterpreted zero chances remain honest across built learning tables', {skip: !built}, () => {
  for (const [slug,value] of [['struggle',-25],['clangorous-soul',-33],['chloroblast',-50]]) {
    const m = moves.find(m => m.slug === slug), html = read(`moves/${slug}`);
    assert.equal(m.effects.heal,value);
    assert.ok(!html.includes(`HP loss/cost field: ${value}`));
    assert.ok(read('reference-sources').includes(`HP loss/cost field: ${value}`));
    assert.doesNotMatch(html,/Configured healing:/);
  }
  for (const family of ['moves','pokemon','items']) {
    for (const r of json(family === 'pokemon' ? 'species' : family)) {
      assert.doesNotMatch(read(`${family}/${r.slug}`),/, 0% chance\.|Configured healing: (231|223|206)%/, `${family}/${r.slug}`);
    }
  }
  assert.ok(hasLink(read('pokemon/kommo-o'), '/moves/clangorous-soul/'));
  assert.ok(!read('pokemon/kommo-o').includes('HP loss/cost field: -33'));
  assert.ok(hasLink(read('pokemon/hisuian-electrode'), '/moves/chloroblast/'));
  assert.ok(!read('pokemon/hisuian-electrode').includes('HP loss/cost field: -50'));
});

test('all restricted tutors survive detail rendering and index method tokens', {skip: !built}, () => {
  const index = read('moves');
  const restricted = json('tutors').filter(t => t.species === 'restricted');
  assert.equal(restricted.length,6);
  for (const t of restricted) {
    const m = moves.find(m => m.id === t.move), html = read(`moves/${m.slug}`);
    assert.ok(html.includes('tutor-details'),m.name);
    assert.ok(html.includes('the full compatible list is not known'),m.name);
    assert.ok(!html.includes('0 known learners'),m.name);
    for (const q of t.quests) assert.ok(hasLink(html,q.href),m.name);
    for (const p of t.places) if (p.area) assert.ok(hasLink(html,`/locations/${p.area}/`),m.name);
    const row = index.match(new RegExp(`<tr id="move-${m.id}"[^>]*>`))[0];
    assert.match(row,/data-method="[^"]*tutor/);
    if (t.cost?.length === 0) assert.ok(html.includes('Cost: Free'),m.name);
  }
  assert.ok(read('moves/charge').includes('₽10000'));
  assert.ok(read('moves/blast-burn').includes('Learn this move from the tutor below'));
});

test('practical move effects retain full tests only in research', {skip: !built}, () => {
  const sources=read('reference-sources');
  for(const slug of ['volt-tackle','blast-burn','lunar-dance','bounce']) {
    const m=moves.find(m=>m.slug===slug),html=read(`moves/${slug}`);
    assert.ok(!html.includes(m.testedNotes[0].text));
    assert.ok(sources.replaceAll('&#39;', "'").includes(m.testedNotes[0].text.replaceAll('&','&amp;')));
    assert.ok(sources.includes(m.testedNotes[0].limitation));
    assert.ok(hasLink(sources,m.testedNotes[0].href));
  }
  assert.ok(read('moves/blast-burn').includes('no recharge needed'));
  assert.ok(read('moves/volt-tackle').includes('No recoil when knocking out a wild Pokémon'));
  assert.ok(read('moves/lunar-dance').includes('stays in battle without fainting'));
  assert.ok(read('moves/bounce').includes('Attacks on the same turn'));
  for(const slug of ['frenzy-plant','hydro-cannon','rock-wrecker']) assert.ok(!read(`moves/${slug}`).includes('may not work'));
  assert.ok(sources.includes('battle behavior needs an in-game test'));
});

test('berry acquisition and Ursaring operation stay accurate without contradictory recipes', {skip: !built}, () => {
  for(const slug of ['qualot-berry','tamato-berry']) assert.ok(read(`items/${slug}`).includes('Scratch-Off'));
  for(const slug of ['salac-berry','petaya-berry']) {
    const html=read(`items/${slug}`);
    assert.ok(html.includes('steal it with Thief or Covet'));
    assert.ok(html.includes('keeps holding it after the battle'));
    assert.ok(!html.includes('No confirmed way to get it'));
  }
  for(const slug of ['apicot-berry','lansat-berry']) assert.ok(read(`items/${slug}`).includes('No way to get it is known in v4'));
  const ursaring=read('pokemon/ursaring');
  assert.match(ursaring,/holding <a[^>]*>Moon Stone<\/a>/);
  assert.ok(!ursaring.includes('Use a Moon Stone at Night'));
  assert.ok(read('reference-sources').includes('Use a Moon Stone at Night'));
  const note=species.find(s=>s.id===217).referenceNotes.find(n=>n.comparison?.evolution);
  assert.equal(note.comparison.evolution.equal,false);
  assert.ok(note.comparison.evolution.configured.some(e=>e.how==='level up holding Moon Stone (night)'));
  const included=json('reference_coverage').sheets.reduce((n,s)=>n+(s.statuses.included??0),0);
  assert.ok(read('about').includes(`${included.toLocaleString('en-US')} included`));
});

test('all gameplay pages omit technical panels and audit copy even inside details', {skip: !built}, () => {
  const families={moves,abilities,items,pokemon:species,locations:json('areas')};
  for(const [family,records] of Object.entries(families)) for(const r of records) {
    const html=read(`${family}/${r.slug}`),main=html.match(/<main[\s\S]*?<\/main>/)?.[0] ?? html;
    assert.doesNotMatch(main,/reference-provenance|<pre|emu_harness|effect field|HP loss\/cost field|Battle test details|Author notes \/ discrepancies|source comparison|configured theft source/,`${family}/${r.slug}`);
  }
  for(const route of ['tms','tutors','trainers','trainers/records/105']) assert.doesNotMatch(read(route),/reference-provenance|<pre|Stored party and script references/);
  const blast=read('moves/blast-burn');
  assert.equal((blast.match(/10% chance to burn/g)??[]).length,2);
  assert.ok(!blast.includes('Recharge in other situations is not confirmed'));
  const sources=read('reference-sources');
  assert.ok(sources.includes('Detailed reference records'));
  assert.ok(sources.includes('emu_harness.py'));
  assert.ok(sources.includes('configured theft source'));
});
