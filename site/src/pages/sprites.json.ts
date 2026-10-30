// /sprites.json: the names the guide can illustrate with a PokéAPI sprite (site/public/ohg.js, phone layout).
// "p" maps a Pokémon name to its national number (the 96 px sprite), "i" an item name to PokéAPI's item slug.
import type { APIRoute } from 'astro';
import { items, species } from '../lib/data';

export const GET: APIRoute = async () => {
	const p: Record<string, number> = {};
	for (const s of species) {
		if (s.formId === 0 && s.baseSpeciesId >= 1 && s.baseSpeciesId <= 1025 && !(s.name in p)) p[s.name] = s.baseSpeciesId;
	}
	const i: Record<string, string> = {};
	for (const it of items) {
		// TMs are named by number here but by type in PokéAPI's sprite set; the rest share the slug
		if (!/^(TM|HM)\d/.test(it.name) && !(it.name in i)) i[it.name] = it.slug;
	}
	return new Response(JSON.stringify({ p, i }), { headers: { 'Content-Type': 'application/json; charset=utf-8' } });
};
