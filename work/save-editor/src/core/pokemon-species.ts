/** Pokémon record writers that need species data. The shared core owns the binary
 * work; this module supplies Origin's form table and gender ratios from the bundled data. */
import {
  createPokemon as createCore, patchPokemonSpecies as speciesCore, patchPokemonGender as genderCore,
  clonePokemon as cloneCore, type NewPokemon, type Gender,
} from './pokemon.js';
import { personalIndex, speciesInfo } from './species-info.js';
import { EditorError } from './errors.js';
import { decodePokemon } from './pokemon.js';
function supportedForm(speciesId: number, form: number): void {
  if (form && personalIndex(speciesId, form) === speciesId) throw new EditorError('invalid-input', 'Unsupported species form.');
}
function ratio(speciesId: number, form: number): number {
  const info = speciesInfo(speciesId, form);
  if (!info) throw new EditorError('invalid-input', 'Unsupported Origin species or form.');
  return info.genderRatio;
}
export function createPokemon(template: Uint8Array, spec: NewPokemon, random: () => number = Math.random, now = new Date()): Uint8Array {
  supportedForm(spec.speciesId, spec.form ?? 0);
  return createCore(template, spec, random, now);
}
export function patchPokemonSpecies(record: Uint8Array, speciesId: number, name: string, personal: Parameters<typeof speciesCore>[3],
  previousThresholds: readonly number[], genderRatio: number, form = 0): Uint8Array {
  supportedForm(speciesId, form);
  return speciesCore(record, speciesId, name, personal, previousThresholds, genderRatio, form);
}
export function patchPokemonGender(record: Uint8Array, gender: Gender): Uint8Array {
  const mon = decodePokemon(record);
  // The native getter uses base-species personal data, regardless of form.
  return genderCore(record, gender, ratio(mon.speciesId, 0));
}
export function clonePokemon(record: Uint8Array, random: () => number = Math.random, naturalTarget?: boolean): Uint8Array {
  const mon = decodePokemon(record);
  return cloneCore(record, ratio(mon.speciesId, mon.form), random, naturalTarget);
}
