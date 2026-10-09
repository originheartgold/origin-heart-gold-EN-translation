import { readSave } from './save.js';
import { EditorError } from './errors.js';
import { applyEditorTransaction } from './transaction.js';
import { DEX_OFFSET, DEX_MARKER, DEX_MAX, DEX_CAUGHT, DEX_SEEN } from './layout.js';
/** Origin rc5 native readers 0x0202a508/0x0202a554: caught +4, seen +0xcc,
 * species (id-1) bit. Save marker at general+0x13a8. Max native ID is 1025.
 * Only these verified flags are edited; gender/form/language records are preserved. */
export { DEX_OFFSET, DEX_MAX, DEX_CAUGHT, DEX_SEEN } from './layout.js';
export function readPokedex(bytes: Uint8Array): {seen: boolean[]; caught: boolean[]; seenCount: number; caughtCount: number} {
  const save = readSave(bytes);
  if (new DataView(save.bytes.buffer).getUint32(save.generalOffset + DEX_OFFSET, true) !== DEX_MARKER) throw new EditorError('invalid-save', 'Origin Pokédex marker is missing.');
  const flag = (offset: number) => Array.from({length: DEX_MAX}, (_, i) => !!(save.bytes[save.generalOffset + DEX_OFFSET + offset + (i >> 3)]! & (1 << (i & 7))));
  const seen = flag(DEX_SEEN), caught = flag(DEX_CAUGHT);
  return {seen, caught, seenCount: seen.filter(Boolean).length, caughtCount: caught.filter(Boolean).length};
}
/** Caught implies seen; unseen implies uncaught. */
export function patchPokedex(bytes: Uint8Array, species: number, changes: {seen?: boolean; caught?: boolean}): Uint8Array {
  if (!changes || typeof changes !== 'object') throw new EditorError('invalid-input', 'Invalid Pokédex flag.');
  return applyEditorTransaction(bytes, [{type: 'setPokedex', species, ...changes}]).bytes;
}
export function completePokedex(bytes: Uint8Array): Uint8Array {
  return applyEditorTransaction(bytes, [{type: 'completePokedex'}]).bytes;
}
