// Run from the repo root against a built site served locally. Uses an existing Playwright install.
// PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs GUIDE_PREVIEW_URL=http://127.0.0.1:4337/ node site/tests/quest-filters-browser.mjs
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4337/';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const go = path => page.goto(new URL(`guide/${path}/`, base).href, { waitUntil: 'networkidle' });
const visible = () => page.locator('section.quest:not(.is-hidden)').evaluateAll(quests => quests.map(q => ({ id: q.querySelector('h2').id, ...q.dataset })));
const choose = (name, value) => page.locator(`.game-setup [name=${name}]`).selectOption(value);
const output = 'work/build/quest-tags-qa';
mkdirSync(output, { recursive: true });
try {
  await go('pewter-to-vermilion');
  assert.equal((await visible()).length, 23);
  assert.equal(await page.locator('.tag-main, .tag-side').count(), 23);
  await choose('kind', 'side');
  assert.ok((await visible()).every(q => q.kind === 'side'));
  await choose('progress', 'postgame');
  assert.equal((await visible()).length, 2);
  assert.ok((await visible()).every(q => q.postgame === 'yes'));
  await choose('kind', 'main');
  assert.equal((await visible()).length, 0);
  assert.match(await page.locator('.hidden-count').innerText(), /No matching quests/);
  await choose('kind', 'side');
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.locator('[name=kind]').inputValue(), 'side');
  assert.equal(await page.locator('[name=progress]').inputValue(), 'postgame');
  assert.equal((await visible()).length, 2);
  await go('pallet-to-pewter');
  assert.equal(await page.locator('[name=kind]').inputValue(), 'side');
  assert.equal((await visible()).length, 0); // Lance's epilogue is a main quest.

  await choose('progress', 'before');
  await choose('starter', 'Pikachu');
  let quests = await visible();
  assert.ok(quests.length > 0);
  assert.ok(quests.every(q => q.kind === 'side' && !q.postgame && (!q.starter || q.starter.includes('Pikachu'))));
  const first = page.locator('section.quest:not(.is-hidden)').first();
  const doneId = await first.locator('h2').getAttribute('id');
  await first.locator('.quest-tools input').check();
  await page.locator('[name=hidedone]').check();
  assert.ok(!(await visible()).some(q => q.id === doneId));
  await page.reload({ waitUntil: 'networkidle' });
  assert.ok(!(await visible()).some(q => q.id === doneId));

  // A direct link overrides every filter, with an explanation, and hash changes reapply filters.
  const postgameId = await page.locator('section.quest[data-postgame=yes] h2').getAttribute('id');
  await page.evaluate(id => { location.hash = id; }, postgameId);
  await page.waitForFunction(id => !document.getElementById(id).closest('section').classList.contains('is-hidden'), postgameId);
  assert.ok((await visible()).some(q => q.id === postgameId));
  assert.match(await page.locator('.hidden-count').innerText(), /linked quest stays visible/);
  await page.evaluate(() => { location.hash = ''; });
  await page.waitForFunction(id => document.getElementById(id).closest('section').classList.contains('is-hidden'), postgameId);

  // Old saved checkbox preferences migrate; malformed saved values fall back to all quests.
  await page.evaluate(() => localStorage.setItem('ohg:setup', JSON.stringify({ postgame: false })));
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.locator('[name=progress]').inputValue(), 'before');
  assert.ok((await visible()).every(q => !q.postgame));
  await choose('progress', '');
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal((await visible()).length, 22);
  await page.evaluate(() => localStorage.setItem('ohg:setup', JSON.stringify({ kind: 'invalid', progress: 'invalid' })));
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal((await visible()).length, 22);
  assert.equal(await page.locator('[name=kind]').inputValue(), '');
  assert.equal(await page.locator('[name=progress]').inputValue(), '');

  // Verify mobile controls in both themes and save review screenshots.
  for (const [width, theme] of [[1440, 'dark'], [390, 'light'], [390, 'dark']]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
    await page.locator('.game-setup').scrollIntoViewIfNeeded();
    const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
      controls: [...document.querySelectorAll('.game-setup select')].map(e => ({ left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right })) }));
    assert.ok(layout.scroll <= width + 1, JSON.stringify(layout));
    assert.ok(layout.controls.every(c => c.left >= 0 && c.right <= width));
    await page.screenshot({ path: `${output}/quests-${width}-${theme}.png` });
  }
  // No-JS readers still see all entries and their tags.
  const nojs = await browser.newContext({ javaScriptEnabled: false });
  const staticPage = await nojs.newPage();
  await staticPage.goto(new URL('guide/pewter-to-vermilion/', base).href);
  assert.equal(await staticPage.locator('section.quest').count(), 23);
  assert.equal(await staticPage.locator('.tag-main, .tag-side').count(), 23);
  assert.equal(await staticPage.locator('.tag-postgame').count(), 2);
  assert.equal(await staticPage.locator('section.quest.is-hidden').count(), 0);
  await nojs.close();
  assert.deepEqual(errors, []);
  console.log('Quest filters: combined filters, persistence, completion, direct links, migration, mobile themes and no-JS checks passed.');
} finally {
  await browser.close();
}
