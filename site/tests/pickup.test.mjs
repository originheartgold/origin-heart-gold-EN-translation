import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const json = name => JSON.parse(readFileSync(new URL(`../src/data/${name}.json`, import.meta.url), 'utf8'));
const pickup = json('pickup'), items = json('items');
const byId = new Map(items.map(item => [item.id, item]));

test('all 22 Pickup items have exactly one source and each level band totals 100%', () => {
	assert.equal(pickup.activationPercent, 10);
	assert.equal(pickup.items.length, 22);
	assert.equal(pickup.bands.length, 10);
	assert.deepEqual(items.filter(item => item.sources.some(s => s.kind === 'Pickup')).map(item => item.id).sort((a,b) => a-b), pickup.items.map(row => row.item).sort((a,b) => a-b));
	for (const row of pickup.items) assert.equal(byId.get(row.item).sources.filter(s => s.kind === 'Pickup').length, 1);
	for (let band = 0; band < 10; band++) assert.equal(pickup.items.reduce((sum, row) => sum + row.rates[band], 0), 100);
	assert.equal(byId.get(53).name, 'PP Max');
	assert.deepEqual(pickup.items.find(row => row.item === 53).rates, [0,0,0,0,0,1,1,3,5,10]);
	assert.ok(!pickup.items.some(row => row.item === 83));
});

test('built chart and item pages preserve all rates and distinguish activation odds', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
	const read = path => readFileSync(new URL(`../dist/${path}/index.html`, import.meta.url), 'utf8');
	const mechanics = read('mechanics');
	const chart = mechanics.split('aria-label="Pickup items by Pokémon level"')[1].split('</table>')[0];
	assert.equal((chart.match(/scope="row"/g) ?? []).length, 10);
	assert.ok(mechanics.includes('10% chance to activate per eligible check'));
	assert.ok(mechanics.includes('3% per eligible check'));
	assert.ok(mechanics.includes('0.1%'));
	for (const row of pickup.items) {
		const item = byId.get(row.item);
		assert.equal((chart.match(new RegExp(`/items/${item.slug}/#source-pickup`, 'g')) ?? []).length, row.rates.filter(Boolean).length);
		const html = read(`items/${item.slug}`);
		const table = html.split('pickup-item-rates')[1].split('</table>')[0];
		const ranges = [...table.matchAll(/<tr><td>(\d+)–(\d+)<\/td><td>(\d+)%<\/td><td>≈([\d.]+)%<\/td><\/tr>/g)];
		assert.ok(ranges.length);
		for (let level = 1; level <= 100; level++) {
			const expected = row.rates[Math.floor((level-1)/10)];
			const found = ranges.find(r => level >= +r[1] && level <= +r[2]);
			assert.equal(found ? +found[3] : 0, expected, `${item.name}, level ${level}`);
			if (found) assert.equal(+found[4], expected / 10);
		}
		assert.ok(html.includes('/mechanics/#pickup'));
	}
	assert.ok(read('abilities/pickup').includes('/mechanics/#pickup'));
});
