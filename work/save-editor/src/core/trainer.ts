import { EditorError } from './errors.js';
import { readSave, patchGeneralRegion } from './save.js';
import { decodeName, encodeName } from './pokemon.js';
/** Origin player profile inside the general block. Do not use vanilla US HGSS badge offsets.
 * Origin ARM9 reads/writes badge IDs 0–7 at profile +0x1c and 8–15 at +0x1f.
 * Profile starts at general +0x64, so the badge bytes are +0x80 and +0x83.
 * Verified against native readers at 0x02029434/0x02029444 and setters at
 * 0x02029460/0x0202946e in the English v4.0.3 rc5 ROM.
 */
const NAME = 0x64, TID = 0x74, SID = 0x76, GENDER = 0x7c, LANGUAGE = 0x7d, BADGES = 0x80, BADGES_2 = 0x83;
export const COINS_OFFSET = 0x84, PLAY_TIME_OFFSET = 0x86;
export const COINS_MAX = 50_000, HOURS_MAX = 999;
export interface PlayTime { hours: number; minutes: number; seconds: number }
export interface Trainer {
  name: string | undefined; tid: number; sid: number; gender: 'male' | 'female'; language: number;
  /** Raw badge bytes in storage order; display order is independent of storage order. */
  badges: [number, number]; badgeCount: number;
  coins: number; playTime: PlayTime;
}
export function readTrainer(input: Uint8Array): Trainer {
  const save = readSave(input);
  const g = save.generalOffset;
  const dv = new DataView(save.bytes.buffer, save.bytes.byteOffset, save.bytes.byteLength);
  const badges: [number, number] = [save.bytes[g + BADGES]!, save.bytes[g + BADGES_2]!];
  const bits = (n: number) => { let c = 0; for (; n; n >>= 1) c += n & 1; return c; };
  return {
    name: decodeName(dv, g + NAME, 8), tid: dv.getUint16(g + TID, true), sid: dv.getUint16(g + SID, true),
    gender: save.bytes[g + GENDER] ? 'female' : 'male', language: save.bytes[g + LANGUAGE]!,
    badges, badgeCount: bits(badges[0]) + bits(badges[1]),
    coins: dv.getUint16(g + COINS_OFFSET, true),
    playTime: {hours: dv.getUint16(g + PLAY_TIME_OFFSET, true), minutes: save.bytes[g + PLAY_TIME_OFFSET + 2]!, seconds: save.bytes[g + PLAY_TIME_OFFSET + 3]!},
  };
}
function integer(value: number, min: number, max: number, label: string): void {
  if (!Number.isInteger(value) || value < min || value > max) throw new EditorError('invalid-input', `${label} must be ${min}–${max.toLocaleString()}.`);
}
export function patchCoins(input: Uint8Array, coins: number): Uint8Array {
  integer(coins, 0, COINS_MAX, 'Coins');
  const bytes = new Uint8Array(2); new DataView(bytes.buffer).setUint16(0, coins, true);
  return patchGeneralRegion(input, COINS_OFFSET, bytes);
}
export function patchPlayTime(input: Uint8Array, time: PlayTime): Uint8Array {
  integer(time.hours, 0, HOURS_MAX, 'Hours'); integer(time.minutes, 0, 59, 'Minutes'); integer(time.seconds, 0, 59, 'Seconds');
  const bytes = new Uint8Array(4); new DataView(bytes.buffer).setUint16(0, time.hours, true);
  bytes[2] = time.minutes; bytes[3] = time.seconds;
  return patchGeneralRegion(input, PLAY_TIME_OFFSET, bytes);
}

/** Toggle one badge without touching other badges, trainer fields or the backup mirror. */
export function patchBadge(input: Uint8Array, bank: number, bit: number, earned: boolean): Uint8Array {
  integer(bank, 0, 1, 'Badge bank');
  integer(bit, 0, 7, 'Badge bit');
  if (typeof earned !== 'boolean') throw new EditorError('invalid-input', 'Badge state must be true or false.');
  const current = readTrainer(input).badges[bank]!;
  const mask = 1 << bit;
  return patchGeneralRegion(input, bank === 0 ? BADGES : BADGES_2,
    Uint8Array.of(earned ? current | mask : current & ~mask));
}

export function patchTrainerProfile(input:Uint8Array, changes:{name?:string;gender?:'male'|'female';tid?:number;sid?:number;language?:number}):Uint8Array {
 let result=input;
 if(changes.name!==undefined){if(!changes.name||[...changes.name].length>7)throw new EditorError('invalid-input','Trainer name must have 1–7 characters.');const encoded=encodeName(changes.name).slice(0,16);if(decodeName(new DataView(encoded.buffer),0,8)!==changes.name)throw new EditorError('invalid-input','Unsupported trainer name.');result=patchGeneralRegion(result,NAME,encoded);}
 for(const [key,offset] of [['tid',TID],['sid',SID]] as const){const n=changes[key];if(n!==undefined){integer(n,0,65535,key);const bytes=new Uint8Array(2);new DataView(bytes.buffer).setUint16(0,n,true);result=patchGeneralRegion(result,offset,bytes);}}
 if(changes.gender!==undefined){if(!['male','female'].includes(changes.gender))throw new EditorError('invalid-input','Invalid gender.');result=patchGeneralRegion(result,GENDER,Uint8Array.of(changes.gender==='female'?1:0));}
 if(changes.language!==undefined){integer(changes.language,1,8,'Language');result=patchGeneralRegion(result,LANGUAGE,Uint8Array.of(changes.language));}
 return result;
}
