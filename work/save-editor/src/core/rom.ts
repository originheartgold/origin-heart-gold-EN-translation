import { EditorError } from './errors.js';
import { POCKETS, type InventoryData, type ItemMetadata } from './inventory.js';
import { readItemNames } from './item-names.js';
import { createNameCatalog, type NameCatalog } from './catalog.js';
/** Developer-only ROM reader for reproducible reference-data generation and verification. */
export interface PersonalData {
  /** HP, Attack, Defense, Speed, Special Attack, Special Defense. */
  baseStats: [number, number, number, number, number, number];
  growthRate: number;
  growthThresholds: readonly number[];
}
export interface OriginData { catalog?: NameCatalog; inventory?: InventoryData; getPersonal(speciesId: number, form: number): PersonalData }
const PERSONAL_HASH = '5652a964195ceb34ed60deb021158ed8ef301c1b479c94098b9e5fb325bb7c34';
const GROWTH_HASH = 'ce5c612e32e537da3cdf7808c3f21ab217e83a75ead56027d98a7d84bb1b55d6';
const FORMS_HASH = '72ec9e351ce206713362b699091359d4fe5fe0303f1bbee8663de8940d41bfa8';
function range(b: Uint8Array, o: number, n: number): Uint8Array {
  if (!Number.isSafeInteger(o) || !Number.isSafeInteger(n) || o < 0 || n < 0 || o > b.length - n) throw new EditorError('invalid-reference', 'Truncated or invalid ROM data.');
  return b.subarray(o, o + n);
}
function u16(b: Uint8Array, o: number): number { const v = range(b, o, 2); return v[0]! | v[1]! << 8; }
function u32(b: Uint8Array, o: number): number { const v = range(b, o, 4); return (v[0]! | v[1]! << 8 | v[2]! << 16 | v[3]! << 24) >>> 0; }
function magic(b: Uint8Array, o: number, s: string): boolean { return Array.from(range(b, o, s.length)).every((v, i) => v === s.charCodeAt(i)); }
/** Bounds-checked Nintendo DS filename/allocation table lookup. */
export function readNdsFile(rom: Uint8Array, path: string): Uint8Array {
  range(rom, 0, 0x50);
  const fnt = range(rom, u32(rom, 0x40), u32(rom, 0x44));
  const fat = range(rom, u32(rom, 0x48), u32(rom, 0x4c));
  if (fat.length % 8) throw new EditorError('invalid-reference', 'Invalid ROM allocation table.');
  const count = u16(fnt, 6);
  if (count < 1 || count > 4096) throw new EditorError('invalid-reference', 'Invalid ROM directory count.');
  range(fnt, 0, count * 8);
  const parts = path.split('/');
  if (parts.some(p => !p || p === '.' || p === '..')) throw new EditorError('invalid-reference', 'Invalid ROM path.');
  let directory = 0;
  for (let depth = 0; depth < parts.length; depth++) {
    let cursor = u32(fnt, directory * 8);
    let fileId = u16(fnt, directory * 8 + 4);
    if (cursor < count * 8) throw new EditorError('invalid-reference', 'Invalid ROM directory offset.');
    let found = false;
    while (true) {
      const tag = range(fnt, cursor++, 1)[0]!;
      if (!tag) break;
      const length = tag & 127;
      if (!length) throw new EditorError('invalid-reference', 'Invalid ROM filename.');
      const name = String.fromCharCode(...range(fnt, cursor, length)); cursor += length;
      const isDirectory = Boolean(tag & 128);
      let child = 0;
      if (isDirectory) { child = u16(fnt, cursor); cursor += 2; }
      if (name === parts[depth]) {
        if (depth === parts.length - 1 && !isDirectory) {
          const start = u32(fat, fileId * 8); return range(rom, start, u32(fat, fileId * 8 + 4) - start);
        }
        if (!isDirectory || depth === parts.length - 1 || child < 0xf000 || child - 0xf000 >= count) throw new EditorError('invalid-reference', 'Invalid ROM directory path.');
        directory = child - 0xf000; found = true; break;
      }
      if (!isDirectory) fileId++;
    }
    if (!found) throw new EditorError('invalid-reference', `ROM file not found: ${path}`);
  }
  throw new EditorError('invalid-reference', 'ROM file not found.');
}
/** Returns validated views of NARC members. */
export function readNarcMembers(bytes: Uint8Array): Uint8Array[] {
  if (!magic(bytes, 0, 'NARC') || u16(bytes, 4) !== 0xfffe || u16(bytes, 6) !== 0x0100 || u32(bytes, 8) !== bytes.length || u16(bytes, 12) !== 16) throw new EditorError('invalid-reference', 'Invalid personal data archive.');
  let cursor = 16;
  let allocation: Uint8Array | undefined; let data: Uint8Array | undefined;
  for (let block = 0; block < u16(bytes, 14); block++) {
    const size = u32(bytes, cursor + 4);
    if (size < 8) throw new EditorError('invalid-reference', 'Invalid NARC block size.');
    const chunk = range(bytes, cursor, size);
    if (magic(chunk, 0, 'BTAF')) {
      if (allocation) throw new EditorError('invalid-reference', 'Duplicate NARC allocation block.');
      allocation = chunk.subarray(8);
    } else if (magic(chunk, 0, 'GMIF')) {
      if (data) throw new EditorError('invalid-reference', 'Duplicate NARC data block.');
      data = chunk.subarray(8);
    }
    cursor += size;
  }
  if (cursor !== bytes.length || !allocation || !data) throw new EditorError('invalid-reference', 'Incomplete NARC archive.');
  const count = u16(allocation, 0);
  range(allocation, 4, count * 8);
  const result: Uint8Array[] = []; let previousEnd = 0;
  for (let i = 0; i < count; i++) {
    const start = u32(allocation, 4 + i * 8); const end = u32(allocation, 8 + i * 8);
    if (start < previousEnd) throw new EditorError('invalid-reference', 'Overlapping NARC members.');
    result.push(range(data, start, end - start)); previousEnd = end;
  }
  return result;
}
async function hash(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new Uint8Array(bytes).buffer);
  return Array.from(new Uint8Array(digest), v => v.toString(16).padStart(2, '0')).join('');
}
export async function loadOriginData(bytes: Uint8Array): Promise<OriginData> {
  const itemArchive = Uint8Array.from(readNdsFile(bytes, 'a/0/1/7'));
  if (await hash(itemArchive) !== 'e28535d77ab2c5fdb7914279b2338a354122303a864c65ed524b79f7c0648637') throw new EditorError('invalid-reference', 'Unsupported Origin item data.');
  const itemRecords = readNarcMembers(itemArchive);
  if (itemRecords.length !== 791 || itemRecords.some(r => r.length !== 34)) throw new EditorError('invalid-reference', 'Invalid Origin item records.');
  const nameBanks = readNarcMembers(readNdsFile(bytes, 'a/0/2/7'));
  const nameBank = nameBanks[219];
  if (!nameBank) throw new EditorError('invalid-reference', 'Missing Origin item names.');
  const names = readItemNames(nameBank);
  const items: ItemMetadata[] = [];
  for (let id = 1; id < itemRecords.length; id++) {
    const pocket = POCKETS.find(p => p.nativeId === ((u16(itemRecords[id]!,8) >> 7) & 15));
    if (!pocket) continue;
    items.push(Object.freeze({id,name:names[id] ?? `Item #${id}`,pocket:pocket.id}));
  }
  const itemMap = new Map(items.map(item => [item.id,item]));
  const inventory: InventoryData = Object.freeze({items:Object.freeze(items), getItem(id: number) { return itemMap.get(id); }});
  const personal = Uint8Array.from(readNdsFile(bytes, 'a/0/0/2'));
  const growth = Uint8Array.from(readNdsFile(bytes, 'a/0/0/3'));
  if (u32(bytes, 0x28) !== 0x02000000) throw new EditorError('invalid-reference', 'Unsupported ROM: expected Origin v4.0.3 ARM9 layout.');
  const arm9 = range(bytes, u32(bytes, 0x20), u32(bytes, 0x2c));
  const forms = Uint8Array.from(range(arm9, 0xfedc0, 415 * 6));
  const [personalHash, formsHash, growthHash] = await Promise.all([hash(personal), hash(forms), hash(growth)]);
  if (personalHash !== PERSONAL_HASH || formsHash !== FORMS_HASH || growthHash !== GROWTH_HASH) throw new EditorError('invalid-reference', 'Unsupported ROM data. Select an Origin HeartGold v4.0.3 Chinese or English ROM.');
  const records = readNarcMembers(personal);
  if (records.length !== 1441 || records.some(r => r.length !== 52 || r[19]! > 5)) throw new EditorError('invalid-reference', 'Invalid Origin personal records.');
  const growthRecords = readNarcMembers(growth);
  if (growthRecords.length !== 8 || growthRecords.some(r => r.length !== 404)) throw new EditorError('invalid-reference', 'Invalid Origin growth records.');
  const thresholds = growthRecords.map(r => Object.freeze(Array.from({ length: 101 }, (_, i) => u32(r, i * 4))));
  const formIndices = new Map<string, number>();
  for (let i = 0; i < 415; i++) {
    const species = u16(forms, i * 6); const target = u16(forms, i * 6 + 2); const form = forms[i * 6 + 4]!;
    if (target >= records.length) throw new EditorError('invalid-reference', 'Invalid Origin form record.');
    const key = `${species}/${form}`;
    if (!formIndices.has(key)) formIndices.set(key, target);
  }
  const moveArchive = Uint8Array.from(readNdsFile(bytes, 'extra/new_move_data.narc'));
  if (await hash(moveArchive) !== '78efc1b184a083bd88e1dc8aa4c144f166a1fa9ede6690e29470887c2f571454') throw new EditorError('invalid-reference', 'Unsupported Origin move data.');
  if (!nameBanks[739] || !nameBanks[232]) throw new EditorError('invalid-reference', 'Missing Origin move or species names.');
  const catalog = createNameCatalog(readItemNames(nameBanks[739]), readItemNames(nameBanks[232]), names, readNarcMembers(moveArchive));
  return { inventory, catalog, getPersonal(speciesId, form) {
    if (!Number.isInteger(speciesId) || speciesId < 1 || speciesId > 1025 || !Number.isInteger(form) || form < 0 || form > 255) throw new EditorError('invalid-reference', 'Unsupported species or form.');
    // Native lookup 0x020721C0 returns species for zero/unlisted forms.
    const index = form === 0 ? speciesId : (formIndices.get(`${speciesId}/${form}`) ?? speciesId);
    const r = records[index]!;
    return { baseStats: [r[0]!, r[1]!, r[2]!, r[3]!, r[4]!, r[5]!], growthRate: r[19]!, growthThresholds: thresholds[r[19]!]! };
  } };
}
