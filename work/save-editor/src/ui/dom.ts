type Child = Node | string | number | false | null | undefined;
type Attrs = Record<string, string | number | boolean | undefined | ((event: Event) => void)>;
/** Tiny element builder. `on*` keys become listeners, booleans toggle attributes. */
export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: Child[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === false) continue;
    if (typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'class') node.className = String(value);
    else if (key === 'value' && 'value' in node) (node as HTMLInputElement).value = String(value);
    else if (value === true) node.setAttribute(key, '');
    else node.setAttribute(key, String(value));
  }
  for (const child of children) if (child !== false && child !== null && child !== undefined) node.append(typeof child === 'number' ? String(child) : child);
  return node;
}
export function svg(markup: string): Element {
  const t = document.createElement('template'); t.innerHTML = markup.trim(); return t.content.firstElementChild!;
}
