import test from 'node:test';
import assert from 'node:assert/strict';
import {fixture} from './fixture.mjs';
import {readSave, patchPartyRecord} from '../dist/core/save.js';
import {decodePokemon, patchPokemonAbility, patchPokemonShiny} from '../dist/core/pokemon.js';
import {hiddenPowerType, ivsForHiddenPower} from '../dist/core/hidden-power.js';
import {speciesInfo, getAbility, typeName} from '../dist/core/species-info.js';

test('species info matches known Origin data', () => {
  const bulba = speciesInfo(1, 0);
  assert.deepEqual(bulba.types.map(typeName), ['Grass', 'Poison']);
  assert.equal(getAbility(bulba.abilities[0]).name, 'Overgrow');
});

test('hidden power picks the cheapest IV spread', () => {
  const perfect = {hp: 31, attack: 31, defense: 31, speed: 31, spAttack: 31, spDefense: 31};
  assert.equal(hiddenPowerType(perfect), 15); // Dark
  for (let type = 0; type < 16; type++) {
    const ivs = ivsForHiddenPower(perfect, type);
    assert.equal(hiddenPowerType(ivs), type);
    for (const key of Object.keys(ivs)) assert.ok(ivs[key] === 31 || ivs[key] === 30);
  }
  // HP Fire from all 31s needs exactly three IVs at 30.
  assert.equal(Object.values(ivsForHiddenPower(perfect, 8)).filter(v => v === 30).length, 3);
});

test('party abilities decode including retained off-species abilities', {skip: !fixture}, () => {
  for (const record of readSave(fixture).partyRecords) {
    const mon = decodePokemon(record);
    assert.ok(Number.isInteger(mon.ability) && mon.ability > 0 && mon.ability <= 65535);
    assert.ok([0, 1, 2].includes(mon.abilitySlot));
    // Species changes intentionally retain the effective ability, including off-species choices.
  }
});

test('ability patch round-trips and only touches the two fields', {skip: !fixture}, () => {
  const save = readSave(fixture);
  const record = save.partyRecords[2];
  const before = decodePokemon(record);
  const hidden = speciesInfo(before.speciesId, before.form).abilities[2];
  const patched = patchPokemonAbility(record, hidden, 2);
  const after = decodePokemon(patched);
  assert.equal(after.ability, hidden);
  assert.equal(after.abilitySlot, 2);
  for (const key of ['pid', 'speciesId', 'nature', 'experience', 'shiny']) assert.deepEqual(after[key], before[key]);
  assert.deepEqual(after.moves, before.moves);
  assert.deepEqual(after.ivs, before.ivs);
  assert.deepEqual(record.subarray(136), patched.subarray(136));
  // Writing back keeps the save valid.
  const bytes = patchPartyRecord(fixture, 2, patched);
  assert.equal(decodePokemon(readSave(bytes).partyRecords[2]).ability, hidden);
  // Custom ability keeps the slot byte.
  const custom = decodePokemon(patchPokemonAbility(record, 22));
  assert.equal(custom.ability, 22);
  assert.equal(custom.abilitySlot, before.abilitySlot);
  // Ability and shiny edits compose.
  const both = decodePokemon(patchPokemonShiny(patched, true));
  assert.equal(both.ability, hidden);
  assert.equal(both.shiny, true);
});

test('reapplying the current ability is a no-op', {skip: !fixture}, () => {
  const record = readSave(fixture).partyRecords[0];
  const mon = decodePokemon(record);
  assert.deepEqual(patchPokemonAbility(record, mon.ability, mon.abilitySlot), record);
  assert.throws(() => patchPokemonAbility(record, 0));
  assert.throws(() => patchPokemonAbility(record, 999));
});

test('created Pokémon decode correctly and join the party', {skip: !fixture}, async () => {
  const {createPokemon} = await import('../dist/core/pokemon.js');
  const {addPartyRecord, removePartyRecord} = await import('../dist/core/save.js');
  const {loadBundledOriginData} = await import('../dist/core/bundled-data.js');
  const {defaultMoves} = await import('../dist/core/species-info.js');
  const data = loadBundledOriginData();
  const save = readSave(fixture);
  const info = speciesInfo(445, 0); // Garchomp
  const personal = data.getPersonal(445, 0);
  const moves = defaultMoves(info, 50).map(id => ({id, pp: data.catalog.getMove(id).basePp}));
  assert.equal(moves.length, 4);
  const ivs = {hp: 31, attack: 31, defense: 31, speed: 31, spAttack: 31, spDefense: 31};
  const record = createPokemon(save.partyRecords[0], {speciesId: 445, level: 50, nature: 13, shiny: true, gender: 'female',
    ability: info.abilities[2], abilitySlot: 2, ivs, moves, name: 'Garchomp', genderRatio: info.genderRatio, baseFriendship: info.baseFriendship, personal});
  const mon = decodePokemon(record);
  assert.equal(mon.speciesId, 445); assert.equal(mon.party.level, 50); assert.equal(mon.nature, 13);
  assert.equal(mon.shiny, true); assert.equal(mon.naturalShiny, false); assert.equal(mon.ability, info.abilities[2]);
  assert.equal(mon.nickname, 'Garchomp'); assert.deepEqual(mon.ivs, ivs);
  assert.equal(mon.party.currentHp, mon.party.stats.hp);
  assert.equal(mon.experience, personal.growthThresholds[50]);
  assert.ok((mon.pid & 0xff) < info.genderRatio, 'female PID');
  const added = addPartyRecord(fixture, record);
  const after = readSave(added);
  assert.equal(after.partyCount, save.partyCount + 1);
  assert.equal(decodePokemon(after.partyRecords[save.partyCount]).speciesId, 445);
  for (let i = 0; i < save.partyCount; i++) assert.deepEqual(after.partyRecords[i], save.partyRecords[i]);
  // Remove the first member: others shift up and the freed slot matches the game's blank record.
  const removed = readSave(removePartyRecord(added, 0));
  assert.equal(removed.partyCount, save.partyCount);
  assert.deepEqual(removed.partyRecords.map(r => decodePokemon(r).speciesId), [...save.partyRecords.slice(1).map(r => decodePokemon(r).speciesId), 445]);
  const g = removed.generalOffset + 0x98 + save.partyCount * 236;
  assert.deepEqual(removed.bytes.subarray(g, g + 236), fixture.subarray(save.generalOffset + 0x98 + 5 * 236, save.generalOffset + 0x98 + 6 * 236));
});
