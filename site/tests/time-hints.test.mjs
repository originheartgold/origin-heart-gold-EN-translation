import test from 'node:test';
import assert from 'node:assert/strict';
import { formatTimeHints, timeHint } from '../src/lib/time-hints.mjs';

test('encounter and evolution daytime keep their different hour ranges', () => {
  assert.equal(timeHint('morning').hours, '04:00–09:59');
  assert.equal(timeHint('day').hours, '10:00–19:59');
  assert.equal(timeHint('day', 'evolution').hours, '04:00–19:59');
  assert.equal(timeHint('night').hours, '20:00–03:59');
  assert.match(timeHint('night').description, /listed calendar date/);
  assert.equal(timeHint('any').hours, 'All 24 hours');
  assert.equal(timeHint('evening').hours, 'Part of Day', 'do not invent a separate evening encounter period');
});

test('combined periods preserve wording and have keyboard-accessible descriptions', () => {
  const html = formatTimeHints('Grass/cave, morning and day');
  assert.match(html, /Grass\/cave, /);
  assert.match(html, /data-time-hint="morning"/);
  assert.match(html, /data-time-hint="day"/);
  assert.match(html, /<button type="button"/);
  assert.match(html, /title="10:00–19:59/);
  assert.equal((html.match(/<button /g) ?? []).length, 2);
  assert.match(formatTimeHints('All day'), /data-time-hint="any"/);
  assert.match(formatTimeHints('during the day (4:00–19:59)', 'evolution'), /title="04:00–19:59/);
});

test('condition markup escapes prose, and ordinary text is left alone', () => {
  assert.equal(formatTimeHints('Use Leaf Stone'), 'Use Leaf Stone');
  const html = formatTimeHints('<script>alert("night")</script>');
  assert.ok(!html.includes('<script>'));
  assert.match(html, /&lt;script&gt;/);
  assert.match(html, /&quot;/);
});
