import { timeHint, timeIcon, escapeHtml } from './time-hints.mjs';
import { ENCOUNTER_HINTS, encounterIcon } from './encounter-hints.mjs';
import { catchHint, catchIcon } from './catch-hints.mjs';

/** One delegated tooltip works with static pages and dynamically rendered planner cards. */
export function setupTimeHints() {
  if (document.documentElement.dataset.timeHints) return;
  document.documentElement.dataset.timeHints = 'true';
  const popup = document.createElement('div');
  popup.id = 'ohg-time-tooltip'; popup.className = 'ohg-time-tooltip';
  popup.setAttribute('role', 'tooltip'); popup.hidden = true;
  document.body.append(popup);
  let active = null, pinned = false, timeout;
  function close() {
    clearTimeout(timeout);
    if (active) { active.removeAttribute('aria-describedby'); if (active.dataset.nativeTitle) active.title = active.dataset.nativeTitle; }
    active = null; pinned = false; popup.hidden = true;
  }
  function show(button) {
    clearTimeout(timeout);
    if (active !== button) { close(); active = button; }
    const method = button.dataset.encounterHint;
    const capture = button.hasAttribute('data-catch-hint');
    const hint = capture ? catchHint(button.dataset.catchHint) : method ? ENCOUNTER_HINTS[method] : timeHint(button.dataset.timeHint, button.dataset.timeContext);
    const detail = hint.detail ?? hint.hours;
    const icon = capture ? catchIcon() : method ? encounterIcon(method) : timeIcon(button.dataset.timeHint);
    if (button.title) { button.dataset.nativeTitle = button.title; button.removeAttribute('title'); }
    popup.innerHTML = `<strong>${icon}${escapeHtml(hint.label)}</strong>${detail ? `<b>${escapeHtml(detail)}</b>` : ''}<p>${escapeHtml(hint.description)}</p>`;
    popup.hidden = false; button.setAttribute('aria-describedby', popup.id);
    const rect = button.getBoundingClientRect(), box = popup.getBoundingClientRect();
    const left = Math.max(12, Math.min(innerWidth - box.width - 12, rect.left + rect.width / 2 - box.width / 2));
    const top = rect.bottom + box.height + 12 <= innerHeight ? rect.bottom + 10 : Math.max(12, rect.top - box.height - 10);
    popup.style.left = `${left}px`; popup.style.top = `${top}px`;
  }
  const buttonAt = target => target instanceof Element ? target.closest('[data-time-hint], [data-encounter-hint], [data-catch-hint]') : null;
  document.addEventListener('pointerover', event => { const button = buttonAt(event.target); if (button) show(button); if (popup.contains(event.target)) clearTimeout(timeout); });
  document.addEventListener('pointerout', event => {
    if (!active || pinned || active.contains(event.relatedTarget) || popup.contains(event.relatedTarget)) return;
    if (active.contains(event.target) || popup.contains(event.target)) timeout = setTimeout(close, 150);
  });
  document.addEventListener('focusin', event => { const button = buttonAt(event.target); if (button) show(button); else close(); });
  document.addEventListener('click', event => {
    const button = buttonAt(event.target);
    if (button) { event.preventDefault(); if (active === button && pinned) close(); else { show(button); pinned = true; } }
    else if (!popup.contains(event.target)) close();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') close(); });
  window.addEventListener('scroll', close, true); window.addEventListener('resize', close);
}
