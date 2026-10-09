/** Character identities are independent of trainer class and team slot.
 * Featured characters already have reviewed identities in trainer_guide.py.
 * Ordinary recurring characters below are reviewed against the quest guide,
 * trainer dialogue (a027/0718), and their exported battle locations.
 * Never merge arbitrary names: Grunts, Impostors, Pokémon and homonyms can
 * represent different opponents, even when their class also matches.
 */
const recurring = [
  [7, 155], // Zhishen: S.S. Anne monk, later at Sprout Tower.
  [13, 19, 165, 460, 464, 618, 633, 974], // Jessie
  [23, 166, 461, 465, 513, 619, 634, 975], // James
  [41, 303], [42, 315], // Eddie and Ethan, Cycling Road / Three Island.
  [163, 323, 562, 734, 755, 769, 832, 986], // Goh
  [173, 671], // Entei's story battles, including Molly's dream.
  [228, 266], // Norman
  [313, 657], [314, 659], [316, 661], [317, 656], [318, 658], [319, 660], // Biker gang
  [506, 637], // Del
  [511, 598], // A.J.
  [551, 750], // Tamao
  [646, 684], [647, 699], // Granny Mae and Dana
  [899, 953], // Kiyo
];
const identityOverrides = new Map(recurring.flatMap(ids => ids.map(id => [id, `recurring:${ids[0]}`])));
// The Fuchsia trial explicitly identifies the opponent using Koga's name as Janine.
for (const id of [325, 473, 564]) identityOverrides.set(id, 'character:Janine');
// The dream-world opponents are Molly's clones. Some battle names say Mei;
// preserve those labels on the actual teams, while collecting the whole scene.
for (const id of [176, 280, 611, 669, 670]) identityOverrides.set(id, 'character:Molly');

export function trainerIdentity(t) {
  return identityOverrides.get(t.id) ??
    (t.group && t.name.trim() && t.name !== 'Unnamed trainer' ? `character:${t.name}` : `record:${t.id}`);
}

export function inactiveEncounter(place) {
  return place.conds.length > 0 && place.conds.every(c => c.startsWith('never '));
}

export function teamLevelRange(t) {
  const levels = t.team.map(m => m.level);
  const min = Math.min(...levels), max = Math.max(...levels);
  return min === max ? `Lv. ${min}` : `Lv. ${min}–${max}`;
}

export function buildTrainerProfiles(trainers) {
  const groups = new Map();
  for (const t of trainers) {
    const key = trainerIdentity(t);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(t);
  }
  const profiles = [], byId = new Map();
  for (const [key, records] of groups) {
    const teams = [...records].sort((a, b) => Math.min(...a.team.map(m => m.level)) - Math.min(...b.team.map(m => m.level)) || a.id - b.id);
    const encounters = teams.flatMap((t, index) => {
      const places = [...new Map(t.places.map(p => [JSON.stringify(p), p])).values()];
      return places.map(place => ({ team: t, number: index + 1, place }));
    }).sort((a, b) => (a.place.map ?? '').localeCompare(b.place.map ?? '') || a.number - b.number);
    const label = key.startsWith('character:') ? key.slice('character:'.length) :
      `${teams[0].cls} ${teams[0].name}`.trim() || 'Unnamed trainer';
    const profile = { id: Math.min(...teams.map(t => t.id)), label, teams,
      note: key === 'character:Molly' ? 'Includes Molly’s dream-world clones. Some teams use the battle name Mei, shown below.' : null,
      encounters: encounters.filter(e => !inactiveEncounter(e.place)),
      inactive: encounters.filter(e => inactiveEncounter(e.place)),
      unconfirmed: teams.filter(t => !t.places.length) };
    profiles.push(profile);
    for (const t of teams) byId.set(t.id, profile);
  }
  profiles.sort((a, b) => a.label.localeCompare(b.label) || a.id - b.id);
  return { profiles, byId };
}
