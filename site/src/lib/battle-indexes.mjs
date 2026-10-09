/** Pure build-time joins. Keep unavailable and form entries in every index.
 * No browser bundle or gameplay verification is implied by these relationships.
 */
export function buildBattleIndexes(species, tms, documentedSource = () => false) {
  const moveLearners = new Map(), abilityHolders = new Map(), tmCompatibility = new Map();
  for (const tm of tms) tmCompatibility.set(tm.itemId, []);
  for (const s of species) {
    const learner = new Map();
    const add = (moveId, method) => {
      const methods = learner.get(moveId) ?? [];
      const existing = methods.find(m => m.method === method.method);
      if (existing) {
        for (const key of ['levels', 'labels', 'itemIds']) {
          if (method[key]) existing[key] = [...new Set([...(existing[key] ?? []), ...method[key]])];
        }
      } else methods.push(method);
      learner.set(moveId, methods);
    };
    for (const [level, move] of s.levelup) add(move, { method: 'level', levels: [level] });
    for (const tm of tms) {
      if (s.tms === 'all' || s.tms.some(([label, move]) => label === tm.label && move === tm.moveId)) {
        add(tm.moveId, { method: 'tm', labels: [tm.label], itemIds: [tm.itemId], allTms: s.tms === 'all' });
        tmCompatibility.get(tm.itemId).push(s.id);
      }
    }
    for (const move of s.tutors) add(move, { method: 'tutor' });
    for (const move of s.egg) add(move, { method: 'egg' });
    for (const [moveId, methods] of learner) {
      const rows = moveLearners.get(moveId) ?? [];
      rows.push({ speciesId: s.id, baseSpeciesId: s.baseSpeciesId, formId: s.formId,
        unavailableReason: s.unavailableReason ?? null, battleOnly: s.battleOnly ?? null,
        documentedSource: documentedSource(s), methods });
      moveLearners.set(moveId, rows);
    }
    const abilities = new Set([...s.abilityIds, s.hiddenAbilityId].filter(Boolean));
    for (const abilityId of abilities) {
      const rows = abilityHolders.get(abilityId) ?? [];
      rows.push({ speciesId: s.id, baseSpeciesId: s.baseSpeciesId, formId: s.formId,
        regularSlots: s.abilitySlots.map((id, slot) => id === abilityId ? slot + 1 : 0).filter(Boolean),
        hidden: s.hiddenAbilityId === abilityId, unavailableReason: s.unavailableReason ?? null,
        documentedSource: documentedSource(s) });
      abilityHolders.set(abilityId, rows);
    }
  }
  return { moveLearners, abilityHolders, tmCompatibility };
}
