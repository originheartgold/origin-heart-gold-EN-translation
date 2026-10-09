// Origin HeartGold guide: small progressive enhancements. Everything works without this script.
// - quest pages: game setup and quest filters, per-quest "done" ticks, report links
// - tables/lists: text filter, select and checkbox filters, click-to-sort headers
(() => {
	const store = {
		get(k, d) { try { const v = localStorage.getItem('ohg:' + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
		set(k, v) { try { localStorage.setItem('ohg:' + k, JSON.stringify(v)); } catch { /* private mode */ } },
	};
	const repo = document.querySelector('meta[name="ohg-repo"]')?.content;

	// ---------------------------------------------------------------- technical references
	// Script files, flags and code addresses are hidden by CSS (.tech). Maintainers turn them on in their own
	// browser by opening any page with ?tech=1 (remembered), and off again with ?tech=0.
	const techParam = new URLSearchParams(location.search).get('tech');
	if (techParam !== null) store.set('tech', techParam === '1');
	if (store.get('tech', false)) document.documentElement.dataset.tech = 'on';

	// ---------------------------------------------------------------- quests
	// "Done" ticks are stored per page and quest: "guide/<page>#<heading id>", or the quest's own id when the
	// guide gives one (<section data-quest-id>). Version 1 stored bare heading ids, which two pages could share
	// ("small-extras"); those are carried over page by page, except the shared ones (data-legacy-shared).
	function pageKey() {
		const m = location.pathname.match(/\/(guide\/[^/]+)\/?(?:index\.html)?$/);
		return m ? m[1] : location.pathname.replace(/\/+$/, '');
	}
	function asArray(v) { return Array.isArray(v) ? v.filter((x) => typeof x === 'string') : []; }

	function setupQuests() {
		const quests = [...document.querySelectorAll('section.quest')];
		if (!quests.length) return;
		const page = pageKey();
		const keyOf = (q) => {
			if (q.dataset.questId) return 'quest:' + q.dataset.questId;
			const id = q.querySelector('h2')?.id;
			return id ? page + '#' + id : null;
		};
		const done = new Set(asArray(store.get('done2', [])));
		// one-time migration of this page's version-1 ticks
		const migrated = new Set(asArray(store.get('done2-migrated', [])));
		if (!migrated.has(page)) {
			const legacy = new Set(asArray(store.get('done', [])));
			if (legacy.size) {
				for (const q of quests) {
					const id = q.querySelector('h2')?.id;
					const key = keyOf(q);
					if (id && key && legacy.has(id) && !q.dataset.legacyShared) done.add(key);
				}
				store.set('done2', [...done]);
			}
			migrated.add(page);
			store.set('done2-migrated', [...migrated]);
		}
		let setup = store.get('setup', null);
		if (!setup || typeof setup !== 'object') setup = { starter: '', gender: '', postgame: true };

		const panel = document.createElement('div');
		panel.className = 'game-setup not-content';
		panel.innerHTML = `
			<strong>Your game</strong>
			<label>Starter <select name="starter"><option value="">Any</option><option>Charmander</option><option>Pikachu</option><option>Bulbasaur</option></select></label>
			<label>Playing as <select name="gender"><option value="">Either</option><option value="male">Boy</option><option value="female">Girl</option></select></label>
			<label>Quest type <select name="kind"><option value="">All quests</option><option value="main">Main quest</option><option value="side">Side quest</option></select></label>
			<label>Progress <select name="progress"><option value="">All stages</option><option value="before">Before post-game</option><option value="postgame">Post-game only</option></select></label>
			<label><input type="checkbox" name="hidedone"> Hide finished</label>
			<span class="quest-filter-help">Post-game quests open after your final Hall of Fame entry. Entries with earlier steps stay under “Before post-game”.</span>
			<span class="hidden-count" role="status" aria-live="polite"></span>`;
		const content = document.querySelector('.sl-markdown-content');
		content?.prepend(panel);
		const $ = (n) => panel.querySelector(`[name="${n}"]`);
		$('starter').value = ['Charmander', 'Pikachu', 'Bulbasaur'].includes(setup.starter) ? setup.starter : '';
		$('gender').value = ['male', 'female'].includes(setup.gender) ? setup.gender : '';
		$('kind').value = ['main', 'side'].includes(setup.kind) ? setup.kind : '';
		// Preserve the old “Show quests after the final Hall of Fame” preference.
		$('progress').value = ['', 'before', 'postgame'].includes(setup.progress) ? setup.progress : setup.postgame === false ? 'before' : '';
		$('hidedone').checked = !!setup.hidedone;

		for (const q of quests) {
			const h = q.querySelector('h2');
			const id = h?.id;
			const key = keyOf(q);
			if (!id || !key) continue;
			const tools = document.createElement('p');
			tools.className = 'quest-tools not-content';
			const issue = repo ? `${repo}/issues/new?template=guide-problem.yml&page=${encodeURIComponent(location.pathname + '#' + id)}&title=${encodeURIComponent('[' + h.textContent.trim() + '] ')}` : '';
			tools.innerHTML = `<label><input type="checkbox"> Done</label>${issue ? `<a href="${issue}" rel="noopener">Report a problem with this quest</a>` : ''}`;
			const box = tools.querySelector('input');
			box.checked = done.has(key);
			q.classList.toggle('is-done', box.checked);
			box.addEventListener('change', () => {
				box.checked ? done.add(key) : done.delete(key);
				q.classList.toggle('is-done', box.checked);
				store.set('done2', [...done]);
				apply();
			});
			(q.querySelector('.quest-meta') || h).after(tools);
		}

		// the quest a link points at is never hidden
		const hashQuest = () => {
			let t = null;
			try { t = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { /* bad hash */ }
			return t?.closest('section.quest') || null;
		};

		function apply() {
			const s = { starter: $('starter').value, gender: $('gender').value, kind: $('kind').value, progress: $('progress').value, hidedone: $('hidedone').checked };
			store.set('setup', s);
			const target = hashQuest();
			let hidden = 0;
			for (const q of quests) {
				const st = q.dataset.starter?.split(',');
				const g = q.dataset.gender?.split(',');
				const key = keyOf(q);
				const hide = q !== target && ((s.starter && st && !st.includes(s.starter)) || (s.gender && g && !g.includes(s.gender)) ||
					(s.kind && q.dataset.kind !== s.kind) ||
					(s.progress === 'before' && q.dataset.postgame === 'yes') ||
					(s.progress === 'postgame' && q.dataset.postgame !== 'yes') || (s.hidedone && key && done.has(key)));
				q.classList.toggle('is-hidden', !!hide);
				if (hide) hidden++;
			}
			panel.querySelector('.hidden-count').textContent = `${quests.length - hidden} of ${quests.length} quests shown.${hidden === quests.length ? ' No matching quests in this chapter. Change your filters to see more.' : ''}${target ? ' The linked quest stays visible.' : ''}`;
			// keep the page's table of contents in step
			document.querySelectorAll('starlight-toc a, mobile-starlight-toc a').forEach((a) => {
				let t = null;
				try { t = document.getElementById(decodeURIComponent(a.hash.slice(1))); } catch { /* bad hash */ }
				const sec = t?.closest('section.quest');
				a.parentElement.style.display = sec?.classList.contains('is-hidden') ? 'none' : '';
			});
		}
		panel.addEventListener('change', apply);
		// a link to a hidden quest still shows it, also for links on the same page
		window.addEventListener('hashchange', () => {
			apply();
			hashQuest()?.querySelector('h2')?.scrollIntoView();
		});
		apply();
	}

	// ---------------------------------------------------------------- tables and lists
	// Accept ordinary keyboard spellings such as "poke ball" and "kings rock".
	const searchText = value => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '')
		.replace(/['’]/g, '').toLowerCase();
	function setupFilters() {
		const filters = [...document.querySelectorAll('.table-filter')];
		const tables = [...document.querySelectorAll('table.sortable')];
		const targets = [...new Set([...filters.map(f => document.getElementById(f.dataset.table)), ...tables])].filter(Boolean);
		const states = targets.map((target, index) => {
			const f = filters.find(f => f.dataset.table === target.id), body = target.tBodies?.[0];
			const rows = body ? [...body.rows] : [...target.querySelectorAll('[data-row]')].filter(r => !r.parentElement?.closest('[data-row]'));
			const text = new Map(rows.map(r => [r, searchText(r.textContent)]));
			const input = f?.querySelector('input[type="search"]');
			const selects = [...(f?.querySelectorAll('select[data-key]') || [])];
			const checks = [...(f?.querySelectorAll('input[type="checkbox"][data-key]') || [])];
			const defaults = new Map(checks.map(c => [c, c.checked]));
			const ths = tables.includes(target) ? [...target.querySelectorAll('thead th')] : [];
			const labels = ths.map(th => th.textContent.trim());
			// Single indexes have short keys; each table on multi-table pages has its own namespace.
			const prefix = targets.length === 1 ? '' : (target.id || `table-${index + 1}`) + '.';
			const param = key => prefix + key, count = f?.querySelector('.filter-count');
			if (count) { count.setAttribute('role', 'status'); count.setAttribute('aria-atomic', 'true'); }
			const empty = document.createElement('p');
			empty.className = 'filter-empty'; empty.hidden = true;
			empty.textContent = 'No matching results. Change your search or filters, or reset to show everything.';
			if (f) target.after(empty);
			const reset = document.createElement('button');
			reset.type = 'button'; reset.className = 'filter-reset'; reset.textContent = 'Reset';
			reset.setAttribute('aria-label', `Reset ${target.id || 'table'} search, filters and sorting`);
			if (f) f.append(reset);
			let sort = null, searchEditing = false;
			function apply() {
				const words = searchText(input?.value || '').trim().split(/\s+/).filter(Boolean);
				let n = 0;
				for (const r of rows) {
					const tokens = key => (r.dataset[key] || '').split('|');
					const ok = words.every(w => text.get(r).includes(w)) && selects.every(s => !s.value || tokens(s.dataset.key).includes(s.value)) && checks.every(c => c.checked || !tokens(c.dataset.key).includes(c.dataset.showValue));
					r.hidden = !ok; if (ok) n++;
				}
				ths.forEach((th, col) => th.setAttribute('aria-sort', sort?.col === col ? sort.dir : 'none'));
				if (body) {
					const ordered = [...rows];
					if (sort) {
						const key = r => r.cells[sort.col]?.dataset.sortValue ?? r.cells[sort.col]?.textContent.trim() ?? '';
						const number = value => /^[-+]?[$]?\d[\d,]*(?:\.\d+)?%?$/.test(value) ? Number(value.replace(/[$,%]/g, '')) : NaN;
						const numeric = ths[sort.col].dataset.sortType === 'number' || ordered.every(r => !key(r) || ['—', 'var.'].includes(key(r)) || !Number.isNaN(number(key(r))));
						const order = new Map(rows.map((r, i) => [r, i]));
						ordered.sort((a, b) => {
							const x = key(a), y = key(b), nx = number(x), ny = number(y);
							if (numeric && (Number.isNaN(nx) || Number.isNaN(ny))) return Number.isNaN(nx) && Number.isNaN(ny) ? order.get(a) - order.get(b) : Number.isNaN(nx) ? 1 : -1;
							const c = numeric ? nx - ny : x.localeCompare(y, undefined, {numeric: true});
							return (sort.dir === 'ascending' ? c : -c) || order.get(a) - order.get(b);
						});
					}
					body.append(...ordered);
				}
				if (count) count.textContent = `${n} of ${rows.length} shown${sort ? `; sorted by ${labels[sort.col]}, ${sort.dir}` : ''}`;
				empty.hidden = n !== 0;
			}
			function restore() {
				const params = new URLSearchParams(location.search);
				if (input) input.value = params.get(param('q')) || '';
				for (const s of selects) { const value = params.get(param(s.dataset.key)); s.value = [...s.options].some(o => o.value === value) ? value : ''; }
				for (const c of checks) { const value = params.get(param(c.dataset.key)); c.checked = value === '1' ? true : value === '0' ? false : defaults.get(c); }
				const match = params.get(param('sort'))?.match(/^(\d+)-(asc|desc)$/);
				sort = match && Number(match[1]) < ths.length ? {col: Number(match[1]), dir: match[2] === 'asc' ? 'ascending' : 'descending'} : null;
				searchEditing = false; apply();
			}
			function save(replace = false) {
				const url = new URL(location.href);
				const set = (key, value) => value ? url.searchParams.set(param(key), value) : url.searchParams.delete(param(key));
				set('q', input?.value.trim());
				for (const s of selects) set(s.dataset.key, s.value);
				for (const c of checks) set(c.dataset.key, c.checked === defaults.get(c) ? '' : c.checked ? '1' : '0');
				set('sort', sort ? `${sort.col}-${sort.dir === 'ascending' ? 'asc' : 'desc'}` : '');
				if (url.href === location.href) return false;
				history[replace ? 'replaceState' : 'pushState'](null, '', url);
				return true;
			}
			input?.addEventListener('input', () => { apply(); if (save(searchEditing)) searchEditing = true; });
			input?.addEventListener('blur', () => { searchEditing = false; });
			f?.addEventListener('change', e => { if (e.target !== input) { apply(); save(); } searchEditing = false; });
			reset.addEventListener('click', () => { if (input) input.value = ''; selects.forEach(s => { s.value = ''; }); checks.forEach(c => { c.checked = defaults.get(c); }); sort = null; searchEditing = false; apply(); save(); });
			ths.forEach((th, col) => {
				const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'sort-button'; btn.append(...th.childNodes); th.append(btn);
				btn.addEventListener('click', () => { sort = {col, dir: sort?.col === col && sort.dir === 'ascending' ? 'descending' : 'ascending'}; searchEditing = false; apply(); save(); });
			});
			restore(); return {restore};
		});
		window.addEventListener('popstate', () => states.forEach(s => s.restore()));
	}

	// Keep wide reference tables inside an accessible, independently scrollable panel.
	function setupTableScroll() {
		const updates = [];
		document.querySelectorAll('.sl-markdown-content table').forEach(table => {
			if (table.closest('.table-scroll, .save-editor')) return;
			const panel = document.createElement('div');
			panel.className = 'table-scroll';
			const hint = document.createElement('p');
			hint.className = 'table-scroll-hint';
			hint.textContent = 'Scroll sideways to see all columns →';
			hint.hidden = true;
			panel.setAttribute('aria-label', `${table.caption?.textContent || table.querySelector('th')?.textContent || 'Reference'} table — scroll for more columns`);
			table.before(panel); panel.append(table); panel.after(hint);
			const update = () => {
				const overflow = panel.scrollWidth > panel.clientWidth + 2;
				hint.hidden = !overflow;
				if (overflow) { panel.tabIndex = 0; panel.setAttribute('role', 'region'); }
				else { panel.removeAttribute('tabindex'); panel.removeAttribute('role'); }
			};
			updates.push(update);
			if (typeof ResizeObserver !== 'undefined') new ResizeObserver(update).observe(panel);
			update();
		});
		if (typeof ResizeObserver === 'undefined') window.addEventListener('resize', () => updates.forEach(update => update()));
	}

	const init = () => { setupQuests(); setupFilters(); setupTableScroll(); };
	document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
