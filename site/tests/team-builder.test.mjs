import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { sanitizeTeam, parseTeamHash, teamHash, filterCatalog, acquisitionFamily, availableTeamPokemon } from '../src/lib/team-builder.mjs';
import { createPlannerData } from '../src/lib/team-builder-data.mjs';

const read = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = read('species'), areas = read('areas'), items = read('items'), moves = read('moves');
const byId = new Map(species.map(mon => [mon.id, mon]));
const known = new Set(byId.keys());
const planner = createPlannerData({ species, areas, items, moves });

test('shared and saved teams preserve form IDs, cap at six and reject malformed state', () => {
  assert.deepEqual(sanitizeTeam([3, 3, 94, '25', -1, 99999, 1027, 25, 133, 1439, 1440], known), [3, 94, 1027, 25, 133, 1439]);
  for (const invalid of [null, {}, '3,94', 42]) assert.deepEqual(sanitizeTeam(invalid, known), []);
  assert.equal(parseTeamHash('#where', known), null);
  assert.deepEqual(parseTeamHash('#team=', known), []);
  assert.deepEqual(parseTeamHash('#team=3,bad,25.5,1e2,-1,999999,94,3', known), [3, 94]);
  assert.deepEqual(parseTeamHash(teamHash([1027, 3, 1440]), known), [1027, 3, 1440]);
});

test('family includes all earlier stages without siblings or assumed base-species links', () => {
  assert.deepEqual(acquisitionFamily(3, byId), [1, 2, 3]);
  assert.deepEqual(acquisitionFamily(94, byId), [92, 93, 94]);
  const espeon = acquisitionFamily(196, byId);
  assert.ok(espeon.includes(133));
  assert.ok(!espeon.includes(197));
  assert.deepEqual(acquisitionFamily(1439, byId), [1439], 'Crystal Onix is not normal Onix');
  assert.deepEqual(acquisitionFamily(1440, byId, [{ base: 150, result: 1440 }]), [150, 1440]);
  const cycle = new Map([[1, { evoFrom: [{ id: 2 }] }], [2, { evoFrom: [{ id: 1 }] }]]);
  assert.deepEqual(acquisitionFamily(1, cycle), [2, 1]);
  assert.deepEqual(acquisitionFamily(99999, byId), []);
});

test('Venusaur includes Bulbasaur catch value, encounter chance and missable gift conditions', () => {
  const detail = planner.detail(3);
  const bulbasaur = detail.members.find(member => member.id === 1);
  assert.equal(bulbasaur.catchRate, 45);
  assert.ok(bulbasaur.wild.some(enc => enc.area === 'fuchsia-city' && enc.method === 'Grass/cave, day' && enc.encounterRate === 1));
  assert.ok(bulbasaur.acquisitions.some(source => source.conditions.includes('Pikachu starter: after the Cascade Badge') && source.conditions.includes('refusing to help loses the gift')));
  assert.deepEqual(detail.steps.map(step => step.text), ['Level up at Lv 16', 'Level up at Lv 32']);
});

test('hack evolution requirements retain trigger, item, clock and priority notes', () => {
  const gengar = planner.detail(94).steps.find(step => step.to.id === 94);
  assert.match(gengar.text, /Level up holding Spell Tag at night \(20:00–3:59\)/);
  assert.equal(gengar.links[0].href, '/items/spell-tag/');
  const espeon = planner.detail(196);
  assert.match(espeon.steps.find(step => step.from.id === 133).text, /Level up.*220.*4:00–19:59/);
  assert.ok(espeon.members.find(member => member.id === 133).evoNotes.some(note => note.includes('becomes Sylveon')));
  const leafeon = planner.detail(470);
  assert.ok(leafeon.steps.some(step => step.blocked && step.text.includes('Moss Rock')));
  assert.ok(leafeon.steps.some(step => !step.blocked && step.text === 'using Leaf Stone'));
});

test('full projection preserves every wild rate, gift condition and species catch value', () => {
  for (const mon of species) {
    const member = planner.detail(mon.id).members.find(member => member.id === mon.id);
    assert.equal(member.catchRate, mon.catch, mon.name);
    assert.equal(member.wild.length, mon.wildEncounters.length, mon.name);
    mon.wildEncounters.forEach((encounter, index) => {
      for (const key of Object.keys(encounter)) assert.deepEqual(member.wild[index][key], encounter[key], `${mon.name}: ${key}`);
      assert.ok(member.wild[index].href.startsWith(`/locations/${encounter.area}/#`));
    });
    assert.equal(member.acquisitions.length, mon.acquisitions.length, mon.name);
    mon.acquisitions.forEach((source, index) => assert.equal(member.acquisitions[index].conditions, source.conditions, mon.name));
  }
});

test('calendar forms stay distinct; held-item forms include their actual base acquisition', () => {
  const forms = [{ base: 150, result: 1440, item: 114, condition: 'No nature requirement.' }];
  const data = createPlannerData({ species: species.map(mon => ({ ...mon, calendar: mon.id === 720 || mon.id === 1243 ? [
    { pokemon: 720, date: 'July 18', period: 'Morning only' }, { pokemon: 1243, date: 'July 18', period: 'Night only' },
  ] : [] })), areas, items, moves, formChanges: forms });
  assert.equal(data.detail(720).members.at(-1).calendar.length, 1);
  assert.equal(data.detail(720).members.at(-1).calendar[0].period, 'Morning only');
  assert.equal(data.detail(1243).members.at(-1).calendar[0].period, 'Night only');
  const armored = data.detail(1440);
  assert.deepEqual(armored.members.map(member => member.id), [150, 1440]);
  assert.match(armored.steps[0].text, /Hold Steel Armor.*Removing the item/);
  assert.ok(armored.members[0].acquisitions.some(source => source.area === 'indigo-plateau' || source.href === '/locations/indigo-plateau/'));
  assert.ok(armored.members[0].acquisitions.some(source => source.conditions.includes('before entering the Elite Four rooms')));
});

test('filters compose secondary type, hidden ability, region and availability', () => {
  const catalog = species.map(mon => ({ ...mon, availability: mon.unavailableReason ? 'unavailable' : mon.how ? 'documented' : 'unknown' }));
  assert.ok(filterCatalog(catalog, { query: 'thick fat', type: 'Poison', region: 'Kanto', availability: 'documented' }).some(mon => mon.id === 1));
  assert.deepEqual(filterCatalog(catalog, { query: 'no-such-pokemon' }), []);
  assert.ok(filterCatalog(catalog, { query: '#150' }).some(mon => mon.id === 1440));
});

test('ordinary keyboard spellings match names with apostrophes and accents', () => {
  for (const [query, name] of [["Farfetch'd", 'Farfetch’d'], ['Farfetchd', 'Farfetch’d'], ["Sirfetch'd", 'Sirfetch’d'], ['Flabebe', 'Flabébé']]) {
    assert.ok(filterCatalog(species, { query }).some(mon => mon.name === name), query);
  }
});

test('production planner and JSON routes are generated', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
  const html = readFileSync(new URL('../dist/team-builder/index.html', import.meta.url), 'utf8');
  assert.ok(html.includes('id="team-builder"'));
  assert.ok(html.includes('More filled bars mean a harder catch'));
  assert.ok(html.includes('richi3f'));
  const catalog = JSON.parse(html.match(/<script[^>]*id="tb-data"[^>]*>(.*?)<\/script>/s)[1]);
  const selectable = new Set(availableTeamPokemon(catalog).map(mon => mon.id));
  assert.ok(selectable.has(1), 'Bulbasaur remains selectable');
  assert.ok(selectable.has(1440), 'documented held-item forms remain selectable');
  assert.deepEqual(parseTeamHash('#team=1,494,1119,1072,1440', selectable), [1, 1440],
    'shared teams discard Victini, battle-only Castform and undocumented Unown forms');

  const detail = JSON.parse(readFileSync(new URL('../dist/team-builder/pokemon/3.json', import.meta.url), 'utf8'));
  assert.deepEqual(detail.members.map(mon => mon.id), [1, 2, 3]);
});

test('all dynamically loaded acquisition and evolution links resolve in the built site', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
  const root = new URL('../dist/', import.meta.url);
  const cache = new Map();
  let checked = 0;
  function visit(value) {
    if (Array.isArray(value)) return value.forEach(visit);
    if (!value || typeof value !== 'object') return;
    for (const [key, child] of Object.entries(value)) {
      if (key !== 'href' || !child) { visit(child); continue; }
      const url = new URL(child, 'https://example.test');
      const path = decodeURIComponent(url.pathname).replace(/^\//, '') + 'index.html';
      if (!cache.has(path)) cache.set(path, new Set([...readFileSync(new URL(path, root), 'utf8').matchAll(/\bid="([^"]+)"/g)].map(match => match[1])));
      if (url.hash) assert.ok(cache.get(path).has(decodeURIComponent(url.hash.slice(1))), child);
      checked++;
    }
  }
  for (const name of readdirSync(new URL('team-builder/pokemon/', root))) {
    visit(JSON.parse(readFileSync(new URL(`team-builder/pokemon/${name}`, root), 'utf8')));
  }
  assert.ok(checked > 15000, `${checked} planner links checked`);
});

test('team choices and restored teams exclude unavailable, battle-only and unknown Pokémon', () => {
  const catalog = [
    { id: 1, availability: 'documented' },
    { id: 2, availability: 'unavailable' },
    { id: 3, availability: 'battle' },
    { id: 4, availability: 'unknown' },
    { id: 5, availability: 'documented' },
  ];
  const choices = availableTeamPokemon(catalog);
  assert.deepEqual(choices.map(mon => mon.id), [1, 5]);
  const selectable = new Set(choices.map(mon => mon.id));
  assert.deepEqual(sanitizeTeam([2, 1, 3, 4, 5], selectable), [1, 5]);
  assert.deepEqual(parseTeamHash('#team=2,1,3,4,5', selectable), [1, 5]);
});
