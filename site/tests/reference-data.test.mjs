import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { PRESETS, TABLE, ROW, GUARD, toSettings, buildCode, hex } from '../src/lib/camera-codes.mjs';
import { isPatchManifest } from '../src/lib/patch-manifest.mjs';
const json = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
for (const [file, audit, count] of [['species', 'not_in_game', 1440], ['items', 'items_not_in_game', 769]]) {
  test(`${file}: full reference catalog retains every audited unavailable entry and reason`, () => {
    const entries = json(`../src/data/${file}.json`);
    const reviewed = json(`../../work/tools/site/${audit}.json`).entries;
    assert.equal(entries.length, count);
    assert.equal(new Set(entries.map(e => e.id)).size, count);
    assert.equal(new Set(entries.map(e => e.slug)).size, count);
    const byId = new Map(entries.map(e => [e.id, e]));
    for (const row of reviewed) {
      const entry = byId.get(row.id);
      assert.ok(entry, `missing ${row.id}`);
      assert.equal(entry.unavailableReason, row.reason, row.name);
      if (file === 'items') assert.deepEqual(entry.sources, []);
      else assert.equal(entry.how, '');
    }
    assert.equal(entries.filter(e => e.unavailableReason).length, reviewed.length);
  });
}
test('camera presets keep exact raw values when their rounded controls are unchanged', () => {
  for (let i = 0; i < PRESETS.length; i++) {
    const raw = PRESETS[i], code = buildCode('everywhere', toSettings(raw), i);
    assert.equal(code[0], GUARD);
    const start = TABLE + ROW * 6;
    assert.ok(code.includes(`${hex(start)} ${hex(raw[0])}`));
    assert.ok(code.includes(`${hex(start + 4)} ${hex(raw[1])}`));
    assert.ok(code.includes(`${hex(start + 12)} ${hex(raw[3] << 16 | raw[2])}`));
    for (let k = 4; k < 9; k++) assert.ok(code.includes(`${hex(start + 16 + (k - 4) * 4)} ${hex(raw[k])}`));
    assert.ok(code.every(line => /^[A-F0-9]{8} [A-F0-9]{8}$/.test(line)));
  }
});
test('interior camera edits touch only the two flat presets and preserve look-at offsets', () => {
  const code = buildCode('interiors', {...toSettings(PRESETS[4]), distance: 800});
  assert.equal(code.length, 10);
  for (const i of [4, 15]) assert.ok(code.includes(`${hex(TABLE + ROW * i)} ${hex(800 * 4096)}`));
  assert.ok(!code.some(line => line.startsWith('20001308')));
});
test('patcher stays disabled for absent or malformed release metadata', () => {
  const good = {tag: 'v1.2.3-rc4', file: 'Origin_EN.xdelta', size: 1024, patched_sha1: 'a'.repeat(40), release_url: 'https://github.com/example/releases/tag/v1.2.3-rc4'};
  assert.equal(isPatchManifest(good), true);
  for (const value of [null, {}, {...good, available: false}, {...good, tag: 7}, {...good, file: '../patch.xdelta'}, {...good, size: -1}, {...good, size: Infinity}, {...good, patched_sha1: 'bad'}, {...good, release_url: 'javascript:alert(1)'}, {...good, prerelease: 'false'}]) assert.equal(isPatchManifest(value), false);
});

test('wild-held sources retain valid species, location links and conditional rates', () => {
  const items = json('../src/data/items.json');
  const species = new Set(json('../src/data/species.json').map(s => s.id));
  const areas = new Set(json('../src/data/areas.json').map(a => a.slug));
  assert.equal(items.filter(i => i.wildHeld?.length).length, 71);
  // Revive's former Linoone sources were disabled radio/Safari-block encounters.
  assert.deepEqual(items.find(i => i.id === 28).wildHeld, []);
  for (const item of items) {
    if (item.unavailableReason) assert.deepEqual(item.wildHeld, [], item.name);
    for (const holder of item.wildHeld ?? []) {
      assert.ok(species.has(holder.species), item.name);
      assert.ok([5, 50, 100].includes(holder.chance), item.name);
      assert.ok(holder.locations.length, item.name);
      for (const location of holder.locations) {
        assert.ok(areas.has(location.area), `${item.name}: ${location.area}`);
        assert.ok(location.method, item.name);
        assert.ok(location.encounterRate === null ||
          (location.encounterRate > 0 && location.encounterRate <= 100), item.name);
      }
    }
  }
  const lightBall = items.find(i => i.slug === 'light-ball');
  assert.equal(lightBall.wildHeld.find(h => h.species === 25).chance, 5);
});
