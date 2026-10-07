import { EditorError } from './errors.js';
import { decodePokemon, decodeName, emptyPartyRecord } from './pokemon.js';
/** Origin v4.0.3 raw save container. Offsets verified against local fixtures.
 * Party/trainer edits use the newest intact general block. PC edits independently
 * select the newest intact storage block. Each operation preserves the other mirror
 * and unrelated blocks. Party editing also accepts damaged PC storage.
 * Equal-counter mirrors with different content and counter rollover stay rejected.
 */
const SAVE_SIZE = 0x80000;
const MIRROR_OFFSET = 0x40000;
const GENERAL_SIZE = 0xf7cc;
// Each mirror also holds a storage (PC box) block at +0xF800, 0x18408 bytes, which is accessed separately by readStorage/patchBoxRecord.
const FOOTER_SIZE = 16;
const PARTY_OFFSET = 0x98;
const PARTY_STRIDE = 236;
const BOXED_SIZE = 136;

export interface OriginSave {
  bytes: Uint8Array;
  generalOffset: number;
  counter: number;
  /** Both general blocks are intact with equal counters: reading is fine, editing is not. */
  tied: boolean;
  partyCount: number;
  party: Uint8Array[];
  /** Full encrypted 236-byte party records, including cached battle stats. */
  partyRecords: Uint8Array[];
}

/** Native rc5 chunk starts/sizes from ARM9 table 0x020f30cc. Every chunk
 * ends with a CRC16 and two padding bytes; the general block has its own CRC. */
const GENERAL_CHUNKS: readonly (readonly [number,number])[] = [[0,0x5c],[0x60,0x2c],[0x90,0x5b0],[0x644,0x864],[0xeac,0x474],[0x1324,0x80],[0x13a8,0x370],[0x171c,0x1e0],[0x1900,0x880],[0x2184,0x2f8],[0x2480,0x1400],[0x3884,0x20],[0x38a8,0x834],[0x40e0,0x460],[0x4544,0x108],[0x4650,0x620],[0x4c74,0x1c0],[0x4e38,0x170],[0x4fac,0x3ec],[0x539c,0x1694],[0x6a34,0x10],[0x6a48,0x68],[0x6ab4,0xf8],[0x6bb0,0xbc8],[0x777c,0xea0],[0x8620,0x8c0],[0x8ee4,0xff8],[0x9ee0,0x1680],[0xb564,0x688],[0xbbf0,0x28],[0xbc1c,8],[0xbc28,0x40],[0xbc6c,8],[0xbc78,8],[0xbc84,0x658],[0xc2e0,0x5fc],[0xc8e0,0x1294],[0xdb78,0xb80],[0xe6fc,0x80],[0xe780,0x134],[0xe8b8,0xf00]];
function repairChunkCrc(bytes:Uint8Array,base:number,start:number,length:number):void {
 const dv=view(bytes);for(const [offset,size] of GENERAL_CHUNKS)if(start<offset+size&&start+length>offset)dv.setUint16(base+offset+size,crc16(bytes.subarray(base+offset,base+offset+size)),true);
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

function identical(bytes: Uint8Array, start: number, other: number, size: number): boolean {
  for (let i = 0; i < size; i++) {
    if (bytes[start + i] !== bytes[other + i]) return false;
  }
  return true;
}

/** Returns independent copies; never changes the supplied byte array.
 * Picks the general block with the higher counter among the intact ones, like the
 * game falling back to its backup. Equal counters require identical general blocks.
 * Widely separated counters are rejected because wraparound order has not been established.
 * Unknown regions outside the general blocks are preserved without interpretation.
 */
export function readSave(input: Uint8Array): OriginSave {
  if (input.length !== SAVE_SIZE) {
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
  let selected = intact[0]!;
  let tied = false;
  if (intact.length === 2) {
    const [first, second] = intact as [typeof selected, typeof selected];
    if (first.counter === second.counter) {
      if (!identical(bytes, 0, MIRROR_OFFSET, GENERAL_SIZE)) {
        throw new EditorError('invalid-save', 'Save mirrors have equal counters but different content; selection is ambiguous.');
      }
      tied = true;
    } else {
      if (Math.abs(first.counter - second.counter) >= 0x80000000) {
        throw new EditorError('invalid-save', 'Save counter rollover is ambiguous and unsupported.');
      }
      if (second.counter > first.counter) selected = second;
    }
  }
  const generalOffset = selected.base;
  const data = view(bytes);
  const capacity = data.getUint32(generalOffset + 0x90, true);
  const partyCount = data.getUint32(generalOffset + 0x94, true);
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
 * The caller supplies correctly encrypted, checksummed data, including updated
 * cached party stats when changing IVs, EVs or level. A 136-byte move-only edit
 * preserves the party tail. Backup mirror and unrelated save data stay intact.
 */
export function patchPartyRecord(input: Uint8Array, slot: number, record: Uint8Array): Uint8Array {
  const save = readSave(input);
  if (!Number.isInteger(slot) || slot < 0 || slot >= save.partyCount) {
    throw new EditorError('invalid-save', 'Party slot is outside the current party.');
  }
  if (record.length !== BOXED_SIZE && record.length !== PARTY_STRIDE) {
    throw new EditorError('invalid-save', 'Expected a 136-byte boxed or 236-byte party Pokémon record.');
  }
  decodePokemon(record);
  const offset = save.generalOffset + PARTY_OFFSET + slot * PARTY_STRIDE;
  const previous = record.length === BOXED_SIZE ? save.party[slot]! : save.partyRecords[slot]!;
  if (record.every((byte, index) => byte === previous[index])) return save.bytes;
  // A changed record would make formerly identical equal-counter mirrors
  // ambiguous on reopening. Do not invent a counter update/recovery policy.
  if (save.tied) {
    throw new EditorError('invalid-save', 'Editing equal-counter mirrors is unsupported; save once in-game first.');
  }
  const data = view(save.bytes);
  save.bytes.set(record, offset);
  repairChunkCrc(save.bytes,save.generalOffset,PARTY_OFFSET+slot*PARTY_STRIDE,record.length);
  const footer = save.generalOffset + GENERAL_SIZE - FOOTER_SIZE;
  data.setUint16(footer + 14, crc16(save.bytes.subarray(save.generalOffset, footer)), true);
  return save.bytes;
}

/** Patch a bounded general-block region and repair its CRC, preserving counters.
 * Callers validate the semantic field and restrict their own writable offsets.
 */
export function patchGeneralRegion(input: Uint8Array, relativeOffset: number, replacement: Uint8Array): Uint8Array {
  if (!Number.isSafeInteger(relativeOffset) || relativeOffset < 0 || relativeOffset + replacement.length > GENERAL_SIZE - FOOTER_SIZE) {
    throw new EditorError('invalid-save', 'General-block patch is outside its data region.');
  }
  const save = readSave(input);
  const offset = save.generalOffset + relativeOffset;
  if (replacement.every((byte, index) => byte === save.bytes[offset + index])) return save.bytes;
  if (save.tied) {
    throw new EditorError('invalid-save', 'Editing equal-counter mirrors is unsupported; save once in-game first.');
  }
  const data = view(save.bytes);
  save.bytes.set(replacement, offset);
  repairChunkCrc(save.bytes,save.generalOffset,relativeOffset,replacement.length);
  const footer = save.generalOffset + GENERAL_SIZE - FOOTER_SIZE;
  data.setUint16(footer + 14, crc16(save.bytes.subarray(save.generalOffset, footer)), true);
  return save.bytes;
}

function u32(value: number): Uint8Array { const b = new Uint8Array(4); view(b).setUint32(0, value, true); return b; }
/** Append a 236-byte party record and bump the party count. */
export function addPartyRecord(input: Uint8Array, record: Uint8Array): Uint8Array {
  const save = readSave(input);
  if (save.partyCount >= 6) throw new EditorError('invalid-save', 'The party is full. Remove a Pokémon first.');
  if (record.length !== PARTY_STRIDE) throw new EditorError('invalid-save', 'Expected a 236-byte party Pokémon record.');
  decodePokemon(record);
  const withRecord = patchGeneralRegion(input, PARTY_OFFSET + save.partyCount * PARTY_STRIDE, record);
  return patchGeneralRegion(withRecord, 0x94, u32(save.partyCount + 1));
}
/** Remove one member, shift the rest up and blank the freed slot the way the game does. */
export function removePartyRecord(input: Uint8Array, slot: number): Uint8Array {
  const save = readSave(input);
  if (!Number.isInteger(slot) || slot < 0 || slot >= save.partyCount) throw new EditorError('invalid-save', 'Party slot is outside the current party.');
  if (save.partyCount <= 1) throw new EditorError('invalid-save', 'The party needs at least one Pokémon.');
  const region = new Uint8Array(save.partyCount * PARTY_STRIDE);
  save.partyRecords.filter((_, i) => i !== slot).forEach((record, i) => region.set(record, i * PARTY_STRIDE));
  region.set(emptyPartyRecord(), (save.partyCount - 1) * PARTY_STRIDE);
  const shifted = patchGeneralRegion(input, PARTY_OFFSET, region);
  return patchGeneralRegion(shifted, 0x94, u32(save.partyCount - 1));
}

/** Origin expands HGSS storage to 24 boxes, each 0x1000 bytes (30 × 136 plus padding).
 * Storage mirrors have their own counters and are selected independently of the party. */
export const BOX_COUNT = 24, BOX_CAPACITY = 30;
const STORAGE_START = 0xf800, STORAGE_SIZE = 0x18408, BOX_STRIDE = 0x1000;
export interface OriginStorage { bytes: Uint8Array; offset: number; counter: number; tied: boolean; names: (string | undefined)[]; wallpapers: number[]; boxes: Uint8Array[][] }
export function readStorage(input: Uint8Array): OriginStorage {
  if (input.length !== SAVE_SIZE) throw new EditorError('invalid-save', 'Expected a raw 512 KiB Origin save.');
  const bytes = Uint8Array.from(input);
  const intact: {offset: number; counter: number}[] = [];
  for (const base of [0, MIRROR_OFFSET]) {
    const offset = base + STORAGE_START;
    try { intact.push({offset, counter: validateBlock(bytes, offset, STORAGE_SIZE, 1)}); }
    catch (error) { if (!(error instanceof EditorError)) throw error; }
  }
  if (!intact.length) throw new EditorError('invalid-save', 'Neither PC storage block has a valid checksum.');
  let selected = intact[0]!, tied = false;
  if (intact.length === 2) {
    const second = intact[1]!;
    if (selected.counter === second.counter) {
      if (!identical(bytes, selected.offset, second.offset, STORAGE_SIZE)) throw new EditorError('invalid-save', 'PC mirrors have equal counters but different content. Save once in-game first.');
      tied = true;
    } else {
      if (Math.abs(selected.counter - second.counter) >= 0x80000000) throw new EditorError('invalid-save', 'PC save counter rollover is ambiguous.');
      if (second.counter > selected.counter) selected = second;
    }
  }
  const names = Array.from({length: BOX_COUNT}, (_, box) => decodeName(view(bytes), selected.offset + 0x18008 + box * 40, 20));
  const boxes = Array.from({length: BOX_COUNT}, (_, box) => Array.from({length: BOX_CAPACITY}, (_, slot) => {
    const start = selected.offset + box * BOX_STRIDE + slot * BOXED_SIZE;
    return bytes.slice(start, start + BOXED_SIZE);
  }));
  const wallpapers = Array.from(bytes.subarray(selected.offset + 0x183c8, selected.offset + 0x183e0));
  return {bytes, offset: selected.offset, counter: selected.counter, tied, names, wallpapers, boxes};
}
export function patchBoxRecord(input: Uint8Array, box: number, slot: number, record: Uint8Array): Uint8Array {
  if (!Number.isInteger(box) || box < 0 || box >= BOX_COUNT || !Number.isInteger(slot) || slot < 0 || slot >= BOX_CAPACITY) throw new EditorError('invalid-input', 'PC box or slot is outside storage.');
  if (record.length !== BOXED_SIZE) throw new EditorError('invalid-pokemon', 'Expected a 136-byte boxed Pokémon.');
  decodePokemon(record); // Reject corrupt or open records before writing.
  const storage = readStorage(input);
  if (record.every((byte, i) => byte === storage.boxes[box]![slot]![i])) return storage.bytes;
  if (storage.tied) throw new EditorError('invalid-save', 'Editing equal-counter PC mirrors is unsupported; save once in-game first.');
  const offset = storage.offset + box * BOX_STRIDE + slot * BOXED_SIZE;
  storage.bytes.set(record, offset);
  const dv = view(storage.bytes);
  const flags = storage.offset + 0x18004;
  dv.setUint32(flags, dv.getUint32(flags, true) | (1 << box), true);
  dv.setUint16(storage.offset+0x183f4,crc16(storage.bytes.subarray(storage.offset,storage.offset+0x183f4)),true);
  const footer = storage.offset + STORAGE_SIZE - FOOTER_SIZE;
  dv.setUint16(footer + 14, crc16(storage.bytes.subarray(storage.offset, footer)), true);
  return storage.bytes;
}
