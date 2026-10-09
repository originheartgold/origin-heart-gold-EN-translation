import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {formatTutorCost} from '../src/lib/reference-format.mjs';
const read = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url)));
const items=read('items'), tutors=read('tutors'), species=read('species'), moves=read('moves'), areas=read('areas');
const facts=JSON.parse(readFileSync(new URL('../../work/tools/site/reference_facts.json',import.meta.url)));
const coverage=JSON.parse(readFileSync(new URL('../../work/tools/site/reference_coverage.json',import.meta.url)));

test('all source row identities remain distinct and accounted for',()=>{
 assert.equal(coverage.rows.length,8074);
 assert.equal(new Set(coverage.rows.map(r=>`${r.source}:${r.sheet}:${r.row}`)).size,8074);
 assert.equal(coverage.sources.length,3);
 assert.ok(coverage.sources.every(s=>/^[0-9a-f]{64}$/.test(s.sha256)));
 assert.equal(coverage.duplicateAttachments.length,8);
 assert.equal(facts.moveChanges.length,56);assert.equal(facts.newTms.length,38);assert.equal(facts.abilityChanges.length,59);
 assert.ok([...facts.moveChanges,...facts.newTms,...facts.abilityChanges].every(n=>n.before===null));
});

test('item summaries have game text and attributed readable source claims',()=>{
 assert.equal(items.length,769);
 assert.ok(items.every(i=>i.effectText?.evidence.kind==='game-text'));
 assert.equal(items.flatMap(i=>i.referenceNotes).length,450);
 assert.equal(items.flatMap(i=>i.legacySourceNotes).length,199);
 for(const i of items) for(const n of [...i.referenceNotes,...i.legacySourceNotes]) {
  for(const field of ['note','effectNote','changeNote','acquisitionNote','useNote','configuredNote'])
   assert.doesNotMatch(n[field]??'',/[\u4e00-\u9fff]|\{(?:NEWLINE|SCROLL|CLEAR)\}/);
  assert.equal(n.evidence.kind,'author-note');
 }
});

test('known stale item claims carry concrete script audit corrections',()=>{
 const note=id=>items.find(i=>i.id===id).referenceNotes[0];
 assert.match(note(15).configuredNote,/standard v4 Poké Mart.*no Quick Ball/);
 for (const id of [171,174]) {
  const berry=items.find(i=>i.id===id);
  assert.ok(berry.sources.some(s=>s.kind==='minigame prize'&&s.area==='battle-frontier'));
  assert.match(note(id).configuredNote,/no reachable v4 Saffron seller/);
  assert.match(note(id).configuredNote,/configured Battle Frontier Scratch-Off prize/);
  assert.doesNotMatch(note(id).configuredNote,/No reachable v4 source/);
 }
 for (const id of [203,204]) {
  assert.match(note(id).configuredNote,/Celadon.*unsupported in v4/);
  assert.match(note(id).configuredNote,/configured theft source/);
  assert.doesNotMatch(note(id).configuredNote,/No reachable v4 source/);
  assert.ok(items.find(i=>i.id===id).sources.some(s=>s.kind==='stolen' && s.place.includes('Thief or Covet') && s.note?.includes('Tested in an emulator')));
 }
 for (const id of [205,206]) assert.match(note(id).configuredNote,/No reachable v4 source/);
 assert.match(note(429).configuredNote,/Fresh Water and \$10,000/);
 assert.equal(note(429).auditEvidence.kind,'rom-data');
});

test('tutor claims join the configured taught move, preserving EN source conflicts',()=>{
 const flail=tutors.find(t=>t.move===175);
 const claimed=flail.authorNotes.find(n=>n.evidence.row===585);
 assert.equal(claimed.moveId,583);assert.equal(claimed.configuredMoveId,175);
 const poltergeist=tutors.find(t=>t.move===809).authorNotes.find(n=>n.evidence.row===573);
 assert.equal(poltergeist.moveId,917);assert.equal(poltergeist.configuredMoveId,809);
 const ancient=tutors.find(t=>t.move===246).authorNotes.find(n=>n.evidence.row===565);
 assert.match(ancient.sourceConflictNote,/Big Nugget.*Rare Bone/);
 assert.equal(facts.tutorNotes.length,79);
});

test('reverse item use links resolve without treating stored equipment as acquisition',()=>{
 const sp=new Set(species.map(s=>s.id)), mv=new Set(moves.map(m=>m.id));
 for(const i of items){
  for(const e of i.evolutionUses){assert.ok(sp.has(e.speciesId));assert.ok(sp.has(e.resultId));}
  for(const t of i.tutorUses)assert.ok(mv.has(t.moveId));
 }
 assert.ok(items.find(i=>i.id===83).evolutionUses.some(e=>e.speciesId===25&&e.resultId===26));
 assert.ok(items.find(i=>i.id===81).tutorUses.some(t=>t.moveId===585));
});

test('missing map-reference source tables remain unassigned and retained',()=>{
 assert.equal(facts.unmappedEncounterTables.length,5);
 assert.equal(facts.unmappedEncounterTables.flatMap(t=>t.rows).length,180);
 assert.ok(facts.unmappedEncounterTables.every(t=>!('areaSlug' in t)));
 assert.ok(areas.flatMap(a=>a.referenceNotes).some(n=>/Squirtle/.test(n.note)));
});

test('Water Veil and Bounce conflicts remain separate from author claims and configuration',()=>{
 const abilities=read('abilities');
 assert.match(abilities.find(a=>a.id===41).conflicts[0].text,/Aqua Ring.*burn immunity/);
 assert.ok(moves.find(m=>m.id===340).conflicts.some(c=>c.kind==='stale-description'));
 assert.ok(!moves.find(m=>m.id===340).flags.includes('charge'));
 assert.ok(!items.some(i=>i.effects.evidence.kind==='tested'));
});

test('unknown tutor costs never become free',()=>{
 assert.equal(formatTutorCost(null),'Cost unknown');
 assert.equal(formatTutorCost(undefined),'Cost unknown');
 assert.equal(formatTutorCost([]),'Free');
 assert.equal(formatTutorCost(['Moon Ball ×1']),'Moon Ball ×1');
});

test('EN TM shop and map labels preserve their actual configured counterparts',()=>{
 const tm97=facts.newTms.find(t=>t.label==='TM97');
 assert.equal(tm97.locationNote,'Goldenrod City Shop');
 assert.equal(tm97.acquisitionComparison.configuredShops[0].area,'saffron-city');
 const locator=facts.mapNotes.find(n=>n.evidence.row===43&&n.evidence.workbook==='pokemon');
 assert.equal(locator.locationLabelMatch,false);
 assert.deepEqual(locator.areaSlugs,['viridian-city']);
});


test('supplied explicit evolution operations retain all five comparisons',()=>{
 const expected = [[232,false,'use'],[493,true,'use'],[494,true,'level-up-holding'],[568,true,'holding'],[775,true,'holding']];
 for (const [row,equal,operation] of expected) {
  const record=coverage.rows.find(r=>r.source==='pokemon'&&r.sheet==='4.0 Pokémon Data'&&r.row===row);
  assert.equal(record.comparison.evolution.equal,equal,`row ${row}`);
  assert.ok(record.comparison.evolution.alternatives.some(a=>a.constraints.some(([k,v])=>k==='operation'&&v===operation)));
 }
 const ursaring=coverage.rows.find(r=>r.source==='pokemon'&&r.sheet==='4.0 Pokémon Data'&&r.row===232);
 assert.equal(ursaring.status,'unresolved');
 assert.ok(ursaring.unresolvedFields.includes('evolution'));
});
