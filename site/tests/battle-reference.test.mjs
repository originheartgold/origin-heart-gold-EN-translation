import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildBattleIndexes } from '../src/lib/battle-indexes.mjs';
const json = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const species=json('../src/data/species.json'), moves=json('../src/data/moves.json');
const abilities=json('../src/data/abilities.json'), tms=json('../src/data/tms.json');
const ids=rows => new Set(rows.map(r=>r.id));

test('all live slots retained, including unnamed slots with explicit reference audit',()=>{
  assert.deepEqual(moves.map(m=>m.id),Array.from({length:920},(_,i)=>i+1));
  const slots=json('../src/data/move_slots.json');
  assert.equal(slots.total,920);
  assert.deepEqual(slots.unnamed.map(m=>m.id),Array.from({length:18},(_,i)=>622+i*2));
  for (const slot of slots.unnamed) assert.ok(moves.find(m=>m.id===slot.id)?.unnamed);
  assert.equal(new Set(moves.map(m=>m.slug)).size,920);
});

test('ability IDs/form IDs/learnsets and explicit TM references resolve',()=>{
  const abilityIds=ids(abilities), moveIds=ids(moves), speciesIds=ids(species);
  const itemIds=ids(json('../src/data/items.json'));
  for(const s of species){
    assert.ok(speciesIds.has(s.baseSpeciesId),s.name);
    for(const id of [...s.abilityIds,s.hiddenAbilityId].filter(Boolean))assert.ok(abilityIds.has(id),s.name);
    for(const id of [...s.levelup.map(l=>l[1]),...s.tutors,...s.egg])assert.ok(moveIds.has(id),s.name);
  }
  assert.equal(tms.length,138);
  assert.equal(tms.filter(t=>t.newInV4).length,38);
  assert.equal(new Set(tms.map(t=>t.itemId)).size,138);
  for(const tm of tms){assert.ok(itemIds.has(tm.itemId));assert.ok(moveIds.has(tm.moveId));}
  const unknown=abilities.find(a=>a.id===327);
  assert.ok(unknown.unnamed);
  assert.equal(unknown.description.evidence.source,'a027/0712#327');
  assert.equal(unknown.authorNotes[0].sourceAlias,'Moonlight Guardian');
});

test('reverse joins combine levels/methods, all-TM learners, duplicate ability slots and unavailable forms',()=>{
  const fixture=[{id:1,baseSpeciesId:1,formId:0,abilityIds:[327],abilitySlots:[327,327],hiddenAbilityId:327,
    levelup:[[1,2],[5,2]],tms:'all',tutors:[2],egg:[2]},
    {id:1001,baseSpeciesId:1,formId:1,abilityIds:[327],abilitySlots:[327,0],hiddenAbilityId:null,
      levelup:[[20,2]],tms:[],tutors:[],egg:[],unavailableReason:'Unobtainable'}];
  const result=buildBattleIndexes(fixture,[{itemId:328,moveId:2,label:'TM01'}],s=>s.id===1);
  const rows=result.moveLearners.get(2);
  assert.equal(rows.length,2);
  assert.deepEqual(rows[0].methods.map(m=>m.method),['level','tm','tutor','egg']);
  assert.deepEqual(rows[0].methods[0].levels,[1,5]);
  assert.equal(rows[0].methods[1].allTms,true);
  assert.equal(rows[1].formId,1);
  assert.equal(rows[1].unavailableReason,'Unobtainable');
  assert.equal(rows[0].documentedSource,true);
  assert.deepEqual(result.tmCompatibility.get(328),[1]);
  assert.deepEqual(result.abilityHolders.get(327)[0].regularSlots,[1,2]);
  assert.equal(result.abilityHolders.get(327)[0].hidden,true);
});

test('real reverse indexes preserve Mew all TMs and all reference species',()=>{
  const result=buildBattleIndexes(species,tms);
  for(const tm of tms){
    assert.ok(result.tmCompatibility.get(tm.itemId).includes(151),tm.label);
    assert.ok(result.moveLearners.get(tm.moveId).find(r=>r.speciesId===151)?.methods.some(m=>m.allTms),tm.label);
  }
  assert.ok(result.abilityHolders.get(327).some(r=>r.speciesId===488&&r.hidden));
});

test('author facts and workbook coverage remain complete without pretending runtime verification',()=>{
  const notes=json('../src/data/battle_notes.json');
  assert.equal(notes.moveChanges.length,56);
  assert.equal(notes.newTms.length,38);
  assert.equal(notes.abilityChanges.length,59);
  assert.equal(notes.applicability.length,36);
  assert.equal(notes.applicability.filter(r=>r.abilityId===178).length,13);
  assert.equal(notes.applicability.filter(r=>r.abilityId===292).length,23);
  const byMove=new Map(moves.map(m=>[m.id,m]));
  for(const row of notes.applicability){
    assert.ok(byMove.has(row.moveId));assert.ok(ids(abilities).has(row.abilityId));
    assert.equal(row.verifiedGameplay,false);
    if(row.abilityId===292) assert.ok(byMove.get(row.moveId).flags.includes('slicing'));
  }
  assert.equal(moves.filter(m=>m.flags.includes('slicing')).length,32);
  assert.equal(notes.applicability.filter(r=>r.addedInHack).length,14);
  const coverage=json('../../work/tools/site/reference_coverage.json');
  assert.equal(coverage.rows.length,8074);
  assert.equal(new Set(coverage.rows.map(r=>`${r.source}/${r.sheet}/${r.row}`)).size,8074);
  assert.ok(coverage.rows.every(r=>['included','duplicate','superseded','unresolved'].includes(r.status)));
  // Included means source-accounted; runtime/acquisition limitations stay at field level.
  assert.ok(coverage.rows.some(r=>r.source==='items'&&r.unresolvedFields?.length));
  assert.ok(coverage.rows.filter(r=>r.status==='included').every(r=>r.refs.length>0 ||
    (r.disposition==='reserved-unnamed-slot'&&r.comparison.evidence&&r.comparison.reason)));
});
