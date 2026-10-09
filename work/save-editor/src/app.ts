import { EditorError, editorErrorMessage } from './errors.js';
import { importSave } from './save-import.js';
import { containerLabel, saveExtension, wrapSave, type SaveContainer } from './save-container.js';
import { createNamePicker } from './name-picker.js';
import { maxMovePp, validateMoveChoice } from './catalog.js';
import { readSave } from './save.js';
import { decodePokemon, patchPokemonMoves, patchPokemonStats, patchPokemonShiny, patchPokemonPokerus } from './pokemon.js';
import { loadBundledOriginData, type BundledOriginData } from './bundled-data.js';
import { applyEditorTransaction } from './transaction.js';
import { renderInventoryEditor, type InventoryDrafts } from './inventory-editor.js';
import { renderTraitEditor, type TraitDrafts } from './trait-editor.js';
import { renderStatEditor, type StatDrafts } from './stat-editor.js';

function element<T extends HTMLElement>(id: string, constructor: {new(): T}): T {
  const found = document.getElementById(id);
  if (!(found instanceof constructor)) throw new Error(`Missing or invalid element: ${id}`);
  return found;
}
const picker = element('file-input', HTMLInputElement);
let originData: BundledOriginData | undefined;
const status = element('status', HTMLElement);
const details = element('save-details', HTMLElement);
const partyList = element('party-list', HTMLElement);
const editor = element('editor', HTMLElement);
const inventoryEditor = element('inventory-editor', HTMLElement);
const originalButton = element('export-original', HTMLButtonElement);
const editedButton = element('export-edited', HTMLButtonElement);
let original: Uint8Array | undefined;
let working: Uint8Array | undefined;
let filename = 'origin.sav';
let container: SaveContainer = {kind: 'raw'};
let selected = 0;
interface MoveFields<T> { id: T; pp: T; ppUps: T }
let moveDraft: MoveFields<string>[] | undefined;
let statDrafts: StatDrafts = {};
let traitDrafts: TraitDrafts = {};
let inventoryDrafts: InventoryDrafts = { pockets: {} };
function hasPending(): boolean { return Boolean(traitDrafts.shiny !== undefined || traitDrafts.pokerus !== undefined || moveDraft || statDrafts.ivs || statDrafts.evs || statDrafts.training || inventoryDrafts.money !== undefined || Object.keys(inventoryDrafts.pockets).length); }
let loading = 0;

function message(text: string, error = false): void {
  status.textContent = text;
  status.className = error ? 'status error' : 'status success';
}
function errorMessage(error: unknown): string {
  return editorErrorMessage(error, id => originData?.inventory.getItem(id)?.name);
}
function updateExports(): void {
  originalButton.disabled = !original;
  editedButton.disabled = !working || !original || hasPending() || working.every((v, i) => v === original![i]);
}
function paragraph(text: string): HTMLParagraphElement {
  const p = document.createElement('p'); p.textContent = text; return p;
}
function render(): void {
  if (!working) return;
  const save = readSave(working);
  const party = save.partyRecords.map(decodePokemon);
  partyList.replaceChildren();
  details.textContent = `${filename} · ${containerLabel(container)} · ${save.partyCount} Pokémon · Save counter ${save.counter}`;
  party.forEach((pokemon, slot) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-pressed', String(slot === selected));
    button.textContent = `Slot ${slot + 1} · ${originData?.catalog?.getSpecies(pokemon.speciesId)?.name ?? `Species #${pokemon.speciesId}`}`;
    const summary = document.createElement('small');
    summary.textContent = `Moves: ${pokemon.moves.map(move => move.id === 0 ? '—' : originData?.catalog?.getMove(move.id)?.name ?? `Unknown move (${move.id})`).join(' / ')}`;
    button.append(summary);
    button.addEventListener('click', () => {
      if (hasPending()) { message('Apply or discard pending changes before switching Pokémon.', true); return; }
      selected = slot; render();
    });
    partyList.append(button);
  });
  inventoryEditor.replaceChildren(renderInventoryEditor({
    bytes: working, data: originData, drafts: inventoryDrafts,
    onDirty: updateExports,
    onSelect(pocket) { inventoryDrafts.selectedPocket = pocket; render(); },
    onDiscard(pocket) {
      if (pocket === undefined) delete inventoryDrafts.money;
      else delete inventoryDrafts.pockets[pocket];
      render(); message('Inventory form reset to the last applied values.');
    },
    onMoney(money) {
      if (!working) return;
      try {
        working = applyEditorTransaction(working,[{type:'setMoney',money}]).bytes; delete inventoryDrafts.money; render();
        message('Money applied. Download the edited copy to use it in-game.');
      } catch (error) { message(errorMessage(error), true); }
    },
    onPocket(pocket, items) {
      if (!working || !originData?.inventory) return;
      try {
        working = applyEditorTransaction(working,[{type:'replacePocket',pocket,items,data:originData.inventory}]).bytes;
        delete inventoryDrafts.pockets[pocket]; render();
        message('Pocket applied. Download the edited copy to use it in-game.');
      } catch (error) { message(errorMessage(error), true); }
    },
  }));
  editor.replaceChildren();
  if (!party.length) {
    partyList.append(paragraph('This save has an empty party.'));
    editor.append(paragraph('There are no party Pokémon to edit.'));
    updateExports(); return;
  }
  const pokemon = party[selected]!;
  const heading = document.createElement('h3');
  heading.textContent = `Slot ${selected + 1} · ${originData?.catalog?.getSpecies(pokemon.speciesId)?.name ?? `Species #${pokemon.speciesId}`}`;
  editor.append(heading, paragraph('Search moves by name. Choosing a different move fills its PP and resets PP Ups. Swapping keeps PP and PP Ups with the move.'));
  const form = document.createElement('form');
  form.setAttribute('aria-label', 'Moves');
  const fields: MoveFields<HTMLInputElement>[] = [];
  const movePickers: ReturnType<typeof createNamePicker>[] = [];
  const moveDetails: HTMLParagraphElement[] = [];
  const namedMoves = originData?.catalog?.moves ?? [];
  const updateMoveDetails = (index: number) => {
    const row = fields[index]!; const metadata = originData?.catalog?.getMove(Number(row.id.value));
    const ups = Number(row.ppUps.value);
    const max = metadata && Number.isInteger(ups) && ups >= 0 && ups <= 3 ? maxMovePp(metadata, ups) : 255;
    row.pp.max = '255';
    moveDetails[index]!.textContent = metadata ? `Base PP ${metadata.basePp} · Maximum PP ${max}` : 'Unknown move metadata. Choose a named move to replace it.';
  };
  const captureMoves = () => { moveDraft = fields.map(row => ({id: row.id.value, pp: row.pp.value, ppUps: row.ppUps.value})); updateExports(); };
  pokemon.moves.forEach((move, index) => {
    const row = document.createElement('div'); row.className = 'move-row';
    const values: MoveFields<HTMLInputElement> = {id: document.createElement('input'), pp: document.createElement('input'), ppUps: document.createElement('input')};
    for (const [key, label, max] of [['id', 'Move ID', 920], ['pp', 'PP', 255], ['ppUps', 'PP Ups', 3]] as const) {
      const wrapper = document.createElement('div');
      const input = values[key];
      input.type = 'number'; input.min = '0'; input.max = String(max); input.step = '1'; input.required = true;
      input.value = moveDraft?.[index]?.[key] ?? String(move[key]); input.id = `move-${index}-${key}`;
      const labelElement = document.createElement('label');
      labelElement.htmlFor = input.id; labelElement.textContent = `${index + 1} · ${label}`;
      input.addEventListener('input', captureMoves);
      wrapper.append(labelElement, input); row.append(wrapper);
    }
    fields.push(values);
    const idInput = values.id; idInput.type = 'hidden'; idInput.parentElement!.hidden = true;
    const namePicker = createNamePicker({label: `Move ${index + 1}`, choices: [{id: 0, name: 'Empty slot'}, ...namedMoves], value: Number(idInput.value), onChange(id) {
      if (Number(idInput.value) === id) return;
      idInput.value = String(id); const metadata = originData?.catalog?.getMove(id);
      values.pp.value = String(metadata?.basePp ?? 0); values.ppUps.value = '0';
      updateMoveDetails(index); captureMoves();
    }});
    const moveInfo = paragraph(''); moveInfo.className = 'small'; moveDetails.push(moveInfo); movePickers.push(namePicker);
    row.prepend(namePicker.root); row.append(moveInfo); updateMoveDetails(index);
    values.ppUps.addEventListener('input', () => updateMoveDetails(index));
    form.append(row);
  });
  const swap = document.createElement('button'); swap.type = 'button'; swap.className = 'secondary';
  swap.textContent = 'Swap moves 1 and 2';
  swap.addEventListener('click', () => {
    for (const key of ['id', 'pp', 'ppUps'] as const) {
      const input = fields[0]![key], other = fields[1]![key];
      [input.value, other.value] = [other.value, input.value];
    }
    movePickers.forEach((picker, index) => { picker.setValue(Number(fields[index]!.id.value)); updateMoveDetails(index); });
    captureMoves(); message('Moves swapped in the form. Apply changes to include them in the download.');
  });
  const apply = document.createElement('button'); apply.type = 'submit'; apply.className = 'primary'; apply.textContent = 'Apply moves';
  const discard = document.createElement('button'); discard.type = 'button'; discard.className = 'secondary'; discard.textContent = 'Discard form changes';
  discard.addEventListener('click', () => { moveDraft = undefined; render(); message('Move form reset to the last applied values.'); });
  const actions = document.createElement('div'); actions.className = 'actions'; actions.append(swap, apply, discard); form.append(actions);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!working || !form.reportValidity()) return;
    try {
      const moves = fields.map(row => ({ id: Number(row.id.value), pp: Number(row.pp.value), ppUps: Number(row.ppUps.value) }));
      if (moves.some(move => move.id === 0 && (move.pp !== 0 || move.ppUps !== 0))) {
        throw new EditorError('invalid-input', 'An empty move (ID 0) must have 0 PP and 0 PP Ups.');
      }
      const catalog = originData?.catalog;
      if (catalog) moves.forEach((move, index) => {
        const before = pokemon.moves[index]!;
        if (move.id !== before.id || move.pp !== before.pp || move.ppUps !== before.ppUps) validateMoveChoice(catalog, move.id, move.pp, move.ppUps);
      });
      const current = readSave(working);
      const record = patchPokemonMoves(current.party[selected]!, moves);
      const candidate = applyEditorTransaction(working,[{type:'replacePartyRecord',slot:selected,record}]).bytes;
      readSave(candidate).party.forEach(decodePokemon);
      working = candidate; moveDraft = undefined; render();
      message('Moves applied. Download the edited copy to use it in-game.');
    } catch (error) { message(errorMessage(error), true); }
  });
  editor.append(form, paragraph('Move names and PP match English Origin v4.0.3. Choices include moves outside normal learnsets; learnset legality is not enforced. Empty slot removes a move.'));
  editor.append(renderStatEditor({
    record: save.partyRecords[selected]!, data: originData, drafts: statDrafts,
    onDirty: updateExports,
    onDiscard(group) { delete statDrafts[group]; render(); message('Stat form reset to the last applied values.'); },
    onApply(changes, group) {
      if (!working || !originData) return;
      try {
        const current = readSave(working);
        const currentRecord = current.partyRecords[selected]!;
        const decoded = decodePokemon(currentRecord);
        const personal = originData.getPersonal(decoded.speciesId, decoded.form);
        const updated = patchPokemonStats(currentRecord, changes, personal, personal.growthThresholds);
        const candidate = applyEditorTransaction(working,[{type:'replacePartyRecord',slot:selected,record:updated}]).bytes;
        readSave(candidate).partyRecords.forEach(decodePokemon);
        working = candidate; delete statDrafts[group]; render();
        message(`${group === 'ivs' ? 'IVs' : group === 'evs' ? 'EVs' : 'Level and nature'} applied. Battle stats recalculated from Origin data.`);
      } catch (error) { message(errorMessage(error), true); }
    },
  }));
  editor.append(renderTraitEditor({
    record: save.partyRecords[selected]!, drafts: traitDrafts,
    onDirty: updateExports,
    onDiscard(group) { delete traitDrafts[group]; render(); message('Trait form reset to the last applied values.'); },
    onShiny(value) { applyTrait('shiny', record => patchPokemonShiny(record, value)); },
    onPokerus(value) { applyTrait('pokerus', record => patchPokemonPokerus(record, value)); },
  }));
  function applyTrait(group: keyof TraitDrafts, patch: (record: Uint8Array) => Uint8Array): void {
    if (!working) return;
    try {
      const current = readSave(working);
      const candidate = applyEditorTransaction(working,[{type:'replacePartyRecord',slot:selected,record:patch(current.partyRecords[selected]!)}]).bytes;
      readSave(candidate).partyRecords.forEach(decodePokemon);
      working = candidate; delete traitDrafts[group]; render();
      message(`${group === 'shiny' ? 'Shiny state' : 'Pokérus status'} applied. Download the edited copy to use it in-game.`);
    } catch (error) { message(errorMessage(error), true); }
  }
  updateExports();
}

try {
  originData = loadBundledOriginData();
} catch (error) {
  picker.disabled = true;
  message(`Reference data could not be loaded. Reload the page or use a fresh editor build. ${errorMessage(error)}`, true);
}

picker.addEventListener('change', () => { void loadSelectedSave(); });
async function loadSelectedSave(): Promise<void> {
  const request = ++loading;
  const file = picker.files?.[0];
  if (!file) return;
  try {
    message('Checking save blocks and Pokémon checksums…');
    const candidate = await importSave(file);
    if (request !== loading) return;
    // Roll back the active session if rendering the new candidate fails too.
    const previous = {original, working, filename, container, selected, moveDraft, statDrafts, traitDrafts, inventoryDrafts};
    original = candidate.bytes.slice(); working = candidate.bytes.slice(); filename = candidate.filename; container = candidate.container; selected = 0;
    moveDraft = undefined; statDrafts = {}; traitDrafts = {}; inventoryDrafts = {pockets: {}};
    try { render(); }
    catch (error) {
      ({original, working, filename, container, selected, moveDraft, statDrafts, traitDrafts, inventoryDrafts} = previous);
      if (working) render();
      else {details.replaceChildren(); partyList.replaceChildren(); editor.replaceChildren(); inventoryEditor.replaceChildren(); updateExports();}
      throw error;
    }
    message('Save loaded. All save-block and party Pokémon checksums passed.');
  } catch (error) {
    if (request !== loading) return;
    updateExports(); message(errorMessage(error), true);
  } finally {
    // Retrying the same file must fire change, including after a failed import.
    if (request === loading) picker.value = '';
  }
}

function download(bytes: Uint8Array, suffix: string): void {
  // Downloads keep the input's container, so a .dsv goes straight back into DeSmuME's Battery folder.
  const url = URL.createObjectURL(new Blob([wrapSave(bytes, container).buffer as ArrayBuffer], { type: 'application/octet-stream' }));
  const link = document.createElement('a'); link.href = url;
  link.download = filename.replace(/\.(sav|dsv)$/i, '') + suffix + saveExtension(container);
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
originalButton.addEventListener('click', () => { if (original) download(original, '-unchanged'); });
editedButton.addEventListener('click', () => {
  if (!working || hasPending()) return;
  try {
    readSave(working).party.forEach(decodePokemon);
    download(working, '-edited'); message('Download requested. Your original file was not changed.');
  } catch (error) { message(errorMessage(error), true); }
});
