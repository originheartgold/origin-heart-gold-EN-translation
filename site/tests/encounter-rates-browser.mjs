// Run from the repo root against a built-site preview; use an existing Playwright installation.
import assert from 'node:assert/strict';
import { mkdirSync, readFileSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4338/';
const output = 'work/build/encounter-rates-qa';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
	const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
	await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
	const page = await context.newPage();
	const errors = [];
	page.on('pageerror', error => errors.push(error.message));
	await page.goto(new URL('pokemon/bulbasaur/', base).href);
	const table = page.locator('#wild-encounters-table');
	assert.match(await page.locator('.pokemon-acquisitions').innerText(), /Pikachu starter:.*Cascade Badge/);
	assert.equal(await page.locator('.pokemon-acquisitions li').count(), 2);
	assert.match(await table.innerText(), /Fuchsia City/);
	assert.match(await table.innerText(), /Grass\/cave, day\s+5\s+1%/);
	await table.scrollIntoViewIfNeeded();
	await page.screenshot({ path: `${output}/bulbasaur-desktop.png` });
	await page.goto(new URL('pokemon/goldeen/', base).href);
	const search = page.getByRole('searchbox', { name: 'Filter Goldeen wild encounters' });
	await search.fill('Route 24');
	await page.waitForFunction(() => [...document.querySelectorAll('#wild-encounters-table tbody tr:not([hidden])')].every(row => row.textContent.includes('Route 24')));
	assert.ok(await page.locator('#wild-encounters-table tbody tr:not([hidden])').count() > 0);
	await search.fill('no-such-location');
	await page.waitForFunction(() => document.querySelectorAll('#wild-encounters-table tbody tr:not([hidden])').length === 0);
	await search.fill('');
	await page.waitForFunction(() => document.querySelectorAll('#wild-encounters-table tbody tr:not([hidden])').length > 10);
	for (const path of ['pokemon/bulbasaur/', 'pokemon/goldeen/', 'locations/safari-zone/']) {
		await page.setViewportSize({ width: 390, height: 844 });
		await page.goto(new URL(path, base).href);
		for (const theme of ['light', 'dark']) {
			await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
			const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
			assert.equal(overflow, false, `${path}: mobile ${theme} overflow`);
		}
	}
	await page.goto(new URL('pokemon/bulbasaur/#where', base).href);
	await page.locator('#where').scrollIntoViewIfNeeded();
	await page.screenshot({ path: `${output}/bulbasaur-mobile.png` });
	await page.setViewportSize({ width: 1440, height: 1000 });
	await page.goto(new URL('pokemon/', base).href);
	const mons = JSON.parse(readFileSync('site/src/data/species.json', 'utf8'));
	const statNames = ['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed'];
	for (const [index, name] of statNames.entries()) {
		const header = page.locator('#mon-table th').filter({ has: page.getByRole('button', { name, exact: true }) });
		for (const descending of [false, true]) {
			await header.getByRole('button').click();
			const actual = await page.locator('#mon-table tbody tr').evaluateAll((rows, col) => rows.map(row => Number(row.cells[col].textContent)), 6 + index);
			const expected = mons.map(mon => mon.stats[index]).sort((a, b) => descending ? b - a : a - b);
			assert.deepEqual(actual, expected, `${name}: ${descending ? 'highest' : 'lowest'} first`);
			assert.equal(await header.getAttribute('aria-sort'), descending ? 'descending' : 'ascending');
		}
	}
	await page.reload();
	assert.equal(await page.locator('#mon-table th').nth(11).getAttribute('aria-sort'), 'descending');
	await page.locator('#mon-table').scrollIntoViewIfNeeded();
	await page.screenshot({ path: `${output}/base-stats-desktop.png` });
	await page.setViewportSize({ width: 390, height: 844 });
	assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'base stats mobile overflow');
	await page.screenshot({ path: `${output}/base-stats-mobile.png` });
	const nojs = await browser.newContext({ javaScriptEnabled: false });
	await nojs.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
	const plain = await nojs.newPage();
	await plain.goto(new URL('pokemon/goldeen/', base).href);
	assert.ok(await plain.locator('#wild-encounters-table tbody tr').count() > 10);
	assert.equal(await plain.locator('#wild-encounters-table tbody tr[hidden]').count(), 0);
	await plain.goto(new URL('pokemon/bulbasaur/', base).href);
	assert.match(await plain.locator('.pokemon-acquisitions').innerText(), /Pikachu starter/);
	assert.deepEqual(errors, []);
	console.log('Encounter tables and all six base-stat sorts: desktop/mobile, filtering, no-JS and browser errors passed.');
} finally {
	await browser.close();
}
