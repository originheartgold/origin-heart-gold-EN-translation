/** Planner state uses the hack's unique record IDs, including alternate forms. */
export const TEAM_SIZE = 6;
export const STORAGE_KEY = 'ohg-team-builder-v1';

export function sanitizeTeam(value, knownIds) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter(id => Number.isInteger(id) && knownIds.has(id)))].slice(0, TEAM_SIZE);
}

/** null means no shared team; an explicit empty/invalid team must not restore local state. */
export function parseTeamHash(hash, knownIds) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  if (!params.has('team')) return null;
  return sanitizeTeam(params.get('team').split(',').filter(id => /^\d+$/.test(id)).map(Number), knownIds);
}

export function teamHash(team) { return `#team=${team.join(',')}`; }

export function filterCatalog(catalog, { query = '', type = '', region = '', availability = '' } = {}) {
  const normalize = text => text.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase();
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  return catalog.filter(mon => (!type || mon.types.includes(type)) && (!region || mon.region === region) &&
    (!availability || mon.availability === availability) &&
    terms.every(term => normalize(`${mon.name} ${mon.game ?? ''} ${mon.types.join(' ')} ${mon.abilities.join(' ')} ${mon.hidden ?? ''} #${mon.baseSpeciesId}`).includes(term)));
}

/** Follow only incoming evolution/transformation links, never siblings or the Pokédex number. */
export function acquisitionFamily(id, byId, formChanges = []) {
  const visited = new Set(), result = [];
  function visit(current) {
    if (visited.has(current) || !byId.has(current)) return;
    visited.add(current);
    const mon = byId.get(current);
    for (const entry of mon.evoFrom ?? []) if (!entry.never) visit(entry.id);
    for (const form of formChanges) if (form.result === current) visit(form.base);
    result.push(current);
  }
  visit(id);
  return result;
}
