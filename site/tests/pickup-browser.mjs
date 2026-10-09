// Run from the repo root against a local build preview with an existing Playwright installation.
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4338/';
const output = 'work/build/pickup-website-qa';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
	const context = await browser.newContext({ javaScriptEnabled: false });
	await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
	const page = await context.newPage();
	const errors = [];
	page.on('pageerror', error => errors.push(error.message));
	for (const viewport of [{width:1440,height:1000}, {width:390,height:844}]) {
		await page.setViewportSize(viewport);
		for (const [path, target] of [['mechanics/', '#pickup'], ['items/pp-max/', '#source-pickup'], ['items/gold-bottle-cap/', '#source-pickup'], ['abilities/pickup/', '#effect']]) {
			await page.goto(new URL(path, base).href);
			await page.locator(target).evaluate(el => el.scrollIntoView({block:'start'}));
			assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${path}: page overflow`);
			for (const theme of ['light','dark']) {
				await page.evaluate(value => document.documentElement.dataset.theme = value, theme);
				await page.screenshot({path:`${output}/${path.replaceAll('/','-')}${viewport.width}-${theme}.png`});
			}
			if (path === 'mechanics/') {
				assert.equal(await page.locator('.pickup-chart tbody tr').count(), 10);
				const chart = page.locator('.pickup-chart');
				await chart.focus();
				await chart.evaluate(el => el.scrollIntoView({block:'start'}));
				await page.screenshot({path:`${output}/chart-${viewport.width}.png`});
				if (viewport.width === 390) {
					await page.keyboard.press('ArrowRight');
					// waitForFunction uses page timers, which are disabled in this no-JS context.
					await page.waitForTimeout(300);
					assert.ok(await chart.evaluate(el => el.scrollLeft > 0), 'chart scrolls by keyboard');
				}
			}
			if (path === 'items/pp-max/') assert.match(await page.locator('.pickup-item-rates').innerText(), /51–70\s+1%\s+≈0.1%/);
		}
	}
	assert.deepEqual(errors, []);
	console.log('Pickup chart/item/ability pages passed: desktop/mobile, light/dark, keyboard scrolling and no-JS.');
} finally {
	await browser.close();
}
