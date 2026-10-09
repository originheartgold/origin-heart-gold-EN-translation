// Produce a disposable combined-edit fixture and independently specified expectations.
// Uses only existing local inputs; never overwrites a source or existing destination.
import assert from 'node:assert/strict';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve, sep } from 'node:path';
import { readSave, patchPartyRecord } from '../../save-core/dist/save.js';
import { decodePokemon, patchPokemonMoves, patchPokemonStats, patchPokemonShiny, patchPokemonPokerus } from '../../save-core/dist/pokemon.js';
import { readInventory, patchMoney, patchInventoryPocket } from '../../save-core/dist/inventory.js';
import { loadBundledOriginData } from '../../save-editor/dist/bundled-data.js';

const [sourcePath, output] = process.argv.slice(2);
if (!sourcePath || !output) throw Error('Usage: node work/research/save_core/runtime_fixture.mjs LOCAL_FULL_PARTY_SAVE NEW_OUTPUT_DIRECTORY');
const out = resolve(output);
assert.ok(out.startsWith(resolve('work/save-editor/local') + sep));
await mkdir(resolve('work/save-editor/local'), {recursive:true});
const source = Uint8Array.from(await readFile(sourcePath));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const originalHash = hash(source);
const save = readSave(source);
const expected = save.partyRecords.map(decodePokemon);
assert.equal(expected.length, 6);
assert.equal(expected[0].speciesId, 5);
assert.equal(expected[0].party.level, 9);
assert.deepEqual(expected[0].moves.map(move => move.id), [9, 14, 27, 40]);
Object.assign(expected[0], {nature:15,experience:11735,shiny:true,shinyOverride:true,pokerus:{raw:16,strain:1,days:0,status:'cured'}});
expected[0].moves[0] = {id:53,pp:12,ppUps:1};
Object.assign(expected[0].ivs, {attack:31,defense:31});
Object.assign(expected[0].evs, {hp:200,speed:100});
Object.assign(expected[0].party, {level:25,currentHp:84,stats:{hp:84,attack:44,defense:41,speed:59,spAttack:57,spDefense:39}});
const inventory = readInventory(source);
assert.equal(inventory.pockets.items[0].id, 232);
inventory.money = 123456;
inventory.pockets.items[0].quantity = 7;

const reference = loadBundledOriginData();
const personal = reference.getPersonal(5, 0);
let mon = patchPokemonMoves(save.partyRecords[0], expected[0].moves);
mon = patchPokemonStats(mon, {level:25,nature:15,ivs:expected[0].ivs,evs:expected[0].evs}, personal, personal.growthThresholds);
mon = patchPokemonShiny(mon, true);
mon = patchPokemonPokerus(mon, 'cured');
let edited = patchPartyRecord(source, 0, mon);
edited = patchMoney(edited, inventory.money);
edited = patchInventoryPocket(edited, 'items', inventory.pockets.items, reference.inventory);
assert.deepEqual(readSave(edited).partyRecords.map(decodePokemon), expected);
assert.deepEqual(readInventory(edited), inventory);
const g = save.generalOffset;
let changes = 0;
for (let i = 0; i < source.length; i++) if (source[i] !== edited[i]) {
  changes++;
  assert.ok((i >= g + 0x98 + 6 && i < g + 0x98 + 236) || (i >= g + 0x78 && i < g + 0x7c) ||
    (i >= g + 0x646 && i < g + 0x648) || (i >= g + 0xf7ca && i < g + 0xf7cc), `Unexpected changed byte ${i.toString(16)}`);
}
assert.equal(hash(await readFile(sourcePath)), originalHash);
await mkdir(out, {recursive:false});
await writeFile(resolve(out, 'edited.sav'), edited, {flag:'wx'});
for (const [name, data] of Object.entries({
  moves:expected.map(p => p.moves.map(m => m.id)), stats:expected,
  traits:expected.map(({shiny,naturalShiny,shinyOverride,pokerus}) => ({shiny,naturalShiny,shinyOverride,pokerus})),
  inventory,
  report:{sourceSha256:originalHash,outputSha256:hash(edited),sourceUnchanged:true,changedBytes:changes,kind:'CLI combined-edit fixture; not a browser download'},
})) await writeFile(resolve(out, name + '.json'), JSON.stringify(data, null, 2) + '\n', {flag:'wx'});
console.log(JSON.stringify({out, sourceSha256:originalHash, outputSha256:hash(edited), changedBytes:changes}));
