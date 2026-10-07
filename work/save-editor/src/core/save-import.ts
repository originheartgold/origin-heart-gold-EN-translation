import { EditorError } from './errors.js';
import { readSave } from './save.js';
import { decodePokemon } from './pokemon.js';
import { ACCEPTED_SAVE_SIZES, unwrapSave, type SaveContainer } from './save-container.js';
export interface SaveFileInput { readonly name: string; readonly size: number; arrayBuffer(): Promise<ArrayBuffer> }
export interface ImportedSave { readonly filename: string; readonly bytes: Uint8Array; readonly container: SaveContainer }
/** Validate a candidate without touching the active editing session. */
export async function importSave(file: SaveFileInput): Promise<ImportedSave> {
  if (!ACCEPTED_SAVE_SIZES.includes(file.size)) throw new EditorError('invalid-save', 'Expected a 512 KiB .sav file or a DeSmuME .dsv save. Emulator save states are unsupported.');
  let buffer: ArrayBuffer;
  try { buffer = await file.arrayBuffer(); }
  catch (cause) { throw new EditorError('read-failed', 'Could not read the selected save. Choose the file again.', undefined, {cause}); }
  const {bytes, container} = unwrapSave(new Uint8Array(buffer));
  readSave(bytes).partyRecords.forEach(decodePokemon);
  return {filename: file.name, bytes, container};
}
