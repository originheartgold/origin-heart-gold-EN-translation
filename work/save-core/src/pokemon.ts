import { BOXED_SIZE, PARTY_STRIDE } from './layout.js';
import { EditorError } from './errors.js';
/** Origin v4.0.3 boxed Pokémon codec; see research-pokemon.md for native evidence. */
export type PokerusStatus = 'none' | 'infected' | 'cured';
export function isPokerusStatus(value: unknown): value is PokerusStatus {
  return value === 'none' || value === 'infected' || value === 'cured';
}
export interface PokemonMove { id: number; pp: number; ppUps: number }
import { mapStats, calculateStats, adjustCurrentHp, validateStatValues, experienceForLevel } from './stats.js';
import type { StatValues } from './stats.js';
export type { StatValues } from './stats.js';
export interface PokemonStatChanges { ivs?: StatValues; evs?: StatValues; level?: number; nature?: number }
/** Fields shared by the browser decoder and the harness's detailed decoder. */
export interface PokemonCoreFields {
  pid: number; speciesId: number; moves: PokemonMove[];

  shiny: boolean; naturalShiny: boolean; shinyOverride: boolean;
  pokerus: { status: PokerusStatus; strain: number; days: number; raw: number };
  ivs: StatValues; evs: StatValues; nature: number; form: number; experience: number; isEgg: boolean;
  party?: { level: number; currentHp: number; stats: StatValues; status: number };
}
export type Gender = 'male' | 'female' | 'genderless';
/** The browser editor's view of a record. */
export interface DecodedPokemon extends PokemonCoreFields {
  gender: Gender;
  /** Origin stores the effective ability as u16 at block B +26 and the species slot (0, 1, 2 = hidden) at block A +13. */
  ability: number; abilitySlot: number; heldItem: number;
  /** Latin-only decode of the nickname; undefined when it uses glyphs this table does not cover. */
  nickname: string | undefined;
  otName: string | undefined; tid: number; sid: number;
}
/** The harness's view: raw name code units and diagnostic header fields. */
export interface DetailedPokemon extends PokemonCoreFields {
  item: number; ability: number; fateful: boolean; otId: number; nickname: number[]; otName: number[];
  flags: number; checksumOk: boolean; badEgg: boolean; natureOverride: number; blocks: Uint8Array;
}
const STAT_KEYS = ['hp', 'attack', 'defense', 'speed', 'spAttack', 'spDefense'] as const;
function statValues(read: (index: number) => number): StatValues {
  return mapStats((_key, index) => read(index));
}

const BLOCKS = [
  [0,32,64,96],[0,32,96,64],[0,64,32,96],[0,96,32,64],
  [0,64,96,32],[0,96,64,32],[32,0,64,96],[32,0,96,64],
  [64,0,32,96],[96,0,32,64],[64,0,96,32],[96,0,64,32],
  [32,64,0,96],[32,96,0,64],[64,32,0,96],[96,32,0,64],
  [64,96,0,32],[96,64,0,32],[32,64,96,0],[32,96,64,0],
  [64,32,96,0],[96,32,64,0],[64,96,32,0],[96,64,32,0],
  [0,32,64,96],[0,32,96,64],[0,64,32,96],[0,96,32,64],
  [0,64,96,32],[0,96,64,32],[32,0,64,96],[32,0,96,64],
] as const;
function view(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
}
function crypt(payload: Uint8Array, seed: number): Uint8Array {
  const result = Uint8Array.from(payload);
  const data = view(result);
  for (let offset = 0; offset < payload.length; offset += 2) {
    seed = (Math.imul(seed, 0x41c64e6d) + 0x6073) >>> 0;
    data.setUint16(offset, data.getUint16(offset, true) ^ (seed >>> 16), true);
  }
  return result;
}
function checksum(payload: Uint8Array): number {
  const data = view(payload);
  let sum = 0;
  for (let offset = 0; offset < 128; offset += 2) sum += data.getUint16(offset, true);
  return sum & 0xffff;
}
function unpack(record: Uint8Array, diagnostic = false) {
  if (!(record instanceof Uint8Array) || (record.length !== BOXED_SIZE && record.length !== PARTY_STRIDE)) {
    throw new EditorError('invalid-pokemon', 'Expected a 136-byte boxed or 236-byte party Pokémon record.');
  }
  const header = view(record);
  const flags = header.getUint16(4, true);
  if (!diagnostic && flags !== 0) throw new EditorError('invalid-pokemon', 'Unsupported Pokémon flags: record may be open or corrupt.');
  const expected = header.getUint16(6, true);
  const payload = diagnostic && (flags & 2) ? Uint8Array.from(record.subarray(8, BOXED_SIZE)) : crypt(record.subarray(8, BOXED_SIZE), expected);
  const checksumOk = checksum(payload) === expected;
  if (!diagnostic && !checksumOk) throw new EditorError('invalid-pokemon', 'Pokémon checksum mismatch.');
  const pid = header.getUint32(0, true);
  const [a, b, c, d] = BLOCKS[(pid >>> 13) & 31]!;
  return { pid, payload, a, b, c, d, flags, checksumOk };
}
const NAME_PUNCT: Record<number, string> = {0x1de:' ',0x1ab:'!',0x1ac:'?',0x1ad:',',0x1ae:'.',0x1b3:'’',0x1be:'-',0x1bb:'♂',0x1bc:'♀',0x1c4:':'};
/** Latin-only decode of a 0xFFFF-terminated name; undefined for glyphs outside this table. */
export function decodeName(data: DataView, start: number, maxChars = 11): string | undefined {
  let name = '';
  for (let i = 0; i < maxChars; i++) {
    const code = data.getUint16(start + i * 2, true);
    if (code === 0xffff) break;
    if (code >= 0x121 && code <= 0x12a) name += String.fromCharCode(48 + code - 0x121);
    else if (code >= 0x12b && code <= 0x144) name += String.fromCharCode(65 + code - 0x12b);
    else if (code >= 0x145 && code <= 0x15e) name += String.fromCharCode(97 + code - 0x145);
    else if (code >= 0x15f && code <= 0x19e) name += String.fromCharCode(192 + code - 0x15f);
    else if (NAME_PUNCT[code] !== undefined) name += NAME_PUNCT[code];
    else return undefined;
  }
  return name.trim() || undefined;
}
const NAME_CODES: Record<string, number> = Object.fromEntries(Object.entries(NAME_PUNCT).map(([code, ch]) => [ch, Number(code)]));
/** Encode up to ten characters plus the 0xFFFF terminator into 22 bytes; unsupported characters are dropped. */
export function encodeName(name: string): Uint8Array {
  const out = new Uint8Array(22); const dv = view(out);
  let n = 0;
  for (const ch of name) {
    if (n >= 10) break;
    const c = ch.charCodeAt(0);
    let code: number | undefined;
    if (c >= 48 && c <= 57) code = 0x121 + c - 48;
    else if (c >= 65 && c <= 90) code = 0x12b + c - 65;
    else if (c >= 97 && c <= 122) code = 0x145 + c - 97;
    else if (c >= 192 && c <= 255) code = 0x15f + c - 192;
    else code = NAME_CODES[ch];
    if (code !== undefined) dv.setUint16(2 * n++, code, true);
  }
  dv.setUint16(2 * n, 0xffff, true);
  return out;
}
export function decodePokemon(record: Uint8Array): DecodedPokemon {
  const d = decodeRecord(record, false);
  const { payload, a, b, c, d: dBlock } = unpack(record);
  const data = view(payload), genderBits = data.getUint8(b + 24);
  return {pid:d.pid,speciesId:d.speciesId,
    gender: (genderBits & 4) ? 'genderless' : (genderBits & 2) ? 'female' : 'male',
    moves:d.moves,shiny:d.shiny,naturalShiny:d.naturalShiny,shinyOverride:d.shinyOverride,pokerus:d.pokerus,ivs:d.ivs,evs:d.evs,nature:d.nature,form:d.form,experience:d.experience,
    ability: d.ability, abilitySlot: data.getUint8(a + 13), heldItem: d.item,
    nickname: decodeName(data, c), otName: decodeName(data, dBlock, 8), tid: d.otId & 0xffff, sid: d.otId >>> 16,
    isEgg:d.isEgg,...(d.party?{party:d.party}:{})};
}
export function decodePokemonDetails(record: Uint8Array): DetailedPokemon { return decodeRecord(record, false); }
/** Diagnostic read only: open and corrupt RAM snapshots must never enter a writer. */
export function decodePokemonDiagnostic(record: Uint8Array): DetailedPokemon {
  return decodeRecord(record, true);
}
function decodeRecord(record: Uint8Array, diagnostic: boolean): DetailedPokemon {
  const { pid, payload, a, b, c, d, flags, checksumOk } = unpack(record, diagnostic);
  const data = view(payload);
  const ivWord = data.getUint32(b + 16, true);
  const natureOverride = (data.getUint32(b + 20, true) >>> 25) & 63;
  const trainer = data.getUint32(a + 4, true);
  const naturalShiny = ((trainer >>> 16) ^ (trainer & 65535) ^ (pid >>> 16) ^ (pid & 65535)) < 8;
  const shinyOverride = (data.getUint32(b + 20, true) >>> 31) !== 0;
  const tail = record.length === PARTY_STRIDE ? view(diagnostic && (flags & 1) ? record.subarray(BOXED_SIZE) : crypt(record.subarray(BOXED_SIZE), pid)) : undefined;
  const blocks = new Uint8Array(128);
  [a,b,c,d].forEach((offset,index) => blocks.set(payload.subarray(offset,offset+32),index*32));
  return {
    item: data.getUint16(a + 2, true), ability: data.getUint16(b + 26, true),
    fateful: (data.getUint8(b + 24) & 1) !== 0, otId: trainer,
    nickname: Array.from({length:11}, (_,i) => data.getUint16(c + 2*i,true)),
    otName: Array.from({length:8}, (_,i) => data.getUint16(d + 2*i,true)),
    flags, checksumOk, badEgg: (flags & 4) !== 0, natureOverride, blocks,
    pokerus: { raw: payload[d + 26]!, strain: payload[d + 26]! >>> 4, days: payload[d + 26]! & 15,
      status: (payload[d + 26]! & 15) ? 'infected' : (payload[d + 26]! >>> 4) ? 'cured' : 'none' },
    pid, shiny: naturalShiny || shinyOverride, naturalShiny, shinyOverride,
    ivs: statValues(i => (ivWord >>> (5 * i)) & 31),
    evs: statValues(i => data.getUint8(a + 16 + i)),
    nature: natureOverride ? natureOverride - 1 : pid % 25,
    form: data.getUint8(b + 24) >>> 3,
    experience: data.getUint32(a + 8, true),
    isEgg: (ivWord & 0x40000000) !== 0,
    ...(tail ? { party: {
      level: tail.getUint8(4), currentHp: tail.getUint16(6, true),
      status: tail.getUint32(0, true), stats: statValues(i => tail.getUint16(8 + i * 2, true)),
    }} : {}),
    speciesId: data.getUint16(a, true),
    moves: Array.from({length: 4}, (_, i) => ({
      id: data.getUint16(b + i * 2, true), pp: data.getUint8(b + 8 + i), ppUps: data.getUint8(b + 12 + i),
    })),
  };
}
/** Change four complete move slots; all other plaintext and party-tail bytes survive. */
export function patchPokemonMoves(record: Uint8Array, moves: readonly PokemonMove[]): Uint8Array {
  const { payload, b } = unpack(record);
  if (!Array.isArray(moves) || moves.length !== 4) throw new EditorError('invalid-pokemon', 'Exactly four move slots are required.');
  const data = view(payload);
  for (let i = 0; i < 4; i++) {
    const move = moves[i];
    if (!move || !Number.isInteger(move.id) || move.id < 0 || move.id > 65535 ||
        !Number.isInteger(move.pp) || move.pp < 0 || move.pp > 255 ||
        !Number.isInteger(move.ppUps) || move.ppUps < 0 || move.ppUps > 3) {
      throw new EditorError('invalid-pokemon', 'Invalid move ID, PP, or PP Ups.');
    }
    data.setUint16(b + i * 2, move.id, true);
    payload[b + 8 + i] = move.pp;
    payload[b + 12 + i] = move.ppUps;
  }
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** Update independently selected training inputs, then recalculate encrypted party stats. */
export function patchPokemonStats(
  record: Uint8Array, changes: PokemonStatChanges,
  personal: { baseStats: readonly [number, number, number, number, number, number]; growthRate: number },
  growthThresholds?: readonly number[],
): Uint8Array {
  const decoded = decodePokemon(record);
  if (!changes || typeof changes !== 'object' || Array.isArray(changes)) throw new EditorError('invalid-pokemon', 'Invalid stat changes.');
  for (const key of Object.keys(changes)) {
    if (!['ivs','evs','level','nature'].includes(key)) throw new EditorError('invalid-pokemon', `Unknown stat field: ${key}.`);
    if ((changes as unknown as Record<string,unknown>)[key] === null) throw new EditorError('invalid-pokemon', `Null stat field: ${key}.`);
  }
  if (!personal || typeof personal !== 'object') throw new EditorError('invalid-reference','Personal data unavailable.');
  // Boxed records have no cached level: derive it from experience on the growth curve.
  const storedLevel = decoded.party?.level ?? (() => {
    // Validate the bundled curve only for boxed records; party IV/nature edits
    // use their cached level and never required growth data.
    experienceForLevel(1, personal.growthRate, growthThresholds);
    return levelForExperience(decoded.experience, growthThresholds!);
  })();
  const ivs = changes.ivs ?? decoded.ivs;
  const evs = changes.evs ?? decoded.evs;
  const level = changes.level ?? storedLevel;
  const nature = changes.nature ?? decoded.nature;
  validateStatValues(ivs, 'IV');
  validateStatValues(evs, 'EV');
  if (!Number.isInteger(level) || level < 1 || level > 100) throw new EditorError('invalid-pokemon', 'Level must be 1–100.');
  if (!Number.isInteger(nature) || nature < 0 || nature > 24) throw new EditorError('invalid-pokemon', 'Unsupported nature.');
  const unchanged = STAT_KEYS.every(key => ivs[key] === decoded.ivs[key] && evs[key] === decoded.evs[key]) &&
    level === storedLevel && nature === decoded.nature;
  if (unchanged) return Uint8Array.from(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Egg stat editing is unsupported.');
  const { payload, a, b, pid } = unpack(record);
  const data = view(payload);
  let ivWord = data.getUint32(b + 16, true) & 0xc0000000;
  STAT_KEYS.forEach((key, index) => {
    ivWord |= ivs[key] << (index * 5);
    data.setUint8(a + 16 + index, evs[key]);
  });
  data.setUint32(b + 16, ivWord >>> 0, true);
  if (nature !== decoded.nature) {
    const original = data.getUint32(b + 20, true);
    data.setUint32(b + 20, ((original & 0x81ffffff) | ((nature + 1) << 25)) >>> 0, true);
  }
  if (level !== storedLevel) data.setUint32(a + 8, experienceForLevel(level, personal.growthRate, growthThresholds), true);
  if (!decoded.party) return seal(record, payload);
  const stats = calculateStats(personal.baseStats, ivs, evs, level, nature, decoded.speciesId);
  const tailBytes = crypt(record.subarray(BOXED_SIZE), pid);
  const tail = view(tailBytes);
  tail.setUint8(4, level);
  tail.setUint16(6, adjustCurrentHp(decoded.party.currentHp, decoded.party.stats.hp, stats.hp, decoded.speciesId), true);
  STAT_KEYS.forEach((key, index) => tail.setUint16(8 + index * 2, stats[key], true));
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  result.set(crypt(tailBytes, pid), BOXED_SIZE);
  return result;
}

/** Origin's native override avoids changing PID, gender, nature or ability. */
export function patchPokemonShiny(record: Uint8Array, shiny: boolean): Uint8Array {
  if (typeof shiny !== 'boolean') throw new EditorError('invalid-pokemon', 'Choose a shiny state.');
  const decoded = decodePokemon(record);
  if (shiny === decoded.shiny) return Uint8Array.from(record);
  if (!shiny && decoded.naturalShiny) throw new EditorError('invalid-pokemon', 'This Pokémon is naturally shiny. Removing that would require changing its identity and is not supported.');
  const { payload, b } = unpack(record);
  const data = view(payload);
  const word = data.getUint32(b + 20, true);
  data.setUint32(b + 20, (shiny ? word | 0x80000000 : word & 0x7fffffff) >>> 0, true);
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

/** Change native infection state; retain existing strain, with a one-day new infection. */
export function patchPokemonPokerus(record: Uint8Array, status: PokerusStatus): Uint8Array {
  if (!isPokerusStatus(status)) throw new EditorError('invalid-pokemon', 'Choose None, Infected or Cured for Pokérus.');
  const decoded = decodePokemon(record);
  if (decoded.pokerus.status === status) return Uint8Array.from(record);
  const { payload, d } = unpack(record);
  const strain = decoded.pokerus.strain || 1;
  payload[d + 26] = status === 'none' ? 0 : (strain << 4) | (status === 'infected' ? 1 : 0);
  const result = Uint8Array.from(record);
  const sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}

export interface PokemonFixtureChanges {
  species?: number; item?: number; ability?: number; form?: number; fateful?: boolean;
  moves?: readonly number[]; pp?: readonly number[]; exp?: number; currentHp?: number; otId?: number;
  friendship?: number; status?: number;
}
function fixtureInteger(value: unknown, maximum: number, label: string): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) {
    throw new EditorError('invalid-pokemon', `${label} must be an integer from 0 to ${maximum}.`);
  }
}
/** Harness fixture edit with explicit stale-cache semantics. Never repairs corrupt records.
 * Partial moves replace only supplied slots, default PP to 10, and preserve PP Ups.
 * Unknown species/items/moves remain usable in bounded fixtures without reference metadata.
 */
export function patchPokemonFixture(record: Uint8Array, changes: PokemonFixtureChanges, options: {tailPolicy: 'preserve'}): Uint8Array {
  if (!options || options.tailPolicy !== 'preserve') throw new EditorError('invalid-input', 'Fixture edits require explicit preserve tail policy.');
  if (!changes || typeof changes !== 'object' || Array.isArray(changes)) throw new EditorError('invalid-input', 'Expected fixture changes.');
  const known = ['species','item','ability','form','fateful','moves','pp','exp','currentHp','otId','friendship','status'];
  for (const key of Object.keys(changes)) if (!known.includes(key)) throw new EditorError('invalid-input', `Unknown Pokémon field: ${key}.`);
  const {pid, payload, a, b} = unpack(record);
  const data = view(payload);
  for (const [key, offset, max] of [['species',a,65535],['item',a+2,65535],['ability',b+26,65535],['exp',a+8,0xffffffff],['otId',a+4,0xffffffff]] as const) {
    const value = changes[key];
    if (value !== undefined) {
      fixtureInteger(value,max,key);
      if (max === 65535) data.setUint16(offset,value,true); else data.setUint32(offset,value,true);
    }
  }
  if (changes.friendship !== undefined) { fixtureInteger(changes.friendship,255,'Friendship'); payload[a+12] = changes.friendship; }
  if (changes.form !== undefined) {
    fixtureInteger(changes.form,31,'Form'); payload[b+24] = (payload[b+24]! & 7) | (changes.form << 3);
  }
  if (changes.fateful !== undefined) {
    if (typeof changes.fateful !== 'boolean') throw new EditorError('invalid-pokemon','Fateful state must be boolean.');
    payload[b+24] = (payload[b+24]! & 254) | Number(changes.fateful);
  }
  if (changes.moves !== undefined) {
    if (!Array.isArray(changes.moves) || changes.moves.length > 4) throw new EditorError('invalid-pokemon','At most four move slots are allowed.');
    if (changes.pp !== undefined && (!Array.isArray(changes.pp) || changes.pp.length !== changes.moves.length)) throw new EditorError('invalid-pokemon','PP must match the supplied move slots.');
    Array.from(changes.moves).forEach((id,i) => {
      fixtureInteger(id,65535,'Move'); const pp = changes.pp === undefined ? 10 : changes.pp[i]; fixtureInteger(pp,255,'PP');
      data.setUint16(b+2*i,id,true); payload[b+8+i] = pp;
    });
  } else if (changes.pp !== undefined) {
    if (!Array.isArray(changes.pp) || changes.pp.length > 4) throw new EditorError('invalid-pokemon','At most four PP slots are allowed.');
    Array.from(changes.pp).forEach((pp,i) => { fixtureInteger(pp,255,'PP'); payload[b+8+i] = pp; });
  }
  const result = Uint8Array.from(record);
  if (changes.currentHp !== undefined || changes.status !== undefined) {
    if (changes.currentHp !== undefined) fixtureInteger(changes.currentHp,65535,'Current HP');
    if (changes.status !== undefined) fixtureInteger(changes.status,0xffffffff,'Status');
    if (record.length !== PARTY_STRIDE) throw new EditorError('invalid-pokemon','HP and status require a party record.');
    const tail = crypt(record.subarray(BOXED_SIZE),pid), tv = view(tail);
    if (changes.status !== undefined) tv.setUint32(0,changes.status,true);
    if (changes.currentHp !== undefined) tv.setUint16(6,changes.currentHp,true);
    result.set(crypt(tail,pid),BOXED_SIZE);
  }
  const sum = checksum(payload); view(result).setUint16(6,sum,true); result.set(crypt(payload,sum),8);
  return result;
}

/** Native ZeroMonData-shaped empty slot. This is not a playable Pokémon constructor. */
export function emptyPokemonFixture(): Uint8Array {
  const record=new Uint8Array(PARTY_STRIDE);
  record.set(crypt(new Uint8Array(128),0),8);
  record.set(crypt(new Uint8Array(PARTY_STRIDE - BOXED_SIZE),0),BOXED_SIZE);
  return record;
}

/** Re-encrypt a changed plaintext payload; header PID, flags and any party tail are kept. */
function seal(record: Uint8Array, payload: Uint8Array): Uint8Array {
  const result = Uint8Array.from(record), sum = checksum(payload);
  view(result).setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  return result;
}
/** Highest level whose growth threshold the experience reaches (1–100). */
export function levelForExperience(experience: number, thresholds: readonly number[]): number {
  let level = 1;
  for (let n = 2; n <= 100; n++) if (experience >= thresholds[n]!) level = n;
  return level;
}
type Personal = { baseStats: readonly [number, number, number, number, number, number]; growthRate: number; growthThresholds: readonly number[] };
function genderFromRatio(pid: number, genderRatio: number): Gender {
  return genderRatio === 255 ? 'genderless' : genderRatio === 254 || (genderRatio !== 0 && (pid & 255) < genderRatio) ? 'female' : 'male';
}
function genderBits(gender: Gender): number { return gender === 'female' ? 2 : gender === 'genderless' ? 4 : 0; }
/** Genders a species with this personal gender ratio can have. */
export function possibleGenders(ratio: number): Gender[] {
  if (ratio === 255) return ['genderless'];
  if (ratio === 254) return ['female'];
  if (ratio === 0) return ['male'];
  return ['male', 'female'];
}
function formInRange(form: number): void {
  if (!Number.isInteger(form) || form < 0 || form > 31) throw new EditorError('invalid-input', 'Unsupported species form.');
}

/** Change only this record's species, retaining its identity and training. Callers
 * check that the species/form pair exists in the game's form table. */
export function patchPokemonSpecies(record: Uint8Array, speciesId: number, name: string, personal: Personal,
  previousThresholds: readonly number[], genderRatio: number, form = 0): Uint8Array {
  const mon = decodePokemon(record);
  if (!Number.isInteger(speciesId) || speciesId < 1 || speciesId > 1025) throw new EditorError('invalid-input', 'Choose a supported species.');
  if (mon.isEgg) throw new EditorError('invalid-pokemon', 'Hatch the egg before changing species.');
  formInRange(form);
  if (mon.speciesId === speciesId && mon.form === form) return Uint8Array.from(record);
  const level = mon.party?.level ?? levelForExperience(mon.experience, previousThresholds);
  const {payload, a, b, c, pid} = unpack(record);
  const dv = view(payload);
  dv.setUint16(a, speciesId, true);
  dv.setUint32(a + 8, experienceForLevel(level, personal.growthRate, personal.growthThresholds), true);
  // Forms do not transfer between species. Gender follows the new species and existing PID.
  payload[b + 24] = (form << 3) | (payload[b + 24]! & 1) | genderBits(genderFromRatio(pid, genderRatio));
  if (!(dv.getUint32(b + 16, true) & 0x80000000)) payload.set(encodeName(name), c);
  const result = seal(record, payload);
  if (mon.party) {
    const tailBytes = crypt(record.subarray(BOXED_SIZE), pid), tail = view(tailBytes);
    const stats = calculateStats(personal.baseStats, mon.ivs, mon.evs, level, mon.nature, speciesId);
    tail.setUint16(6, adjustCurrentHp(mon.party.currentHp, mon.party.stats.hp, stats.hp, speciesId), true);
    STAT_KEYS.forEach((key, i) => tail.setUint16(8 + i * 2, stats[key], true));
    result.set(crypt(tailBytes, pid), BOXED_SIZE);
  }
  return result;
}

/** Edit stored Gen IV gender bits; PID, form, nature and shininess remain unchanged. */
export function patchPokemonGender(record: Uint8Array, gender: Gender, genderRatio: number): Uint8Array {
  const mon = decodePokemon(record);
  if (!possibleGenders(genderRatio).includes(gender)) throw new EditorError('invalid-input', 'That gender is not possible for this species.');
  if (mon.isEgg) throw new EditorError('invalid-pokemon', 'Hatch the egg before changing gender.');
  if (mon.gender === gender) return Uint8Array.from(record);
  const {payload, b} = unpack(record);
  payload[b + 24] = (payload[b + 24]! & ~6) | genderBits(gender);
  return seal(record, payload);
}

export const ABILITY_MAX = 326;
/** Write the ability ID (block B +26). When it is one of the species' own abilities,
 * also record that slot (block A +13) so evolution keeps the same slot. A custom
 * ability leaves the slot byte alone. PID, nature and everything else is untouched. */
export function patchPokemonAbility(record: Uint8Array, ability: number, slot?: number): Uint8Array {
  if (!Number.isInteger(ability) || ability < 1 || ability > ABILITY_MAX) throw new EditorError('invalid-pokemon', 'Choose a valid ability.');
  if (slot !== undefined && (!Number.isInteger(slot) || slot < 0 || slot > 2)) throw new EditorError('invalid-pokemon', 'Ability slot must be 0, 1 or 2.');
  const decoded = decodePokemon(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Eggs cannot have their ability changed.');
  if (decoded.ability === ability && (slot === undefined || decoded.abilitySlot === slot)) return Uint8Array.from(record);
  const { payload, a, b } = unpack(record);
  view(payload).setUint16(b + 26, ability, true);
  if (slot !== undefined) payload[a + 13] = slot;
  return seal(record, payload);
}

/** Held item lives at block A +2. 0 clears it. */
export function patchPokemonHeldItem(record: Uint8Array, item: number): Uint8Array {
  if (!Number.isInteger(item) || item < 0 || item > 790) throw new EditorError('invalid-pokemon', 'Choose a valid item.');
  const decoded = decodePokemon(record);
  if (decoded.isEgg) throw new EditorError('invalid-pokemon', 'Eggs cannot hold items.');
  if (decoded.heldItem === item) return Uint8Array.from(record);
  const { payload, a } = unpack(record);
  view(payload).setUint16(a + 2, item, true);
  return seal(record, payload);
}

/** What the game writes into an unused party slot: an all-zero record, encrypted with seed 0. */
export function emptyPartyRecord(): Uint8Array { return emptyPokemonFixture(); }

export interface NewPokemon {
  speciesId: number; form?: number; level: number; nature: number; shiny: boolean;
  gender: Gender;
  ability: number; abilitySlot: number;
  ivs: StatValues; moves: readonly { id: number; pp: number }[]; name: string;
  /** From the species' personal data. */
  genderRatio: number; baseFriendship: number;
  personal: Personal;
}
/** Build a fresh party record. Trainer data (OT ID/name, language, origin game, met
 * location, ribbon/mail tail) is copied from `template`, an existing party member,
 * so the new Pokémon belongs to this save's player. PID is chosen to match nature
 * and gender without being naturally shiny; shiny uses Origin's override bit.
 * Callers check that the species/form pair exists in the game's form table. */
export function createPokemon(template: Uint8Array, spec: NewPokemon, random: () => number = Math.random, now = new Date()): Uint8Array {
  if (template.length !== PARTY_STRIDE) throw new EditorError('invalid-pokemon', 'A party Pokémon is needed as the trainer template.');
  const integer = (v: number, min: number, max: number, label: string) => {
    if (!Number.isInteger(v) || v < min || v > max) throw new EditorError('invalid-input', `${label} must be ${min}–${max}.`);
  };
  integer(spec.speciesId, 1, 1025, 'Species'); integer(spec.level, 1, 100, 'Level'); integer(spec.nature, 0, 24, 'Nature');
  integer(spec.ability, 1, ABILITY_MAX, 'Ability'); integer(spec.abilitySlot, 0, 2, 'Ability slot');
  validateStatValues(spec.ivs, 'IV');
  if (!Array.isArray(spec.moves) || spec.moves.length > 4) throw new EditorError('invalid-input', 'Choose up to four moves.');
  for (const m of spec.moves) { integer(m.id, 1, 920, 'Move'); integer(m.pp, 0, 255, 'PP'); }
  const form = spec.form ?? 0;
  formInRange(form);
  const r = spec.genderRatio;
  const allowed = r === 255 ? 'genderless' : r === 254 ? 'female' : r === 0 ? 'male' : undefined;
  if (allowed ? spec.gender !== allowed : spec.gender === 'genderless') throw new EditorError('invalid-input', 'That gender is not possible for this species.');

  const source = unpack(template);
  const sourceView = view(source.payload);
  const otId = sourceView.getUint32(source.a + 4, true);
  let pid = 0;
  for (let tries = 0; ; tries++) {
    if (tries > 1_000_000) throw new EditorError('invalid-pokemon', 'Could not find a matching personality value.');
    pid = Math.floor(random() * 0x100000000) >>> 0;
    if (pid % 25 !== spec.nature) continue;
    if (((otId >>> 16) ^ (otId & 0xffff) ^ (pid >>> 16) ^ (pid & 0xffff)) < 8) continue;
    if (!allowed) { const female = (pid & 0xff) < r; if (female !== (spec.gender === 'female')) continue; }
    break;
  }
  const [a, b, c, d] = BLOCKS[(pid >>> 13) & 31]!;
  const payload = new Uint8Array(128); const data = view(payload);
  // Block A
  data.setUint16(a, spec.speciesId, true);
  data.setUint32(a + 4, otId, true);
  data.setUint32(a + 8, experienceForLevel(spec.level, spec.personal.growthRate, spec.personal.growthThresholds), true);
  payload[a + 12] = spec.baseFriendship;
  payload[a + 13] = spec.abilitySlot;
  payload[a + 15] = source.payload[source.a + 15]!;
  // Block B
  spec.moves.forEach((m, i) => { data.setUint16(b + i * 2, m.id, true); payload[b + 8 + i] = m.pp; });
  let ivWord = 0;
  STAT_KEYS.forEach((key, i) => { ivWord |= spec.ivs[key] << (i * 5); });
  data.setUint32(b + 16, ivWord >>> 0, true);
  data.setUint32(b + 20, spec.shiny ? 0x80000000 : 0, true);
  payload[b + 24] = (form << 3) | genderBits(spec.gender);
  data.setUint16(b + 26, spec.ability, true);
  payload.set(source.payload.subarray(source.b + 28, source.b + 32), b + 28);
  // Block C
  payload.set(encodeName(spec.name), c);
  payload[c + 23] = source.payload[source.c + 23]!;
  // Block D
  payload.set(source.payload.subarray(source.d, source.d + 32), d);
  payload.fill(0, d + 16, d + 19);
  payload[d + 19] = now.getFullYear() % 100; payload[d + 20] = now.getMonth() + 1; payload[d + 21] = now.getDate();
  payload[d + 22] = 0; payload[d + 23] = 0; payload[d + 26] = 0;
  payload[d + 27] = 4; payload[d + 30] = 4; // Poké Ball
  payload[d + 28] = (spec.level & 0x7f) | (source.payload[source.d + 28]! & 0x80);
  payload[d + 31] = 0;
  // Party tail: battle stats, then the template's mail/capsule bytes.
  const evs = mapStats(() => 0);
  const stats = calculateStats(spec.personal.baseStats, spec.ivs, evs, spec.level, spec.nature, spec.speciesId);
  const tail = new Uint8Array(PARTY_STRIDE - BOXED_SIZE); const tv = view(tail);
  tail[4] = spec.level;
  tv.setUint16(6, stats.hp, true);
  STAT_KEYS.forEach((key, i) => tv.setUint16(8 + i * 2, stats[key], true));
  tail.set(crypt(template.subarray(BOXED_SIZE), source.pid).subarray(20), 20);

  const result = new Uint8Array(PARTY_STRIDE); const rv = view(result);
  const sum = checksum(payload);
  rv.setUint32(0, pid, true); rv.setUint16(6, sum, true);
  result.set(crypt(payload, sum), 8);
  result.set(crypt(tail, pid), BOXED_SIZE);
  decodePokemon(result);
  return result;
}

/** Update this Pokémon's original trainer fields, preserving PID and party battle data. */
export function patchPokemonOT(record: Uint8Array, changes: {name?: string; tid?: number; sid?: number}): Uint8Array {
  const {payload, a, d} = unpack(record);
  const dv = view(payload);
  for (const key of ['tid', 'sid'] as const) {
    const value = changes[key];
    if (value !== undefined) {
      if (!Number.isInteger(value) || value < 0 || value > 65535) throw new EditorError('invalid-input', `${key === 'tid' ? 'Trainer ID' : 'Secret ID'} must be 0–65535.`);
      dv.setUint16(a + (key === 'tid' ? 4 : 6), value, true);
    }
  }
  if (changes.name !== undefined) {
    const name = changes.name;
    if (typeof name !== 'string' || !name.trim() || [...name].length > 7) throw new EditorError('invalid-input', 'OT name must contain 1–7 characters.');
    const encoded = encodeName(name).slice(0, 16);
    if (decodeName(view(encoded), 0, 8) !== name) throw new EditorError('invalid-input', 'OT name contains unsupported characters or surrounding spaces.');
    payload.set(encoded, d);
  }
  return seal(record, payload);
}

export interface PokemonMetadata {
 nickname: string | undefined; nicknamed: boolean; friendship: number; markings: number; language: number;
 originGame: number; otGender: 'male' | 'female'; ball: number; metLevel: number; metLocation: number; eggLocation: number;
 metDate: string; eggDate: string; encounterType: number; fateful: boolean; ribbons: [number, number, number];
}
function storedDate(payload: Uint8Array, offset: number): string {
 return payload[offset + 1] ? `${2000 + payload[offset]!}-${String(payload[offset+1]).padStart(2,'0')}-${String(payload[offset+2]).padStart(2,'0')}` : '';
}
export function readPokemonMetadata(record: Uint8Array): PokemonMetadata {
 const {payload,a,b,c,d} = unpack(record), dv = view(payload);
 const location = (newOffset:number,oldOffset:number) => { const n=dv.getUint16(newOffset,true); return n && n!==3002 ? n : dv.getUint16(oldOffset,true); };
 return {nickname:decodeName(dv,c),nicknamed:!!(dv.getUint32(b+16,true)&0x80000000),friendship:payload[a+12]!,markings:payload[a+14]!,language:payload[a+15]!,
 originGame:payload[c+23]!,otGender:payload[d+28]!&128?'female':'male',ball:payload[d+30]!||payload[d+27]!,metLevel:payload[d+28]!&127,
 metLocation:location(b+30,d+24),eggLocation:location(b+28,d+22),metDate:storedDate(payload,d+19),eggDate:storedDate(payload,d+16),encounterType:payload[d+29]!,fateful:!!(payload[b+24]!&1),
 ribbons:[dv.getUint32(a+28,true),dv.getUint32(c+24,true),dv.getUint32(c+28,true)]};
}
export function patchPokemonMetadata(record: Uint8Array, changes: Partial<PokemonMetadata>): Uint8Array {
 const {payload,a,b,c,d} = unpack(record), dv = view(payload);
 const integer=(value:number,min:number,max:number,label:string) => {if(!Number.isInteger(value)||value<min||value>max)throw new EditorError('invalid-input',`${label} must be ${min}–${max}.`);};
 if(changes.nickname!==undefined){integer([...changes.nickname].length,1,10,'Nickname length');const encoded=encodeName(changes.nickname);if(decodeName(view(encoded),0)!==changes.nickname)throw new EditorError('invalid-input','Unsupported nickname characters.');payload.set(encoded,c);}
 if(changes.nicknamed!==undefined){if(typeof changes.nicknamed!=='boolean')throw new EditorError('invalid-input','Invalid nickname flag.');dv.setUint32(b+16,((dv.getUint32(b+16,true)&0x7fffffff)|(changes.nicknamed?0x80000000:0))>>>0,true);}
 for(const [key,offset] of [['friendship',a+12],['markings',a+14],['language',a+15],['originGame',c+23],['encounterType',d+29]] as const){const n=changes[key];if(n!==undefined){integer(n,0,key==='markings'?63:255,key);payload[offset]=n;}}
 if(changes.otGender!==undefined){if(!['male','female'].includes(changes.otGender))throw new EditorError('invalid-input','Invalid OT gender.');payload[d+28]=(payload[d+28]!&127)|(changes.otGender==='female'?128:0);}
 if(changes.metLevel!==undefined){integer(changes.metLevel,0,100,'Met level');payload[d+28]=(payload[d+28]!&128)|changes.metLevel;}
 if(changes.ball!==undefined){integer(changes.ball,1,24,'Poké Ball');payload[d+27]=changes.ball;payload[d+30]=changes.ball;}
 for(const [key,modern,old] of [['metLocation',d+24,b+30],['eggLocation',d+22,b+28]] as const){const n=changes[key];if(n!==undefined){integer(n,0,65535,key);dv.setUint16(modern,n,true);dv.setUint16(old,n,true);}}
 for(const [key,offset] of [['metDate',d+19],['eggDate',d+16]] as const){const date=changes[key];if(date!==undefined){if(date===''){payload.fill(0,offset,offset+3);continue;}const parsed=new Date(`${date}T00:00:00Z`);if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(parsed.getTime())||parsed.toISOString().slice(0,10)!==date)throw new EditorError('invalid-input','Invalid date.');integer(parsed.getUTCFullYear(),2000,2255,'Year');payload[offset]=parsed.getUTCFullYear()-2000;payload[offset+1]=parsed.getUTCMonth()+1;payload[offset+2]=parsed.getUTCDate();}}
 if(changes.fateful!==undefined){if(typeof changes.fateful!=='boolean')throw new EditorError('invalid-input','Invalid encounter flag.');payload[b+24]=(payload[b+24]!&~1)|(changes.fateful?1:0);}
 if(changes.ribbons!==undefined){if(changes.ribbons.length!==3)throw new EditorError('invalid-input','Three ribbon banks required.');[a+28,c+24,c+28].forEach((offset,i)=>{integer(changes.ribbons![i]!,0,0xffffffff,'Ribbon bank');dv.setUint32(offset,changes.ribbons![i]!,true);});}
 return seal(record,payload);
}
export function patchPokemonExperience(record: Uint8Array, experience: number, personal: Personal): Uint8Array {
 const mon=decodePokemon(record);if(mon.isEgg||!Number.isInteger(experience)||experience<personal.growthThresholds[1]!||experience>personal.growthThresholds[100]!)throw new EditorError('invalid-input','Experience must fit this species’ level 1–100 growth curve.');
 const {payload,a,pid}=unpack(record);view(payload).setUint32(a+8,experience,true);
 const result=seal(record,payload);
 if(mon.party){const level=levelForExperience(experience,personal.growthThresholds);
 const stats=calculateStats(personal.baseStats,mon.ivs,mon.evs,level,mon.nature,mon.speciesId),tail=crypt(record.subarray(BOXED_SIZE),pid),dv=view(tail);
 dv.setUint8(4,level);dv.setUint16(6,adjustCurrentHp(mon.party.currentHp,mon.party.stats.hp,stats.hp,mon.speciesId),true);STAT_KEYS.forEach((key,i)=>dv.setUint16(8+i*2,stats[key],true));result.set(crypt(tail,pid),BOXED_SIZE);}
 return result;
}
/** Add a freshly calculated party tail to a boxed record (PC → party). */
export function toPartyPokemon(record: Uint8Array, personal: {baseStats:readonly [number,number,number,number,number,number];growthThresholds:readonly number[]}): Uint8Array {
 const mon=decodePokemon(record);if(record.length===PARTY_STRIDE)return Uint8Array.from(record);
 const level=levelForExperience(mon.experience,personal.growthThresholds);
 const result=new Uint8Array(PARTY_STRIDE);result.set(record);const tail=new Uint8Array(PARTY_STRIDE-BOXED_SIZE),dv=view(tail),stats=calculateStats(personal.baseStats,mon.ivs,mon.evs,level,mon.nature,mon.speciesId);
 dv.setUint8(4,level);dv.setUint16(6,stats.hp,true);STAT_KEYS.forEach((key,i)=>dv.setUint16(8+i*2,stats[key],true));result.set(crypt(tail,mon.pid),BOXED_SIZE);return result;
}
/** Create a distinct identity while retaining all metadata and effective shiny/nature/gender.
 * `genderRatio` is the species' personal gender ratio. */
export function clonePokemon(record: Uint8Array, genderRatio: number, random:()=>number=Math.random, naturalTarget?:boolean): Uint8Array {
 const mon=decodePokemon(record),old=unpack(record),ot=(mon.sid<<16)|mon.tid;
 let pid=0;for(let tries=0;;tries++){if(tries>1000000)throw new EditorError('invalid-input','Could not generate a distinct personality.');pid=Math.floor(random()*0x100000000)>>>0;
 if(naturalTarget ?? mon.naturalShiny){const low=pid&65535,high=((ot>>>16)^(ot&65535)^low^Math.floor(random()*8))&65535;pid=((high<<16)|low)>>>0;}
 const natural=((ot>>>16)^(ot&65535)^(pid>>>16)^(pid&65535))<8;
 if(pid!==mon.pid&&pid%25===mon.nature&&genderFromRatio(pid,genderRatio)===mon.gender&&natural===(naturalTarget??mon.naturalShiny))break;}
 const [a,b,c,d]=BLOCKS[(pid>>>13)&31]!,payload=new Uint8Array(128);
 [a,b,c,d].forEach((offset,i)=>payload.set(old.payload.slice([old.a,old.b,old.c,old.d][i]!,[old.a,old.b,old.c,old.d][i]!+32),offset));
 const result=Uint8Array.from(record),sum=checksum(payload);view(result).setUint32(0,pid,true);view(result).setUint16(6,sum,true);result.set(crypt(payload,sum),8);
 if(record.length===PARTY_STRIDE)result.set(crypt(crypt(record.subarray(BOXED_SIZE),old.pid),pid),BOXED_SIZE);return result;
}
