import { escapeHtml, formatTimeHints } from './time-hints.mjs';

/** Explanations of existing encounter categories; the row retains its exact conditions. */
export const ENCOUNTER_HINTS = {
  land: { label: 'Grass / cave', description: 'Land encounters in grass or caves, depending on the location. Follow the time and conditions listed in this row.' },
  grass: { label: 'Grass', description: 'Walk through encounter grass in the listed area. Follow any time or special conditions shown.' },
  cave: { label: 'Cave', description: 'Walking encounters inside the listed cave. Follow any time or special conditions shown.' },
  surf: { label: 'Surfing', description: 'Encounter Pokémon on the water while using Surf in the listed area.' },
  oldrod: { label: 'Old Rod', description: 'Fish with the Old Rod. Each rod has its own encounter table; the chance shown is the species share of encounters, not the chance of getting a bite.' },
  goodrod: { label: 'Good Rod', description: 'Fish with the Good Rod. Each rod has its own encounter table; the chance shown is the species share of encounters, not the chance of getting a bite.' },
  superrod: { label: 'Super Rod', description: 'Fish with the Super Rod. Each rod has its own encounter table; the chance shown is the species share of encounters, not the chance of getting a bite.' },
  headbutt: { label: 'Headbutt trees', description: 'Use Headbutt on the listed tree type. Common and rare trees depend on your Trainer ID; special trees use a separate encounter table.' },
  rock: { label: 'Rock Smash', description: 'Use Rock Smash on breakable rocks in this area. The chance shown applies when a Pokémon encounter occurs.' },
  radio: { label: 'Radio encounters', description: 'Tune the radio to the station listed in this row. These encounters replace the specified grass slots; other slots stay unchanged.' },
  swarm: { label: 'Swarm', description: 'Requires the listed swarm encounter conditions. The shown rates cover replacement slots; other slots stay unchanged.' },
  safari: { label: 'Safari Zone', description: 'Select the listed Safari area. Available Pokémon can depend on placed objects and their development; no fixed encounter chance is established.' },
  contest: { label: 'Bug-Catching Contest', description: 'Join the contest under the weekday and National Pokédex conditions shown. Contest values are stored weights, not percentages.' },
  calendar: { label: 'Calendar encounter', description: 'Requires the date and time shown, using your game clock. These encounters replace a grass/cave slot on that date.' },
};
const shapes = {
  grass: '<path d="M4 20h16M7 20C7 14 5 10 3 8c5 1 8 5 9 12 0-8 3-14 8-17-2 6-3 12-3 17M12 15C10 9 9 6 7 4"/>',
  cave: '<path d="m2 20 4-12 6-5 6 5 4 12H2Zm6 0v-5a4 4 0 0 1 8 0v5M8 7l2 3m6-3-2 3"/>',
  surf: '<path d="M2 8c3 3 4-3 7 0s4-3 7 0 4-3 6 0M2 14c3 3 4-3 7 0s4-3 7 0 4-3 6 0M2 20c3 3 4-3 7 0s4-3 7 0 4-3 6 0"/>',
  rod: '<path d="M4 21 15 3h4v12a5 5 0 0 1-10 0v-2l3 3M7 16l3 2M15 3l-1 9"/>',
  headbutt: '<path d="M10 21v-5H6a4 4 0 0 1-2-7 5 5 0 0 1 4-6 5 5 0 0 1 8 0 5 5 0 0 1 4 6 4 4 0 0 1-2 7h-4v5M8 21h8"/>',
  rock: '<path d="m3 19 2-10 6-6 9 5 2 11H3ZM11 3l-1 6 5 3-3 7M2 4l2 2m16-3-2 2"/>',
  radio: '<rect x="3" y="8" width="18" height="13" rx="2"/><path d="m5 8 13-5M14 12h4m-4 4h4"/><circle cx="8" cy="14" r="2"/>',
  swarm: '<rect x="8" y="7" width="8" height="14" rx="4"/><path d="M9 3l2 4m4-4-2 4M4 9l4 2m12-2-4 2M3 15h5m8 0h5M5 21l3-3m11 3-3-3M12 11v10"/>',
  safari: '<path d="m3 11 3-8h3v10m12-2-3-8h-3v10M9 12h6M9 7h6"/><circle cx="6" cy="16" r="4"/><circle cx="18" cy="16" r="4"/>',
  contest: '<circle cx="12" cy="9" r="6"/><path d="m8 14-2 8 6-3 6 3-2-8m-7-5 2 2 4-4"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4m10-4v4M3 11h18m-14 4h2m6 0h2m-10 3h2"/>',
};
// Land tables combine grass and cave; a single compact landscape symbol represents both.
shapes.land = '<path d="m8 20 3-11 5-5 5 16H8Zm5 0v-5a2 2 0 0 1 4 0v5M2 20h7M5 20c0-5-1-8-3-10m3 7 3-5"/>';
export function encounterIcon(key) {
  return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[key] ?? shapes.rod}</svg>`;
}
const terms = {
  'grass/cave': 'land', grass: 'grass', cave: 'cave', surfing: 'surf',
  'old rod': 'oldrod', 'good rod': 'goodrod', 'super rod': 'superrod',
  headbutt: 'headbutt', 'rock smash': 'rock', radio: 'radio', swarm: 'swarm',
  'safari zone': 'safari', 'bug-catching contest': 'contest', 'calendar encounter': 'calendar',
};
/** Only method fields: never annotate Pokémon, item or move names in ordinary prose. */
export function formatEncounterHints(value) {
  const text = String(value ?? '');
  const pattern = /\b(grass\/cave|grass|cave|surfing|old rod|good rod|super rod|headbutt|rock smash|radio|swarm|safari zone|bug-catching contest|calendar encounter)\b/gi;
  let result = '', offset = 0;
  for (const match of text.matchAll(pattern)) {
    const key = terms[match[0].toLowerCase()], hint = ENCOUNTER_HINTS[key];
    result += formatTimeHints(text.slice(offset, match.index));
    result += `<button type="button" class="ohg-hint ohg-method ohg-method-${key}" data-encounter-hint="${key}" title="${escapeHtml(hint.description)}">${encounterIcon(key)}<span>${escapeHtml(match[0])}</span></button>`;
    offset = match.index + match[0].length;
  }
  return result + formatTimeHints(text.slice(offset));
}
