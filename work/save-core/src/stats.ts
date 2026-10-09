import { EditorError } from './errors.js';
/** Origin v4.0.3 stat rules verified against the untouched ROM's ARM9. */
export interface StatValues {
  hp: number;
  attack: number;
  defense: number;
  speed: number;
  spAttack: number;
  spDefense: number;
}
export type StatKey = keyof StatValues;
/** Complete six-key record, with the native stat index made explicit. */
export function mapStats<T>(read: (key: StatKey, index: number) => T): Record<StatKey, T> {
  return {hp: read('hp', 0), attack: read('attack', 1), defense: read('defense', 2),
    speed: read('speed', 3), spAttack: read('spAttack', 4), spDefense: read('spDefense', 5)};
}
const keys = ['hp', 'attack', 'defense', 'speed', 'spAttack', 'spDefense'] as const;

function integer(value: number, min: number, max: number, label: string): void {
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new EditorError('invalid-input', `${label} must be an integer from ${min} to ${max}.`);
  }
}

export function validateStatValues(values: StatValues, kind: 'IV' | 'EV'): void {
  if (kind !== 'IV' && kind !== 'EV') throw new EditorError('invalid-input', 'Unknown stat value kind.');
  if (!values || Object.keys(values).length !== 6 || keys.some(key => !Object.hasOwn(values, key))) {
    throw new EditorError('invalid-input', `${kind}s must include exactly the six stats.`);
  }
  for (const key of keys) integer(values[key], 0, kind === 'IV' ? 31 : 255, `${key} ${kind}`);
  if (kind === 'EV' && keys.reduce((total, key) => total + values[key], 0) > 510) {
    throw new EditorError('invalid-input', 'Total EVs cannot exceed 510.');
  }
}

export function calculateStats(
  baseStats: readonly [number, number, number, number, number, number],
  ivs: StatValues, evs: StatValues, level: number, nature: number, speciesId: number,
): StatValues {
  validateStatValues(ivs, 'IV');
  validateStatValues(evs, 'EV');
  integer(level, 1, 100, 'Level');
  integer(nature, 0, 24, 'Nature');
  integer(speciesId, 1, 65535, 'Species ID');
  if (!Array.isArray(baseStats) || baseStats.length !== 6) throw new EditorError('invalid-input', 'Base stats must include exactly six stats.');
  Array.from(baseStats).forEach(base => integer(base, 1, 255, 'Base stat'));
  const increased = Math.floor(nature / 5);
  const decreased = nature % 5;
  return mapStats((key, index) => {
    const core = Math.floor((2 * baseStats[index]! + ivs[key] + Math.floor(evs[key] / 4)) * level / 100);
    if (index === 0) {
      return speciesId === 292 ? 1 : core + level + 10;
    } else {
      const stat = core + 5;
      const modifier = increased === decreased ? 100 : index - 1 === increased ? 110 : index - 1 === decreased ? 90 : 100;
      // Native ApplyNature (0x0206F1F0) narrows the product to u16 before dividing.
      return modifier === 100 ? stat : Math.floor(((stat * modifier) & 0xffff) / 100);
    }
  });
}

export function adjustCurrentHp(oldCurrent: number, oldMax: number, newMax: number, speciesId: number): number {
  integer(oldCurrent, 0, 65535, 'Current HP');
  integer(oldMax, 0, 65535, 'Previous maximum HP');
  integer(newMax, 1, 65535, 'Maximum HP');
  integer(speciesId, 1, 65535, 'Species ID');
  // Native 0x0206D7F0 preserves fainting; shrinking maximum HP only clamps.
  if (oldCurrent === 0 && oldMax !== 0) return 0;
  if (speciesId === 292) return 1;
  if (oldCurrent === 0) return newMax;
  return newMax < oldMax ? Math.min(oldCurrent, newMax) : oldCurrent + newMax - oldMax;
}

export function experienceForLevel(level: number, growthRate: number, thresholds?: readonly number[]): number {
  integer(level, 1, 100, 'Level');
  integer(growthRate, 0, 7, 'Growth rate');
  if (!thresholds || thresholds.length !== 101) throw new EditorError('invalid-input', 'Reference growth data unavailable. Reload the editor before changing level.');
  for (let index = 0; index < thresholds.length; index++) {
    integer(thresholds[index]!, 0, 0xffffffff, 'Experience threshold');
    if (index > 0 && thresholds[index]! < thresholds[index - 1]!) {
      throw new EditorError('invalid-input', 'Experience thresholds must be in increasing order.');
    }
  }
  if (thresholds[1] !== 0) throw new EditorError('invalid-input', 'The level 1 experience threshold must be zero.');
  return thresholds[level]!;
}
