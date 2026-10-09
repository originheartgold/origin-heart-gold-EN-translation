/** These are the encounter windows used by Origin HeartGold, not local browser time. */
export const TIME_HINTS = {
  morning: { label: 'Morning', hours: '04:00–09:59', description: 'Early morning encounters. Uses the clock set on your DS or emulator.' },
  day: { label: 'Day', hours: '10:00–19:59', description: 'Daytime encounters, including the evening before 20:00. Uses the game clock.' },
  evening: { label: 'Evening', hours: 'Part of Day', description: 'Encounter tables include evening in Day, which ends at 19:59. Night begins at 20:00. Follow any narrower hours given by an event.' },
  night: { label: 'Night', hours: '20:00–03:59', description: 'Spans midnight: late evening and the following early morning. Date-specific events still require the listed calendar date.' },
  any: { label: 'Any time', hours: 'All 24 hours', description: 'No time-of-day restriction. Other requirements, such as the date, story progress or encounter method, still apply.' },
};
export const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
const shapes = {
  morning: '<path d="M3 17h18M5 21h14M6 13a6 6 0 0 1 12 0M12 2v3M3 7l2 2M21 7l-2 2"/>',
  day: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
  evening: '<path d="M3 17h18M5 21h14M6 13a6 6 0 0 1 12 0M12 2v4m-2-2 2 2 2-2"/>',
  night: '<path d="M20.5 14A8.8 8.8 0 0 1 10 3.5 9 9 0 1 0 20.5 14Z"/>',
  any: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};
export function timeIcon(key) {
  return `<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${shapes[key] ?? shapes.any}</svg>`;
}
export function timeHint(key, context = 'encounter') {
  if (key === 'day' && context === 'evolution') return { label: 'Daytime evolution', hours: '04:00–19:59', description: 'For this evolution, daytime includes the morning. Level up during these hours and meet the other listed requirements.' };
  return TIME_HINTS[key] ?? TIME_HINTS.any;
}
/** Call only on condition prose, never on names (Morning Sun and Sunny Day are moves). */
export function formatTimeHints(text, context = 'encounter') {
  const pattern = /\b(any time|all day|morning|day|evening|night)\b/gi;
  let result = '', offset = 0;
  for (const match of String(text ?? '').matchAll(pattern)) {
    const key = /^(any time|all day)$/i.test(match[0]) ? 'any' : match[0].toLowerCase();
    const hint = timeHint(key, context);
    result += escapeHtml(text.slice(offset, match.index));
    result += `<button type="button" class="ohg-hint ohg-time ohg-time-${key}" data-time-hint="${key}" data-time-context="${context}" title="${escapeHtml(`${hint.hours}. ${hint.description}`)}">${timeIcon(key)}<span>${escapeHtml(match[0])}</span></button>`;
    offset = match.index + match[0].length;
  }
  return result + escapeHtml(String(text ?? '').slice(offset));
}
