import { escapeHtml } from './time-hints.mjs';

// Guide-defined comparison bands, not game rules or per-throw probabilities.
const bands = [
  { min: 200, level: 1, name: 'Very easy', tone: 'easy' },
  { min: 120, level: 2, name: 'Easy', tone: 'easy' },
  { min: 60, level: 3, name: 'Moderate', tone: 'moderate' },
  { min: 30, level: 4, name: 'Hard', tone: 'hard' },
  { min: 0, level: 5, name: 'Very hard', tone: 'very-hard' },
];
export function catchHint(value) {
  const known = value !== null && value !== '' && Number.isInteger(Number(value)) && Number(value) >= 0 && Number(value) <= 255;
  const band = known ? bands.find(band => Number(value) >= band.min) : { level: 0, name: 'Unknown', tone: 'unknown' };
  return {
    ...band,
    label: `Catch difficulty: ${band.name}`,
    detail: known ? `Base value: ${Number(value)} / 255` : 'Base catch value unknown',
    description: 'More filled bars mean a harder catch. This guide’s relative rating uses the base catch value: lower values mean harder catches. It is not a percentage. Your chance per throw also depends on remaining HP, status conditions and the ball you use.',
  };
}
export function catchIcon() {
  return '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><path d="M3 12h6m6 0h6"/></svg>';
}
export function formatCatchHint(value) {
  const hint = catchHint(value);
  const rating = hint.level ? ` (${hint.level} of 5)` : '';
  const meter = `<span class="ohg-catch-meter" aria-hidden="true">${Array.from({ length: 5 }, (_, i) => `<i${i < hint.level ? ' class="filled"' : ''}></i>`).join('')}</span>`;
  return `<button type="button" class="ohg-hint ohg-catch ohg-catch-${hint.tone}" data-catch-hint="${escapeHtml(value ?? '')}" aria-label="${escapeHtml(hint.label + rating)}" title="${escapeHtml(`${hint.label}. ${hint.detail}. ${hint.description}`)}">${catchIcon()}<span>${hint.name} catch</span>${meter}</button>`;
}
