import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const read = file => JSON.parse(readFileSync(new URL(file, import.meta.url), 'utf8'));
const species = read('../src/data/species.json');
const areas = read('../src/data/areas.json');
const byId = new Map(species.map(s => [s.id, s]));

test('every mapped gift, Egg and trade has a Pokémon acquisition source', () => {
	let checked = 0;
	for (const area of areas) {
		for (const gift of area.statics.filter(row => ['gift', 'egg'].includes(row.kind))) {
			assert.ok(byId.get(gift.id).acquisitions.some(row => row.area === area.slug && row.level === gift.level), `${gift.name}: ${area.name}`);
			checked++;
		}
		for (const trade of area.trades) {
			assert.ok(byId.get(trade.get).acquisitions.some(row => row.area === area.slug && (trade.loan || row.offer === trade.give)), `${trade.getName}: ${area.name}`);
			checked++;
		}
	}
	assert.ok(checked >= 60);
	for (const s of species) for (const row of s.acquisitions) {
		assert.ok(row.evidence.length > 0);
		assert.ok(row.offer == null || byId.has(row.offer));
		assert.ok(areas.some(area => area.slug === row.area));
	}
});

test('starter requirements, prices, exclusions and exchange direction survive export', () => {
	const bulba = byId.get(1);
	assert.equal(bulba.acquisitions.length, 2);
	assert.match(bulba.acquisitions.find(s => s.kind === 'gift').conditions, /Pikachu starter only.*Cascade Badge.*Sabrina/);
	assert.ok(!bulba.otherSources.includes('gift'));
	assert.equal(byId.get(95).acquisitions.find(s => s.kind === 'trade').offer, 15);
	assert.equal(byId.get(252).acquisitions.find(s => s.kind === 'egg').level, null);
	assert.match(byId.get(23).acquisitions[0].conditions, /700 Coins/i);
	assert.match(byId.get(133).acquisitions.find(s => s.kind === 'prize').conditions, /6,666 Coins/);
	assert.ok(!byId.get(27).acquisitions.some(s => s.kind === 'prize'));
	assert.ok(!byId.get(61).acquisitions.some(s => s.evidence.some(e => e.file === 842)));
	assert.match(byId.get(142).otherSources, /revive Old Amber/i);
});

test('built gift and trade details appear in the existing Where section', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
	for (const id of [1, 95, 133, 252]) {
		const mon = byId.get(id);
		const html = readFileSync(new URL(`../dist/pokemon/${mon.slug}/index.html`, import.meta.url), 'utf8');
		assert.ok(html.indexOf('class="pokemon-acquisitions"') > html.indexOf('id="where"'));
		assert.ok(!html.includes('No confirmed way to get it.'));
		for (const row of mon.acquisitions) {
			if (row.offer != null) assert.ok(html.includes(`/pokemon/${byId.get(row.offer).slug}/`));
			for (const quest of row.quests) assert.ok(html.includes(quest.href));
		}
	}
});
