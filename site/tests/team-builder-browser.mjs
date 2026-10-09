// Run from the repo root with an existing Playwright installation and a built preview.
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4346/poke/';
const output = 'work/build/team-builder-qa';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
let checks = 0;
const check = (actual, expected, message) => { assert.deepEqual(actual, expected, message); checks++; };
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  // Deterministic interaction tests do not depend on external artwork or analytics.
  await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [];
  const analyticsRequests = [];
  page.on('request', request => { if (/gc\.zgo\.at|goatcounter/.test(request.url())) analyticsRequests.push(request.url()); });
  page.on('pageerror', error => errors.push(error.message));
  const goto = async hash => {
    let response = await page.goto(new URL(`team-builder/${hash}`, base).href);
    if (!response) response = await page.reload();
    check(response.status(), 200, 'planner loads');
    await page.locator('#team-builder[data-ready=true]').waitFor();
  };
  const guide = async name => {
    await page.waitForFunction(() => document.querySelector('#tb-details').getAttribute('aria-busy') === 'false');
    assert.equal(await page.locator('#tb-details h3').count(), 1, await page.locator('#tb-details').textContent());
    check(await page.locator('#tb-details h3').textContent(), name, 'active guide');
  };
  await goto('#team=3,94,196,1440'); await guide('Venusaur');
  await page.locator('[data-stage="1"]').click();
  check(await page.locator('#tb-source-1').getAttribute('open'), '', 'evolution stage opens its catch locations');
  check(await page.locator('#tb-slots [data-select]').count(), 4, 'shared team');
  const text = await page.locator('#tb-details').textContent();
  assert.match(text, /Lv\. 16/); assert.match(text, /Lv\. 32/);
  assert.match(text, /Pikachu starter: after the Cascade Badge/);
  assert.match(text, /Hard catch/); assert.doesNotMatch(text, /45 \/ 255/); assert.match(text, /Grass\/cave, day/); assert.match(text, /1%/);
  checks += 6;
  await page.locator('[data-select="94"]').click(); await guide('Gengar');
  assert.match(await page.locator('#tb-details').textContent(), /Level up holding Spell Tag at night/); checks++;
  check(await page.locator('#tb-details a[href$="/items/spell-tag/"]').getAttribute('href'), new URL('items/spell-tag/', base).pathname, 'item links respect base');
  await page.locator('[data-select="196"]').click(); await guide('Espeon');
  await page.locator('.tb-evolution-notes summary').click();
  assert.match(await page.locator('#tb-details').textContent(), /becomes Sylveon/); checks++;
  await page.locator('[data-select="1440"]').click(); await guide('Armored Mewtwo');
  assert.match(await page.locator('#tb-details').textContent(), /Hold Steel Armor/); checks++;
  await page.locator('#tb-search').fill('Pikachu');
  await page.locator('[data-add="25"]').click(); await guide('Pikachu');
  check(await page.locator('#tb-slots [data-select]').count(), 5, 'add');
  await page.locator('[data-add="25"]').click();
  check(await page.locator('#tb-slots [data-select]').count(), 5, 'no duplicates');
  await page.locator('#tb-search').fill('Crobat'); await page.locator('[data-add="169"]').click(); await guide('Crobat');
  await page.locator('#tb-search').fill('Bulbasaur');
  check(await page.locator('[data-add="1"]').isDisabled(), true, 'six-slot cap');
  await page.locator('[data-remove="25"]').click();
  check(await page.locator('[data-add="1"]').isEnabled(), true, 'remove frees a slot');
  await page.locator('[data-add="1"]').focus(); await page.keyboard.press('Enter'); await guide('Bulbasaur');
  await page.reload(); await guide('Venusaur');
  check(await page.locator('#tb-slots [data-select]').count(), 6, 'reload');
  await goto(''); check(await page.locator('#tb-slots [data-select]').count(), 6, 'local persistence');
  await page.locator('#tb-clear').click();
  check(await page.locator('#tb-slots [data-select]').count(), 0, 'clear');
  await page.locator('.tb-filter-disclosure > summary').click();
  await page.locator('#tb-reset').click(); await page.locator('#tb-search').fill('no-such-pokemon');
  check(await page.locator('#tb-catalog .tb-mon').count(), 0, 'no search results');
  await page.locator('#tb-reset').click(); await page.locator('#tb-type').selectOption('Poison');
  await page.locator('#tb-region').selectOption('Kanto'); await page.locator('#tb-search').fill('thick fat');
  check(await page.locator('[data-add="1"]').count(), 1, 'combined filters include hidden ability');
  await page.locator('#tb-reset').click(); await page.locator('#tb-next').click();
  assert.match(await page.locator('#tb-page').textContent(), /^Page 2 of \d+$/); checks++;
  await goto('#team=720,1243'); await guide('Hoopa');
  await page.locator('#tb-source-720 > summary').click();
  let calendar = await page.locator('.tb-calendar').textContent();
  assert.match(calendar, /Morning only/); assert.doesNotMatch(calendar, /Night only/); checks += 2;
  await page.locator('[data-select="1243"]').click(); await guide('Hoopa Unbound');
  await page.locator('#tb-source-1243 > summary').click();
  calendar = await page.locator('.tb-calendar').textContent();
  assert.match(calendar, /Night only/); assert.doesNotMatch(calendar, /Morning only/); checks += 2;
  // Failed clipboard writes reveal a manually selectable link.
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { value: { writeText: async () => { throw new Error('denied'); } }, configurable: true }));
  await page.locator('#tb-share').click();
  check(await page.locator('#tb-share-url').isVisible(), true, 'clipboard fallback');
  assert.match(await page.locator('#tb-share-url').inputValue(), /#team=720,1243$/); checks++;
  // A transient data failure must offer a retry without dropping the team.
  await context.route('**/team-builder/pokemon/3.json', route => route.abort());
  await goto('#team=3'); await page.locator('[data-retry]').waitFor();
  check(await page.locator('#tb-slots [data-select]').count(), 1, 'team survives fetch failure');
  await context.unroute('**/team-builder/pokemon/3.json'); await page.locator('[data-retry]').click(); await guide('Venusaur');
  // Quickly switching members cannot replace the latest member with a slower response.
  await goto('#team=3,94');
  await page.locator('[data-select="94"]').click(); await guide('Gengar');
  await page.locator('[data-select="3"]').click(); await guide('Venusaur');
  const layouts = [];
  for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark']) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(theme => document.documentElement.dataset.theme = theme, theme);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
    check(overflow, false, `${width}px ${theme}: no page overflow`);
    if (width < 1184) {
      await page.locator('button[data-view="guide"]').click();
      check(await page.locator('.tb-guide').isVisible(), true, 'mobile field guide tab');
      check(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${width}px ${theme}: guide fits`);
    }
    layouts.push({ width, theme, overflow });
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => { document.documentElement.dataset.theme = 'light'; scrollTo(0, 0); });
  await page.screenshot({ path: `${output}/desktop.png` });
  await page.locator('#tb-details').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${output}/acquisition.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => { document.documentElement.dataset.theme = 'dark'; scrollTo(0, 0); });
  await page.screenshot({ path: `${output}/mobile.png` });
  // The same time hint works with pointer, keyboard and touch-style clicks on any page.
  await page.locator('[data-stage="1"]').click();
  const time = page.locator('#tb-source-1 [data-time-hint="day"]').first();
  await time.hover();
  check(await page.locator('#ohg-time-tooltip').isVisible(), true, 'hover time definition');
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /10:00–19:59/); checks++;
  await page.keyboard.press('Escape'); check(await page.locator('#ohg-time-tooltip').isVisible(), false, 'Escape dismisses');
  await time.focus(); check(await page.locator('#ohg-time-tooltip').isVisible(), true, 'keyboard time definition');
  check(await time.getAttribute('aria-describedby'), 'ohg-time-tooltip', 'accessible description');
  await page.keyboard.press('Escape'); await time.click();
  check(await page.locator('#ohg-time-tooltip').isVisible(), true, 'tap time definition');
  const bounds = await page.locator('#ohg-time-tooltip').boundingBox();
  assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= 390); checks++;
  await page.screenshot({ path: `${output}/time-tooltip-mobile.png` });
  const capture = page.locator('#tb-source-1 [data-catch-hint]');
  check(await capture.getAttribute('aria-label'), 'Catch difficulty: Hard (4 of 5)', 'difficulty is named without opening the popup');
  check(await capture.locator('.filled').count(), 4, 'hard catch fills four of five bars');
  await capture.click();
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /Base value: 45 \/ 255/); checks++;
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /not a percentage/); checks++;
  await page.keyboard.press('Escape');
  await capture.blur(); await capture.focus();
  check(await capture.getAttribute('aria-describedby'), 'ohg-time-tooltip', 'keyboard catch explanation');
  await page.screenshot({ path: `${output}/catch-tooltip-mobile.png` });
  await page.keyboard.press('Escape');
  const method = page.locator('#tb-source-1 [data-encounter-hint="land"]').first();
  await method.hover();
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /Land encounters in grass or caves/); checks++;
  await page.keyboard.press('Escape');
  await method.focus();
  check(await method.getAttribute('aria-describedby'), 'ohg-time-tooltip', 'keyboard method description');
  await page.keyboard.press('Escape'); await method.click();
  check(await page.locator('#ohg-time-tooltip').isVisible(), true, 'tap method definition');
  const methodBounds = await page.locator('#ohg-time-tooltip').boundingBox();
  assert.ok(methodBounds.x >= 0 && methodBounds.x + methodBounds.width <= 390); checks++;
  await page.screenshot({ path: `${output}/method-tooltip-mobile.png` });
  for (const path of ['pokemon/bulbasaur/', 'locations/viridian-forest/', 'items/miracle-seed/']) {
    await page.goto(new URL(path, base).href);
    await page.locator('[data-encounter-hint]').first().click();
    check(await page.locator('#ohg-time-tooltip').isVisible(), true, `${path}: shared method hints`);
  }
  for (const path of ['pokemon/bulbasaur/', 'locations/viridian-forest/', 'calendar/']) {
    await page.goto(new URL(path, base).href);
    const button = page.locator('[data-time-hint]').first(); await button.click();
    check(await page.locator('#ohg-time-tooltip').isVisible(), true, `${path}: shared time hints`);
  }
  await page.goto(new URL('pokemon/espeon/', base).href);
  await page.locator('[data-catch-hint]').click();
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /Base value: 45 \/ 255/); checks++;
  await page.keyboard.press('Escape');
  await page.locator('[data-time-context="evolution"][data-time-hint="day"]').first().click();
  assert.match(await page.locator('#ohg-time-tooltip').textContent(), /04:00–19:59/); checks++;
  const denied = await browser.newContext();
  await denied.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  await denied.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } }); });
  const dp = await denied.newPage(); await dp.goto(new URL('team-builder/#team=3', base).href);
  await dp.locator('#tb-details h3').waitFor();
  assert.match(await dp.locator('#tb-save-status').textContent(), /storage is unavailable/); checks++;
  await denied.close();
  const nojs = await browser.newContext({ javaScriptEnabled: false });
  const np = await nojs.newPage(); await np.goto(new URL('team-builder/', base).href);
  check(await np.locator('noscript a').getAttribute('href'), new URL('pokemon/', base).pathname, 'no-JS fallback');
  await nojs.close();
  check(errors, [], 'no uncaught errors');
  check(analyticsRequests, [], 'local preview never requests analytics');
  writeFileSync(`${output}/browser-results.json`, JSON.stringify({ checks, layouts, errors }, null, 2));
  console.log(`Team Builder: ${checks} browser checks passed.`);
} finally { await browser.close(); }
