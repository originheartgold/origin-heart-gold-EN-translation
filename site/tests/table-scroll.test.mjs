import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

function fixture({ overflow = true, editor = false } = {}) {
  const listeners = {};
  const makeElement = () => ({
    attrs: {}, clientWidth: 390, scrollWidth: overflow ? 700 : 390,
    setAttribute(key, value) { this.attrs[key] = value; },
    removeAttribute(key) { delete this.attrs[key]; if (key === 'tabindex') delete this.tabIndex; },
    append(child) { this.child = child; },
    after(element) { this.afterElement = element; },
  });
  const table = {
    closest: () => editor ? {} : null,
    caption: { textContent: 'Trainer Pokémon' },
    before(element) { this.panel = element; },
  };
  const document = {
    readyState: 'complete', documentElement: { dataset: {} }, querySelector: () => null,
    querySelectorAll: selector => selector === '.sl-markdown-content table' ? [table] : [],
    createElement: makeElement,
  };
  const window = { addEventListener(name, fn) { (listeners[name] ??= []).push(fn); } };
  const location = { search: '' };
  vm.runInNewContext(readFileSync(new URL('../public/ohg.js', import.meta.url), 'utf8'), {
    document, window, location, URLSearchParams,
    localStorage: { getItem: () => null, setItem() {} },
  });
  return { table, resize() { listeners.resize?.forEach(fn => fn()); } };
}

test('overflowing reference tables are keyboard-scrollable and retain their actual table node', () => {
  const { table, resize } = fixture();
  assert.equal(table.panel.child, table);
  assert.equal(table.panel.tabIndex, 0);
  assert.equal(table.panel.attrs.role, 'region');
  assert.match(table.panel.attrs['aria-label'], /Trainer Pokémon/);
  assert.equal(table.panel.afterElement.hidden, false);
  // A wider viewport removes a redundant keyboard stop and the scroll hint.
  table.panel.clientWidth = 900;
  resize();
  assert.equal(table.panel.tabIndex, undefined);
  assert.equal(table.panel.attrs.role, undefined);
  assert.equal(table.panel.afterElement.hidden, true);
});

test('tables gain scrolling affordances when resized to a phone; embedded editor tables are untouched', () => {
  const { table, resize } = fixture({ overflow: false });
  assert.equal(table.panel.afterElement.hidden, true);
  table.panel.clientWidth = 200;
  resize();
  assert.equal(table.panel.tabIndex, 0);
  assert.equal(table.panel.afterElement.hidden, false);
  assert.equal(fixture({ editor: true }).table.panel, undefined);
});
