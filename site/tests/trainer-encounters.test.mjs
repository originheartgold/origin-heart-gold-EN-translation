import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildTrainerProfiles, inactiveEncounter } from '../src/lib/trainer-encounters.mjs';

const trainers = JSON.parse(readFileSync(new URL('../src/data/trainers.json', import.meta.url), 'utf8'));
const { profiles, byId } = buildTrainerProfiles(trainers);
const ids = id => byId.get(id).teams.map(t => t.id).sort((a, b) => a - b);

test('every trainer record and every distinct battle context survives grouping', () => {
  assert.equal(byId.size, trainers.length);
  assert.equal(profiles.flatMap(p => p.teams).length, trainers.length);
  for (const t of trainers) {
    const profile = byId.get(t.id);
    assert.ok(profile.teams.includes(t));
    const actual = [...profile.encounters, ...profile.inactive].filter(e => e.team.id === t.id).map(e => JSON.stringify(e.place)).sort();
    assert.deepEqual(actual, [...new Set(t.places.map(p => JSON.stringify(p)))].sort(), `trainer ${t.id}`);
    assert.equal(profile.unconfirmed.includes(t), t.places.length === 0);
  }
});

test('every Giovanni URL includes all eight teams, all locations and memory rematches', () => {
  const expected = [244, 287, 288, 289, 402, 496, 662, 701];
  for (const id of expected) assert.deepEqual(ids(id), expected);
  const profile = byId.get(287);
  assert.deepEqual([...new Set(profile.encounters.map(e => e.place.area))].sort(),
    ['cerulean-cave', 'frontier-access', 'mt-silver', 'pokemon-league', 'saffron-city', 'victory-road', 'viridian-city']);
  assert.equal(profile.encounters.filter(e => e.place.how.includes('memory rematch')).length, 4);
  assert.equal(profile.inactive.length, 1);
  assert.equal(profile.inactive[0].place.area, 'cherrygrove-city');
});

test('characters retain class changes, partner teams, disguises and unconfirmed teams', () => {
  for (const name of ['Blue', 'Steven', 'Cynthia', 'Gold', 'Misty', 'Archie', 'Petrel', 'Proton']) {
    const ts = trainers.filter(t => t.name === name);
    assert.deepEqual(ids(ts[0].id), ts.map(t => t.id));
  }
  assert.deepEqual(ids(325), [325, 473, 564]);
  assert.deepEqual(ids(257), [257, 286, 724]);
  assert.deepEqual(ids(669), [176, 280, 611, 669, 670]);
  assert.equal(byId.get(325).label, 'Janine');
  assert.ok(byId.get(2).encounters.some(e => e.place.how.startsWith('your partner')));
  assert.ok(byId.get(177).unconfirmed.some(t => t.id === 492));
});

test('ordinary recurring characters are included without merging homonyms or generic opponents', () => {
  assert.deepEqual(ids(41), [41, 303]);
  assert.deepEqual(ids(313), [313, 657]);
  assert.equal(ids(13).length, 8); // Jessie
  assert.equal(ids(23).length, 8); // James
  assert.equal(ids(163).length, 8); // Goh
  for (const [a, b] of [[117, 640], [319, 773], [27, 160], [519, 520], [17, 462], [856, 928]]) {
    assert.notEqual(byId.get(a), byId.get(b));
  }
  for (const t of trainers.filter(t => !t.name || ['Grunt', 'Unnamed trainer'].includes(t.name))) {
    assert.deepEqual(ids(t.id), [t.id]);
  }
});

test('inactive scenes are separated without hiding active alternatives', () => {
  assert.equal(inactiveEncounter({ conds: ["never used: the scene can't trigger"] }), true);
  assert.equal(inactiveEncounter({ conds: [] }), false);
  assert.equal(inactiveEncounter({ conds: ['never used', 'if you pick “Singles”'] }), false);
  for (const profile of profiles) {
    assert.ok(profile.encounters.every(e => !inactiveEncounter(e.place)));
    assert.ok(profile.inactive.every(e => inactiveEncounter(e.place)));
  }
});
