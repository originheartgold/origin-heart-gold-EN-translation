// Run from the repository root against a built site and an existing Playwright installation:
// PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node site/tests/mobile-menu-browser.mjs
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
const { webkit, chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4338/';
const output = 'work/build/mobile-menu';
mkdirSync(output, { recursive: true });

// Simulate the missing HTML, JS, and CSS popover features of pre-iOS 17.
// This is a compatibility regression, not a substitute for testing a physical old iPhone.
async function withoutPopovers(context) {
  await context.addInitScript(() => {
    Object.defineProperty(HTMLElement.prototype, 'popover', {
      configurable: true,
      get() { return this.getAttribute('data-unsupported-popover'); },
      set(value) {
        if (value === null) this.removeAttribute('data-unsupported-popover');
        else this.setAttribute('data-unsupported-popover', value);
      },
    });
    delete HTMLElement.prototype.showPopover;
    delete HTMLElement.prototype.hidePopover;
    delete HTMLElement.prototype.togglePopover;
  });
  await context.route('**/*', async (route) => {
    const request = route.request();
    if (new URL(request.url()).origin !== new URL(base).origin) return route.abort();
    if (!['document', 'stylesheet'].includes(request.resourceType())) return route.continue();
    const response = await route.fetch();
    let body = await response.text();
    if (request.resourceType() === 'document') {
      body = body.replace(/<sl-sidebar-pane\b[^>]*>/g, tag => tag.replace(/\bpopover(?=[\s=>])/g, 'data-unsupported-popover'))
        .replace(/<button\b[^>]*>/g, tag => tag.replace(/\bpopovertarget=/g, 'data-unsupported-popovertarget='));
    }
    // Activate the no-popover @supports fallback in the modern test browser.
    body = body.replace(/@supports not selector\(:popover-open\)/g, '@supports (display:block)');
    await route.fulfill({ response, body });
  });
}
async function stripPopoverSelectors(page) {
  await page.evaluate(() => {
    const strip = (owner) => {
      for (let i = owner.cssRules.length - 1; i >= 0; i--) {
        const rule = owner.cssRules[i];
        if (rule.selectorText?.includes(':popover-open')) owner.deleteRule(i);
        else if (rule.cssRules) strip(rule);
      }
    };
    for (const sheet of document.styleSheets) strip(sheet);
  });
}
async function state(page) {
  return page.evaluate(() => ({
    expanded: document.querySelector('.sl-menu-button').getAttribute('aria-expanded'),
    visible: getComputedStyle(document.getElementById('starlight__sidebar')).display !== 'none',
    locked: getComputedStyle(document.body).overflow === 'hidden',
    inert: document.querySelector('.main-frame').hasAttribute('inert'),
  }));
}
async function expectState(page, open, desktop = false) {
  await page.waitForFunction(({ open, desktop }) => {
    const button = document.querySelector('.sl-menu-button');
    const sidebar = document.getElementById('starlight__sidebar');
    return button.getAttribute('aria-expanded') === String(open)
      && (getComputedStyle(sidebar).display !== 'none') === (open || desktop)
      && document.querySelector('.main-frame').hasAttribute('inert') === open
      && (getComputedStyle(document.body).overflow === 'hidden') === open;
  }, { open, desktop });
  assert.deepEqual(await state(page), { expanded: String(open), visible: open || desktop, locked: open, inert: open });
}

for (const [name, engine] of Object.entries({ webkit, chromium })) {
  const browser = await engine.launch({ headless: true });
  try {
    for (const legacy of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
      await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      if (legacy) await withoutPopovers(context);
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(new URL('faq/', base).href);
      if (legacy) await stripPopoverSelectors(page);
      const button = page.locator('.sl-menu-button');
      await expectState(page, false);
      for (let i = 0; i < 3; i++) {
        await button.tap();
        await expectState(page, true);
        await button.tap();
        await expectState(page, false);
      }
      // Closing restores actual content interactions and scrolling.
      const headingLink = page.locator('main a[href^="#"]').first();
      await headingLink.click();
      await page.evaluate(() => scrollTo(0, 600));
      await page.waitForFunction(() => scrollY > 0);
      await button.tap();
      await expectState(page, true);
      await page.screenshot({ path: `${output}/fixed-${name}-${legacy ? 'legacy' : 'native'}-open.png` });
      await page.keyboard.press('Escape');
      await expectState(page, false);
      assert.equal(await button.evaluate(element => document.activeElement === element), true);
      // A menu link targeting this page must close the drawer too.
      await button.tap();
      const link = page.locator('#starlight__sidebar a').first();
      await link.evaluate(element => element.setAttribute('href', '#_top'));
      await link.tap();
      await expectState(page, false);
      // Orientation / desktop breakpoint changes must release the old mobile lock.
      await button.tap();
      await expectState(page, true);
      await page.setViewportSize({ width: 1024, height: 768 });
      await expectState(page, false, true);
      await page.setViewportSize({ width: 390, height: 844 });
      await expectState(page, false);
      // Simulate restoring an open page from Safari's back/forward cache.
      await button.tap();
      await expectState(page, true);
      await page.evaluate(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })));
      await expectState(page, false);
      await page.screenshot({ path: `${output}/fixed-${name}-${legacy ? 'legacy' : 'native'}-closed.png` });
      assert.deepEqual(errors, []);
      console.log(`${name} ${legacy ? 'no-popover fallback' : 'native popover'}: tap, close, content, scroll, Escape, links, resize, pageshow passed`);
      await context.close();
    }
    for (const legacy of [false, true]) {
      const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, javaScriptEnabled: false });
      await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
      if (legacy) await withoutPopovers(context);
      const page = await context.newPage();
      await page.goto(new URL('faq/', base).href);
      if (legacy) {
        await stripPopoverSelectors(page);
        assert.equal(await page.locator('.sl-menu-button').isVisible(), false);
        assert.equal(await page.locator('#starlight__sidebar').evaluate(el => getComputedStyle(el).position), 'static');
        // Check a concrete content target, rather than the top of the full main
        // element (which may be above the viewport or behind the fixed header).
        await page.locator('main a[href^="#"]').first().click({ trial: true });
      } else {
        assert.equal(await page.locator('#starlight__sidebar').isVisible(), false);
        await page.locator('.sl-menu-button').tap();
        assert.equal(await page.locator('#starlight__sidebar').isVisible(), true);
        await page.locator('.sl-menu-button').tap();
        assert.equal(await page.locator('#starlight__sidebar').isVisible(), false);
      }
      console.log(`${name} JavaScript disabled, ${legacy ? 'no popovers: navigation stays in page flow' : 'native menu works'}: passed`);
      await context.close();
    }
  } finally {
    await browser.close();
  }
}
