import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { encounterChance } from '../src/lib/encounter-format.mjs';

const json = (name) => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const species = json('species'), areas = json('areas');
const byId = new Map(species.map(s => [s.id, s]));

test('all location encounter rows reach the correct Pokémon page with their rates and conditions', () => {
	let checked = 0;
	const check = (area, place, method, row, rate, kind) => {
		const mon = byId.get(row.id);
		if (!mon) return;
		const found = mon.wildEncounters.find(e => e.area === area.slug && e.place === place &&
			e.method.startsWith(method) && e.level === row.level && e.encounterRate === rate &&
			e.rateKind === (rate == null ? 'unknown' : kind));
		assert.ok(found, `${mon.name}: ${place}, ${method}, ${rate}`);
		checked++;
	};
	for (const area of areas) {
		for (const block of area.encounters) for (const section of block.sections) for (const row of section.rows)
			check(area, block.label, section.title, row, row.pct, 'percent');
		for (const block of area.headbutt) for (const section of block.sections) for (const row of section.rows)
			check(area, block.label, `Headbutt: ${section.title}`, row, row.pct, 'percent');
		for (const group of area.contest?.sets ?? []) for (const row of group.rows)
			check(area, area.name, `Bug-Catching Contest: ${group.title}`, row, row.rate, 'weight');
		for (const section of area.safari) for (const row of section.rows) {
			assert.ok(byId.get(row.id)?.wildEncounters.some(e => e.area === area.slug && e.method === section.title &&
				e.level === row.level && e.encounterRate == null && e.rateKind === 'unknown'));
			checked++;
		}
	}
	assert.ok(checked > 4000, `full ROM scan: ${checked} rows`);
});

test('starter examples reflect the ROM instead of the suggested five percent', () => {
	assert.ok(byId.get(1).wildEncounters.some(e => e.area === 'fuchsia-city' && e.method === 'Grass/cave, day' && e.encounterRate === 1));
	assert.ok(byId.get(4).wildEncounters.some(e => e.area === 'rock-tunnel' && e.method === 'Grass/cave, morning' && e.encounterRate === 1));
	assert.ok(!byId.get(1).wildEncounters.some(e => e.area === 'viridian-forest'));
	assert.ok(!byId.get(4).wildEncounters.some(e => e.area === 'cinnabar-island'));
});

test('rate rendering never presents contest weights or unknown odds as percentages', () => {
	assert.equal(encounterChance({ encounterRate: 5, rateKind: 'percent' }), '5%');
	assert.equal(encounterChance({ encounterRate: 0, rateKind: 'weight' }), '0 (weight)');
	assert.equal(encounterChance({ encounterRate: 80, rateKind: 'weight' }), '80 (weight)');
	assert.equal(encounterChance({ encounterRate: null, rateKind: 'unknown' }), 'Not fixed');
	for (const mon of species) for (const e of mon.wildEncounters) {
		assert.ok(areas.some(a => a.slug === e.area));
		assert.ok(!e.method.startsWith('Scripted wild battle'), 'one-time battles are not random encounter odds');
		if (e.rateKind === 'percent') assert.ok(e.encounterRate > 0 && e.encounterRate <= 100);
	}
});

test('built Pokémon pages show encounter tables and preserve gifts separately', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
	const read = (path) => readFileSync(new URL(`../dist/${path}/index.html`, import.meta.url), 'utf8');
	const bulbasaur = read('pokemon/bulbasaur');
	assert.ok(bulbasaur.includes('id="wild-encounters-table"'));
	assert.ok(!bulbasaur.includes('Wild encounter rates'));
	assert.ok(bulbasaur.includes('Pikachu starter only.') && bulbasaur.includes('After the Cascade Badge'));
	assert.ok(bulbasaur.includes('Route 5 House'));
	assert.ok(bulbasaur.includes('Starter choice'));
	assert.ok(!bulbasaur.includes('gift (Lv 15), Route 5 House'));
	assert.ok(bulbasaur.includes("Pallet Oak&#39;s Lab") || bulbasaur.includes("Pallet Oak's Lab"));
	assert.ok(bulbasaur.includes('Fuchsia City'));
	assert.ok(bulbasaur.replace(/<[^>]*>/g, '').includes('Grass/cave, day'));
	assert.ok(bulbasaur.includes('data-time-hint="day"'));
	assert.ok(bulbasaur.includes('<td>1%</td>'));
	assert.ok(read('pokemon/goldeen').includes('aria-label="Filter Goldeen wild encounters"'));
	assert.ok(read('locations/safari-zone').replace(/<[^>]*>/g, '').includes('Safari Zone areas'));
	assert.ok(read('pokemon/pinsir').includes('0 (weight)'));
});
