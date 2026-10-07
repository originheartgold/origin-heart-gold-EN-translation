import {editorReference} from '../core/editor-reference.js';
import {advancedPokemon, boxTools, pokedexTile, metadataFields, type EditorContext} from './advanced.js';
import { editorErrorMessage } from '../core/errors.js';
import { importSave } from '../core/save-import.js';
import { wrapSave, type SaveContainer } from '../core/save-container.js';
import { readSave, readStorage, patchBoxRecord, BOX_COUNT, BOX_CAPACITY, patchPartyRecord, addPartyRecord, removePartyRecord } from '../core/save.js';
import {
  decodePokemon, patchPokemonMetadata, readPokemonMetadata, patchPokemonGender, patchPokemonSpecies, patchPokemonMoves, patchPokemonStats, patchPokemonShiny, patchPokemonPokerus,
  patchPokemonOT, patchPokemonAbility, patchPokemonHeldItem, createPokemon, emptyPartyRecord, type DecodedPokemon, type PokerusStatus,
} from '../core/pokemon.js';
import { maxMovePp, validateMoveChoice } from '../core/catalog.js';
import { loadBundledOriginData } from '../core/bundled-data.js';
import { POCKETS, fillBag, MONEY_MAX, readInventory, patchMoney, patchInventoryPocket, type PocketId, type ItemStack } from '../core/inventory.js';
import { mapStats, calculateStats, type StatValues, type StatKey } from '../core/stats.js';
import { readTrainer, patchBadge, patchCoins, patchPlayTime, patchTrainerProfile, COINS_MAX, HOURS_MAX } from '../core/trainer.js';
import { hiddenPowerType, ivsForHiddenPower, HIDDEN_POWER_TYPES } from '../core/hidden-power.js';
import { FORM_CHOICES, speciesSelection, selectionId, hisuiName, speciesInfo, typeName, ABILITIES, getAbility, TYPE_NAMES, defaultMoves, possibleGenders, type Gender } from '../core/species-info.js';
import { h, svg } from './dom.js';
import { PC_WALLPAPERS } from './pc-wallpapers.js';
import { BADGE_SPRITES } from './badge-sprites.js';
import { combobox, type ComboChoice } from './combobox.js';
import { artworkUrl, fallbackArtworkUrl, miniSpriteUrl, itemSpriteUrl, pcSprite, img } from './sprites.js';

try {
  const savedTheme = localStorage.getItem('ohg-editor-theme');
  if (savedTheme === 'light' || savedTheme === 'dark') document.documentElement.dataset.theme = savedTheme;
} catch {}
const themeToggle = document.getElementById('theme-toggle') as HTMLButtonElement;
const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
function updateThemeToggle(): void {
  const dark = document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme && systemTheme.matches);
  themeToggle.replaceChildren(svg(dark
    ? '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></svg>'
    : '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20.5 14.2A8.5 8.5 0 0 1 9.8 3.5a8.5 8.5 0 1 0 10.7 10.7Z"/></svg>'));
  themeToggle.title = `Switch to ${dark ? 'light' : 'dark'} mode`;
  themeToggle.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} mode`);
}
themeToggle.addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme === 'dark'
    || (!document.documentElement.dataset.theme && systemTheme.matches);
  const theme = dark ? 'light' : 'dark';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('ohg-editor-theme', theme); } catch {}
  updateThemeToggle();
});
systemTheme.addEventListener('change', updateThemeToggle);
updateThemeToggle();

const data = loadBundledOriginData();
const NATURES = ['Hardy','Lonely','Brave','Adamant','Naughty','Bold','Docile','Relaxed','Impish','Lax','Timid','Hasty','Serious','Jolly','Naive','Modest','Mild','Quiet','Bashful','Rash','Calm','Gentle','Sassy','Careful','Quirky'];
const NATURE_STATS: StatKey[] = ['attack', 'defense', 'speed', 'spAttack', 'spDefense'];
const STAT_LABEL: Record<StatKey, string> = {hp: 'HP', attack: 'Attack', defense: 'Defense', speed: 'Speed', spAttack: 'Sp. Atk', spDefense: 'Sp. Def'};
const STAT_SHORT: Record<StatKey, string> = {hp: 'HP', attack: 'Atk', defense: 'Def', speed: 'Spe', spAttack: 'SpA', spDefense: 'SpD'};
const STAT_ORDER: StatKey[] = ['hp', 'attack', 'defense', 'spAttack', 'spDefense', 'speed'];

interface Session { original: Uint8Array; working: Uint8Array; container: SaveContainer; filename: string; history: Uint8Array[] }
let session: Session | undefined;
let selected = 0;
let pocket: PocketId = 'items';
let bagSelectedId: number | undefined;
let pcBox = 0, pcSlot = 0;
type View = 'pc' | 'pokemon' | 'trainer' | 'bag';
let view: View = 'pokemon';

const app = document.getElementById('app')!;
const fileInput = document.getElementById('file-input') as HTMLInputElement;
const exportButton = document.getElementById('export') as HTMLButtonElement;
const undoButton = document.getElementById('undo') as HTMLButtonElement;
const dock = document.getElementById('dock')!;
const dockUndo = document.getElementById('dock-undo') as HTMLButtonElement;
const dockExport = document.getElementById('dock-export') as HTMLButtonElement;
const viewSwitch = document.getElementById('view-switch')!;
const addDialog = document.getElementById('add-dialog') as HTMLDialogElement;
const fileMeta = document.getElementById('file-meta')!;
const toastNode = document.getElementById('toast')!;

/* ---------- helpers ---------- */
let toastTimer = 0;
function toast(text: string, error = false): void {
  toastNode.textContent = text;
  toastNode.className = `toast show${error ? ' error' : ''}`;
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toastNode.className = 'toast'; }, error ? 4200 : 2000);
}
const errorText = (error: unknown) => editorErrorMessage(error, id => data.inventory.getItem(id)?.name);
const speciesName = (id: number, form = 0) => { const choice = speciesSelection(id); return hisuiName(choice.speciesId, form || choice.form) ?? data.catalog.getSpecies(choice.speciesId)?.name ?? `Species #${id}`; };
const itemName = (id: number) => id === 0 ? 'None' : data.inventory.getItem(id)?.name ?? `Item #${id}`;
const typeKey = (id: number) => typeName(id).toLowerCase();
function typeChip(id: number, small = false): HTMLElement {
  return h('span', {class: `type${small ? ' sm' : ''}`, style: `--c: var(--t-${typeKey(id)})`}, typeName(id));
}
function sameBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
function isDirty(): boolean { return !!session && !sameBytes(session.original, session.working); }

/** Apply a byte transform; on failure nothing changes and the reason is shown. */
function commit(change: (bytes: Uint8Array) => Uint8Array, done: string): void {
  if (!session) return;
  try {
    const next = change(session.working);
    if (sameBytes(next, session.working)) { render(); return; }
    session.history.push(session.working);
    if (session.history.length > 60) session.history.shift();
    session.working = next;
    render(); toast(done);
  } catch (error) { render(); toast(errorText(error), true); }
}
function editMon(change: (record: Uint8Array, mon: DecodedPokemon) => Uint8Array, done: string): void {
  const slot = selected;
  commit(bytes => {
    if (view === 'pc') {
      const record = readStorage(bytes).boxes[pcBox]![pcSlot]!;
      return patchBoxRecord(bytes, pcBox, pcSlot, change(record, decodePokemon(record)));
    }
    const record = readSave(bytes).partyRecords[slot]!;
    return patchPartyRecord(bytes, slot, change(record, decodePokemon(record)));
  }, done);
}
function editStats(changes: Parameters<typeof patchPokemonStats>[1], done: string): void {
  editMon((record, mon) => {
    const personal = data.getPersonal(mon.speciesId, mon.form);
    return patchPokemonStats(record, changes, personal, personal.growthThresholds);
  }, done);
}
function numberInput(attrs: {id: string; value: number; min: number; max: number; disabled?: boolean; label: string}, onCommit: (value: number) => void, onLive?: () => void): HTMLInputElement {
  const input = h('input', {type: 'number', id: attrs.id, min: attrs.min, max: attrs.max, step: 1, value: attrs.value, 'aria-label': attrs.label, disabled: attrs.disabled, inputmode: 'numeric'});
  if (onLive) input.addEventListener('input', onLive);
  input.addEventListener('change', () => {
    const value = Number(input.value);
    if (input.value === '' || !Number.isInteger(value)) { input.value = String(attrs.value); return; }
    const clamped = Math.min(attrs.max, Math.max(attrs.min, value));
    if (clamped !== attrs.value) onCommit(clamped); else input.value = String(attrs.value);
  });
  input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); });
  return input;
}

function editorContext(): EditorContext {
 return {bytes:session!.working, location:view==='pc'?{kind:'pc',box:pcBox,slot:pcSlot}:{kind:'party',slot:selected},data,commit,
 navigate:location=>{if(location.kind==='pc'){pcBox=location.box;pcSlot=location.slot;setView('pc');}else{selected=location.slot;setView('pokemon');}},error:message=>toast(message,true)};
}
/* ---------- tiles ---------- */
function heroTile(mon: DecodedPokemon): HTMLElement {
  const info = speciesInfo(mon.speciesId, mon.form);
  const name = mon.isEgg ? 'Egg' : mon.nickname ?? speciesName(mon.speciesId, mon.form);
  const types = info ? [...new Set(info.types)] : [];
  const tile = h('section', {class: 'tile hero span-2 row-2', style: types[0] !== undefined ? `--tint: var(--t-${typeKey(types[0])})` : undefined});
  const star = h('button', {type: 'button', class: 'star', 'aria-pressed': String(mon.shiny), 'aria-label': 'Shiny',
    title: mon.naturalShiny ? 'Naturally shiny (cannot be removed)' : mon.shiny ? 'Shiny: click to remove' : 'Make shiny',
    disabled: mon.isEgg || (mon.naturalShiny && mon.shiny),
    onclick: () => editMon(r => patchPokemonShiny(r, !mon.shiny), mon.shiny ? 'No longer shiny' : 'Now shiny')},
  svg('<svg viewBox="0 0 16 16"><path d="M8 1.5l1.6 4.3 4.4.3-3.4 2.8 1.1 4.4L8 10.9l-3.7 2.4 1.1-4.4L2 6.1l4.4-.3z" fill="currentColor"/></svg>'));
  const genders = info ? possibleGenders(info.genderRatio) : [];
  const genderIcon = h('div', {id:'pokemon-gender', class:'gender-toggle', role:'group', 'aria-label':'Pokémon gender', 'data-gender':mon.gender},
    h('span', {class:'gender-selection', 'aria-hidden':'true'}));
  for (const gender of ['male','female'] as const) {
    genderIcon.append(h('button', {type:'button', class:'gender-choice', 'aria-label':gender === 'male' ? 'Male' : 'Female',
      'aria-pressed':String(mon.gender === gender), disabled:mon.isEgg || !genders.includes(gender) || genders.length < 2,
      onclick:event => {
        if(mon.gender === gender)return;
        const previous = mon.gender === 'female' ? 'translateX(30px)' : 'translateX(0)';
        editMon(record => patchPokemonGender(record, gender), `Gender changed to ${gender}`);
        const slider = document.querySelector<HTMLElement>('#pokemon-gender .gender-selection');
        if(slider && event instanceof MouseEvent && event.detail > 0 && !matchMedia('(prefers-reduced-motion: reduce)').matches)
          slider.animate([{transform:previous},{transform:gender === 'female' ? 'translateX(30px)' : 'translateX(0)'}],{duration:160,easing:'ease-out'});
      }}, gender === 'male' ? '♂' : '♀'));
  }
  const species = mon.isEgg ? '' : mon.nickname && mon.nickname !== speciesName(mon.speciesId, mon.form) ? speciesName(mon.speciesId, mon.form) : `No. ${String(mon.speciesId).padStart(4, '0')}`;
  tile.append(h('div', {class: 'hero-top'},
    h('div', {}, h('h1', {class: 'hero-name'}, name), h('div', {class: 'hero-species'}, species)),
    h('div', {style: 'display:flex;gap:10px;align-items:center'}, mon.party ? h('span', {class: 'hero-lv'}, `Lv ${mon.party.level}`) : null, h('div', {class:'hero-actions'}, star, genderIcon))));
  const art = h('div', {class: 'hero-art'});
  if (mon.isEgg) art.append(h('span', {class: 'missing'}, 'Egg — hatch it to edit'));
  else if (hisuiName(mon.speciesId, mon.form)) art.append(h('span', {class: 'missing'}, hisuiName(mon.speciesId, mon.form)!));
  else art.append(img(artworkUrl(mon.speciesId, mon.shiny), speciesName(mon.speciesId, mon.form), '', fallbackArtworkUrl(mon.speciesId, mon.shiny)));
  tile.append(art, h('div', {class: 'types'}, ...types.map(t => typeChip(t))));
  const ability = getAbility(mon.ability);
  const facts = h('dl', {class: 'hero-facts'});
  const fact = (k: string, v: string) => facts.append(h('div', {}, h('dt', {}, k), h('dd', {title: v}, v)));
  fact('Nature', NATURES[mon.nature] ?? '—');
  fact('Ability', ability?.name ?? `#${mon.ability}`);
  fact('Held item', itemName(mon.heldItem));
  if (mon.party) fact(view === 'pc' ? 'Calculated HP' : 'HP', `${mon.party.currentHp} / ${mon.party.stats.hp}`);
  tile.append(facts, combobox({id: 'change-species', label: 'Change this Pokémon’s species',
    value: selectionId(mon.speciesId, mon.form), disabled: mon.isEgg, choices: [...data.catalog.species, ...FORM_CHOICES],
    onSelect: id => editMon((record, current) => {
      const next = speciesSelection(id);
      return patchPokemonSpecies(record, next.speciesId, data.catalog.getSpecies(next.speciesId)!.name, data.getPersonal(next.speciesId, next.form),
        data.getPersonal(current.speciesId, current.form).growthThresholds, speciesInfo(next.speciesId, next.form)!.genderRatio, next.form);
    }, `Species changed to ${speciesName(id)}`)}),
    h('p', {class: 'note'}, 'Changes this Pokémon only. Keeps nickname, moves, ability, held item, IVs and EVs; uses the selected form and keeps level.'));
  return tile;
}

let moveChoices: ComboChoice[] | undefined;
function getMoveChoices(): ComboChoice[] {
  moveChoices ??= [{id: 0, name: '— Empty —'}, ...data.catalog.moves.map(m => ({id: m.id, name: m.name,
    meta: () => h('span', {class: 'meta'}, typeChip(m.type, true), h('span', {class: 'num'}, m.power ? String(m.power) : '—'))}))];
  return moveChoices;
}
function movesTile(mon: DecodedPokemon): HTMLElement {
  const grid = h('div', {class: 'moves'});
  const setMove = (index: number, next: {id: number; pp: number; ppUps: number}, done: string) => editMon((record, current) => {
    validateMoveChoice(data.catalog, next.id, next.pp, next.ppUps);
    const moves = current.moves.map((m, i) => i === index ? next : m);
    return patchPokemonMoves(record, moves);
  }, done);
  mon.moves.forEach((move, index) => {
    const meta = data.catalog.getMove(move.id);
    const card = h('div', {class: 'move', style: meta && move.id ? `--c: var(--t-${typeKey(meta.type)})` : 'opacity:.85'});
    card.append(combobox({choices: getMoveChoices(), value: move.id, label: `Move ${index + 1}`, id: `move-${index}`, disabled: mon.isEgg,
      placeholder: 'Empty — search a move',
      onSelect: id => {
        const m = data.catalog.getMove(id);
        setMove(index, {id, pp: id ? m?.basePp ?? 0 : 0, ppUps: 0}, id ? `Move ${index + 1}: ${m?.name ?? id}` : `Move ${index + 1} cleared`);
      }}));
    if (move.id && meta) {
      const max = maxMovePp(meta, move.ppUps);
      const ups = h('span', {class: 'pp-ups', title: 'PP Ups'}, ...[1, 2, 3].map(n => h('button', {type: 'button', class: n <= move.ppUps ? 'on' : '', 'aria-label': `${n} PP Up${n > 1 ? 's' : ''}`, disabled: mon.isEgg,
        onclick: () => { const target = move.ppUps === n ? n - 1 : n; setMove(index, {id: move.id, ppUps: target, pp: maxMovePp(meta, target)}, `PP Ups: ${target}`); }})));
      card.append(h('div', {class: 'move-meta'}, typeChip(meta.type, true),
        h('span', {}, 'Pow ', h('span', {class: 'num'}, meta.power || '—')),
        h('span', {}, 'Acc ', h('span', {class: 'num'}, meta.accuracy ? meta.accuracy : '—'))));
      card.append(h('div', {class: 'move-pp'}, h('span', {}, 'PP'),
        numberInput({id: `pp-${index}`, value: move.pp, min: 0, max, label: `Move ${index + 1} PP`, disabled: mon.isEgg}, pp => setMove(index, {...move, pp}, `PP set to ${pp}`)),
        h('span', {class: 'num'}, `/ ${max}`), h('span', {style: 'margin-left:auto'}, 'PP Ups'), ups));
    } else if (move.id) card.append(h('p', {class: 'note'}, `Unnamed move #${move.id} — kept as is unless replaced.`));
    grid.append(card);
  });
  return h('section', {class: 'tile span-4 glow glow-tr wide'}, h('h2', {}, 'Moves', h('span', {class: 'aside'}, 'New moves start with full PP')), grid);
}

function abilityTile(mon: DecodedPokemon): HTMLElement {
  const info = speciesInfo(mon.speciesId, mon.form);
  const slots: {slot: number; id: number; label: string}[] = [];
  if (info) {
    const [a1, a2, hidden] = info.abilities;
    if (a1) slots.push({slot: 0, id: a1, label: 'Ability 1'});
    if (a2 && a2 !== a1) slots.push({slot: 1, id: a2, label: 'Ability 2'});
    if (hidden) slots.push({slot: 2, id: hidden, label: 'Hidden'});
  }
  const own = slots.some(s => s.id === mon.ability);
  const list = h('div', {class: 'abilities'}, ...slots.map(s => {
    const ability = getAbility(s.id);
    const active = mon.ability === s.id && (mon.abilitySlot === s.slot || !slots.some(o => o.id === s.id && o.slot === mon.abilitySlot));
    return h('button', {type: 'button', class: 'ability', 'aria-pressed': String(active), disabled: mon.isEgg,
      onclick: () => editMon(r => patchPokemonAbility(r, s.id, s.slot), `Ability: ${ability?.name ?? s.id}`)},
    h('span', {class: 'a-name'}, ability?.name ?? `#${s.id}`), h('span', {class: 'a-slot'}, s.label),
    h('span', {class: 'a-desc'}, ability?.description ?? ''));
  }));
  const custom = h('div', {class: 'custom-ability'},
    h('label', {class: 'field', for: 'ability-any'}, 'Any ability'),
    combobox({id: 'ability-any', label: 'Any ability', value: own ? undefined : mon.ability, disabled: mon.isEgg, placeholder: 'Search all abilities…',
      choices: ABILITIES.map(a => ({id: a.id, name: a.name, meta: () => a.description.length > 38 ? `${a.description.slice(0, 36)}…` : a.description})),
      onSelect: id => {
        const slot = slots.find(s => s.id === id)?.slot;
        editMon(r => patchPokemonAbility(r, id, slot), `Ability: ${getAbility(id)?.name ?? id}`);
      }}));
  if (!own && !mon.isEgg) {
    const current = getAbility(mon.ability);
    custom.append(h('p', {class: 'note warn'}, `${current?.name ?? `#${mon.ability}`} is not one of this species’ abilities. Evolving may reset it.`));
  } else custom.append(h('p', {class: 'note'}, 'Picking an off-species ability keeps the slot, so evolution may swap it back.'));
  return h('section', {class: 'tile span-2 glow glow-bl alt'}, h('h2', {}, 'Ability'), list, custom);
}

function detailsTile(mon: DecodedPokemon): HTMLElement {
  const disabled = mon.isEgg || !mon.party;
  const nature = h('select', {id: 'nature', disabled, 'aria-label': 'Nature'}, ...NATURES.map((n, i) => {
    const up = NATURE_STATS[Math.floor(i / 5)]!, down = NATURE_STATS[i % 5]!;
    return h('option', {value: i}, up === down ? `${n} (neutral)` : `${n}  +${STAT_SHORT[up]} −${STAT_SHORT[down]}`);
  }));
  nature.value = String(mon.nature);
  nature.addEventListener('change', () => editStats({nature: Number(nature.value)}, `Nature: ${NATURES[Number(nature.value)]}`));
  const level = numberInput({id: 'level', value: mon.party?.level ?? 1, min: 1, max: 100, label: 'Level', disabled},
    lv => editStats({level: lv}, `Level ${lv}`));
  const seg = h('div', {class: 'seg', role: 'group', 'aria-label': 'Pokérus'}, ...(['none', 'infected', 'cured'] as PokerusStatus[]).map(status =>
    h('button', {type: 'button', 'aria-pressed': String(mon.pokerus.status === status), disabled: mon.isEgg,
      onclick: () => editMon(r => patchPokemonPokerus(r, status), `Pokérus: ${status}`)}, status[0]!.toUpperCase() + status.slice(1))));
  const held = combobox({id: 'held-item', label: 'Held item', value: mon.heldItem, disabled: mon.isEgg, placeholder: 'None — search items',
    choices: [{id: 0, name: 'None'}, ...data.inventory.items.filter(i => i.pocket !== 'keyItems' && i.pocket !== 'tmHm' && i.name && !i.name.startsWith('Item #')).map(i => ({id: i.id, name: i.name,
      icon: () => img(itemSpriteUrl(i.name, i.pocket), '')}))],
    onSelect: id => editMon(r => patchPokemonHeldItem(r, id), id ? `Holding ${itemName(id)}` : 'Held item removed')});
  return h('section', {class: 'tile span-2 glow glow-br'}, h('h2', {}, 'Details'),
    h('div', {class: 'kv'},
      h('div', {class: 'inline'}, h('label', {class: 'field', style: 'width:88px'}, 'Level', level),
        h('label', {class: 'field', style: 'flex:1'}, 'Nature', nature)),
      h('div', {class: 'field'}, h('span', {}, 'Held item'), held),
      h('div', {class: 'field'}, h('span', {}, 'Pokérus'), seg),
      mon.pokerus.status === 'infected' ? h('p', {class: 'note'}, `${mon.pokerus.days} day${mon.pokerus.days === 1 ? '' : 's'} left. Time passed since your last save may cure it on load.`) : null));
}

/** Last drawn bar widths, so a re-render can animate from the previous value. */
const barWidths = new Map<StatKey, number>();
function maxStat(base: number, level: number, key: StatKey): number {
  const core = Math.floor((2 * base + 31 + 63) * level / 100);
  return key === 'hp' ? core + level + 10 : Math.floor((core + 5) * 1.1);
}
function statsTile(mon: DecodedPokemon): HTMLElement {
  const disabled = mon.isEgg || !mon.party;
  const personal = data.getPersonal(mon.speciesId, mon.form);
  const base = mapStats((_k, i) => personal.baseStats[i]!);
  const level = mon.party?.level ?? 1;
  const up = NATURE_STATS[Math.floor(mon.nature / 5)], down = NATURE_STATS[mon.nature % 5];
  const setIv = (key: StatKey, v: number) => editStats({ivs: {...mon.ivs, [key]: v}}, `${STAT_LABEL[key]} IV ${v}`);
  const setEv = (key: StatKey, v: number) => editStats({evs: {...mon.evs, [key]: v}}, `${STAT_LABEL[key]} EV ${v}`);
  const ivInputs = {} as Record<StatKey, HTMLInputElement>, evInputs = {} as Record<StatKey, HTMLInputElement>;
  const fills = {} as Record<StatKey, HTMLElement>, vals = {} as Record<StatKey, HTMLElement>;
  const evTotalNode = h('span', {class: 'num'});
  const evTotalWrap = h('span', {class: 'ev-total'}, evTotalNode, ' EVs');
  const width = (key: StatKey, stat: number) => Math.max(2, Math.min(100, stat / maxStat(base[key], level, key) * 100));

  /** Recompute stats from whatever is typed right now; nothing is written until the field commits. */
  const live = () => {
    const read = (inputs: Record<StatKey, HTMLInputElement>, max: number, fallback: StatValues) => mapStats(k => {
      const v = Number(inputs[k].value);
      return inputs[k].value !== '' && Number.isInteger(v) ? Math.min(max, Math.max(0, v)) : fallback[k];
    });
    const ivs = read(ivInputs, 31, mon.ivs), evs = read(evInputs, 255, mon.evs);
    const total = STAT_ORDER.reduce((sum, k) => sum + evs[k], 0);
    evTotalNode.textContent = `${total} / 510`;
    evTotalWrap.classList.toggle('over', total > 510);
    if (!mon.party) return;
    let stats: StatValues;
    try { stats = calculateStats(personal.baseStats, ivs, total > 510 ? mon.evs : evs, level, mon.nature, mon.speciesId); }
    catch { return; }
    for (const key of STAT_ORDER) {
      const w = width(key, stats[key]);
      fills[key].style.width = `${w}%`; barWidths.set(key, w);
      vals[key].textContent = String(stats[key]);
      vals[key].classList.toggle('changed', stats[key] !== mon.party.stats[key]);
    }
  };

  const body = h('tbody');
  for (const key of STAT_ORDER) {
    const cls = up !== down ? (key === up ? 'plus' : key === down ? 'minus' : '') : '';
    ivInputs[key] = numberInput({id: `iv-${key}`, value: mon.ivs[key], min: 0, max: 31, label: `${STAT_LABEL[key]} IV`, disabled}, v => setIv(key, v), live);
    evInputs[key] = numberInput({id: `ev-${key}`, value: mon.evs[key], min: 0, max: 255, label: `${STAT_LABEL[key]} EV`, disabled}, v => setEv(key, v), live);
    const target = mon.party ? width(key, mon.party.stats[key]) : 0;
    fills[key] = h('div', {class: 'fill', style: `width:${barWidths.get(key) ?? 0}%`});
    vals[key] = h('span', {class: 'val'}, mon.party ? mon.party.stats[key] : '—');
    requestAnimationFrame(() => requestAnimationFrame(() => { fills[key].style.width = `${target}%`; }));
    barWidths.set(key, target);
    body.append(h('tr', {class: cls},
      h('td', {}, STAT_LABEL[key], cls === 'plus' ? ' +' : cls === 'minus' ? ' −' : ''),
      h('td', {class: 'base'}, base[key]),
      h('td', {}, ivInputs[key]),
      h('td', {}, evInputs[key]),
      h('td', {class: 'bar-cell'}, h('div', {class: 'stat-bar', title: mon.party ? `Max at Lv ${level}: ${maxStat(base[key], level, key)}` : undefined},
        h('div', {class: 'track'}, fills[key]), vals[key]))));
  }
  live();
  const hp = hiddenPowerType(mon.ivs);
  const hpSelect = h('select', {id: 'hidden-power', disabled, 'aria-label': 'Hidden Power type'}, ...HIDDEN_POWER_TYPES.map((t, i) => h('option', {value: i}, `Hidden Power ${t}`)));
  hpSelect.value = String(hp);
  hpSelect.addEventListener('change', () => {
    const type = Number(hpSelect.value);
    editStats({ivs: ivsForHiddenPower(mon.ivs, type)}, `Hidden Power ${HIDDEN_POWER_TYPES[type]} (IVs adjusted by 1 where needed)`);
  });
  const all = (v: number): StatValues => mapStats(() => v);
  const hpTypeId = TYPE_NAMES.indexOf(HIDDEN_POWER_TYPES[hp]!);
  return h('section', {class: 'tile span-4 glow glow-tl alt wide'},
    h('h2', {}, 'Stats', h('span', {class: 'aside'}, mon.party ? `Lv ${level} · ${NATURES[mon.nature]} · bars vs. max at this level` : '')),
    h('table', {class: 'stats'}, h('thead', {}, h('tr', {}, h('th', {}, ''), h('th', {}, 'Base'), h('th', {}, 'IV'), h('th', {}, 'EV'), h('th', {}, 'Stat'))), body),
    h('div', {class: 'stats-foot'},
      evTotalWrap,
      hpTypeId >= 0 ? typeChip(hpTypeId, true) : null, hpSelect,
      h('button', {type: 'button', class: 'btn small', disabled, onclick: () => editStats({ivs: all(31)}, 'All IVs set to 31')}, 'Max IVs'),
      h('button', {type: 'button', class: 'btn small', disabled, onclick: () => editStats({evs: all(0)}, 'EVs cleared')}, 'Clear EVs')));
}

function infoTile(mon: DecodedPokemon, partyCount: number): HTMLElement {
  const info = h('dl', {class: 'info'});
  const row = (k: string, v: string) => info.append(h('div', {}, h('dt', {}, k), h('dd', {title: v}, v)));
  row('Experience', mon.experience.toLocaleString());
  row('Personality', mon.pid.toString(16).toUpperCase().padStart(8, '0'));
  row('Form', String(mon.form));
  row('Ability slot', mon.abilitySlot === 2 ? 'Hidden' : String(mon.abilitySlot + 1));
  const otName = h('input', {type: 'text', id: 'ot-name', maxlength: 7, value: mon.otName ?? '', placeholder: mon.otName === undefined ? 'Unsupported name characters' : undefined, 'aria-label': 'Original trainer name'});
  otName.addEventListener('change', () => {
    if (otName.value !== mon.otName) editMon(record => patchPokemonOT(record, {name: otName.value}), 'Original trainer name updated');
  });
  const otFields = h('div', {class: 'ot-fields'},
    h('label', {class: 'field', for: 'ot-name'}, 'Original trainer (OT)', otName),
    h('div', {class: 'ot-ids'},
      h('label', {class: 'field', for: 'ot-tid'}, 'Trainer ID', numberInput({id: 'ot-tid', value: mon.tid, min: 0, max: 65535, label: 'Pokémon Trainer ID'}, tid => editMon(record => patchPokemonOT(record, {tid}), 'Trainer ID updated'))),
      h('label', {class: 'field', for: 'ot-sid'}, 'Secret ID', numberInput({id: 'ot-sid', value: mon.sid, min: 0, max: 65535, label: 'Pokémon Secret ID'}, sid => editMon(record => patchPokemonOT(record, {sid}), 'Secret ID updated')))),
    h('p', {class: 'note'}, 'These fields belong to this Pokémon. Changing them can affect ownership and natural shiny status.'));
  const remove = h('button', {type: 'button', class: 'btn small danger', disabled: view !== 'pc' && partyCount <= 1,
    title: view !== 'pc' && partyCount <= 1 ? 'The party needs at least one Pokémon' : undefined,
    onclick: () => {
      const name = mon.nickname ?? speciesName(mon.speciesId, mon.form);
      if (view === 'pc') {
        if (confirm(`Remove ${name} from this PC slot? You can undo this.`)) commit(bytes => patchBoxRecord(bytes, pcBox, pcSlot, emptyPartyRecord().slice(0, 136)), `${name} removed from PC`);
        return;
      }
      if (!confirm(`Remove ${name} from the party? You can undo this.`)) return;
      const slot = selected;
      commit(bytes => removePartyRecord(bytes, slot), `${name} removed`);
    }}, view === 'pc' ? 'Remove from PC' : 'Remove from party');
  return h('section', {class: 'tile span-2 glow glow-tr'}, h('h2', {}, 'Info'), info, otFields, h('div', {class: 'tile-foot'}, remove));
}

const LANGUAGES: Record<number, string> = {1: 'Japanese', 2: 'English', 3: 'French', 4: 'Italian', 5: 'German', 7: 'Spanish', 8: 'Korean'};
const pad = (n: number, w = 2) => String(n).padStart(w, '0');

const BADGE_COLORS: Record<string, string> = {
  Boulder: '#929695', Cascade: '#59afe0', Thunder: '#e5b51c', Rainbow: '#62b947',
  Marsh: '#eac120', Soul: '#c36eaf', Volcano: '#e51e42', Earth: '#49a94b',
  Zephyr: '#969c9f', Hive: '#d52e26', Plain: '#aabe24', Fog: '#64438e',
  Storm: '#a54b29', Mineral: '#668fba', Glacier: '#60c5df', Rising: '#73787b',
};
const BADGE_PAINT: Record<string, string> = {
  Rainbow: 'conic-gradient(#ee2148, #f86a21, #f2eb37, #a4d13a, #60bd42, #77c7ce, #477ebc, #c362ad, #ee2148)',
  Hive: 'linear-gradient(155deg, #8d9495 0% 30%, #ef4826 36%, #cb202c 85%)',
  Rising: 'linear-gradient(180deg, #b9bdc0 0% 35%, #df2939 40% 49%, #777c80 55%, #3e4548 100%)',
};
function badgeArt(name: string): HTMLElement {
  const sprite = BADGE_SPRITES[name.toLowerCase()]!;
  return h('span', {class: 'badge-art', 'aria-hidden': 'true'},
    img(sprite, '', 'badge-sprite'),
    h('span', {class: 'badge-paint', style: `--badge-paint: ${BADGE_PAINT[name] ?? BADGE_COLORS[name]}; mask-image: url("${sprite}"); -webkit-mask-image: url("${sprite}")`}));
}
function trainerOverview(party: DecodedPokemon[], badges: [number, number]): HTMLElement {
  const count = (byte: number) => Array.from({length: 8}, (_, bit) => byte >> bit & 1).reduce((a, b) => a + b, 0);
  return h('div', {class: 'tc-overview'},
    h('div', {class: 'tc-progress'}, ...['Kanto', 'Johto'].map((region, bank) => {
      const earned = count(badges[bank]!);
      return h('div', {class: 'tc-region'},
        h('div', {class: 'tc-section-heading'}, h('span', {}, `${region} badges`), h('strong', {class: 'num'}, `${earned} / 8`)),
        h('progress', {max: 8, value: earned, 'aria-label': `${region} badges earned`}),
        h('span', {class: 'note'}, earned === 8 ? 'All badges earned' : `${8 - earned} remaining`));
    })),
    h('div', {class: 'tc-section-heading'}, h('h2', {}, 'Current party'), h('span', {class: 'note'}, `${party.length} / 6 · select to edit`)),
    h('div', {class: 'tc-party'}, ...party.map((mon, slot) => {
      const hp = mon.party;
      return h('button', {type: 'button', class: 'tc-member', onclick: () => { selected = slot; setView('pokemon'); },
        'aria-label': `Edit party slot ${slot + 1}: ${mon.isEgg ? 'Egg' : speciesName(mon.speciesId, mon.form)}`},
        mon.isEgg ? h('span', {class: 'tc-egg'}, 'Egg') : img(miniSpriteUrl(mon.speciesId, mon.shiny), '', 'tc-member-sprite'),
        h('div', {class: 'tc-member-info'},
          h('strong', {}, mon.isEgg ? 'Egg' : mon.nickname ?? speciesName(mon.speciesId, mon.form)),
          h('span', {class: 'note'}, mon.isEgg ? 'Waiting to hatch' : `${speciesName(mon.speciesId, mon.form)} · Lv. ${hp?.level ?? '—'}`),
          !mon.isEgg && hp ? h('span', {class: 'tc-hp num'}, `HP ${hp.currentHp} / ${hp.stats.hp}`) : null));
    })));
}

function trainerCardTile(party: DecodedPokemon[]): HTMLElement {
  const t = readTrainer(session!.working);
  const name = t.name ?? '—';
  const lead = party.find(m => !m.isEgg);
  return h('section', {class: 'tile span-4 glow glow-tl trainer-card'},
    h('div', {class: 'tc-top'},
      h('div', {class: 'tc-avatar', 'data-gender': t.gender}, name.slice(0, 1).toUpperCase()),
      h('div', {class: 'tc-id'},
        h('span', {class: 'tc-label'}, 'Trainer'),
        h('h1', {class: 'tc-name'}, name, h('span', {class: `tc-gender ${t.gender}`, title: t.gender}, t.gender === 'female' ? '♀' : '♂')),
        h('span', {class: 'tc-sub num'}, `ID No. ${pad(t.tid, 5)}`)),
      lead ? img(artworkUrl(lead.speciesId, lead.shiny), '', 'tc-lead', fallbackArtworkUrl(lead.speciesId, lead.shiny)) : null),
    h('dl', {class: 'tc-stats'},
      h('div', {}, h('dt', {}, 'Money'), h('dd', {class: 'num'}, `₽${readInventory(session!.working).money.toLocaleString()}`)),
      h('div', {}, h('dt', {}, 'Play time'), h('dd', {class: 'num'}, `${t.playTime.hours}:${pad(t.playTime.minutes)}`)),
      h('div', {}, h('dt', {}, 'Badges'), h('dd', {class: 'num'}, t.badgeCount)),
      h('div', {}, h('dt', {}, 'Coins'), h('dd', {class: 'num'}, t.coins.toLocaleString())),
      h('div', {}, h('dt', {}, 'Secret ID'), h('dd', {class: 'num'}, pad(t.sid, 5))),
      h('div', {}, h('dt', {}, 'Language'), h('dd', {}, LANGUAGES[t.language] ?? `#${t.language}`))),
    trainerOverview(party, t.badges),
    h('p', {class: 'note', style: 'margin-top:12px'}, 'Edit your name, IDs and gender under Trainer profile. Existing Pokémon keep their original trainer details.'));
}

function badgesTile(): HTMLElement {
  const t = readTrainer(session!.working);
  // Origin's GiveBadge scripts award Kanto IDs 0–7 (the first stored byte).
  const kanto = ['Boulder', 'Cascade', 'Thunder', 'Rainbow', 'Marsh', 'Soul', 'Volcano', 'Earth'];
  const johto = ['Zephyr', 'Hive', 'Plain', 'Fog', 'Storm', 'Mineral', 'Glacier', 'Rising'];
  const row = (bank: number, label: string, names: string[]) => h('div', {class: 'badge-row'},
    h('span', {class: 'badge-label'}, label),
    h('div', {class: 'badges'}, ...names.map((name, bit) => {
      const earned = !!(t.badges[bank]! & (1 << bit));
      return h('button', {type: 'button', class: `badge${earned ? ' on' : ''}`, style: `--badge-color: ${BADGE_COLORS[name]}`, 
        title: `${name} Badge · ${earned ? 'earned' : 'not earned'}`,
        'aria-label': `${label}: ${name} Badge`, 'aria-pressed': String(earned),
        onclick: () => {
          commit(bytes => patchBadge(bytes, bank, bit, !earned), `${name} Badge ${earned ? 'removed' : 'earned'}`);
          // Rendering replaces the controls; restore keyboard focus to this badge.
          app.querySelector<HTMLButtonElement>(`[data-badge="${bank}-${bit}"]`)?.focus();
        }, 'data-badge': `${bank}-${bit}`},
        badgeArt(name),
        h('span', {class: 'badge-name'}, name));
    })));
  return h('section', {class: 'tile span-2 glow glow-tr gold'}, h('h2', {}, 'Badges', h('span', {class: 'aside'}, `${t.badgeCount} / 16`)),
    row(0, 'Kanto', kanto), row(1, 'Johto', johto),
    h('p', {class: 'note', style: 'margin-top:12px'}, 'Select a badge to mark it earned or remove it. Badge edits do not complete gym battles or story events.'));
}

function walletTile(): HTMLElement {
  const inv = readInventory(session!.working);
  const trainer = readTrainer(session!.working);
  const trainerFields=h('div',{class:'trainer-profile'},h('h3',{},'Trainer profile'));
  const trainerName=h('input',{type:'text',value:trainer.name??'',maxlength:7,'aria-label':'Player name'});
  trainerName.addEventListener('change',()=>commit(bytes=>patchTrainerProfile(bytes,{name:trainerName.value}),'Trainer name updated'));
  const trainerGender=h('select',{'aria-label':'Player gender'},h('option',{value:'male'},'Male'),h('option',{value:'female'},'Female'));trainerGender.value=trainer.gender;
  trainerGender.addEventListener('change',()=>commit(bytes=>patchTrainerProfile(bytes,{gender:trainerGender.value as 'male'|'female'}),'Trainer gender updated'));
  trainerFields.append(h('div',{class:'editor-fields'},h('label',{class:'field'},'Name',trainerName),h('label',{class:'field'},'Gender',trainerGender),
  h('label',{class:'field'},'Trainer ID',numberInput({id:'player-tid',value:trainer.tid,min:0,max:65535,label:'Player Trainer ID'},tid=>commit(bytes=>patchTrainerProfile(bytes,{tid}),'Player ID updated'))),
  h('label',{class:'field'},'Secret ID',numberInput({id:'player-sid',value:trainer.sid,min:0,max:65535,label:'Player Secret ID'},sid=>commit(bytes=>patchTrainerProfile(bytes,{sid}),'Player secret ID updated')))),h('p',{class:'note'},'Changing the player profile does not change existing Pokémon OT fields.'));

  const t = readTrainer(session!.working);
  const money = numberInput({id: 'money', value: inv.money, min: 0, max: MONEY_MAX, label: 'Money'}, v => commit(b => patchMoney(b, v), `Money: ₽${v.toLocaleString()}`));
  const coins = numberInput({id: 'coins', value: t.coins, min: 0, max: COINS_MAX, label: 'Coins'}, v => commit(b => patchCoins(b, v), `Coins: ${v.toLocaleString()}`));
  return h('section', {class: 'tile span-2 glow glow-bl gold'}, h('h2', {}, 'Wallet'), trainerFields,
    h('div', {class: 'kv'},
      h('div', {class: 'field'}, h('label', {for: 'money'}, 'Money (₽)'), h('div', {class: 'money'}, money,
        h('button', {type: 'button', class: 'btn', onclick: () => commit(b => patchMoney(b, MONEY_MAX), 'Money maxed')}, 'Max'))),
      h('div', {class: 'field'}, h('label', {for: 'coins'}, 'Game Corner coins'), h('div', {class: 'money'}, coins,
        h('button', {type: 'button', class: 'btn', onclick: () => commit(b => patchCoins(b, COINS_MAX), 'Coins maxed')}, 'Max')))));
}

function playTimeTile(): HTMLElement {
  const t = readTrainer(session!.working).playTime;
  const set = (part: 'hours' | 'minutes' | 'seconds') => (v: number) => commit(b => patchPlayTime(b, {...t, [part]: v}), 'Play time updated');
  return h('section', {class: 'tile span-2 glow glow-br'}, h('h2', {}, 'Play time'),
    h('p', {class: 'big-money'}, `${t.hours}`, h('small', {}, 'h '), pad(t.minutes), h('small', {}, 'm '), pad(t.seconds), h('small', {}, 's')),
    h('div', {class: 'time-inputs'},
      h('label', {class: 'field'}, 'Hours', numberInput({id: 'pt-h', value: t.hours, min: 0, max: HOURS_MAX, label: 'Hours'}, set('hours'))),
      h('label', {class: 'field'}, 'Min', numberInput({id: 'pt-m', value: t.minutes, min: 0, max: 59, label: 'Minutes'}, set('minutes'))),
      h('label', {class: 'field'}, 'Sec', numberInput({id: 'pt-s', value: t.seconds, min: 0, max: 59, label: 'Seconds'}, set('seconds')))));
}

const POCKET_ICONS: Record<PocketId, string> = {
  items: 'Exp Share', keyItems: 'Bicycle', tmHm: 'TM01', mail: 'Air Mail',
  medicine: 'Potion', berries: 'Oran Berry', balls: 'Poké Ball', battle: 'X Attack',
};
function bagTile(): HTMLElement {
  const inv = readInventory(session!.working);
  const def = POCKETS.find(p => p.id === pocket)!;
  const stacks = inv.pockets[pocket];
  if (!stacks.some(s => s.id === bagSelectedId)) bagSelectedId = stacks[0]?.id;
  const chosen = stacks.find(s => s.id === bagSelectedId);
  const setPocket = (items: ItemStack[], done: string) => commit(b => patchInventoryPocket(b, pocket, items, data.inventory), done);
  const pockets = h('nav', {class: 'game-pockets', 'aria-label': 'Bag pockets'}, ...POCKETS.map(p =>
    h('button', {type: 'button', class: 'game-pocket', id: `bag-pocket-${p.id}`, 'aria-pressed': String(p.id === pocket), title: p.label,
      onclick: () => { pocket = p.id; bagSelectedId = undefined; render(); }},
      img(itemSpriteUrl(POCKET_ICONS[p.id], p.id), '', 'game-pocket-icon'),
      h('span', {}, p.label), h('small', {class: 'num'}, inv.pockets[p.id].length))));
  const list = h('div', {class: 'game-item-list', 'aria-label': `${def.label} items`});
  stacks.forEach(stack => {
    const meta = data.inventory.getItem(stack.id);
    list.append(h('button', {type: 'button', class: 'game-item-row', id: `bag-item-${stack.id}`, 'aria-pressed': String(stack.id === bagSelectedId),
      onclick: () => { bagSelectedId = stack.id; render(); }},
      h('span', {class: 'game-cursor', 'aria-hidden': 'true'}, stack.id === bagSelectedId ? '▶' : ''),
      meta ? img(itemSpriteUrl(meta.name, meta.pocket), '', 'game-row-icon') : h('span', {class: 'ph'}),
      h('span', {class: 'game-item-name'}, itemName(stack.id)), h('span', {class: 'num'}, `×${stack.quantity}`)));
  });
  if (!stacks.length) list.append(h('p', {class: 'game-empty'}, 'This pocket is empty.', h('small', {}, 'Add an item below to fill it.')));
  const detail = h('aside', {class: 'game-item-detail', 'aria-label': 'Selected item'});
  if (chosen) {
    const meta = data.inventory.getItem(chosen.id), name = itemName(chosen.id);
    detail.append(h('div', {class: 'game-item-art'}, meta ? img(itemSpriteUrl(meta.name, meta.pocket), '', '') : h('span', {class: 'ph'})),
      h('span', {class: 'game-detail-label'}, def.label), h('h2', {}, name),
      h('label', {class: 'field', for: `bag-qty-${chosen.id}`}, 'Quantity',
        numberInput({id: `bag-qty-${chosen.id}`, value: chosen.quantity, min: 1, max: def.maxQuantity, label: `${name} quantity`},
          quantity => setPocket(stacks.map(s => s.id === chosen.id ? {...s, quantity} : s), `${name} ×${quantity}`))),
      h('div', {class: 'game-item-actions'},
        h('button', {type: 'button', class: 'btn', disabled: chosen.quantity === def.maxQuantity,
          onclick: () => setPocket(stacks.map(s => s.id === chosen.id ? {...s, quantity: def.maxQuantity} : s), `${name} quantity maxed`)}, `Max ×${def.maxQuantity}`),
        h('button', {type: 'button', class: 'btn danger', onclick: () => setPocket(stacks.filter(s => s.id !== chosen.id), `Removed ${name}`)}, 'Remove')));
    const ref = editorReference.items[chosen.id];
    if (ref) detail.append(h('dl', {class: 'bag-reference'},
      ...[['Price', `₽${ref.price.toLocaleString()}`], ['Fling power', String(ref.flingPower)],
        ['Held effect ID', `${ref.hold} / ${ref.holdParameter}`], ['Fling effect ID', String(ref.flingEffect)],
        ['Use IDs · field / battle / party', `${ref.fieldUse} / ${ref.battleUse} / ${ref.partyUse}`]]
        .map(([label, value]) => h('div', {}, h('dt', {}, label), h('dd', {class: 'num'}, value)))));
  } else detail.append(h('div', {class: 'game-item-art'}, img(itemSpriteUrl(POCKET_ICONS[pocket], pocket), '', '')), h('h2', {}, def.label), h('p', {class: 'note'}, 'Select an item to change its quantity or remove it.'));
  const present = new Set(stacks.map(s => s.id));
  let pendingId = 0;
  const full = stacks.length >= def.capacity;
  const qty = h('input', {type: 'number', min: 1, max: def.maxQuantity, value: 1, disabled: full, 'aria-label': 'New item quantity', id: 'add-qty'});
  const add = () => {
    if (!pendingId) { toast('Pick an item first', true); return; }
    const quantity = Math.min(def.maxQuantity, Math.max(1, Math.floor(Number(qty.value)) || 1));
    bagSelectedId = pendingId;
    setPocket([...stacks, {id: pendingId, quantity}], `Added ${quantity}× ${itemName(pendingId)}`);
  };
  const picker = combobox({id: 'add-item', label: `Add to ${def.label}`, value: undefined, disabled: full,
    placeholder: full ? 'Pocket full' : 'Find an item to add…',
    choices: data.inventory.items.filter(i => i.pocket === pocket && !present.has(i.id) && !i.name.startsWith('Item #')).map(i => ({id: i.id, name: i.name, icon: () => img(itemSpriteUrl(i.name, i.pocket), '')})),
    onSelect: id => { pendingId = id; qty.focus(); qty.select(); }});
  qty.addEventListener('keydown', e => { if (e.key === 'Enter') add(); });
  return h('section', {class: 'tile span-6 game-bag'},
    h('div', {class: 'game-bag-title'}, h('h1', {}, 'Bag'), h('button', {type: 'button', class: 'btn small',
      title: 'Fill available slots; key items unchanged. TMs/HMs use ×99.',
      onclick: () => {
        try {
          const result = fillBag(session!.working, data.inventory);
          commit(() => result.bytes, 'Bag filled');
          toast(`Bag filled: ×999 (TMs/HMs ×99). ${result.omitted} items did not fit. Key items unchanged.`);
        } catch (error) { toast(errorText(error), true); }
      }}, 'Add all items ×999'), h('span', {}, def.label), h('span', {class: 'num'}, `${stacks.length} / ${def.capacity} slots`)),
    pockets, h('div', {class: 'game-bag-screen'}, list, detail),
    h('div', {class: 'game-bag-footer'}, h('div', {class: 'game-add'}, picker, qty, h('button', {type: 'button', class: 'btn primary', disabled: full, onclick: add}, 'Add item')),
      h('div', {class: 'game-bag-status'}, h('span', {}, `${def.capacity - stacks.length} slots free`),
        h('button', {type: 'button', class: 'btn small', disabled: !stacks.length || stacks.every(s => s.quantity === def.maxQuantity),
          onclick: () => setPocket(stacks.map(s => ({...s, quantity: def.maxQuantity})), `All ${def.label.toLowerCase()} set to ${def.maxQuantity}`)}, `Max this pocket ×${def.maxQuantity}`))));
}

function partyRail(party: DecodedPokemon[]): HTMLElement {
  const rail = h('nav', {class: 'party', 'aria-label': 'Party'}, h('div', {class: 'party-label'}, h('span', {}, 'Party'), h('span', {class: 'num'}, `${party.length}/6`)));
  party.forEach((mon, slot) => {
    const name = mon.isEgg ? 'Egg' : mon.nickname ?? speciesName(mon.speciesId, mon.form);
    rail.append(h('button', {type: 'button', class: 'slot', 'aria-current': String(slot === selected), onclick: () => { selected = slot; render(); }},
      mon.isEgg ? h('span', {class: 'egg'}, 'Egg') : img(miniSpriteUrl(mon.speciesId, mon.shiny), ''),
      h('span', {}, h('span', {class: 'slot-name'}, name), h('span', {class: 'slot-sub'}, mon.party ? `Lv ${mon.party.level}` : ''))));
  });
  const full = party.length >= 6, noTemplate = !party.some(m => !m.isEgg);
  rail.append(h('button', {type: 'button', class: 'slot-add', disabled: full || noTemplate, 'aria-label': 'Add Pokémon',
    title: full ? 'Party is full — remove one first' : noTemplate ? 'Needs one hatched Pokémon in the party' : 'Add a Pokémon to the party',
    onclick: openAddDialog},
  h('span', {class: 'plus'}, '+'), h('span', {class: 'label'}, 'Add Pokémon', h('small', {}, full ? 'Party full' : `${6 - party.length} slot${6 - party.length === 1 ? '' : 's'} free`))));
  return rail;
}

/** Boxed records have no cached battle stats; derive a display-only preview. */
function boxedPreview(record: Uint8Array): DecodedPokemon {
  const mon = decodePokemon(record);
  if (!mon.speciesId || mon.isEgg) return mon;
  const personal = data.getPersonal(mon.speciesId, mon.form);
  let level = 1;
  for (let lv = 2; lv <= 100; lv++) if (mon.experience >= personal.growthThresholds[lv]!) level = lv;
  const stats = calculateStats(personal.baseStats, mon.ivs, mon.evs, level, mon.nature, mon.speciesId);
  return {...mon, party: {level, currentHp: stats.hp, stats, status: 0}};
}
function renderPC(bento: HTMLElement): void {
  try {
    const storage = readStorage(session!.working);
    const records = storage.boxes[pcBox]!;
    const boxSelect = h('select', {id: 'pc-box', 'aria-label': 'PC box'}, ...storage.names.map((name, box) => h('option', {value: box}, name || `Box ${box + 1}`)));
    boxSelect.value = String(pcBox);
    boxSelect.addEventListener('change', () => { pcBox = Number(boxSelect.value); pcSlot = 0; render(); });
    const wallpaper = storage.wallpapers[pcBox]!;
    const grid = h('div', {class: 'pc-grid pc-wallpaper', style: `background-image: url("${PC_WALLPAPERS[wallpaper >= 32 && wallpaper <= 39 ? wallpaper - 16 : wallpaper] ?? PC_WALLPAPERS[0]}")`});
    let occupied = 0;
    records.forEach((record, slot) => {
      try {
        const mon = decodePokemon(record), empty = !mon.speciesId;
        if (!empty) occupied++;
        grid.append(h('button', {type: 'button', class: `pc-slot${slot === pcSlot ? ' selected' : ''}${empty ? ' empty' : ''}`,
          'aria-pressed': String(slot === pcSlot), title: `Slot ${slot + 1}: ${empty ? 'Empty' : mon.isEgg ? 'Egg' : mon.nickname ?? speciesName(mon.speciesId, mon.form)}`, 'aria-label': `Slot ${slot + 1}: ${empty ? 'Empty' : mon.isEgg ? 'Egg' : speciesName(mon.speciesId, mon.form)}`,
          onclick: () => { pcSlot = slot; render(); }}, empty ? null : mon.isEgg ? h('span', {class: 'pc-egg'}, 'Egg') : pcSprite(mon.speciesId, mon.shiny)));
      } catch {
        grid.append(h('button', {type: 'button', class: 'pc-slot', disabled: true, title: 'Record has an invalid checksum'}, 'Unreadable'));
      }
    });
    bento.append(h('section', {class: 'tile span-6 pc-browser'},
      h('h2', {}, 'PC storage', h('span', {class: 'aside'}, `${BOX_COUNT} boxes · ${occupied} / ${BOX_CAPACITY} in this box`)),
      h('div', {class: 'pc-controls'}, h('button', {type: 'button', class: 'btn pc-arrow', 'aria-label': 'Previous box', title: 'Previous box', disabled: pcBox === 0, onclick: () => { pcBox--; pcSlot = 0; render(); }}, '◀'), boxSelect,
        h('button', {type: 'button', class: 'btn pc-arrow', 'aria-label': 'Next box', title: 'Next box', disabled: pcBox === BOX_COUNT - 1, onclick: () => { pcBox++; pcSlot = 0; render(); }}, '▶')), grid, boxTools(editorContext(),pcBox)));
    const mon = boxedPreview(records[pcSlot]!);
    if (mon.speciesId) {
      bento.append(heroTile(mon), movesTile(mon), abilityTile(mon), detailsTile(mon), statsTile(mon), infoTile(mon, 0), advancedPokemon(editorContext()));
    } else {
      const noTemplate = !readSave(session!.working).partyRecords.some(record => !decodePokemon(record).isEgg);
      bento.append(h('section', {class: 'tile span-6'}, h('h2', {}, `Empty slot ${pcSlot + 1}`),
        h('p', {class: 'note'}, 'Select a Pokémon above to edit it, or add one to this slot.'),
        h('button', {type: 'button', class: 'btn primary', disabled: noTemplate || storage.tied, onclick: openAddDialog}, 'Add Pokémon')));
    }
  } catch (error) {
    bento.append(h('section', {class: 'tile span-6'}, h('h2', {}, 'PC storage unavailable'), h('p', {class: 'note'}, errorText(error))));
  }
}

/* ---------- render ---------- */
function setView(next: View): void {
  if (view !== next) { view = next; window.scrollTo(0, 0); }
  render();
}
function render(): void {
  if (!session) return;
  const focusedId = document.activeElement instanceof HTMLElement && document.activeElement.matches('input[type="number"], select, .game-item-row, .game-pocket') ? document.activeElement.id : '';
  const scroll = window.scrollY;
  const openPanels = new Set([...app.querySelectorAll('details[open]')].map(node=>node.querySelector('summary')?.textContent));
  const bagScroll = app.querySelector('.game-item-list')?.scrollTop ?? 0;
  const save = readSave(session.working);
  const party = save.partyRecords.map(decodePokemon);
  if (selected >= party.length) selected = Math.max(0, party.length - 1);
  const bento = h('div', {class: 'bento'});
  // Tint the cards from the selected Pokémon (Pokémon view) or the lead Pokémon (Trainer view).
  const tinted = view === 'pokemon' ? party[selected] : party.find(m => !m.isEgg);
  const tintInfo = tinted && !tinted.isEgg ? speciesInfo(tinted.speciesId, tinted.form) : undefined;
  if (tintInfo) bento.style.cssText = `--tint: var(--t-${typeKey(tintInfo.types[0])}); --tint2: var(--t-${typeKey(tintInfo.types[1])})`;
  if (view === 'pokemon') {
    const mon = party[selected];
    if (mon) bento.append(heroTile(mon), movesTile(mon), abilityTile(mon), detailsTile(mon), statsTile(mon), infoTile(mon, party.length), advancedPokemon(editorContext()));
    else bento.append(h('section', {class: 'tile span-6'}, h('h2', {}, 'Party'), h('p', {class: 'note'}, 'This save has no party Pokémon.')));
    app.replaceChildren(h('div', {class: 'layout'}, partyRail(party), bento));
  } else if (view === 'pc') {
    renderPC(bento);
    const browser = bento.querySelector('.pc-browser');
    app.replaceChildren(h('div', {class: 'layout pc-layout'}, browser, bento));
  } else if (view === 'trainer') {
    bento.append(trainerCardTile(party), badgesTile(), walletTile(), playTimeTile(), pokedexTile(editorContext()));
    app.replaceChildren(h('div', {class: 'layout single'}, bento));
  } else {
    bento.append(bagTile());
    app.replaceChildren(h('div', {class: 'layout single'}, bento));
  }
  const bagList = app.querySelector('.game-item-list');
  if (bagList) bagList.scrollTop = bagScroll;
  window.scrollTo(0, scroll);
  for(const node of app.querySelectorAll('details'))if(openPanels.has(node.querySelector('summary')?.textContent))node.open=true;
  if (focusedId) document.getElementById(focusedId)?.focus();

  const dirty = isDirty();
  fileMeta.hidden = false;
  fileMeta.replaceChildren(h('span', {class: 'name'}, session.filename), h('span', {class: 'sep'}, '·'), h('span', {}, dirty ? 'edited' : 'unchanged'));
  viewSwitch.hidden = false; dock.hidden = false;
  for (const button of [...viewSwitch.querySelectorAll('button'), ...dock.querySelectorAll<HTMLButtonElement>('button[data-view]')]) {
    button.setAttribute('aria-pressed', String(button.dataset.view === view));
  }
  undoButton.disabled = dockUndo.disabled = !session.history.length;
  exportButton.disabled = false;
  exportButton.replaceChildren(...(dirty ? [h('span', {class: 'dot'}), 'Export'] : ['Export']));
  dockExport.classList.toggle('dirty', dirty);
}
for (const button of [...viewSwitch.querySelectorAll('button'), ...dock.querySelectorAll<HTMLButtonElement>('button[data-view]')]) {
  button.addEventListener('click', () => setView(button.dataset.view === 'pc' || button.dataset.view === 'trainer' || button.dataset.view === 'bag' ? button.dataset.view : 'pokemon'));
}

/* ---------- add pokémon ---------- */
interface AddDraft { species: number; level: number; nature: number; slot: number; gender: Gender; shiny: boolean; perfect: boolean }
let draft: AddDraft = {species: 0, level: 5, nature: 0, slot: 0, gender: 'male', shiny: false, perfect: false};
let creationMetadata: ReturnType<typeof readPokemonMetadata> | undefined;
let creationOT = {name:'',tid:0,sid:0};
let speciesChoices: ComboChoice[] | undefined;
function abilitySlots(info: NonNullable<ReturnType<typeof speciesInfo>>): {slot: number; id: number; label: string}[] {
  const [a1, a2, hidden] = info.abilities, out: {slot: number; id: number; label: string}[] = [];
  if (a1) out.push({slot: 0, id: a1, label: 'Ability 1'});
  if (a2 && a2 !== a1) out.push({slot: 1, id: a2, label: 'Ability 2'});
  if (hidden) out.push({slot: 2, id: hidden, label: 'Hidden'});
  return out;
}
function setSpecies(id: number): void {
  const info = speciesInfo(speciesSelection(id).speciesId, speciesSelection(id).form);
  const genders = info ? possibleGenders(info.genderRatio) : ['male' as Gender];
  draft = {...draft, species: id, slot: 0, gender: genders.includes(draft.gender) ? draft.gender : genders[0]!};
  if(creationMetadata&&info)creationMetadata={...creationMetadata,friendship:info.baseFriendship};
}
function openAddDialog(): void {
  if (!session) return;
  if (!draft.species) { setSpecies(1); draft.nature = Math.floor(Math.random() * 25); }
  const trainer = readTrainer(session.working), template=readSave(session.working).partyRecords.find(r=>!decodePokemon(r).isEgg);
  if(template){creationMetadata=readPokemonMetadata(template);const choice=speciesSelection(draft.species);creationMetadata={...creationMetadata,friendship:speciesInfo(choice.speciesId,choice.form)!.baseFriendship,otGender:trainer.gender,language:trainer.language,metLevel:draft.level,metDate:new Date().toISOString().slice(0,10),eggLocation:0,eggDate:'',ball:4,fateful:false};}
  creationOT={name:trainer.name??'Trainer',tid:trainer.tid,sid:trainer.sid};
  renderAddDialog();
  addDialog.showModal();
  addDialog.querySelector<HTMLInputElement>('#add-species')?.focus();
}
function renderAddDialog(): void {
  const info = speciesInfo(speciesSelection(draft.species).speciesId, speciesSelection(draft.species).form);
  const name = speciesName(draft.species);
  const moves = info ? defaultMoves(info, draft.level) : [];
  const slots = info ? abilitySlots(info) : [];
  const genders = info ? possibleGenders(info.genderRatio) : [];
  speciesChoices ??= [...data.catalog.species, ...FORM_CHOICES].map(sp => ({id: sp.id, name: sp.name, icon: () => img(miniSpriteUrl(sp.id, false), ''),
    meta: () => `#${String(sp.id).padStart(4, '0')}`}));

  const types = info ? [...new Set(info.types)] : [];
  const preview = h('div', {class: 'sheet-preview', style: types[0] !== undefined ? `--tint: var(--t-${typeKey(types[0])})` : undefined},
    h('div', {class: 'art'}, speciesSelection(draft.species).form ? h('span',{class:'missing'},name) : img(artworkUrl(draft.species, draft.shiny), name, '', fallbackArtworkUrl(draft.species, draft.shiny))),
    h('div', {}, h('div', {class: 'p-name'}, name), h('div', {class: 'p-sub'}, `No. ${String(draft.species).padStart(4, '0')} · Lv ${draft.level}`),
      h('div', {class: 'types', style: 'margin-top:8px'}, ...types.map(t => typeChip(t, true)))),
    h('div', {class: 'preview-moves'}, ...moves.map(id => {
      const m = data.catalog.getMove(id);
      return h('div', {}, h('span', {}, m?.name ?? `#${id}`), m ? typeChip(m.type, true) : null);
    })));

  const level = h('input', {type: 'number', id: 'add-level', min: 1, max: 100, value: draft.level, inputmode: 'numeric'});
  level.addEventListener('change', () => { draft.level = Math.min(100, Math.max(1, Math.floor(Number(level.value)) || 1)); renderAddDialog(); });
  const nature = h('select', {id: 'add-nature'}, ...NATURES.map((n, i) => {
    const up = NATURE_STATS[Math.floor(i / 5)]!, down = NATURE_STATS[i % 5]!;
    return h('option', {value: i}, up === down ? `${n} (neutral)` : `${n}  +${STAT_SHORT[up]} −${STAT_SHORT[down]}`);
  }));
  nature.value = String(draft.nature);
  nature.addEventListener('change', () => { draft.nature = Number(nature.value); });
  const gender = h('div', {class: 'seg', role: 'group', 'aria-label': 'Gender'}, ...(['male', 'female', 'genderless'] as Gender[]).filter(g => genders.includes(g) || (g !== 'genderless' && genders.length === 2)).map(g =>
    h('button', {type: 'button', 'aria-pressed': String(draft.gender === g), disabled: !genders.includes(g), onclick: () => { draft.gender = g; renderAddDialog(); }},
      g === 'male' ? '♂ Male' : g === 'female' ? '♀ Female' : 'Genderless')));
  const abilities = h('div', {class: 'abilities'}, ...slots.map(s => {
    const ability = getAbility(s.id);
    return h('button', {type: 'button', class: 'ability', 'aria-pressed': String(draft.slot === s.slot), onclick: () => { draft.slot = s.slot; renderAddDialog(); }},
      h('span', {class: 'a-name'}, ability?.name ?? `#${s.id}`), h('span', {class: 'a-slot'}, s.label));
  }));
  const shiny = h('input', {type: 'checkbox', checked: draft.shiny});
  shiny.addEventListener('change', () => { draft.shiny = shiny.checked; renderAddDialog(); });
  const ivs = h('div', {class: 'seg', role: 'group', 'aria-label': 'IVs'},
    h('button', {type: 'button', 'aria-pressed': String(!draft.perfect), onclick: () => { draft.perfect = false; renderAddDialog(); }}, 'Random IVs'),
    h('button', {type: 'button', 'aria-pressed': String(draft.perfect), onclick: () => { draft.perfect = true; renderAddDialog(); }}, 'Perfect IVs'));

  const form = h('div', {class: 'sheet-form'},
    h('div', {class: 'field'}, h('label', {for: 'add-species'}, 'Species'),
      combobox({id: 'add-species', label: 'Species', value: draft.species, choices: speciesChoices, placeholder: 'Search 1025 Pokémon…', limit: 60,
        onSelect: id => { setSpecies(id); renderAddDialog(); addDialog.querySelector<HTMLInputElement>('#add-level')?.focus(); }})),
    h('div', {class: 'row'}, h('label', {class: 'field'}, 'Level', level), h('label', {class: 'field'}, 'Nature', nature)),
    h('div', {class: 'field'}, h('span', {}, 'Ability'), abilities),
    h('div', {class: 'field'}, h('span', {}, 'Gender'), gender),
    h('div', {class: 'inline', style: 'justify-content:space-between;align-items:center'}, ivs, h('label', {class: 'check'}, shiny, 'Shiny')));

  if(creationMetadata){
    const customOT=h('input',{type:'text',value:creationOT.name,maxlength:7,'aria-label':'New Pokémon OT name'});customOT.addEventListener('change',()=>{creationOT.name=customOT.value;});
    const otID=h('input',{type:'number',value:creationOT.tid,min:0,max:65535,'aria-label':'New Pokémon Trainer ID'});otID.addEventListener('change',()=>{creationOT.tid=Number(otID.value);});
    const otSID=h('input',{type:'number',value:creationOT.sid,min:0,max:65535,'aria-label':'New Pokémon Secret ID'});otSID.addEventListener('change',()=>{creationOT.sid=Number(otSID.value);});
    form.append(h('details',{class:'editor-advanced'},h('summary',{},'Original trainer & encounter'),h('div',{class:'editor-fields'},h('label',{class:'field'},'OT name',customOT),h('label',{class:'field'},'Trainer ID',otID),h('label',{class:'field'},'Secret ID',otSID)),metadataFields(creationMetadata,changes=>{creationMetadata={...creationMetadata!,...changes};})));
  }
  const add = h('button', {type: 'button', class: 'btn primary', disabled: !info, onclick: () => confirmAdd()}, view === 'pc' ? 'Add to PC' : 'Add to party');
  addDialog.replaceChildren(
    h('div', {class: 'sheet-head'}, h('h2', {id: 'add-title'}, 'Add Pokémon'),
      h('button', {type: 'button', class: 'x', 'aria-label': 'Close', onclick: () => addDialog.close()},
        svg('<svg width="12" height="12" viewBox="0 0 12 12"><path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'))),
    h('div', {class: 'sheet-body'}, preview, form),
    h('div', {class: 'sheet-foot'}, h('p', {class: 'note'}, moves.length ? 'Starts with its level-up moves; edit them after adding.' : 'Starts with empty move slots. Choose its moves after adding, before using it in battle.'),
      h('button', {type: 'button', class: 'btn', onclick: () => addDialog.close()}, 'Cancel'), add));
}
function confirmAdd(): void {
  if (!session) return;
  const info = speciesInfo(speciesSelection(draft.species).speciesId, speciesSelection(draft.species).form);
  if (!info) return;
  const slot = abilitySlots(info).find(s => s.slot === draft.slot) ?? abilitySlots(info)[0]!;
  const ivs: StatValues = mapStats(() => draft.perfect ? 31 : Math.floor(Math.random() * 32));
  const moves = defaultMoves(info, draft.level).map(id => ({id, pp: data.catalog.getMove(id)?.basePp ?? 0}));
  const name = speciesName(draft.species);
  commit(bytes => {
    const save = readSave(bytes);
    const template = save.partyRecords.find(r => !decodePokemon(r).isEgg);
    if (!template) throw new Error('No template');
    let record = createPokemon(patchPokemonOT(template,creationOT), {speciesId: speciesSelection(draft.species).speciesId, form: speciesSelection(draft.species).form, level: draft.level, nature: draft.nature, shiny: draft.shiny, gender: draft.gender,
      ability: slot.id, abilitySlot: slot.slot, ivs, moves, name: data.catalog.getSpecies(speciesSelection(draft.species).speciesId)!.name, genderRatio: info.genderRatio, baseFriendship: info.baseFriendship,
      personal: data.getPersonal(speciesSelection(draft.species).speciesId, speciesSelection(draft.species).form)});
    if(creationMetadata)record=patchPokemonMetadata(record,{friendship:creationMetadata.friendship,language:creationMetadata.language,originGame:creationMetadata.originGame,otGender:creationMetadata.otGender,ball:creationMetadata.ball||4,metLevel:creationMetadata.metLevel,metLocation:creationMetadata.metLocation,eggLocation:creationMetadata.eggLocation,metDate:creationMetadata.metDate,eggDate:creationMetadata.eggDate,encounterType:creationMetadata.encounterType,fateful:creationMetadata.fateful});
    if (view === 'pc') {
      if (decodePokemon(readStorage(bytes).boxes[pcBox]![pcSlot]!).speciesId) throw new Error('Choose an empty PC slot first.');
      return patchBoxRecord(bytes, pcBox, pcSlot, record.slice(0, 136));
    }
    selected = save.partyCount;
    return addPartyRecord(bytes, record);
  }, `${name} added to ${view === 'pc' ? 'PC' : 'party'}`);
  addDialog.close();
  if (view !== 'pc') view = 'pokemon';
  render(); window.scrollTo(0, 0);
}

/* ---------- file io ---------- */
async function open(file: File): Promise<void> {
  try {
    const imported = await importSave(file);
    session = {original: imported.bytes, working: imported.bytes.slice(), container: imported.container, filename: imported.filename, history: []};
    selected = 0; pcBox = 0; pcSlot = 0;
    render();
    const save = readSave(imported.bytes);
    toast(save.tied ? 'Loaded — this save needs one in-game save before it can be edited' : `Loaded ${imported.filename}`, save.tied);
  } catch (error) { toast(errorText(error), true); }
}
fileInput.addEventListener('change', () => {
  const file = fileInput.files?.[0];
  if (file && (!isDirty() || confirm('Discard your edits and open another save?'))) void open(file);
  fileInput.value = '';
});
function exportSave(): void {
  if (!session) return;
  const blob = new Blob([new Uint8Array(wrapSave(session.working, session.container))], {type: 'application/octet-stream'});
  const url = URL.createObjectURL(blob);
  const a = h('a', {href: url, download: session.filename});
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(isDirty() ? 'Exported. Keep a backup of the original.' : 'Exported (no changes)');
}
exportButton.addEventListener('click', exportSave);
dockExport.addEventListener('click', exportSave);
function undo(): void {
  if (!session?.history.length) return;
  session.working = session.history.pop()!;
  render(); toast('Undone');
}
undoButton.addEventListener('click', undo);
dockUndo.addEventListener('click', undo);
document.addEventListener('keydown', event => {
  const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'z' && !event.shiftKey && !typing) { event.preventDefault(); undo(); }
});
let dragDepth = 0;
window.addEventListener('dragenter', e => { e.preventDefault(); dragDepth++; document.body.classList.add('dragging'); });
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove('dragging'); } });
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('drop', e => {
  e.preventDefault(); dragDepth = 0; document.body.classList.remove('dragging');
  const file = e.dataTransfer?.files[0];
  if (file && (!isDirty() || confirm('Discard your edits and open another save?'))) void open(file);
});
window.addEventListener('beforeunload', e => { if (isDirty()) e.preventDefault(); });
