import { readFileSync } from 'node:fs';
import { createPokemon, emptyPartyRecord } from '../dist/core/pokemon.js';
import { loadBundledOriginData } from '../dist/core/bundled-data.js';
import { speciesInfo } from '../dist/core/species-info.js';
import { crc16 } from '../dist/core/save.js';

export const GENERAL_SIZE = 0xf7cc;
export const STORAGE_SIZE = 0x18408;
export const MIRROR = 0x40000;
export const STORAGE = 0xf800;

export function sealBlock(bytes, offset, size, id, counter) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const footer = offset + size - 16;
  view.setUint32(footer, counter, true);
  view.setUint32(footer + 4, size, true);
  view.setUint32(footer + 8, 0x20060623, true);
  view.setUint16(footer + 12, id, true);
  view.setUint16(footer + 14, crc16(bytes.subarray(offset, footer)), true);
}

// Generated in memory: no private save, ROM, or downloaded fixture is needed in CI.
export function syntheticSave() {
  const bytes = new Uint8Array(0x80000);
  const view = new DataView(bytes.buffer);
  const data = loadBundledOriginData();
  let seed = 42;
  const random = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 0x100000000);
  const records = [1, 4, 7].map(speciesId => {
    const info = speciesInfo(speciesId, 0);
    return createPokemon(emptyPartyRecord(), {
      speciesId, form: 0, level: 50, nature: 3, shiny: false, gender: 'male',
      ability: info.abilities[0], abilitySlot: 0,
      ivs: {hp: 31, attack: 20, defense: 19, speed: 18, spAttack: 17, spDefense: 16},
      moves: [{id: 33, pp: 35}], name: data.catalog.getSpecies(speciesId).name,
      genderRatio: info.genderRatio, baseFriendship: info.baseFriendship,
      personal: data.getPersonal(speciesId, 0),
    }, random, new Date(2024, 0, 1));
  });
  for (const base of [0, MIRROR]) {
    view.setUint32(base + 0x90, 6, true);
    view.setUint32(base + 0x94, records.length, true);
    for (let slot = 0; slot < 6; slot++) bytes.set(records[slot] ?? emptyPartyRecord(), base + 0x98 + slot * 236);
    view.setUint32(base + 0x13a8, 0xbeefcafe, true);
    for (let box = 0; box < 24; box++) {
      for (let slot = 0; slot < 30; slot++) bytes.set(emptyPartyRecord().subarray(0, 136), base + STORAGE + box * 0x1000 + slot * 136);
    }
    view.setUint16(base + 0x640, crc16(bytes.subarray(base + 0x90, base + 0x640)), true);
    view.setUint16(base + STORAGE + 0x183f4, crc16(bytes.subarray(base + STORAGE, base + STORAGE + 0x183f4)), true);
    sealBlock(bytes, base, GENERAL_SIZE, 0, base ? 1 : 2);
    sealBlock(bytes, base + STORAGE, STORAGE_SIZE, 1, base ? 2 : 1);
  }
  return bytes;
}

// An explicit local fixture remains available for extra compatibility checks.
export const fixture = process.env.OHG_SAVE_FIXTURE
  ? new Uint8Array(readFileSync(process.env.OHG_SAVE_FIXTURE)) : syntheticSave();
