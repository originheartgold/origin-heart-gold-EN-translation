import { readSave } from './save.js';
import { decodeName } from './pokemon.js';
import { applyEditorTransaction } from './transaction.js';
import type { TrainerProfileChanges } from './transaction.js';
import { TRAINER_NAME_OFFSET as NAME, TRAINER_TID_OFFSET as TID, TRAINER_SID_OFFSET as SID, TRAINER_GENDER_OFFSET as GENDER, TRAINER_LANGUAGE_OFFSET as LANGUAGE, BADGES_OFFSET as BADGES, BADGES_2_OFFSET as BADGES_2, COINS_OFFSET, PLAY_TIME_OFFSET } from './layout.js';
/** Origin player profile inside the general block. Do not use vanilla US HGSS badge offsets.
 * Origin ARM9 reads/writes badge IDs 0–7 at profile +0x1c and 8–15 at +0x1f.
 * Profile starts at general +0x64, so the badge bytes are +0x80 and +0x83.
 * Verified against native readers at 0x02029434/0x02029444 and setters at
 * 0x02029460/0x0202946e in the English v4.0.3 rc5 ROM.
 */
export { COINS_OFFSET, PLAY_TIME_OFFSET } from './layout.js';
export { COINS_MAX, HOURS_MAX } from './transaction.js';
export type { TrainerProfileChanges } from './transaction.js';
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
export function patchCoins(input: Uint8Array, coins: number): Uint8Array {
  return applyEditorTransaction(input, [{type: 'setCoins', coins}]).bytes;
}
export function patchPlayTime(input: Uint8Array, time: PlayTime): Uint8Array {
  return applyEditorTransaction(input, [{type: 'setPlayTime', hours: time.hours, minutes: time.minutes, seconds: time.seconds}]).bytes;
}
/** Toggle one badge without touching other badges, trainer fields or the backup mirror. */
export function patchBadge(input: Uint8Array, bank: number, bit: number, earned: boolean): Uint8Array {
  return applyEditorTransaction(input, [{type: 'setBadge', bank, bit, earned}]).bytes;
}
export function patchTrainerProfile(input: Uint8Array, changes: TrainerProfileChanges): Uint8Array {
  return applyEditorTransaction(input, [{type: 'setTrainerProfile', ...changes}]).bytes;
}
