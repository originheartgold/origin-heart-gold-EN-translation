/** Artwork comes from the PokéAPI sprites repository; nothing from the ROM is shipped. */
const BASE = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites';
export function artworkUrl(species: number, shiny: boolean): string {
  return `${BASE}/pokemon/other/home/${shiny ? 'shiny/' : ''}${species}.png`;
}
export function fallbackArtworkUrl(species: number, shiny: boolean): string {
  return `${BASE}/pokemon/other/official-artwork/${shiny ? 'shiny/' : ''}${species}.png`;
}
export function miniSpriteUrl(species: number, shiny: boolean): string {
  return `${BASE}/pokemon/${shiny ? 'shiny/' : ''}${species}.png`;
}
// In-game names are abbreviated to fit the DS; map the common ones back to PokéAPI slugs.
const ITEM_ALIASES: Record<string, string> = {
  'potion': 'potion', 'parlyz heal': 'paralyze-heal', 'exp share': 'exp-share', 'blackglasses': 'black-glasses',
  'brightpowder': 'bright-powder', 'silverpowder': 'silver-powder', 'twistedspoon': 'twisted-spoon',
  'nevermeltice': 'never-melt-ice', 'deepseatooth': 'deep-sea-tooth', 'deepseascale': 'deep-sea-scale',
  'thunderstone': 'thunder-stone', 'x defend': 'x-defense', 'x special': 'x-sp-atk', 'x sp def': 'x-sp-def',
  'kings rock': 'kings-rock', 'energypowder': 'energy-powder', 'tinymushroom': 'tiny-mushroom',
};
export function itemSlug(name: string): string {
  const plain = name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[’'.]/g, '');
  return ITEM_ALIASES[plain] ?? plain.replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}
export function itemSpriteUrl(name: string, pocket: string): string {
  if (pocket === 'tmHm') return `${BASE}/items/${name.startsWith('HM') ? 'hm-normal' : 'tm-normal'}.png`;
  return `${BASE}/items/${itemSlug(name)}.png`;
}
/** Swap to a fallback once, then to a neutral placeholder. */
export function img(src: string, alt: string, className = '', fallback?: string): HTMLImageElement {
  const node = document.createElement('img');
  node.alt = alt; node.loading = 'lazy'; node.decoding = 'async'; node.src = src;
  if (className) node.className = className;
  node.addEventListener('error', () => {
    if (fallback && node.src !== fallback) { node.src = fallback; return; }
    node.replaceWith(Object.assign(document.createElement('span'), {className: 'ph', title: alt}));
  });
  return node;
}

/** Fit the visible sprite pixels inside a PC slot, ignoring transparent padding. */
export function pcSprite(species: number, shiny: boolean): HTMLElement {
  const frame = document.createElement('span');
  frame.className = 'pc-sprite-frame';
  const sprite = img(miniSpriteUrl(species, shiny), '', 'pc-sprite');
  // Anonymous CORS allows measuring the public sprite's transparent bounds.
  sprite.crossOrigin = 'anonymous';
  sprite.addEventListener('load', () => {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = sprite.naturalWidth; canvas.height = sprite.naturalHeight;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.drawImage(sprite, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let left = canvas.width, top = canvas.height, right = -1, bottom = -1;
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
        if (pixels[(y * canvas.width + x) * 4 + 3]! > 0) {
          left = Math.min(left, x); right = Math.max(right, x);
          top = Math.min(top, y); bottom = Math.max(bottom, y);
        }
      }
      if (right < left) return;
      const width = right - left + 1, height = bottom - top + 1;
      // A nested viewBox crops padding without changing or resampling the asset.
      const ns = 'http://www.w3.org/2000/svg';
      const fitted = document.createElementNS(ns, 'svg');
      fitted.setAttribute('viewBox', `${left - 2} ${top - 2} ${width + 4} ${height + 4}`);
      fitted.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      fitted.setAttribute('aria-hidden', 'true');
      const art = document.createElementNS(ns, 'image');
      art.setAttribute('href', sprite.src);
      art.setAttribute('width', String(canvas.width)); art.setAttribute('height', String(canvas.height));
      fitted.append(art); frame.replaceChildren(fitted);
    } catch {
      // If CORS prevents measuring, the complete image still fits without clipping.
    }
  });
  frame.append(sprite);
  return frame;
}
