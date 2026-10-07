import { EditorError } from './errors.js';
import { mapStats, type StatValues } from './stats.js';
/** Gen IV Hidden Power: the low bit of each IV picks one of 16 types (Fighting → Dark). */
export const HIDDEN_POWER_TYPES = ['Fighting','Flying','Poison','Ground','Rock','Bug','Ghost','Steel','Fire','Water','Grass','Electric','Psychic','Ice','Dragon','Dark'] as const;
// Bit weights follow the native order HP, Atk, Def, Spe, SpA, SpD.
const ORDER = ['hp', 'attack', 'defense', 'speed', 'spAttack', 'spDefense'] as const;

function typeFromBits(bits: number): number { return Math.floor(bits * 15 / 63); }
export function hiddenPowerType(ivs: StatValues): number {
  return typeFromBits(ORDER.reduce((sum, key, i) => sum | ((ivs[key] & 1) << i), 0));
}
/** Smallest IV change giving the requested type: flips the fewest low bits, and each flip moves an IV by exactly one. */
export function ivsForHiddenPower(ivs: StatValues, type: number): StatValues {
  if (!Number.isInteger(type) || type < 0 || type > 15) throw new EditorError('invalid-input', 'Unknown Hidden Power type.');
  const current = ORDER.reduce((sum, key, i) => sum | ((ivs[key] & 1) << i), 0);
  let best = -1, bestCost = 7;
  for (let bits = 0; bits < 64; bits++) {
    if (typeFromBits(bits) !== type) continue;
    let diff = bits ^ current, cost = 0;
    while (diff) { cost += diff & 1; diff >>= 1; }
    if (cost < bestCost) { best = bits; bestCost = cost; }
  }
  return mapStats((key, i) => (((best >> i) & 1) === (ivs[key] & 1) ? ivs[key] : ivs[key] ^ 1));
}
