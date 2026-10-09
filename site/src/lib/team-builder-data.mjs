import { acquisitionFamily } from './team-builder.mjs';
import { playerNote } from './reference-format.mjs';

/** Project only acquisition facts, rather than shipping movesets and other unrelated data. */
export function createPlannerData({ species, areas, items, moves, formChanges = [] }) {
  const byId = new Map(species.map(mon => [mon.id, mon]));
  const areaBySlug = new Map(areas.map(area => [area.slug, area]));
  const itemById = new Map(items.map(item => [item.id, item]));
  const moveById = new Map(moves.map(move => [move.id, move]));
  const monLink = id => ({ id, name: byId.get(id)?.name ?? `Pokémon #${id}`, href: `/pokemon/${byId.get(id)?.slug}/` });
  const condition = entry => {
    if (entry.never) return { text: playerNote(entry.blocked) || `This evolution does not work in Origin HeartGold${entry.official ? ` (official games: ${entry.official})` : ''}.`, links: [], blocked: true };
    const links = [];
    const text = (entry.conds ?? []).map(cond => {
      const record = cond.item != null ? itemById.get(cond.item) : cond.move != null ? moveById.get(cond.move) : byId.get(cond.species);
      if (record) links.push({ name: record.name, href: `/${cond.item != null ? 'items' : cond.move != null ? 'moves' : 'pokemon'}/${record.slug}/` });
      return cond.text.replace('{}', record?.name ?? 'Unknown requirement');
    }).join(' ');
    const levelUp = /^(level up\b|high friendship\b|Beauty\b|Lv\s)/i.test(entry.how);
    return { text: `${levelUp ? 'Level up ' : ''}${text || entry.how}`, links, blocked: false };
  };
  const evolution = (from, to, entry) => ({ from: monLink(from), to: monLink(to), ...condition(entry), kind: 'evolution' });
  const transformation = form => ({ from: monLink(form.base), to: monLink(form.result), kind: 'form', blocked: false,
    text: `Hold ${itemById.get(form.item)?.name ?? 'the required item'}. ${form.condition.replace(' Tested in an emulator.', '')} Removing the item returns it to its base form.`,
    links: itemById.has(form.item) ? [{ name: itemById.get(form.item).name, href: `/items/${itemById.get(form.item).slug}/` }] : [] });
  return {
    detail(id) {
      const selected = byId.get(id);
      if (!selected) return null;
      const ids = acquisitionFamily(id, byId, formChanges);
      return {
        id,
        members: ids.map(memberId => {
          const mon = byId.get(memberId);
          return {
            ...monLink(memberId), catchRate: mon.catch, unavailableReason: playerNote(mon.unavailableReason),
            battleOnly: mon.battleOnly, note: playerNote(mon.note), otherSources: playerNote(mon.otherSources),
            quests: mon.quests ?? [], evoNotes: mon.evoNotes.map(playerNote),
            wild: mon.wildEncounters.map(encounter => ({ ...encounter,
              notes: (areaBySlug.get(encounter.area)?.encNotes ?? []).map(playerNote),
              href: `/locations/${encounter.area}/#${encounter.method.startsWith('Calendar encounter:') ? 'calendar' : 'wild'}` })),
            acquisitions: mon.acquisitions.map(({ kind, area, place, level, offer, conditions, quests }) => ({
              kind, place, level, conditions, quests, href: area ? `/locations/${area}/` : null,
              offer: offer == null ? null : monLink(offer),
            })),
            // Base-species calendar matches can refer to a DIFFERENT form. Never advertise those here.
            calendar: (mon.calendar ?? []).filter(event => event.pokemon === memberId),
          };
        }),
        steps: ids.flatMap(memberId => [
          ...byId.get(memberId).evoFrom.map(entry => evolution(entry.id, memberId, entry)),
          ...formChanges.filter(form => form.result === memberId).map(transformation),
        ]),
        next: [...selected.evoTo.map(entry => evolution(id, entry.id, entry)),
          ...formChanges.filter(form => form.base === id).map(transformation)],
      };
    },
  };
}
