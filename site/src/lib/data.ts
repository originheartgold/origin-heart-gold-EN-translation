// Typed access to the generated game data (src/data/*.json, written by work/tools/site/export_data.py).
// Everything here runs at build time only; nothing is shipped to the browser unless a page embeds it.
import speciesJson from '../data/species.json';
import movesJson from '../data/moves.json';
import itemsJson from '../data/items.json';
import areasJson from '../data/areas.json';
import trainersJson from '../data/trainers.json';
import tutorsJson from '../data/tutors.json';
import abilitiesJson from '../data/abilities.json';
import tmsJson from '../data/tms.json';
import battleNotesJson from '../data/battle_notes.json';
import referenceCoverageJson from '../data/reference_coverage.json';
import { formatTutorCost } from './reference-format.mjs';
import { buildBattleIndexes } from './battle-indexes.mjs';
import { engineItemSources, formChanges, calendarEncounters, type FormChange, type CalendarEncounter } from './verified-mechanics';

export interface Evidence {
	kind: 'rom-data' | 'game-text' | 'author-note' | 'tested'; source?: string;
	workbook?: string; sheet?: string; row?: number; columns?: string; audit?: string;
}
export interface Description { text: string; evidence: Evidence; translationStatus?: string }
export interface AuthorNote {
	moveId?: number | null; abilityId?: number | null; itemId?: number; sourceAlias?: string;
	changeKind?: string; baseline?: string; before?: null; effectNote?: string | null;
	changeNote?: string | null; locationNote?: string | null; costNote?: string | null;
	note?: string | null; label?: string; fields?: Record<string, unknown>;
	areaSlugs?: string[]; locationLabelMatch?: boolean; configuredMoveId?: number | null; sourceConflictNote?: string; priorAuditNote?: string | null;
	configuredFields?: Record<string, unknown>;
	acquisitionComparison?: { status: string; areas: string[]; configuredShops?: {area: string | null; place: string}[]; evidence?: Evidence };
	highlightedFields?: string[]; addedInHack?: boolean; comparison?: unknown;
	verifiedGameplay?: boolean; evidence: Evidence;
}
export interface Ability {
	id: number; name: string; slug: string; unnamed: boolean; description: Description | null;
	authorNotes: AuthorNote[]; applicability: AuthorNote[]; evidence: Evidence[]; conflicts: { kind: string; text: string; source: string }[];
}
export interface TM { itemId: number; moveId: number; label: string; newInV4: boolean; evidence: Evidence; authorNotes: AuthorNote[] }
export interface Species {
	unavailableReason?: string | null;
	id: number; name: string; slug: string; region: string; types: string[];
	baseSpeciesId: number; formId: number; abilityIds: number[]; abilitySlots: number[]; hiddenAbilityId: number | null;
	abilities: string[]; hidden: string | null; stats: number[]; catch: number; gender: string;
	eggGroups: string[]; growth: string; ev: number[]; held: string[];
	evoFrom: EvoLink[]; evoTo: EvoLink[]; evoNotes: string[];
	how: string; battleOnly?: string | null; note?: string | null; levelup: [number, number][]; tms: 'all' | [string, number][];
	tutors: number[]; egg: number[]; foundIn: { area: string; methods: string[] }[];
	game?: string | null; tmNote?: string | null; quests?: Quest[];
	formChanges: FormChange[]; calendar: CalendarEncounter[]; referenceNotes: AuthorNote[];
}
/** One evolution as the game checks it; `never` marks a method the game's evolution code ignores. */
export interface EvoCond { text: string; item?: number; move?: number; species?: number }
export interface EvoLink {
	id: number; how: string; conds: EvoCond[]; never?: boolean; official?: string; blocked?: string; name?: string; original?: string | null;
}
/** A guide quest that explains a source (its heading carries the condition, e.g. a starter). */
export interface Quest { title: string; href: string }
export interface Move {
	originalComparison: { baseline: string | null; fields: { field: string; before: string | null; after: string }[]; effects: { text: string; uncertain: boolean; evidence: Evidence }[] };
	unnamed: boolean; description: Description | null; priority: number; targetId: number; target: string | null;
	flags: string[]; flagBits: number[]; evidence: Evidence[]; authorNotes: AuthorNote[];
	effectSummary: { text: string; evidence: Evidence }[];
	testedNotes: { text: string; playerSummary: string; limitation: string; href: string; evidence: Evidence }[];
	effects: { quality: number; hits: number[]; condition: number; condition_chance: number;
		condition_kind: number; condition_turns: number[]; crit_stage: number; flinch_chance: number;
		effect: number; drain: number; heal: number; stat_changes: { stat: number; stages: number; chance: number }[] };
	conflicts: { kind: string; text: string; source: string }[];
	id: number; name: string; slug: string; type: string; cat: string; power: string; acc: string; pp: string; tm: string[];
	game?: string | null;
}
export interface ItemSource {
	kind: string; area: string | null; place: string; tech?: string; qty?: number; pay?: string; price?: number;
	near?: string | null; quests?: Quest[]; note?: string;
}
export interface WildHeldSource {
	species: number; chance: number;
	locations: { area: string; place: string; method: string; level: string; encounterRate: number | null }[];
}
export interface ItemReferenceNote extends AuthorNote {
	rarity?: string | null; acquisitionNote?: string | null; useNote?: string | null; configuredNote?: string; auditEvidence?: Evidence;
}
export interface Item {
	description: Description | null; effectText: Description | null; authorNotes: AuthorNote[];
	referenceNotes: ItemReferenceNote[]; legacySourceNotes: AuthorNote[]; legacyUseNotes: AuthorNote[];
	evolutionUses: { speciesId: number; resultId: number; how: string; never: boolean; blocked?: string }[];
	tutorUses: { moveId: number; places: { place: string; area: string | null }[]; cost: unknown }[]; trainerUses: number[];
	effects: { holdEffectId: number; evidence: Evidence; note: string };
	unavailableReason?: string | null;
	id: number; name: string; slug: string; pocket: string; price: number; sources: ItemSource[];
	wildHeld?: WildHeldSource[];
	neededBy: { place: string; area: string | null }[]; game?: string | null; note?: string | null;
}
export interface ContestRow { id: number; name: string; level: string; rate: number; score: number }
export interface EncRow { id: number | null; name: string; level: string; pct: number | null }
export interface EncSection { title: string; rows: EncRow[] }
export interface Area {
	name: string; slug: string; region: string; rank: number; zones: number[]; calendar: CalendarEncounter[];
	referenceNotes: AuthorNote[]; maps: { zone: number; name: string; type: string; vanilla: string }[];
	encounters: { label: string; rates: Record<string, number>; sections: EncSection[] }[];
	encNotes: string[]; contest: { note: string; sets: { title: string; rows: ContestRow[] }[] } | null;
	headbutt: { label: string; trees: number; special: number; sections: EncSection[] }[];
	trainers: number[];
	items: { id: number; name: string; qty: number; kind: string; map: string; near?: string | null }[];
	gifts: { id: number; name: string; qty: number; pay: string; kind: string; quests: Quest[] }[];
	shops: { list: number; room: string; stock: { id: number; name: string; price: number }[] }[];
	trades: { give: number; giveName: string; get: number; getName: string; nickname: string; loan: boolean }[];
	statics: { kind: string; id: number; name: string; level: number | null; quests: Quest[] }[];
}
export interface TrainerMon {
	abilityId: number | null; itemId: number | null; moveIds: number[];
	id: number; name: string; level: number; ability: string | null; item: string | null; nature: string | null;
	ivs: number; hpIvs: number; evs: number[] | null; moves: string[];
}
export interface Trainer {
	evidence: Evidence; id: number; cls: string; name: string; double: boolean; items: string[]; team: TrainerMon[];
	places: { area: string | null; map: string | null; how: string; conds: string[] }[]; group: string | null; note?: string | null;
}
export interface Tutor {
	authorNotes: AuthorNote[];
	move: number; moveName: string; game?: string | null; places: { place: string; area: string | null }[]; cost: unknown;
	species: 'all' | 'restricted' | number[]; quests: Quest[];
	note: { text: string; alias: string; href: string } | null;
}

export const species: Species[] = speciesJson.map((s) => ({ ...s,
	formChanges: formChanges.filter((f) => f.base === s.id || f.result === s.id),
	calendar: calendarEncounters.filter((e) => e.pokemon === s.id || e.species === s.id),
})) as Species[];
export const moves = movesJson as Move[];
export const abilities = abilitiesJson as Ability[];
export const tms = tmsJson as TM[];
export const battleNotes = battleNotesJson as Record<string, AuthorNote[]>;
export const referenceCoverage = referenceCoverageJson;
export const items: Item[] = itemsJson.map((i) => ({ ...i, sources: [
	...i.sources, ...engineItemSources.filter((s) => s.item === i.id).map(({ item, ...source }) => source),
] })) as Item[];
// Region of a location as players know it. The map data only knows "kanto" or "johto" (by map number),
// which puts the hack's island chain under Kanto and the ship and the far-away places under Johto.
// Reviewed by hand; slugs not listed keep the exported region. The Resort Zone is Johto (Route 48).
const REGION_OVERRIDES: Record<string, string> = {
	'one-island': 'sevii', 'two-island': 'sevii', 'three-island': 'sevii', 'four-island': 'sevii',
	'five-island': 'sevii', 'six-island': 'sevii', 'seven-island': 'sevii',
	'island-cave': 'sevii', 'island-forest': 'sevii', 'islanders-house': 'sevii', 'ritual-shrine': 'sevii',
	'secret-forest': 'sevii', 'shipyard-ruins': 'sevii', 'sky-pillar-peak': 'sevii',
	'alto-mare-library': 'sevii', 'alto-mare-waters': 'sevii',
	's-s-anne': 'other', 'jubilife-city': 'other', 'dream-world': 'other',
	'safari-zone-gate': 'johto',    // the Pal Park map; reached only from the Resort Zone
};
export const areas: Area[] = areasJson.map((a) => ({ ...a,
	region: REGION_OVERRIDES[a.slug] ?? a.region,
	calendar: calendarEncounters.filter((e) => a.zones.includes(e.zone)),
})) as Area[];
export const trainers = trainersJson as Trainer[];
export const tutors = tutorsJson as Tutor[];

export const speciesById = new Map(species.map((s) => [s.id, s]));
export const abilityById = new Map(abilities.map((a) => [a.id, a]));
export const abilityByName = new Map(abilities.map((a) => [a.name, a]));
export const tmByItemId = new Map(tms.map((t) => [t.itemId, t]));
export const moveById = new Map(moves.map((m) => [m.id, m]));
export const moveByName = new Map(moves.map((m) => [m.name, m]));
export const itemById = new Map(items.map((i) => [i.id, i]));
export const itemByName = new Map(items.map((i) => [i.name, i]));
export const areaBySlug = new Map(areas.map((a) => [a.slug, a]));
export const areaByName = new Map(areas.map((a) => [a.name, a]));
export const trainerById = new Map(trainers.map((t) => [t.id, t]));

// A documented route is not a promise of a completed capture test. Only configured calendar rows count.
export function hasDocumentedSource(s: Species) {
	return !s.unavailableReason && !!(s.how || s.formChanges.some((f) => f.result === s.id && speciesById.get(f.base)?.how) ||
		s.calendar.some((e) => e.pokemon === s.id && e.status === 'configured'));
}

export interface LearnMethod { method: 'level' | 'tm' | 'tutor' | 'egg'; levels?: number[]; labels?: string[]; itemIds?: number[]; allTms?: boolean }
export interface MoveLearner { speciesId: number; baseSpeciesId: number; formId: number; unavailableReason: string | null; battleOnly: string | null; documentedSource: boolean; methods: LearnMethod[] }
export interface AbilityHolder { speciesId: number; baseSpeciesId: number; formId: number; regularSlots: number[]; hidden: boolean; unavailableReason: string | null; documentedSource: boolean }
export const { moveLearners, abilityHolders, tmCompatibility } = buildBattleIndexes(species, tms, hasDocumentedSource) as {
	moveLearners: Map<number, MoveLearner[]>; abilityHolders: Map<number, AbilityHolder[]>;
	tmCompatibility: Map<number, number[]>;
};

export function hasData(a: Area) {
	return !!(a.encounters.length || a.headbutt.length || a.trainers.length || a.items.length || a.gifts.length ||
		a.shops.length || a.trades.length || a.statics.length || a.calendar.length);
}

/** Site-relative URL that respects the configured base path. */
export function url(path: string) {
	const base = import.meta.env.BASE_URL.replace(/\/$/, '');
	return base + (path.startsWith('/') ? path : '/' + path);
}

export const pokemonUrl = (id: number | null) => {
	const s = id == null ? undefined : speciesById.get(id);
	return s ? url(`/pokemon/${s.slug}/`) : undefined;
};
export const moveUrl = (m: Move | undefined) => (m ? url(`/moves/${m.slug}/`) : undefined);
export const itemUrl = (i: Item | undefined) => (i ? url(`/items/${i.slug}/`) : undefined);
export const areaUrl = (slug: string | null) => (slug && areaBySlug.has(slug) ? url(`/locations/${slug}/`) : undefined);

export const STAT_NAMES = ['HP', 'Attack', 'Defense', 'Sp. Atk', 'Sp. Def', 'Speed'];
export const REGIONS = ['kanto', 'johto', 'sevii', 'other'];

export function regionLabel(r: string) {
	return ({ kanto: 'Kanto', johto: 'Johto', sevii: 'Sevii Islands and Alto Mare' } as Record<string, string>)[r] || 'Other places';
}

/** Trainers worth a heading of their own (Gym Leaders, rivals, Elite Four...). */
export function trainerTitle(t: Trainer) {
	return `${t.cls} ${t.name}`.trim();
}

export const abilityUrl = (a: Ability | undefined) => a ? url(`/abilities/${a.slug}/`) : undefined;
export const tmByLabel = new Map(tms.map(t => [t.label, t]));
export const tutorsByMove = new Map<number, Tutor[]>();
for (const tutor of tutors) {
  const list = tutorsByMove.get(tutor.move) ?? [];
  list.push(tutor); tutorsByMove.set(tutor.move, list);
}
export function availabilityToken(s: Species) {
  return s.unavailableReason ? 'unavailable' : hasDocumentedSource(s) ? 'documented' : s.battleOnly ? 'battle' : 'unknown';
}
export function availabilityLabel(s: Species) {
  return ({ unavailable: 'NOT AVAILABLE IN GAME', documented: 'Where to get it', battle: 'Battle only', unknown: 'No known way to get it' })[availabilityToken(s)];
}
export function abilityAlias(a: Ability) {
  return a.unnamed ? a.authorNotes.find(n => n.sourceAlias)?.sourceAlias : undefined;
}
export const tutorCost = formatTutorCost;
