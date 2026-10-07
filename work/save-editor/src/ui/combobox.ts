import { h } from './dom.js';
export interface ComboChoice { id: number; name: string; meta?: () => Node | string; icon?: () => Node }
interface Options {
  choices: readonly ComboChoice[]; value: number | undefined; label: string;
  placeholder?: string; disabled?: boolean; id?: string; limit?: number;
  onSelect(id: number): void;
}
function normalize(value: string): string {
  return value.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[’'\s-]/g, '');
}
/** Searchable single-select. Typing filters; Enter or click commits; Escape restores. */
export function combobox(options: Options): HTMLElement {
  const current = () => options.choices.find(c => c.id === options.value)?.name ?? (options.value ? `#${options.value}` : '');
  const listId = `${options.id ?? Math.random().toString(36).slice(2)}-list`;
  const input = h('input', {type: 'text', role: 'combobox', 'aria-label': options.label, 'aria-expanded': 'false', 'aria-controls': listId,
    'aria-autocomplete': 'list', autocomplete: 'off', spellcheck: 'false', placeholder: options.placeholder ?? 'Search…', id: options.id, disabled: options.disabled});
  input.value = current();
  const list = h('ul', {class: 'combo-list', role: 'listbox', id: listId, hidden: true});
  const root = h('div', {class: 'combo'}, input, list);
  let matches: ComboChoice[] = [], active = 0;
  const indexed = options.choices.map(c => ({c, key: normalize(c.name)}));

  const paint = () => {
    list.replaceChildren();
    if (!matches.length) { list.append(h('li', {class: 'empty'}, 'No matches')); return; }
    matches.forEach((choice, i) => {
      const li = h('li', {role: 'option', 'aria-selected': String(i === active), onmousedown: (e: Event) => { e.preventDefault(); commit(choice); }},
        choice.icon?.() ?? null, h('span', {}, choice.name), choice.meta ? h('span', {class: 'meta'}, choice.meta()) : null);
      li.addEventListener('mousemove', () => { if (active !== i) { active = i; sync(); } });
      list.append(li);
    });
  };
  const sync = () => [...list.children].forEach((li, i) => {
    li.setAttribute('aria-selected', String(i === active));
    if (i === active) (li as HTMLElement).scrollIntoView({block: 'nearest'});
  });
  const filter = () => {
    const q = normalize(input.value);
    const limit = options.limit ?? 80;
    if (!q || input.value === current()) matches = options.choices.slice(0, limit);
    else {
      const starts = indexed.filter(e => e.key.startsWith(q)), contains = indexed.filter(e => !e.key.startsWith(q) && e.key.includes(q));
      matches = [...starts, ...contains].slice(0, limit).map(e => e.c);
    }
    active = Math.max(0, matches.findIndex(c => c.id === options.value));
    paint();
  };
  const open = () => { if (!list.hidden) return; list.hidden = false; input.setAttribute('aria-expanded', 'true'); filter(); input.select(); };
  const close = () => { list.hidden = true; input.setAttribute('aria-expanded', 'false'); };
  const commit = (choice: ComboChoice) => {
    close(); input.value = choice.name;
    if (choice.id !== options.value) options.onSelect(choice.id);
  };
  input.addEventListener('focus', open);
  input.addEventListener('click', open);
  input.addEventListener('input', () => { list.hidden = false; filter(); });
  input.addEventListener('blur', () => { close(); input.value = current(); });
  input.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); open();
      if (matches.length) { active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length; sync(); }
    } else if (event.key === 'Enter') {
      event.preventDefault(); const choice = matches[active]; if (!list.hidden && choice) commit(choice);
    } else if (event.key === 'Escape') { input.value = current(); close(); input.blur(); }
  });
  return root;
}
