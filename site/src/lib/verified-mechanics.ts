/** Manually reviewed native mechanics for v4.0.3; kept outside the generated JSON.
 * Evidence: work/notes/chinese_source_rom_verify_{data,mechanics,calendar}.md.
 * CN CRC32 59CBBDAA; the reviewed code/table ranges also match the existing EN WIP.
 * Keep configured calendar rows distinct from proven acquisition routes.
 */
export interface EngineItemSource {
	item: number; kind: string; area: null; place: string; qty: number;
	note: string; quests: { title: string; href: string }[];
}
export const engineItemSources: EngineItemSource[] = [
	{ item: 744, kind: 'automatic', area: null, place: 'Starting equipment', qty: 1,
		note: 'Added to the Bag during new-game setup.',
		quests: [{ title: 'Capture chains and the Chain Logger', href: '/mechanics/#capture-chains' }] },
	{ item: 745, kind: 'automatic', area: null, place: 'After battle', qty: 1,
		note: 'The game adds an EV Allocator after battle if you do not already have one. The exact first acquisition screen has not been replayed.',
		quests: [{ title: 'Redistributing EVs', href: '/mechanics/#ev-allocator' }] },
	...[{ item: 740, savings: '30,000' }, { item: 741, savings: '40,000' }, { item: 743, savings: '50,000' }].map(({ item, savings }) => ({
		item, kind: 'savings reward', area: null, place: "Mom's savings purchases", qty: 1,
		note: `Savings threshold: $${savings}. Costs $3,000 from your savings. Queued for delivery; reaching the threshold does not mean immediate receipt.`,
		quests: [{ title: "Mom's charm purchases", href: '/mechanics/#moms-charms' }],
	})),
];

export interface FormChange {
	base: number; result: number; item: number; condition: string;
}
export const formChanges: FormChange[] = [
	{ base: 6, result: 1027, item: 325, condition: 'Any nature except Timid or Modest.' },
	{ base: 6, result: 1028, item: 325, condition: 'Timid or Modest nature.' },
	{ base: 150, result: 1440, item: 114, condition: 'No nature requirement.' },
	{ base: 658, result: 1194, item: 761, condition: 'No nature requirement.' },
	{ base: 487, result: 1152, item: 112, condition: 'No nature requirement.' },
	// Plates 298–313 (Flame … Iron) → the Arceus form players see, in item order. The stored form number follows the
	// Gen 4 type order (D-1501), but the summary shows the Plate's type and colours (tested in an emulator, all 16).
	...[1162, 1163, 1165, 1164, 1167, 1154, 1156, 1157, 1155, 1166, 1159, 1158, 1160, 1168, 1169, 1161].map((result, i) => ({
		base: 493, result, item: 298 + i, condition: 'Its Multitype Ability changes its type to match the Plate. Tested in an emulator.',
	})),
];

export interface CalendarEncounter {
	key: string; month: number; day: number; date: string; zone: number; area: string;
	place: string; species: number; pokemon: number; form: number; name: string;
	period: string; level: number | null; status: 'configured' | 'unresolved' | 'unavailable'; note: string;
}
// Native table 0x020F6A64. It replaces the final land slot, not water/fishing slots.
export const calendarEncounters: CalendarEncounter[] = [
	{ key: 'keldeo', month: 6, day: 23, date: 'June 23', zone: 181, area: 'fuchsia-city', place: "Fuchsia City — Koga's forest preserve", species: 647, pokemon: 647, form: 0, name: 'Keldeo', period: 'All day', level: 5, status: 'configured', note: 'The forest preserve only; not every part of Fuchsia City.' },
	{ key: 'meloetta', month: 7, day: 14, date: 'July 14', zone: 117, area: 'ilex-forest', place: 'Ilex Forest', species: 648, pokemon: 648, form: 0, name: 'Meloetta', period: 'All day', level: 6, status: 'configured', note: 'Replaces the final land encounter slot.' },
	{ key: 'hoopa', month: 7, day: 18, date: 'July 18', zone: 90, area: 'mt-silver', place: 'Mt. Silver — exterior', species: 720, pokemon: 720, form: 0, name: 'Hoopa', period: 'Morning only', level: 50, status: 'configured', note: '04:00–09:59. Neither Hoopa entry applies during the daytime period.' },
	{ key: 'hoopa-unbound', month: 7, day: 18, date: 'July 18', zone: 90, area: 'mt-silver', place: 'Mt. Silver — exterior', species: 720, pokemon: 1243, form: 1, name: 'Hoopa Unbound', period: 'Night only', level: 50, status: 'configured', note: '20:00–03:59, while the calendar date is July 18.' },
	{ key: 'diancie', month: 7, day: 19, date: 'July 19', zone: 492, area: 'island-forest', place: 'Island Forest', species: 719, pokemon: 719, form: 4, name: 'Diancie', period: 'All day', level: 17, status: 'configured', note: 'The entry uses a form number the game does not define, so it appears as a normal Diancie (not Mega Diancie).' },
	{ key: 'genesect', month: 8, day: 11, date: 'August 11', zone: 113, area: 'ruins-of-alph', place: 'Ruins of Alph — exterior', species: 649, pokemon: 649, form: 0, name: 'Genesect', period: 'All day', level: 5, status: 'configured', note: 'The exterior only; not the puzzle chambers.' },
	{ key: 'floette-eternal-flower', month: 10, day: 16, date: 'October 16', zone: 96, area: 'national-park', place: 'National Park', species: 670, pokemon: 1222, form: 5, name: 'Floette (Eternal Flower)', period: 'All day', level: 14, status: 'configured', note: 'The normal park encounter table; not a verified Bug-Catching Contest encounter.' },
];
