/** Explicitly empty configured payment lists are free; absent data remains unknown. */
export function formatTutorCost(cost) {
  if (Array.isArray(cost)) return cost.length ? cost.join(', ') : 'Free';
  return cost == null ? 'Cost unknown' : String(cost);
}

/** Keep undecoded HP costs and disputed effects in source details, not as gameplay advice. */
export function playerMoveEffects(move) {
  if (move.conflicts.some(c => c.kind === 'unresolved-behavior')) return [];
  return move.effectSummary.flatMap(({text}) => {
    if (text.includes('HP loss/cost field')) return [];
    return [text.replace(/^Configured /, '')
      .replace(/^hits: (.+)\.$/, 'Hits $1 times.')
      .replace(/^critical-hit stage: \+(.+)\.$/, (_, stage) => `Critical-hit rate: +${stage} ${Number(stage) === 1 ? 'stage' : 'stages'}.`)
      .replace(/^healing: /, 'HP restored: ')
      .replace(/^drain: /, 'HP drained: ')
      .replace(/^recoil: /, 'Recoil: ')
      .replace(/^(.+) change: ([+-]\d+) stage\(s\)(?:, (\d+)% chance)?\.$/, (_, stat, stages, chance) => `${stat} ${stages} ${Math.abs(Number(stages)) === 1 ? 'stage' : 'stages'}${chance ? `; ${chance}% chance` : ''}.`)];
  });
}

/** Player wording of existing acquisition audits; originals remain in source panels. */
export function playerItemCaveat(id, text) {
  const specific = {
    15: 'Buy it in Saffron City or get the Route 16 gift. Regular Poké Marts do not sell it.',
    32: 'Use the vending machines listed above; Azalea shops do not sell Lemonade.',
    86: 'Look for hidden items or the Route 9 gift. The Azalea shop does not sell it.',
    155: 'Costs $100 at New Bark Town, $80 at Goldenrod City or $20 at Viridian City.',
    169: 'Get it from the Fuchsia shard exchange.', 170: 'Get it from the Fuchsia shard exchange.',
    171: 'Win it from Battle Frontier Scratch-Off Cards.', 172: 'Get it from the Fuchsia shard exchange.',
    173: 'Get it from the Fuchsia shard exchange.', 174: 'Win it from Battle Frontier Scratch-Off Cards.',
    201: 'Buy it from the S.S. Anne vendor for $800.', 202: 'Buy it from the S.S. Anne vendor for $800.',
    203: 'Steal it from the Team Rocket Grunt’s Pinsir on the S.S. Anne with Thief or Covet. Your Pokémon keeps holding the berry after battle.',
    204: 'Steal it from Swimmer♂ Ned’s Empoleon on Route 21 with Thief or Covet. Your Pokémon keeps holding the berry after battle.',
    205: 'No way to get it is known in v4.', 206: 'No way to get it is known in v4.',
    209: 'Buy it from the Route 9 vendor for $1,500.', 210: 'Buy it from the Route 9 vendor for $1,500.',
    242: 'Buy it in Goldenrod City or get it as a gift in the places listed above.',
    286: 'No way to get it is known in v4.',
    370: 'Get the gift in the Route 26 house.',
    373: 'No way to get TM46 is known. Do not rely on the Six Island Meowth quest for it.',
    429: 'The Ice Path recipe requires 10 Durin Berries, 5 Rare Candies, Sacred Ash, Fresh Water and $10,000.',
    481: 'Get it through the Olivine City event.',
  };
  if (specific[id]) return specific[id];
  if (text.startsWith('The author’s S rarity')) return 'Older availability notes overlook the shops or other sources listed above.';
  return text.replace(/Configured sources/g, 'Sources').replace(/configured /g, '')
    .replace(/The audited v4 sources/g, 'The v4 sources').replace(/the audited vendors/g, 'the vendors')
    .replace(/the audited quest/g, 'the quest').replace(/ in the reachable scripts/g, '')
    .replace(/reachable v4/g, 'v4').replace(/reachable TM46/g, 'TM46').replace(/reachable /g, '')
    .replace(/, recorded separately under Sources/g, '').replace(/ \(D-\d+\)/g, '');
}

/** Presentation only: original descriptions, test limits and provenance stay in normalized data. */
export function playerMoveDescription(move) {
  const practical = {
    55: 'Blasts the target with water. Does not burn the target.',
    295: 'Attacks with a burst of light. Has a 30% chance to lower the target’s Sp. Def by one stage.',
    307: 'Unleashes a blast of flame with a 10% chance to burn the target. Attack again on the next turn—no recharge needed.',
    337: 'Slashes the target with huge, sharp claws.',
    340: 'Attacks on the same turn, with a 30% chance to paralyze the target.',
    344: 'Charges the target with electricity, with a 10% chance to paralyze it. No recoil when knocking out a wild Pokémon.',
    461: 'Raises the user’s Sp. Atk and Speed by one stage. The user stays in battle without fainting.',
  };
  return practical[move.id] ?? move.authorNotes.find(n => n.effectNote)?.effectNote ?? move.description?.text ?? '';
}

export function playerAbilityDescription(ability) {
  // Water Veil's genuine disagreement is kept as a specific limitation, not resolved here.
  if (ability.id === 41) return ability.description?.text ?? '';
  return ability.authorNotes.find(n => n.effectNote)?.effectNote ?? ability.description?.text ?? '';
}

/** A single labeled baseline; missing previous values remain explicitly absent. */
export function playerMoveChanges(move) {
  const comparison = move.originalComparison;
  if (!comparison) return [];
  const value = (field, text) => field === 'Accuracy' && text !== '—' ? `${text}%` : text;
  return [
    ...comparison.fields.map(({field, before, after}) => before == null
      ? `${field} changed to ${value(field, after)}.`
      : `${field}: ${value(field, before)} → ${value(field, after)}.`),
    ...comparison.effects.map(({text}) => text),
  ];
}

/** Access prose is usable only when the source identity and place agree. */
export function playerTutorAccess(tutor) {
  return [...new Set(tutor.authorNotes.filter(n => n.comparison?.identityMatches !== false && n.comparison?.locationAreas?.length && n.locationNote).map(n => n.locationNote))];
}

export function playerItemDescription(item) {
  return item.referenceNotes.find(n => n.effectNote)?.effectNote ?? item.effectText?.text ?? 'No effect description is available.';
}

export function playerNote(text) {
  if (!text) return '';
  if (text.startsWith('Every wild Unown')) return 'Wild Unown always appear as the A form, so the other letters cannot be caught normally.';
  if (text.startsWith("Lycanroc's form depends")) return 'Lycanroc’s form depends on when Rockruff evolves: Dusk Form at 17:00–19:59, Midnight Form at 20:00–03:59, otherwise Midday Form.';
  return text.replace(/ \(tested in an emulator[^)]*\)/gi, '')
    .replace(/; read from the game code; not tested in game/gi, '')
    .replace(/ Read from the game code; not tested in game\./gi, '')
    .replace(/ Tested in an emulator[^.]*\./gi, '');
}
