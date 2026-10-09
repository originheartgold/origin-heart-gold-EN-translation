import test from 'node:test';
import assert from 'node:assert/strict';
import {playerMoveEffects,playerItemCaveat,playerMoveChanges,playerMoveDescription} from '../src/lib/reference-format.mjs';
import {readFileSync} from 'node:fs';
const moves=JSON.parse(readFileSync(new URL('../src/data/moves.json',import.meta.url),'utf8'));
const bySlug=slug=>moves.find(m=>m.slug===slug);
test('original move comparisons retain values and useful changed behavior',()=>{
 assert.deepEqual(playerMoveChanges(bySlug('blast-burn')), [
  'Category: Special → Physical.', 'Power: 150 → 100.', 'Accuracy: 90% → 100%.', 'PP: 5 → 10.',
  'Recharge turn removed.', 'Adds a 10% chance to burn the target.',
 ]);
 assert.equal(bySlug('blast-burn').originalComparison.baseline,'Pokémon HeartGold');
 assert.ok(playerMoveChanges(bySlug('bounce')).includes('Attacks in one turn instead of spending the first turn bouncing up.'));
 assert.match(playerMoveChanges(bySlug('lunar-dance')).join(' '),/raises.*Sp\. Atk and Speed.*instead of sacrificing/i);
 assert.deepEqual(bySlug('luster-purge').authorNotes[0].highlightedFields,[]);
 assert.deepEqual(playerMoveChanges(bySlug('luster-purge')),['Power: 70 → 95.','Sp. Def drop chance: 50% → 30%.']);
});
test('source notes do not invent changes to stale or later moves',()=>{
 for(const slug of ['water-gun','pound']) assert.deepEqual(playerMoveChanges(bySlug(slug)),[]);
 const water=bySlug('water-gun');assert.ok(water.conflicts.some(c=>c.kind==='stale-description'));
 assert.equal(bySlug('play-rough').originalComparison.baseline,null);
 assert.deepEqual(playerMoveChanges(bySlug('play-rough')),['Accuracy changed to 100%.']);
 const newTmOnly=moves.find(m=>m.id>467&&m.authorNotes.length&&m.authorNotes.every(n=>n.changeKind!=='changed'));
 assert.ok(newTmOnly);assert.deepEqual(playerMoveChanges(newTmOnly),[]);
 const claw=bySlug('dragon-claw');
 assert.equal(claw.originalComparison.fields.length,0);
 assert.equal(claw.originalComparison.effects[0].uncertain,true);
 assert.deepEqual(playerMoveChanges(claw),['The advertised critical-hit boost is not confirmed.']);
 assert.doesNotMatch(playerMoveDescription(claw),/critical/i);
});
test('player effect summaries preserve chances and stages without inventing disputed effects',()=>{
 assert.deepEqual(playerMoveEffects(bySlug('swords-dance')),['Attack +2 stages.']);
 assert.deepEqual(playerMoveEffects(bySlug('growl')),['Attack -1 stage.']);
 assert.deepEqual(playerMoveEffects(bySlug('luster-purge')),['Sp. Def -1 stage; 30% chance.']);
 for(const slug of ['blast-burn','volt-tackle','lunar-dance'])assert.deepEqual(playerMoveEffects(bySlug(slug)),[]);
 for(const slug of ['struggle','clangorous-soul','chloroblast']){
  assert.ok(bySlug(slug).effects.heal<0);
  assert.ok(!playerMoveEffects(bySlug(slug)).some(t=>/HP loss\/cost|HP restored/.test(t)));
 }
 for(const m of moves){
  assert.ok(!playerMoveEffects(m).some(t=>/Configured|decoded|\b0% chance/.test(t)),m.name);
  // The player summary must not mutate the evidence records used in source details.
  const original=JSON.stringify(m);playerMoveEffects(m);assert.equal(JSON.stringify(m),original);
 }
});
test('player item instructions retain practical acquisition without source disputes',()=>{
 for(const id of [171,174])assert.match(playerItemCaveat(id,''),/Scratch-Off/);
 assert.match(playerItemCaveat(203,''),/Pinsir.*S\.S\. Anne.*Thief or Covet.*keeps holding/);
 assert.match(playerItemCaveat(204,''),/Empoleon.*Route 21.*Thief or Covet.*keeps holding/);
 assert.match(playerItemCaveat(205,''),/No way to get it is known in v4/);
});
