/** Pure URLs shared by the save editor and guide. No assets are downloaded at build time. */
export const SPRITE_BASE = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites';
export function artworkUrl(species: number, shiny: boolean): string {
  return `${SPRITE_BASE}/pokemon/other/home/${shiny ? 'shiny/' : ''}${species}.png`;
}
export function fallbackArtworkUrl(species: number, shiny: boolean): string {
  return `${SPRITE_BASE}/pokemon/other/official-artwork/${shiny ? 'shiny/' : ''}${species}.png`;
}
/** Internal form record IDs are never public artwork IDs. Without a verified form mapping,
 * use the base species and label the fallback. Invalid base IDs get no remote image. */
export function referenceArtwork(baseSpeciesId: number, formId: number) {
  if (!Number.isInteger(baseSpeciesId) || baseSpeciesId < 1 || baseSpeciesId > 1025) return null;
  return { src: artworkUrl(baseSpeciesId, false), fallback: fallbackArtworkUrl(baseSpeciesId, false), baseFallback: formId !== 0 };
}
