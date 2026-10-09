import test from 'node:test';
import assert from 'node:assert/strict';
import { formatEncounterHints } from '../src/lib/encounter-hints.mjs';

test('method and time hints preserve compound encounter conditions without nested buttons', () => {
  for (const text of [
    'Grass/cave, morning and day',
    'Safari Zone: Forest area selected, Good Rod, night; object requirements vary',
    'Radio on Hoenn Sound (replaces the 10% grass slots)',
    'Headbutt: Rare trees',
    'Bug-Catching Contest: Set 2: Tuesdays, with the National Pokédex',
    'Calendar encounter: October 16, any time (replaces the 1% grass/cave slot)',
  ]) {
    const html = formatEncounterHints(text);
    assert.equal(html.replace(/<[^>]*>/g, ''), text);
    assert.match(html, /data-encounter-hint=/);
    assert.doesNotMatch(html, /<button[^>]*>(?:(?!<\/button>)[\s\S])*<button/);
  }
  const land = formatEncounterHints('Grass/cave, day');
  assert.equal((land.match(/data-encounter-hint=/g) ?? []).length, 1);
  assert.match(land, /data-time-hint="day"/);
});

test('method descriptions escape untrusted text and keep native title fallback', () => {
  const html = formatEncounterHints('<script>Surfing</script> & "Old Rod"');
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&amp; &quot;/);
  assert.match(html, /title="Fish with the Old Rod/);
  assert.equal(formatEncounterHints('Unknown method'), 'Unknown method');
});
