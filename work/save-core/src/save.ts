import { SAVE_SIZE, MIRROR_OFFSET, GENERAL_SIZE, STORAGE_OFFSET, STORAGE_SIZE, FOOTER_SIZE, PARTY_OFFSET, PARTY_STRIDE, BOXED_SIZE, PARTY_CAPACITY_OFFSET, PARTY_COUNT_OFFSET } from './layout.js';
import { applyEditorTransaction } from './transaction.js';
import { EditorError } from './errors.js';
/** Origin v4.0.3 raw save container. Native selection uses coherent general/storage
 * generations. Only the chosen general block is modified; storage stays byte-exact.
 * See work/research/save_core/native_evidence.md and the native boot matrix.
 */

export interface OriginSave {
  bytes: Uint8Array;
  generalOffset: number;
  counter: number;
  /** Both coherent generations have equal counters; native selects the first mirror. */
  tied: boolean;
  partyCount: number;
  party: Uint8Array[];
  /** Full encrypted 236-byte party records, including cached battle stats. */
  partyRecords: Uint8Array[];
}

/** CRC16-CCITT: polynomial 0x1021, seed 0xffff, no reflection/final XOR. */
export function crc16(bytes: Uint8Array): number {
  let crc = 0xffff;
  for (const byte of bytes) {
    crc ^= byte << 8;
    for (let bit = 0; bit < 8; bit++) {
      crc = ((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0)) & 0xffff;
    }
  }
  return crc;
}

function view(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}

function validateBlock(bytes: Uint8Array, offset: number, size: number, id: number): number {
  const data = view(bytes);
  const footer = offset + size - FOOTER_SIZE;
  const label = `${id === 0 ? 'General' : 'Storage'} block at 0x${offset.toString(16)}`;
  if (data.getUint32(footer + 4, true) !== size ||
      data.getUint32(footer + 8, true) !== 0x20060623 ||
      data.getUint16(footer + 12, true) !== id) {
    throw new EditorError('invalid-save', `${label} has an unsupported footer.`);
  }
  if (crc16(bytes.subarray(offset, footer)) !== data.getUint16(footer + 14, true)) {
    throw new EditorError('invalid-save', `${label} checksum failed.`);
  }
  return data.getUint32(footer, true);
}

/** Native counter comparator treats exactly FFFFFFFF -> 0 as rollover.
 * All other distinct pairs use ordinary unsigned order, including wide gaps. */
function newer(a: number, b: number): boolean {
  if(a === 0 && b === 0xffffffff) return true;
  if(a === 0xffffffff && b === 0) return false;
  return a > b;
}
/** Owns its returned bytes. Rejects incoherent generations rather than repairing
 * counters or combining independently selected mirrors. Native assertion paths
 * are intentionally not editable. */
export function readSave(input: Uint8Array): OriginSave {
  if (!(input instanceof Uint8Array) || input.length !== SAVE_SIZE) {
    throw new EditorError('invalid-save', 'Expected a raw 512 KiB Origin save (.sav).');
  }
  // Uint8Array.from also copies Node Buffers (whose slice method can alias).
  const bytes = Uint8Array.from(input);
  const generals = [0, MIRROR_OFFSET].map(base => {
    try {
      return {base, counter: validateBlock(bytes, base, GENERAL_SIZE, 0)};
    } catch (error) {
      if (error instanceof EditorError) return {base, error};
      throw error;
    }
  });
  const intact = generals.filter((block): block is {base: number; counter: number} => 'counter' in block);
  if (intact.length === 0) {
    const reasons = generals.map(block => 'error' in block ? block.error.message : '').join(' ');
    throw new EditorError('invalid-save', `Neither copy of the save is intact. ${reasons}`);
  }
  const storage = new Map<number, number>();
  for (const base of [0, MIRROR_OFFSET]) {
    try { storage.set(base, validateBlock(bytes, base + STORAGE_OFFSET, STORAGE_SIZE, 1)); }
    catch (error) { if (!(error instanceof EditorError)) throw error; }
  }
  // Follow the native ranking before testing coherence: filtering safe pairs
  // first can silently choose a different mirror in the native 2-general /
  // 1-storage artificial-zero bug. That native unsafe selection is a rejection,
  // not permission to fall through to an otherwise coherent older generation.
  const ranked = [...intact];
  if (ranked[1] && newer(ranked[1].counter, ranked[0]!.counter)) ranked.reverse();
  let selected: typeof intact[number] | undefined;
  for (const block of ranked) {
    if (intact.length === 2 && storage.size === 1 && !storage.has(block.base) && block.counter === 0) {
      throw new EditorError('invalid-save', 'Native recovery would select an invalid storage block through its artificial zero counter; editing is unsafe.');
    }
    if (storage.get(block.base) === block.counter) { selected = block; break; }
  }
  if (!selected) throw new EditorError('invalid-save', 'No coherent general/storage generation is intact; native recovery is unsafe.');
  const tied = intact.length === 2 && intact[0]!.counter === intact[1]!.counter &&
    storage.get(intact[0]!.base) === intact[0]!.counter && storage.get(intact[1]!.base) === intact[1]!.counter;
  const generalOffset = selected.base;
  const data = view(bytes);
  const capacity = data.getUint32(generalOffset + PARTY_CAPACITY_OFFSET, true);
  const partyCount = data.getUint32(generalOffset + PARTY_COUNT_OFFSET, true);
  if (capacity !== 6 || partyCount > 6) {
    throw new EditorError('invalid-save', 'Unsupported party header: expected capacity 6 and count 0–6.');
  }
  const party = Array.from({length: partyCount}, (_, slot) => {
    const start = generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
    return bytes.slice(start, start + BOXED_SIZE);
  });
  const partyRecords = Array.from({length: partyCount}, (_, slot) => {
    const start = generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
    return bytes.slice(start, start + PARTY_STRIDE);
  });
  return {bytes, generalOffset, counter: selected.counter, tied, partyCount, party, partyRecords};
}

/** Replace a boxed record or full party record plus the selected block's CRC.
 * Both source and replacement must be closed, checksummed records. Callers supply updated
 * cached party stats when changing IVs, EVs or level. A 136-byte move-only edit
 * preserves the party tail. Backup mirror and unrelated save data stay intact.
 */
export function patchPartyRecord(input: Uint8Array, slot: number, record: Uint8Array): Uint8Array {
  return applyEditorTransaction(input,[{type:'replacePartyRecord',slot,record}]).bytes;
}
