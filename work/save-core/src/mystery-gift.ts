import { readSave } from './save.js';
import { decodeName } from './pokemon.js';
import { EditorError } from './errors.js';
import { applyEditorTransaction } from './transaction.js';
import { MG_OFFSET, MG_SIZE, MG_GIFTS, MG_GIFT_STRIDE, MG_GIFT_COUNT, MG_CARDS, MG_CARD_SIZE, MG_CARD_COUNT, MG_RECEIPTS } from './layout.js';
// Native rc5 save table entry 27 at 0x020f327c; size getter 0x0202ddd0.
export { MG_OFFSET, MG_SIZE } from './layout.js';
export const CARD_SIZE = MG_CARD_SIZE;
export const giftTagValid = (tag: number): boolean => tag > 0 && tag < 16;
export function readMysteryGifts(bytes: Uint8Array) {
  const save = readSave(bytes), raw = save.bytes.slice(save.generalOffset + MG_OFFSET, save.generalOffset + MG_OFFSET + MG_SIZE);
  const dv = new DataView(raw.buffer);
  return {
    received: Array.from({length: MG_RECEIPTS}, (_, i) => !!(raw[i >> 3]! & (1 << (i & 7)))),
    gifts: Array.from({length: MG_GIFT_COUNT}, (_, slot) => { const offset = MG_GIFTS + slot * MG_GIFT_STRIDE; return {slot, tag: dv.getUint16(offset, true), cardSlot: dv.getUint16(offset + 2, true) & 3}; }),
    cards: Array.from({length: MG_CARD_COUNT}, (_, slot) => { const offset = MG_CARDS + slot * MG_CARD_SIZE; return {slot, tag: dv.getUint16(offset, true), id: dv.getUint16(offset + 0x150, true), title: decodeName(dv, offset + 0x104, 36), bytes: raw.slice(offset, offset + MG_CARD_SIZE)}; }),
    specialTag: dv.getUint16(0x1328, true),
  };
}
export function patchGiftReceived(bytes: Uint8Array, id: number, received: boolean): Uint8Array {
  return applyEditorTransaction(bytes, [{type: 'setGiftReceived', id, received}]).bytes;
}
export function removePendingGift(bytes: Uint8Array, slot: number): Uint8Array {
  return applyEditorTransaction(bytes, [{type: 'removePendingGift', slot}]).bytes;
}
/** Native card removal clears its tag, its receipt bit and any linked pending gift. */
export function removeWonderCard(bytes: Uint8Array, slot: number): Uint8Array {
  return applyEditorTransaction(bytes, [{type: 'removeWonderCard', slot}]).bytes;
}
/** Structural insertion only: callers validate the card's payload against game data first. */
export function storeWonderCard(bytes: Uint8Array, card: Uint8Array): Uint8Array {
  if (!(card instanceof Uint8Array)) throw new EditorError('invalid-input', 'Expected a Wonder Card.');
  return applyEditorTransaction(bytes, [{type: 'storeWonderCard', card}]).bytes;
}
