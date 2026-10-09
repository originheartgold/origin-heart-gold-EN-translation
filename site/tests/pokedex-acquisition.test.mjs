import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const species = new Map(read('../src/data/species.json').map(s => [s.id, s]));
const areas = read('../src/data/areas.json');
const conditions = source => source.conditions.join(' ');

test('Charmander distinguishes morning wild encounter, starter choice and Pikachu rescue', () => {
  const s = species.get(4);
  assert.equal(s.wildSources.length, 1);
  assert.deepEqual(s.wildSources[0], {
    area: 'rock-tunnel', place: 'Rock Tunnel', method: 'Grass/cave, morning', level: '5', encounterRate: 1, rateKind: 'percent',
  });
  assert.equal(s.acquisition.length, 2);
  const rescue = s.acquisition.find(a => a.text.includes('Pewter'));
  assert.match(conditions(rescue), /Pikachu starter only/);
  assert.match(conditions(rescue), /before the Cascade Badge/);
  assert.doesNotMatch(s.how, /Route 3/);
  assert.ok(s.quests.some(q => q.href.includes('abandoned-charmander')));
  assert.ok(!s.quests.some(q => q.title.includes('Meowth thief')));
  assert.ok(!areas.find(a => a.slug === 'route-3').statics.some(a => a.id === 4));
});

test('alternative gifts retain complementary starter conditions', () => {
  assert.match(species.get(84).how, /Charmander starter only/);
  assert.match(species.get(339).how, /Bulbasaur or Pikachu starter only/);
  assert.match(species.get(1).how, /Pikachu starter only/);
  assert.match(species.get(58).how, /Bulbasaur or Charmander starter only/);
  const ralts = species.get(280).acquisition.filter(a => a.text.includes('Route 3'));
  assert.equal(ralts.length, 2);
  assert.ok(ralts.some(a => /Before the Cascade Badge/.test(conditions(a))));
  assert.ok(ralts.some(a => /After the Cascade Badge/.test(conditions(a))));
});

test('unused and wrong-version sources do not survive through other pages', () => {
  assert.doesNotMatch(species.get(27).how, /Goldenrod Game Corner/);
  assert.doesNotMatch(species.get(145).how, /Lv 50/);
  for (const id of [82, 88, 101]) assert.doesNotMatch(species.get(id).how, /Scripted wild battle.*Power Plant/);
  assert.equal(species.get(486).how, '');
  assert.equal(species.get(493).how, '');
});

test('permanent loan-command rewards preserve their actual requirements', () => {
  const pidgeot = species.get(18).acquisition.find(a => a.kind === 'replacement');
  const gyarados = species.get(130).acquisition.find(a => a.kind === 'gift');
  assert.match(conditions(pidgeot), /Pikachu starter only/);
  assert.match(conditions(pidgeot), /original Pidgeot is not returned/);
  assert.match(conditions(gyarados), /Male player with Bulbasaur starter only/);
  assert.match(conditions(gyarados), /keep it/);
  assert.match(species.get(130).how, /Male player with Bulbasaur starter only/);
});

test('unavailable Safari blocks are excluded and all scripted sources have reviewed conditions', () => {
  const beldum = species.get(374).wildSources.filter(s => s.method.includes('Safari'));
  assert.equal(beldum.length, 0);
  for (const s of species.values()) {
    for (const source of s.acquisition) {
      assert.doesNotMatch(conditions(source), /access requirements have not been verified/);
    }
    for (const row of s.wildSources) {
      assert.ok(areas.some(a => a.slug === row.area), s.name);
      assert.ok(row.method && row.place, s.name);
      assert.doesNotMatch(row.method, /block points|object requirements/);
    }
  }
});

test('disabled vanilla encounter systems are not advertised as catch locations', () => {
  for (const s of species.values()) {
    for (const row of s.wildSources) {
      assert.doesNotMatch(row.method, /Swarm|Hoenn Sound|Sinnoh Sound|Fishing at night/);
    }
  }
  const contest = areas.find(a => a.contest)?.contest;
  assert.equal(contest.sets.length, 1);
  assert.match(contest.note, /same species set/);
  assert.ok(!species.get(290).wildSources.some(s => s.method.startsWith('Bug-Catching Contest')));
  assert.ok(!species.get(201).wildSources.some(s => /unused Arceus/.test(s.place)));
});
