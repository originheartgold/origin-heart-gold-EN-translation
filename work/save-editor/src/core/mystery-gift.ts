/** Wonder Card file import/export. The shared core owns the save layout and writes;
 * this module only validates card payloads against the bundled Origin data. */
import { readMysteryGifts, storeWonderCard, giftTagValid, CARD_SIZE } from '../../../save-core/dist/mystery-gift.js';
import { decodePokemon } from './pokemon.js';
import { importPokemonFile } from './operations.js';
import { type BundledOriginData } from './bundled-data.js';
import { EditorError } from './errors.js';
export * from '../../../save-core/dist/mystery-gift.js';
export function exportWonderCard(bytes: Uint8Array, slot: number): string {
  const card = readMysteryGifts(bytes).cards[slot];
  if (!card || !giftTagValid(card.tag)) throw new EditorError('invalid-input', 'Choose an occupied Wonder Card.');
  return JSON.stringify({format: 'origin-heartgold-wonder-card', version: 1, bytes: [...card.bytes]}, null, 2);
}
export function importWonderCard(bytes: Uint8Array, text: string, data: BundledOriginData): Uint8Array {
  const value = JSON.parse(text);
  if (value.format !== 'origin-heartgold-wonder-card' || value.version !== 1 || !Array.isArray(value.bytes) || value.bytes.length !== CARD_SIZE
    || value.bytes.some((n: unknown) => !Number.isInteger(n) || Number(n) < 0 || Number(n) > 255)) throw new EditorError('invalid-input', 'Choose an Origin .ohgwc4 file.');
  const card = Uint8Array.from(value.bytes), cdv = new DataView(card.buffer), tag = cdv.getUint16(0, true);
  if (![1, 2, 3].includes(tag)) throw new EditorError('invalid-input', 'Only native Pokémon, Egg and Item gift imports are validated.');
  if (tag === 3) {
    const item = data.inventory.getItem(cdv.getUint32(4, true));
    if (!item || item.name.startsWith('Item #')) throw new EditorError('invalid-input', 'Unknown Origin gift item.');
  } else {
    const offset = tag === 1 ? 8 : 4, record = card.slice(offset, offset + 236);
    importPokemonFile(JSON.stringify({format: 'origin-heartgold-pokemon', version: 1, bytes: [...record]}), data);
    if (tag === 2 && !decodePokemon(record).isEgg) throw new EditorError('invalid-input', 'Egg gift does not contain an egg.');
  }
  return storeWonderCard(bytes, card);
}
