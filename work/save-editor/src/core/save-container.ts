import { EditorError } from './errors.js';

/** Raw battery data size for HeartGold/SoulSilver (512 KiB flash). */
export const RAW_SAVE_SIZE = 524288;
// DeSmuME appends: notice text, six little-endian u32 fields, then a 16-byte cookie.
const DESMUME_NOTICE = '|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:';
const DESMUME_COOKIE = '|-DESMUME SAVE-|';
export const DESMUME_FOOTER_SIZE = DESMUME_NOTICE.length + 24 + DESMUME_COOKIE.length;
const DESMUME_PAD_SIZE_OFFSET = DESMUME_NOTICE.length + 4;

/** How the raw save was stored on disk, so downloads can be written back the same way. */
export type SaveContainer =
  | { readonly kind: 'raw' }
  | { readonly kind: 'desmume'; readonly footer: Uint8Array };
export const ACCEPTED_SAVE_SIZES: readonly number[] = [RAW_SAVE_SIZE, RAW_SAVE_SIZE + DESMUME_FOOTER_SIZE];

function ascii(bytes: Uint8Array): string { return String.fromCharCode(...bytes); }

/** Split a file into raw 512 KiB save data and its emulator container. Detection uses content, not the file extension. */
export function unwrapSave(file: Uint8Array): { readonly bytes: Uint8Array; readonly container: SaveContainer } {
  if (file.length === RAW_SAVE_SIZE) return {bytes: Uint8Array.from(file), container: {kind: 'raw'}};
  if (file.length === RAW_SAVE_SIZE + DESMUME_FOOTER_SIZE) {
    const footer = Uint8Array.from(file.subarray(RAW_SAVE_SIZE));
    const view = new DataView(footer.buffer, footer.byteOffset, footer.byteLength);
    if (ascii(footer.subarray(0, DESMUME_NOTICE.length)) === DESMUME_NOTICE
      && ascii(footer.subarray(footer.length - DESMUME_COOKIE.length)) === DESMUME_COOKIE
      && view.getUint32(DESMUME_PAD_SIZE_OFFSET, true) === RAW_SAVE_SIZE) {
      return {bytes: Uint8Array.from(file.subarray(0, RAW_SAVE_SIZE)), container: {kind: 'desmume', footer}};
    }
    throw new EditorError('invalid-save', 'This file has the size of a DeSmuME .dsv save but no valid DeSmuME footer.');
  }
  throw new EditorError('invalid-save', 'Expected a 512 KiB .sav file or a DeSmuME .dsv save. Emulator save states are unsupported.');
}

/** Rebuild the on-disk file; the DeSmuME footer is kept byte for byte. */
export function wrapSave(bytes: Uint8Array, container: SaveContainer): Uint8Array {
  if (bytes.length !== RAW_SAVE_SIZE) throw new EditorError('invalid-save', 'Save data must be exactly 512 KiB.');
  if (container.kind === 'raw') return Uint8Array.from(bytes);
  const file = new Uint8Array(RAW_SAVE_SIZE + container.footer.length);
  file.set(bytes); file.set(container.footer, RAW_SAVE_SIZE);
  return file;
}

export function saveExtension(container: SaveContainer): string { return container.kind === 'desmume' ? '.dsv' : '.sav'; }
export function containerLabel(container: SaveContainer): string { return container.kind === 'desmume' ? 'DeSmuME .dsv' : 'raw .sav'; }
