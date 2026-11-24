// Origin HeartGold guide: small progressive enhancements. Everything works without this script.
// - quest pages: game setup and quest filters, per-quest "done" ticks, report links
// - guide pages on phones: steps and quests as rows that open on tap, a dock with Sections and Quests sheets,
//   sprites beside Pokémon and items; every page on a phone gets the menu sheet
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
			<label><input type="checkbox" name="hidedone"> Hide finished</label>
			<span class="hidden-count" role="status" aria-live="polite"></span>`;
		const content = document.querySelector('.sl-markdown-content');
		content?.prepend(panel);
		const $ = (n) => panel.querySelector(`[name="${n}"]`);
		$('starter').value = ['Charmander', 'Pikachu', 'Bulbasaur'].includes(setup.starter) ? setup.starter : '';
		$('gender').value = ['male', 'female'].includes(setup.gender) ? setup.gender : '';
		$('kind').value = ['main', 'side'].includes(setup.kind) ? setup.kind : '';
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

		// a quest is filtered out when the player's game can't get it (starter, gender) or it is the other quest type
		const filteredOut = (ds, s) => !!((s.starter && ds.starter && !ds.starter.split(',').includes(s.starter)) ||
			(s.gender && ds.gender && !ds.gender.split(',').includes(s.gender)) || (s.kind && ds.kind && ds.kind !== s.kind));

		// Chapter walkthrough: quest links under "Opens up" and "Warning". Done quests are crossed out; filtered-out ones
		// vanish. A Warning box disappears when everything in it is done or filtered out, and an empty list goes with its box.
		function applyChapterLinks(s) {
			for (const li of document.querySelectorAll('li.chapter-quest')) {
				const isDone = done.has('quest:' + li.dataset.questId);
				li.classList.toggle('is-done', isDone);
				li.classList.toggle('is-hidden', filteredOut(li.dataset, s));
			}
			for (const box of document.querySelectorAll('.chapter-warning, .chapter-unlocks')) {
				const items = [...box.querySelectorAll('li.chapter-quest')];
				const warn = box.classList.contains('chapter-warning');
				const live = items.filter((li) => !li.classList.contains('is-hidden') && !(warn && li.classList.contains('is-done')));
				box.classList.toggle('is-hidden', !live.length);
			}
		}

		function apply() {
			const s = { starter: $('starter').value, gender: $('gender').value, kind: $('kind').value, hidedone: $('hidedone').checked };
			store.set('setup', s);
			const target = hashQuest();
			let hidden = 0;
			for (const q of quests) {
				const st = q.dataset.starter?.split(',');
				const g = q.dataset.gender?.split(',');
				const key = keyOf(q);
				const hide = q !== target && (filteredOut(q.dataset, s) || (s.hidedone && key && done.has(key)));
				q.classList.toggle('is-hidden', !!hide);
				if (hide) hidden++;
			}
			applyChapterLinks(s);
			panel.querySelector('.hidden-count').textContent = `${quests.length - hidden} of ${quests.length} quests shown.${hidden === quests.length ? ' No matching quests in this chapter. Change your filters to see more.' : ''}${target ? ' The linked quest stays visible.' : ''}`;
			// keep the page's table of contents in step
			document.querySelectorAll('starlight-toc a, mobile-starlight-toc a').forEach((a) => {
				let t = null;
				try { t = document.getElementById(decodeURIComponent(a.hash.slice(1))); } catch { /* bad hash */ }
				const sec = t?.closest('section.quest');
				a.parentElement.style.display = sec?.classList.contains('is-hidden') ? 'none' : '';
			});
			document.dispatchEvent(new Event('ohg:quests'));
		}
		panel.addEventListener('change', apply);
		// a link to a hidden quest still shows it, also for links on the same page
		window.addEventListener('hashchange', () => {
			apply();
			hashQuest()?.querySelector('h2')?.scrollIntoView();
		});
		apply();
	}

	// ---------------------------------------------------------------- guide pages on phones
	// Below 50rem a guide page becomes one sequence. Walkthrough steps are rows that open on tap; the quests a step
	// opens move under that step (and the separate "Quests in this chapter" section goes), each a row with its Done tick
	// that opens on tap too. A dock at the bottom opens two sheets: Sections (the page's steps and headings, with a find
	// box) and Quests (every quest on the page with its tick and a jump link, plus the game filters). Wider screens are
	// untouched: the extra controls stay hidden unless <html data-ohg-mobile> is set, and the quests go back where they were.
	function setupMobileGuide() {
		if (!/\/guide\//.test(location.pathname)) return;
		const content = document.querySelector('.sl-markdown-content');
		if (!content) return;
		const steps = [...content.querySelectorAll('.chapter-step')];
		const quests = [...content.querySelectorAll('section.quest')];
		const tocLinks = [...document.querySelectorAll('mobile-starlight-toc nav a')];
		if (!steps.length && !quests.length && tocLinks.length < 2) return;
		const root = document.documentElement;
		const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html) e.innerHTML = html; return e; };
		const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
		const chevron = '<svg class="ohg-m-chevron" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
		const byHash = (hash) => { try { return hash ? document.getElementById(decodeURIComponent(hash.slice(1))) : null; } catch { return null; } };
		const questById = new Map(quests.map((q) => [q.dataset.questId, q]));

		// folds: data-open on the element shows its body; its toggle carries aria-expanded
		const setOpen = (fold, open) => {
			fold.toggleAttribute('data-open', open);
			fold.querySelector(':scope > .ohg-m-row .ohg-m-toggle, :scope > .ohg-m-toggle')?.setAttribute('aria-expanded', String(open));
		};
		// a link into a fold opens it and every fold around it
		const openTo = (t) => { for (let f = t?.closest('.ohg-m-fold'); f; f = f.parentElement?.closest('.ohg-m-fold')) setOpen(f, true); };

		// quests: a row with the Done tick (a mirror of the quest's own box, which setupQuests owns) and the title; the
		// body opens on tap. The real heading stays in the body for anchors and screen readers.
		const questTitle = (q) => q.querySelector('h2')?.textContent.trim() || '';
		quests.forEach((q) => {
			const h = q.querySelector('h2');
			const real = q.querySelector('.quest-tools input[type="checkbox"]');
			if (!h || !real) return;
			const tags = [...q.querySelectorAll('.quest-meta .tag-missable, .quest-meta .tag-starter, .quest-meta .tag-gender, .quest-meta .tag-postgame')]
				.map((t) => t.textContent.trim()).join(' · ');
			const row = el('div', 'ohg-m-row', `<label class="ohg-m-tick"><input type="checkbox" aria-label="Done: ${esc(questTitle(q))}"></label>` +
				`<button type="button" class="ohg-m-toggle"><span class="ohg-m-title">${esc(questTitle(q))}</span>${tags ? `<span class="ohg-m-meta">${esc(tags)}</span>` : ''}${chevron}</button>`);
			const box = row.querySelector('input');
			const sync = () => { box.checked = real.checked; q.classList.toggle('ohg-m-done', real.checked); };
			box.addEventListener('change', () => { real.checked = box.checked; real.dispatchEvent(new Event('change', { bubbles: true })); });
			document.addEventListener('ohg:quests', sync);
			sync();
			row.querySelector('.ohg-m-toggle').addEventListener('click', () => setOpen(q, !q.hasAttribute('data-open')));
			q.prepend(row);
			q.classList.add('ohg-m-fold');
			setOpen(q, false);
		});

		// hidden items: the chapter's locations (pictures and directions, see sync_guide.py chapter_hidden_areas) go under
		// the first step that names the place; the rest gather in a "Hidden items nearby" step at the end
		const areasBox = content.querySelector('.chapter-hidden-areas');
		const areas = [...content.querySelectorAll('.chapter-hidden-area')];
		const areasOf = new Map(); // step -> its areas
		const spare = [];
		// The locations come in route order, like the steps, so each goes to the first step at or after the previous
		// location's step whose title names it, or failing that whose text does; "Mt. Moon" never matches inside
		// "Mt. Moon Square", because longer location names are blanked out of the text first.
		const names = areas.map((a) => a.dataset.area.toLowerCase()).sort((x, y) => y.length - x.length);
		const blank = (text, name) => names.filter((n) => n !== name && n.includes(name)).reduce((t, n) => t.split(n).join(' '), text);
		const named = steps.map((s) => [s, s.dataset.title?.toLowerCase() || '', (s.querySelector('p')?.textContent || '').toLowerCase()]);
		let from = 0;
		for (const area of areas) {
			const name = area.dataset.area.toLowerCase();
			const after = named.slice(from);
			const hit = after.find(([, title]) => blank(title, name).includes(name)) || after.find(([, , text]) => blank(text, name).includes(name));
			if (!hit) { spare.push(area); continue; }
			areasOf.set(hit[0], [...(areasOf.get(hit[0]) || []), area]);
			from = named.indexOf(hit);
		}
		areas.forEach((area) => {
			const spots = parseInt(area.dataset.spots || '0', 10);
			const toggle = el('button', 'ohg-m-toggle', `<span class="ohg-m-title">Hidden items: ${esc(area.dataset.area)}</span><span class="ohg-m-meta">${spots === 1 ? '1 spot' : spots + ' spots'} · pictures show where to press A</span>${chevron}`);
			toggle.type = 'button';
			toggle.addEventListener('click', () => setOpen(area, !area.hasAttribute('data-open')));
			const row = el('div', 'ohg-m-row');
			row.append(toggle);
			area.prepend(row);
			area.classList.add('ohg-m-fold', 'ohg-m-area');
			setOpen(area, false);
		});
		areasOf.forEach((list, step) => list.sort((x, y) => areas.indexOf(x) - areas.indexOf(y)));

		// steps: a row that opens the text, then the quests it opens (moved in from the quests section), the warning
		// and the hidden items of the place
		const places = new Map(); // moved node -> the comment that holds its place
		const park = (node) => { if (!places.has(node)) { const c = document.createComment('moved'); node.before(c); places.set(node, c); } };
		steps.forEach((step, i) => {
			const title = step.dataset.title || step.querySelector('p strong')?.textContent.replace(/[.:]\s*$/, '') || `Step ${i + 1}`;
			const unlocks = step.querySelector('.chapter-unlocks');
			const mine = [...(unlocks?.querySelectorAll('li.chapter-quest') || [])].map((li) => questById.get(li.dataset.questId)).filter(Boolean);
			const hidden = areasOf.get(step) || [];
			const spots = hidden.reduce((n, a) => n + parseInt(a.dataset.spots || '0', 10), 0);
			const meta = [];
			if (step.classList.contains('chapter-optional')) meta.push('Optional');
			if (mine.length) meta.push(mine.length === 1 ? '1 quest' : `${mine.length} quests`);
			if (spots) meta.push(spots === 1 ? '1 hidden item' : `${spots} hidden items`);
			if (step.querySelector('.chapter-warning')) meta.push('<span class="ohg-m-warn">Closes a missable</span>');
			const toggle = el('button', 'ohg-m-toggle', `<span class="ohg-m-title">${esc(title)}</span>${meta.length ? `<span class="ohg-m-meta">${meta.join(' · ')}</span>` : ''}${chevron}`);
			toggle.type = 'button';
			toggle.addEventListener('click', () => setOpen(step, !step.hasAttribute('data-open')));
			const row = el('div', 'ohg-m-row');
			row.append(toggle);
			step.prepend(row);
			step.classList.add('ohg-m-fold', 'ohg-m-step');
			if (mine.length) {
				const list = el('div', 'ohg-m-quests');
				(unlocks || step).after(list);
				step.ohgQuests = { list, mine };
			}
			if (hidden.length) {
				const list = el('div', 'ohg-m-areas');
				step.append(list);
				step.ohgAreas = { list, hidden };
			}
			setOpen(step, false);
		});
		let spareStep = null;
		if (spare.length && steps.length) {
			spareStep = el('div', 'chapter-step chapter-optional ohg-m-fold ohg-m-step ohg-m-extra');
			const toggle = el('button', 'ohg-m-toggle', `<span class="ohg-m-title">Hidden items nearby</span><span class="ohg-m-meta">${spare.length === 1 ? '1 place' : spare.length + ' places'} this chapter passes</span>${chevron}`);
			toggle.type = 'button';
			toggle.addEventListener('click', () => setOpen(spareStep, !spareStep.hasAttribute('data-open')));
			const row = el('div', 'ohg-m-row');
			row.append(toggle);
			spareStep.append(row, el('div', 'ohg-m-areas'));
			steps[steps.length - 1].after(spareStep);
			setOpen(spareStep, false);
		}
		const placed = new Set(steps.flatMap((s) => s.ohgQuests?.mine || []));
		const loose = quests.filter((q) => !placed.has(q)); // quests no step opens: they stay where they are
		const questsHeading = document.getElementById('quests-in-this-chapter')?.closest('.sl-heading-wrapper') || document.getElementById('quests-in-this-chapter');
		const questsIntro = questsHeading?.nextElementSibling?.matches('p') ? questsHeading.nextElementSibling : null;
		const moveIn = () => {
			for (const step of steps) {
				for (const q of step.ohgQuests?.mine || []) { park(q); step.ohgQuests.list.append(q); }
				for (const a of step.ohgAreas?.hidden || []) { park(a); step.ohgAreas.list.append(a); }
			}
			if (spareStep) for (const a of spare) { park(a); spareStep.querySelector('.ohg-m-areas').append(a); }
			questsHeading?.classList.toggle('ohg-m-hidden', !loose.length);
			questsIntro?.classList.toggle('ohg-m-hidden', !loose.length);
		};
		const moveBack = () => {
			for (const [node, c] of places) c.replaceWith(node);
			places.clear();
			questsHeading?.classList.remove('ohg-m-hidden');
			questsIntro?.classList.remove('ohg-m-hidden');
		};

		// Pages made of headings fold on a phone. Each heading becomes a row that shows what sits under it (closed
		// to start with); the front page also turns its chapter list into rows. Wider screens keep the pages as they are.
		const isIndex = /\/guide\/(index\.html)?$/.test(location.pathname);
		const isHidden = /\/guide\/hidden-items\/?(index\.html)?$/.test(location.pathname);
		const isIssues = /\/guide\/known-issues\/?(index\.html)?$/.test(location.pathname);
		if (isIndex || isHidden || isIssues) {
			content.classList.add('ohg-m-index');
			// a row that shows or hides `nodes`; `lvl` keeps nested folds apart (a closed h2 hides its h3 rows too)
			const foldRow = (title, meta, nodes, before, lvl = 2) => {
				const toggle = el('button', 'ohg-m-toggle', `<span class="ohg-m-title">${esc(title)}</span>${meta ? `<span class="ohg-m-meta">${meta}</span>` : ''}${chevron}`);
				toggle.type = 'button';
				toggle.setAttribute('aria-expanded', 'false');
				const row = el('div', `ohg-m-row ohg-m-index-row ohg-m-index-row-${lvl}`);
				row.append(toggle);
				toggle.addEventListener('click', () => {
					const open = toggle.getAttribute('aria-expanded') !== 'true';
					toggle.setAttribute('aria-expanded', String(open));
					row.toggleAttribute('data-open', open);
					nodes.forEach((n) => n.toggleAttribute('data-open' + lvl, open));
				});
				nodes.forEach((n) => n.setAttribute('data-ohg-sec' + lvl, ''));
				before.before(row);
				return row;
			};
			const sectionsOf = (w, stop) => {
				const nodes = [];
				for (let n = w.nextElementSibling; n && !n.matches(stop); n = n.nextElementSibling) nodes.push(n);
				return nodes;
			};
			const plural = (n, one, many = one + 's') => `${n} ${n === 1 ? one : many}`;
			// the introduction: the first paragraph stays, the rest folds
			const intro = [];
			for (let n = content.firstElementChild; n && !n.matches('.sl-heading-wrapper'); n = n.nextElementSibling) intro.push(n);
			const lead = intro.find((n) => n.matches('p'));
			const rest = intro.filter((n) => n !== lead && !n.matches('.game-setup'));
			if (lead && rest.length) foldRow(isIndex ? 'About this guide' : isHidden ? 'About these pictures' : 'About this list', '', rest, rest[0]);
			// the front page's chapter list: rows with number, title, summary and quest count
			const chaptersList = isIndex && (document.getElementById('chapters')?.closest('.sl-heading-wrapper')?.nextElementSibling?.matches('ul') ? document.getElementById('chapters').closest('.sl-heading-wrapper').nextElementSibling
				: [...content.querySelectorAll(':scope > ul')].find((ul) => ul.querySelector('a[href*="ch01"]')));
			if (chaptersList) {
				chaptersList.classList.add('ohg-m-chapters');
				const note = chaptersList.previousElementSibling?.matches('p') ? chaptersList.previousElementSibling : null;
				note?.classList.add('ohg-m-chapters-note');
				for (const li of chaptersList.children) {
					const a = li.querySelector('a[href]');
					if (!a) continue;
					const name = chapterName(a.textContent);
					const after = li.textContent.replace(a.textContent, '').trim().replace(/^:\s*/, '');
					const count = after.match(/\((\d+)\)\s*$/)?.[1];
					const summary = after.replace(/\s*\(\d+\)\s*$/, '');
					const notes = [count ? plural(+count, 'quest') : '', name.post ? 'Postgame' : ''].filter(Boolean).join(' · ');
					const row = el('a', 'ohg-m-chapter-row', `<span class="ohg-m-chapter-num${name.num ? '' : ' ohg-m-chapter-dot'}">${esc(name.num)}</span><span class="ohg-m-chapter-body"><span class="ohg-m-chapter-title">${esc(name.title)}</span>${summary ? `<span class="ohg-m-chapter-sum">${esc(summary)}</span>` : ''}${notes ? `<span class="ohg-m-chapter-count">${esc(notes)}</span>` : ''}</span>${chevron.replace('ohg-m-chevron', 'ohg-m-chevron ohg-m-chevron-go')}`);
					row.href = a.getAttribute('href');
					li.append(row);
				}
			}
			// h3 sections first (known issues: one per issue), then h2 sections, so a closed h2 hides its h3 rows
			for (const w of content.querySelectorAll(':scope > .sl-heading-wrapper.level-h3')) {
				const h = w.querySelector('h3');
				const nodes = sectionsOf(w, '.sl-heading-wrapper');
				if (!h || !nodes.length) continue;
				const fixed = nodes.map((n) => n.textContent).join(' ').match(/Fixed in (rc\d+)/i);
				w.classList.add('ohg-m-index-heading');
				foldRow(h.textContent.trim(), fixed ? `<span class="ohg-m-fixed">Fixed in ${esc(fixed[1])}</span>` : '', nodes, w.nextElementSibling, 3);
			}
			for (const w of content.querySelectorAll(':scope > .sl-heading-wrapper.level-h2')) {
				const h = w.querySelector('h2');
				if (!h || h.id === 'chapters') continue;
				const nodes = sectionsOf(w, '.sl-heading-wrapper.level-h2');
				if (!nodes.length) continue;
				let meta = '';
				if (isIndex) { const k = nodes.reduce((n, x) => n + x.querySelectorAll('a[href]').length, 0); meta = k ? plural(k, 'entry', 'entries') : ''; }
				else if (isHidden) { const k = nodes.reduce((n, x) => n + x.querySelectorAll('img').length + (/Missing screenshot/.test(x.textContent) ? 1 : 0), 0); meta = k ? plural(k, 'spot') : ''; }
				else if (isIssues) { const k = nodes.filter((x) => x.matches('.sl-heading-wrapper.level-h3')).length; meta = k ? plural(k, 'issue') : ''; }
				w.classList.add('ohg-m-index-heading');
				foldRow(h.textContent.trim(), meta, nodes, w.nextElementSibling, 2);
			}
		}

		// at a glance: "Where:", "Reward:" and the other lead-ins become labels on their own line; Yes and No answers
		// get their colours; prose tables stack one row at a time
		for (const strong of content.querySelectorAll('section.quest p > strong:first-child, .sl-markdown-content > p > strong:first-child, .chapter-hidden-area p > strong:first-child')) {
			if (!/:\s*$/.test(strong.textContent) || strong.textContent.length >= 48) continue;
			strong.classList.add('ohg-m-label');
			if (/^(warning|watch out|missable|deadline|one chance)/i.test(strong.textContent)) strong.classList.add('ohg-m-label-warn');
		}
		for (const strong of content.querySelectorAll('section.quest strong, .chapter-step > p strong')) {
			const m = strong.textContent.trim().match(/^(?:answer\s+)?(yes|no)\b/i);
			if (m) strong.classList.add(m[1].toLowerCase() === 'yes' ? 'ohg-m-yes' : 'ohg-m-no');
		}
		for (const table of content.querySelectorAll('section.quest table')) {
			const heads = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim());
			const rows = [...table.querySelectorAll('tbody tr')];
			if (heads.length < 2 || !rows.length || rows.length > 14) continue;
			if (!rows.some((tr) => [...tr.cells].some((td) => td.textContent.trim().length > 36))) continue;
			rows.forEach((tr) => [...tr.cells].forEach((td, i) => { if (heads[i]) td.dataset.label = heads[i]; }));
			table.classList.add('ohg-m-stack');
		}

		// sheets: a native modal <dialog> (focus, Escape and the top layer for free); a tap on the backdrop closes it
		const sheet = (id, title) => {
			const d = el('dialog', 'ohg-m-sheet not-content');
			d.setAttribute('aria-labelledby', id + '-title');
			d.innerHTML = `<div class="ohg-m-sheet-head"><h2 id="${id}-title">${title}</h2><button type="button" class="ohg-m-close" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div><div class="ohg-m-sheet-body"></div>`;
			d.querySelector('.ohg-m-close').addEventListener('click', () => d.close());
			d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
			// following a link inside closes the sheet first, so the page can scroll to it
			d.addEventListener('click', (e) => { if (e.target.closest('a[href^="#"]')) d.close(); });
			document.body.append(d);
			return d;
		};
		const dock = el('nav', 'ohg-m-dock not-content');
		dock.setAttribute('aria-label', 'Page tools');
		const dockButton = (label, icon, cls) => {
			const b = el('button', cls, `${icon}<span>${label}</span>`);
			b.type = 'button';
			dock.append(b);
			return b;
		};
		// the previous and next chapter, from the links at the end of the page
		const turn = (rel, icon) => {
			const link = document.querySelector(`.pagination-links a[rel="${rel}"]`);
			const a = el(link ? 'a' : 'span', `ohg-m-dock-turn ohg-m-dock-${rel}`, icon);
			if (link) {
				a.href = link.href;
				a.setAttribute('aria-label', `${rel === 'prev' ? 'Previous' : 'Next'}: ${link.querySelector('.link-title')?.textContent.trim() || ''}`);
			} else a.setAttribute('aria-hidden', 'true');
			dock.append(a);
			return a;
		};
		turn('prev', '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M15 5l-7 7 7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');

		// Walkthrough: every chapter (from the sidebar), with this page's own steps and headings nested under the
		// chapter the reader is on; the find box searches both
		const sections = sheet('ohg-m-sections', 'Sections');
		const sectionsBody = sections.querySelector('.ohg-m-sheet-body');
		sectionsBody.innerHTML = '<input type="search" class="ohg-m-find" placeholder="Find a chapter, step or section" aria-label="Find a chapter, step or section"><ul class="ohg-m-toc"></ul>';
		const find = sectionsBody.querySelector('.ohg-m-find');
		const tocList = sectionsBody.querySelector('.ohg-m-toc');
		const chapterLinks = (() => {
			const group = [...document.querySelectorAll('#starlight__sidebar details')].find((d) => /quest guide/i.test(d.querySelector('summary')?.textContent || ''));
			return group ? [...group.querySelectorAll('a[href]')] : [];
		})();
		const pageEntries = () => {
			const out = [];
			const links = tocLinks.length ? tocLinks : [...content.querySelectorAll('h2[id]')].map((h) => ({ hash: '#' + h.id, textContent: h.textContent }));
			for (const a of links) {
				if (a.parentElement && a.parentElement.style?.display === 'none') continue;
				const href = a.hash || a.getAttribute('href');
				if (href === '#_top') continue;
				const t = byHash(href);
				const q = t?.closest('section.quest');
				if (q && placed.has(q)) continue; // quests under their steps are in the Quests sheet
				if (href === '#quests-in-this-chapter' && !loose.length) continue;
				const sub = q || parseInt(a.style?.getPropertyValue('--depth') || '0', 10) > 0;
				// a chapter's two sections get short labels instead of their headings
				if (href === '#walkthrough' && steps.length) {
					out.push([null, 'Steps', 'ohg-m-toc-label']);
					steps.forEach((s) => s.id && out.push(['#' + s.id, s.dataset.title || s.id, 'ohg-m-stepline' + (s.classList.contains('chapter-optional') ? ' ohg-m-optional' : '')]));
					continue;
				}
				if (href === '#quests-in-this-chapter') { out.push([null, 'Quests', 'ohg-m-toc-label']); continue; }
				out.push([href, a.textContent.trim(), sub ? 'ohg-m-sub' : '']);
			}
			return out;
		};
		const renderSections = () => {
			tocList.innerHTML = '';
			const item = (href, text, cls) => {
				const li = el('li', cls);
				const a = el(href ? 'a' : 'span');
				if (href) a.href = href;
				a.textContent = text;
				li.append(a);
				return li;
			};
			const page = pageEntries();
			const pageList = el('ul', 'ohg-m-toc-page');
			page.forEach(([href, text, cls]) => pageList.append(item(href, text, cls)));
			if (!chapterLinks.length) { tocList.append(...pageList.children); filterSections(); return; }
			for (const a of chapterLinks) {
				const current = !!a.getAttribute('aria-current');
				const name = chapterName(a.textContent);
				if (!current || !pageList.children.length) {
					const li = item(a.getAttribute('href'), name.label, 'ohg-m-chapter');
					if (name.post) li.firstChild.insertAdjacentHTML('beforeend', '<span class="ohg-m-meta ohg-m-meta-inline">Postgame</span>');
					tocList.append(li);
					continue;
				}
				// the chapter the reader is on: a fold holding this page's entries, open to start with
				const li = el('li', 'ohg-m-chapter ohg-m-chapter-current');
				const fold = el('details', 'ohg-m-toc-fold', `<summary><span>${esc(name.label)}${name.post ? '<span class="ohg-m-meta ohg-m-meta-inline">Postgame</span>' : ''}</span>${chevron}</summary>`);
				fold.open = true;
				fold.append(pageList);
				li.append(fold);
				tocList.append(li);
			}
			filterSections();
		};
		const filterSections = () => {
			const q = searchText(find.value.trim());
			for (const li of tocList.querySelectorAll('li')) li.hidden = !!q && !searchText(li.querySelector(':scope > a, :scope > span, :scope > details > summary').textContent).includes(q);
			// a chapter stays (and opens) while any of its page entries match; labels follow their entries
			for (const li of tocList.querySelectorAll('.ohg-m-chapter')) {
				const hits = [...li.querySelectorAll('li:not(.ohg-m-toc-label)')].some((c) => !c.hidden);
				if (li.hidden && hits) li.hidden = false;
				const fold = li.querySelector('details');
				if (fold && q) fold.open = hits;
				li.querySelectorAll('.ohg-m-toc-label').forEach((l) => { l.hidden = !!q && !hits; });
			}
		};
		find.addEventListener('input', filterSections);
		const sectionsButton = dockButton('Sections', '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M4 6h16M4 12h10M4 18h13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>', 'ohg-m-dock-sections');
		sectionsButton.addEventListener('click', () => {
			renderSections();
			find.value = '';
			filterSections();
			sections.showModal();
			tocList.querySelector('.ohg-m-chapter-current')?.scrollIntoView({ block: 'start' });
		});

		// Quests: one row per quest the filters leave on the page, with its tick and a jump link, and the game filters.
		// The tick drives the quest's own Done box; setupQuests announces changes with "ohg:quests" and the list redraws.
		let questsSheet = null;
		const panel = content.querySelector('.game-setup');
		if (quests.length) {
			questsSheet = sheet('ohg-m-quests', 'Quests');
			const body = questsSheet.querySelector('.ohg-m-sheet-body');
			const list = el('ul', 'ohg-m-quest-list');
			body.append(list);
			const render = () => {
				const focused = document.activeElement?.closest('.ohg-m-quest')?.dataset.key;
				list.innerHTML = '';
				for (const q of quests) {
					if (q.classList.contains('is-hidden')) continue;
					const h = q.querySelector('h2');
					const real = q.querySelector('.quest-tools input[type="checkbox"]');
					if (!h || !real) continue;
					const flags = [...q.querySelectorAll('.quest-meta .tag-missable, .quest-meta .tag-postgame')].map((t) => t.textContent.trim());
					const li = el('li', 'ohg-m-quest');
					li.dataset.key = h.id;
					li.classList.toggle('is-done', real.checked);
					li.innerHTML = `<label class="ohg-m-tick"><input type="checkbox" aria-label="Done: ${esc(questTitle(q))}"></label>` +
						`<a class="ohg-m-jump" href="#${esc(h.id)}"><span class="ohg-m-title">${esc(questTitle(q))}</span>${flags.length ? `<span class="ohg-m-meta">${esc(flags.join(' · '))}</span>` : ''}</a>`;
					const box = li.querySelector('input');
					box.checked = real.checked;
					box.addEventListener('change', () => { real.checked = box.checked; real.dispatchEvent(new Event('change', { bubbles: true })); });
					list.append(li);
				}
				if (!list.children.length) list.innerHTML = '<li class="ohg-m-empty">No quests match your filters.</li>';
				if (focused) list.querySelector(`[data-key="${CSS.escape(focused)}"] input`)?.focus();
			};
			document.addEventListener('ohg:quests', render);
			render();
			const questsButton = dockButton('Quests', '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M9 11l3 3 8-8M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>', 'ohg-m-dock-quests');
			questsButton.addEventListener('click', () => { render(); questsSheet.showModal(); });
		}
		turn('next', '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="m9 5 7 7-7 7" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>');
		document.body.append(dock);

		// switch between the phone layout and the normal one as the width changes
		const mq = matchMedia('(max-width: 50rem)');
		const update = () => {
			root.toggleAttribute('data-ohg-mobile', mq.matches);
			if (mq.matches) { moveIn(); decorateSprites(content); } else moveBack();
			if (panel) {
				if (mq.matches && questsSheet) questsSheet.querySelector('.ohg-m-sheet-body').prepend(panel);
				else if (panel.parentElement !== content) content.prepend(panel);
			}
			if (!mq.matches) document.querySelectorAll('dialog.ohg-m-sheet[open]').forEach((d) => d.close());
		};
		mq.addEventListener ? mq.addEventListener('change', update) : mq.addListener(update);
		update();
		openTo(byHash(location.hash));
		window.addEventListener('hashchange', () => { const t = byHash(location.hash); openTo(t); t?.scrollIntoView(); });
		// the same link twice fires no hashchange, so a tap on an in-page link opens its fold as well
		document.addEventListener('click', (e) => {
			const a = e.target.closest?.('a[href^="#"]');
			if (a && root.hasAttribute('data-ohg-mobile')) openTo(byHash(a.hash));
		});
	}

	// ---------------------------------------------------------------- the menu on phones
	// Below 50rem the header's menu button opens a sheet of the site's own instead of Starlight's sidebar drawer: the
	// main places as a grid, the other reference pages and the help pages as folds, and the theme. The chapters are
	// under Walkthrough (its page, and the guide dock's own sheet). Wider screens keep the sidebar.
	const base = (document.querySelector('script[src$="ohg.js"]')?.getAttribute('src') || '/ohg.js').replace(/ohg\.js$/, '');
	// Chapter titles come in two spellings ("26. Mahogany Town…", "Chapter 33: Postgame, Lance's Visit…"); on a phone
	// they all read "33. Lance's Visit…" with Postgame as a note beside them. Other pages keep their names.
	const chapterName = (text) => {
		const m = text.trim().match(/^(?:Chapter\s+(\d+)\s*:|(\d+)\.)\s*(.+)$/i);
		if (!m) return { label: text.trim(), num: '', title: text.trim(), post: false };
		const post = /^post-?game\b[,:]?\s*/i.test(m[3]);
		const title = m[3].replace(/^post-?game\b[,:]?\s*/i, '').replace(/^(the\s)/, (x) => x[0].toUpperCase() + x.slice(1));
		const num = m[1] || m[2];
		return { label: `${num}. ${title}`, num, title, post };
	};
	const ICONS = {
		map: '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Zm0 0v14m6-12v14"/>',
		ball: '<circle cx="12" cy="12" r="9"/><path d="M3 12h6m6 0h6"/><circle cx="12" cy="12" r="3"/>',
		bag: '<path d="M6 8h12l1 12H5L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
		bolt: '<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z"/>',
		pin: '<path d="M12 21s6-5.2 6-11a6 6 0 0 0-12 0c0 5.8 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
		person: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
		grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
		calc: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M8 7h8M8 12h2m2 0h2m2 0h0M8 16h2m2 0h2m2 0h0"/>',
		save: '<path d="M5 3h11l3 3v15H5V3Z"/><path d="M8 3v5h7V3M8 21v-7h8v7"/>',
		download: '<path d="M12 4v11m0 0 4-4m-4 4-4-4M4 19h16"/>',
		help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.4-1 .9-1 1.7M12 17h0"/>',
		spark: '<path d="M12 3l2.2 5.6L20 9.5l-4.4 3.9 1.3 5.8L12 16.2l-4.9 3 1.3-5.8L4 9.5l5.8-.9L12 3Z"/>',
		disc: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
		tutor: '<path d="M3 9l9-4 9 4-9 4-9-4Z"/><path d="M7 11v4c0 1.5 2.2 3 5 3s5-1.5 5-3v-4M21 9v5"/>',
		book: '<path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4Z"/><path d="M5 17a3 3 0 0 1 3-3h11M9 8h6"/>',
	};
	const icon = (name) => `<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
	const PLACES = [
		['Walkthrough', 'guide/', 'map'], ['Pokédex', 'pokemon/', 'ball'], ['Items', 'items/', 'bag'], ['Moves', 'moves/', 'bolt'],
		['Locations', 'locations/', 'pin'], ['Trainers', 'trainers/', 'person'], ['Team builder', 'team-builder/', 'grid'],
		['Abilities', 'abilities/', 'spark'], ['TMs & HMs', 'tms/', 'disc'], ['Tutors', 'tutors/', 'tutor'],
		['Damage calc', 'damage-calc/', 'calc'], ['Save editor', 'save-editor/', 'save'],
	];
	// the rest of the sidebar's Reference group, so no page is reachable only from a link inside another page
	const REFERENCE = [
		['Mechanics and controls', 'mechanics/'], ['Calendar encounters', 'calendar/'], ['Overworld abilities', 'overworld-abilities/'],
		['Type changes', 'type-changes/'], ['Base stat changes', 'stat-changes/'], ['Apricorn trees', 'apricorn-trees/'], ['Reference sources', 'reference-sources/'],
	];
	const HELP = [
		['FAQ', 'faq/'], ['How to use this guide', 'about/'], ['Difficulty settings', 'difficulty/'],
		['Camera and widescreen codes', 'camera-codes/'], ['Changelog and contributors', 'changelog/'], ['Report a problem or contribute', 'contribute/'],
	];

	function setupMobileMenu() {
		const button = document.querySelector('.sl-menu-button, .primary-menu-button');
		if (!button) return;
		const mq = matchMedia('(max-width: 50rem)');
		const here = location.pathname.replace(/index\.html$/, '');
		const current = (href) => here === href ? 'page' : (href !== base && here.startsWith(href) ? 'true' : null);
		const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
		let sheet = null;
		const build = () => {
			sheet = document.createElement('dialog');
			sheet.className = 'ohg-m-sheet ohg-m-menu not-content';
			sheet.setAttribute('aria-label', 'Menu');
			const link = (label, href, cls = '') => {
				const h = base + href;
				const cur = current(h);
				return `<a href="${h}" class="${cls}"${cur ? ` aria-current="${cur}"` : ''}>${label}</a>`;
			};
			sheet.innerHTML = `<div class="ohg-m-sheet-head"><h2>Origin <span>HeartGold</span></h2><button type="button" class="ohg-m-close" aria-label="Close"><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button></div>` +
				`<div class="ohg-m-sheet-body">` +
				link(`${icon('download')}<span>Get the patch</span>`, 'patch/', 'ohg-m-menu-cta') +
				`<nav class="ohg-m-menu-grid" aria-label="Main">${PLACES.map(([label, href, ic]) => link(`${icon(ic)}<span>${label}</span>`, href)).join('')}</nav>` +
				`<details class="ohg-m-menu-fold" open><summary>${icon('book')}Reference</summary><ul>${REFERENCE.map(([label, href]) => `<li>${link(label, href)}</li>`).join('')}</ul></details>` +
				`<details class="ohg-m-menu-fold"><summary>${icon('help')}Help</summary><ul>${HELP.map(([label, href]) => `<li>${link(label, href)}</li>`).join('')}</ul></details>` +
				`<div class="ohg-m-menu-theme" role="group" aria-label="Theme"><button type="button" data-theme="light">Light</button><button type="button" data-theme="dark">Dark</button><button type="button" data-theme="auto">Auto</button></div>` +
				`</div>`;
			sheet.querySelector('.ohg-m-close').addEventListener('click', () => sheet.close());
			sheet.addEventListener('click', (e) => { if (e.target === sheet) sheet.close(); });
			// the theme: Starlight's own picker does the switching and the remembering
			const picker = document.querySelector('starlight-theme-select select');
			const themeButtons = [...sheet.querySelectorAll('.ohg-m-menu-theme button')];
			const syncTheme = () => {
				const v = picker?.value || 'auto';
				themeButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.theme === v)));
			};
			themeButtons.forEach((b) => b.addEventListener('click', () => {
				if (picker) { picker.value = b.dataset.theme; picker.dispatchEvent(new Event('change')); }
				else document.documentElement.dataset.theme = b.dataset.theme === 'auto' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : b.dataset.theme;
				syncTheme();
			}));
			if (!picker) sheet.querySelector('.ohg-m-menu-theme').hidden = true;
			syncTheme();
			document.body.append(sheet);
		};
		document.addEventListener('click', (e) => {
			const b = e.target.closest?.('.sl-menu-button, .primary-menu-button');
			if (!b || !mq.matches) return;
			e.preventDefault();
			e.stopImmediatePropagation();
			if (!sheet) build();
			sheet.open ? sheet.close() : sheet.showModal();
		}, true);
		// <html data-ohg-phone> styles the button and the sheet on every page (data-ohg-mobile is the guide layout);
		// data-ohg-home marks the home page, the one page that keeps the footer on a phone
		document.documentElement.toggleAttribute('data-ohg-home', location.pathname.replace(/index\.html$/, '') === base);
		const onChange = () => {
			document.documentElement.toggleAttribute('data-ohg-phone', mq.matches);
			if (!mq.matches && sheet?.open) sheet.close();
		};
		mq.addEventListener ? mq.addEventListener('change', onChange) : mq.addListener(onChange);
		onChange();
	}

	// ---------------------------------------------------------------- sprites on phones
	// Every Pokémon, item and Berry named in the text gets its PokéAPI sprite beside the name; one named with a level
	// ("Scyther Lv. 11", also in a trainer's bracketed team) becomes a chip with the level. The names come from
	// /sprites.json. Nothing changes for wider screens: the text stays as written and the pictures are hidden.
	const SPRITES = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites';
	let spriteNames = null;
	function decorateSprites(content, reference = false) {
		if (content.dataset.ohgSprites) return;
		content.dataset.ohgSprites = 'on';
		spriteNames ||= fetch(base + 'sprites.json').then((r) => r.ok ? r.json() : null).catch(() => null);
		spriteNames.then((names) => {
			if (!names) return;
			const rx = (list) => new RegExp('(?<![\\w’\'])(' + list.sort((a, b) => b.length - a.length).map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')(s?)(?!\\w)', 'g');
			const monRx = rx(Object.keys(names.p));
			const itemRx = rx(Object.keys(names.i));
			const monImg = (id) => `<img class="ohg-m-sprite ohg-m-sprite-mon" src="${SPRITES}/pokemon/${id}.png" width="40" height="40" alt="" loading="lazy" decoding="async">`;
			const itemImg = (slug) => `<img class="ohg-m-sprite ohg-m-sprite-item" src="${SPRITES}/items/${slug}.png" width="30" height="30" alt="" loading="lazy" decoding="async">`;
			// replace matches of `re` inside the text nodes under `root`, leaving links and pictures alone
			// On a reference page a name inside a link is only pictured when the link goes to that Pokémon or item: "Metronome" the move and "Honey Gather" the ability stay as they are. Places that already
			// show a picture (a list's sprite cell, the artwork, the evolution chain) and the controls are left alone.
			const skip = '.ohg-m-mon, .ohg-m-item, .ohg-m-row, .ohg-m-label, .tech, .quest-meta, .game-setup, .quest-tools, .chapter-unlocks, h1, h2, h3, h4, summary, script, style' +
				(reference ? ', .ohg-m-questlinks, .ohg-m-quest, .pokemon-cell, .types, .ohg-m-evo, .ohg-m-item-hero, .table-filter, .reference-provenance, .sr-only, .tag, .type, nav, caption, thead, select, button, pre' : '');
			const mark = (root, re, build, kind) => {
				const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: (n) => {
					if (n.parentElement.closest(skip)) return NodeFilter.FILTER_REJECT;
					const a = reference ? n.parentElement.closest('a') : null;
					if (a && (!new RegExp(`/(${kind === 'item' ? 'items' : 'pokemon'})/`).test(a.getAttribute('href') || '') || a.previousElementSibling?.matches('.ohg-m-sprite'))) return NodeFilter.FILTER_REJECT;
					return NodeFilter.FILTER_ACCEPT;
				} });
				const nodes = [];
				for (let n = walker.nextNode(); n; n = walker.nextNode()) { re.lastIndex = 0; if (re.test(n.data)) nodes.push(n); }
				re.lastIndex = 0;
				for (const n of nodes) {
					const html = n.data.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]).replace(re, build);
					const span = document.createElement('span');
					span.innerHTML = html;
					n.replaceWith(...span.childNodes);
				}
			};
			const levelled = new RegExp(monRx.source + '(,?\\s+\\(?Lv\\.\\s?\\d+\\)?)', 'g'); // groups: name, plural s, level
			const mon = (name, level = '', text = name) => `<span class="ohg-m-mon${level ? '' : ' ohg-m-mon-plain'}">${monImg(names.p[name])}<span class="ohg-m-mon-name">${text}</span>${level ? `<span class="ohg-m-mon-level">${level.replace(/[,()]/g, '').trim()}</span>` : ''}</span>`;
			// a trainer's team in brackets: "(Beldum Lv. 12, Baltoy Lv. 11)" becomes a row of chips
			const team = new RegExp('\\((' + levelled.source + '(?:,\\s*)?)+\\)', 'g');
			if (!reference) mark(content, team, (m) => `<span class="ohg-m-team"><span class="ohg-m-punct">(</span>${m.slice(1, -1).replace(levelled, (_, name, s, level) => mon(name, level, name + s)).replace(/,\s*/g, '<span class="ohg-m-punct">, </span>')}<span class="ohg-m-punct">)</span></span>`);
			if (!reference) mark(content, levelled, (_, name, s, level) => mon(name, level, name + s));
			// then every other mention: Pokémon first (an item never contains a Pokémon's name), then items and Berries
			mark(content, monRx, (m, name) => mon(name, '', m), 'mon');
			mark(content, itemRx, (m, name) => `<span class="ohg-m-item">${itemImg(names.i[name])}${m}</span>`, 'item');
		});
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
			const resetName = target.tagName === 'TABLE' ? tableName(target) : '';
			reset.setAttribute('aria-label', `Reset search, filters and sorting${resetName ? ` for ${resetName}` : ''}`);
			if (f) f.append(reset);
			// `sorted`: whether the rows are out of page order. Re-appending every row is costly on long tables, so it only
			// happens while sorting or when going back to page order (W-051).
			let sort = null, searchEditing = false, sorted = false;
			function apply() {
				const words = searchText(input?.value || '').trim().split(/\s+/).filter(Boolean);
				let n = 0;
				for (const r of rows) {
					const tokens = key => (r.dataset[key] || '').split('|');
					const ok = words.every(w => text.get(r).includes(w)) && selects.every(s => !s.value || tokens(s.dataset.key).includes(s.value)) && checks.every(c => c.checked || !tokens(c.dataset.key).includes(c.dataset.showValue));
					if (r.hidden === ok) r.hidden = !ok; if (ok) n++;
				}
				ths.forEach((th, col) => th.setAttribute('aria-sort', sort?.col === col ? sort.dir : 'none'));
				if (body && (sort || sorted)) {
					sorted = !!sort;
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
	// A table's name: its caption or ARIA label, else the nearest heading before it (W-033). The panel becomes a
	// focusable, named region only while it really scrolls; otherwise it is a plain div with no ARIA (W-032).
	const textOf = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
	function tableName(table) {
		const own = textOf(table.caption) || table.getAttribute?.('aria-label') ||
			(table.getAttribute?.('aria-labelledby') || '').split(/\s+/).map(id => textOf(document.getElementById(id))).join(' ').trim();
		if (own) return own;
		const headings = [...document.querySelectorAll('.sl-markdown-content :is(h2, h3, h4), h1')];
		const before = headings.filter(h => h.compareDocumentPosition?.(table) & 4).pop();
		return textOf(before);
	}
	function setupTableScroll(root = document) {
		const updates = [];
		root.querySelectorAll('.sl-markdown-content table').forEach(table => {
			if (table.closest('.table-scroll, .save-editor')) return;
			const name = tableName(table);
			if (name && !textOf(table.caption) && !table.getAttribute('aria-label') && !table.getAttribute('aria-labelledby')) table.setAttribute('aria-label', name);
			const panel = document.createElement('div');
			panel.className = 'table-scroll';
			const hint = document.createElement('p');
			hint.className = 'table-scroll-hint';
			hint.textContent = 'Scroll sideways to see all columns →';
			hint.hidden = true;
			table.before(panel); panel.append(table); panel.after(hint);
			const update = () => {
				const overflow = panel.scrollWidth > panel.clientWidth + 2;
				hint.hidden = !overflow;
				if (overflow) {
					panel.tabIndex = 0; panel.setAttribute('role', 'region');
					panel.setAttribute('aria-label', `${name || 'Table'} (scrolls sideways)`);
				} else { panel.removeAttribute('tabindex'); panel.removeAttribute('role'); panel.removeAttribute('aria-label'); }
			};
			updates.push(update);
			if (typeof ResizeObserver !== 'undefined') new ResizeObserver(update).observe(panel);
			update();
		});
		if (typeof ResizeObserver === 'undefined') window.addEventListener('resize', () => updates.forEach(update => update()));
	}

	// Pages that insert tables later (trainer cards on /trainers/) give them the same panel.
	window.ohgTableScroll = setupTableScroll;
	// a sprite PokéAPI doesn't have (hack-only items, renamed forms) goes away instead of showing a broken picture
	if (typeof document.addEventListener === 'function') {
		document.addEventListener('error', (e) => { if (e.target instanceof HTMLImageElement && e.target.classList.contains('ohg-m-sprite')) e.target.remove(); }, true);
	}
	// The Items list renders its sprites hidden (they only show on phones), and the browser's own lazy loading never
	// starts a picture that was hidden when the page loaded. On a phone, each one loads as it comes into view.
	function setupItemSprites() {
		const imgs = [...document.querySelectorAll('#item-table img.ohg-m-sprite')];
		if (!imgs.length || typeof IntersectionObserver === 'undefined' || typeof matchMedia === 'undefined') return;
		const mq = matchMedia('(max-width: 50rem)');
		const io = new IntersectionObserver((entries) => {
			for (const e of entries) if (e.isIntersecting && mq.matches) { e.target.loading = 'eager'; io.unobserve(e.target); }
		}, { rootMargin: '300px' });
		imgs.forEach((img) => io.observe(img));
	}
	// Reference pages on phones (a Pokémon, an item): move tables become rows (level or TM, the move and its type on
	// one line, the numbers under it, the effect last) and the encounter table stacks. The cells get the column names
	// as labels; the CSS does the rest and wider screens keep the tables.
	function setupMobileReference() {
		if (!/\/(pokemon|items|moves|abilities|locations|trainers)\/[^/]+\/?(index\.html)?$/.test(location.pathname)) return;
		const label = (table) => {
			const heads = [...table.querySelectorAll('thead th')].map((th) => th.textContent.trim());
			if (!heads.length) return false;
			table.querySelectorAll('thead th').forEach((th, i) => { if (heads[i]) th.dataset.label = heads[i]; });
			for (const tr of table.querySelectorAll('tbody tr')) [...tr.cells].forEach((td, i) => { if (heads[i]) td.dataset.label = heads[i]; });
			return heads;
		};
		const SHORT = { Accuracy: 'Acc', Power: 'Pow', Level: 'Lv', 'TM / HM': 'TM', 'Learning method': 'How', Compatibility: 'TM', 'Hold chance': 'Hold', 'Encounter chance': 'Chance', 'Method / time / condition': 'Method' };
		const shorten = (table) => table.querySelectorAll('thead th').forEach((th) => {
			const full = th.textContent.trim();
			if (SHORT[full]) th.innerHTML = `<span class="ohg-m-full">${th.innerHTML}</span><span class="ohg-m-short" aria-hidden="true">${SHORT[full]}</span>`;
		});
		for (const table of document.querySelectorAll('.sl-markdown-content table')) {
			const heads = label(table);
			if (!heads) continue;
			// a Pokémon's wild encounters become a list grouped by place (setupMobileTabs)
			if (table.id === 'wild-encounters-table') continue;
			// a move's numbers: one grid of tiles instead of a line each
			if (/^Move stats$/.test(table.querySelector('caption')?.textContent.trim() || '')) { table.classList.add('ohg-m-movestats'); continue; }
			// an item's wild holders: the summary and each holder's locations stay tables, fitted to the width
			if (/^wild-locations/.test(table.id) || /^Wild Pokémon holding/.test(table.querySelector('caption')?.textContent || '')) {
				table.classList.add('ohg-m-fit');
				shorten(table);
				continue;
			}
			// a place's wild Pokémon (name, level, chance; the contest adds rate and score): one line each
			if (heads[0] === 'Pokémon' && heads[1] === 'Level' && heads.length <= 4 && table.closest('.enc-block')) { table.classList.add('ohg-m-enc'); continue; }
			// the items of a place (found, prizes, bought): the name with its quantity, the rest under it
			if (heads[0] === 'Item' && heads[1] === 'Qty') { table.classList.add('ohg-m-loot'); continue; }
			if (heads.includes('Move') && heads.includes('Type') && heads.includes('Power')) {
				table.classList.add('ohg-m-moves');
				table.querySelectorAll('thead th').forEach((th) => {
					const full = th.textContent.trim();
					if (SHORT[full]) th.innerHTML = `<span class="ohg-m-full">${th.innerHTML}</span><span class="ohg-m-short" aria-hidden="true">${SHORT[full]}</span>`;
				});
			} else if (/^learners-table/.test(table.id) || (heads.length === 4 && heads[0] === 'Pokémon' && heads[1] === 'Type' && heads[3] === 'Availability')) {
				// a list of Pokémon (a move's learners, a TM's compatible Pokémon, an ability's holders): sprite, name and the one detail
				table.classList.add('ohg-m-learners');
				table.querySelectorAll('thead th').forEach((th) => {
					const full = th.textContent.trim();
					if (SHORT[full]) th.innerHTML = `<span class="ohg-m-full">${th.innerHTML}</span><span class="ohg-m-short" aria-hidden="true">${SHORT[full]}</span>`;
				});
			}
			else if (heads.length >= 3 && heads.length <= 7) table.classList.add('ohg-m-stack');
		}
	}
	// A Pokémon's page on a phone splits into tabs on a bar along the bottom: Overview (artwork, facts, stats), Where
	// (where to find it, forms, calendar), Evolution and Moves (level-up, TMs, tutors, egg). A link into a section opens
	// its tab. Wider screens keep the one long page.
	function setupMobileTabs() {
		if (!/\/pokemon\/[^/]+\/?(index\.html)?$/.test(location.pathname)) return;
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined') return;
		const ICON = {
			overview: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h0"/>',
			where: '<path d="M12 21s6-5.2 6-11a6 6 0 0 0-12 0c0 5.8 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
			evolution: '<path d="M4 17h5l3-10 3 10h5M4 7h3M17 7h3"/>',
			moves: '<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z"/>',
		};
		const TABS = [['overview', 'Overview'], ['where', 'Where'], ['evolution', 'Evolution'], ['moves', 'Moves']];
		const tabOf = { where: 'where', forms: 'where', calendar: 'where', evolution: 'evolution', moves: 'moves', tm: 'moves', tutors: 'moves', egg: 'moves' };
		let cur = 'overview';
		const present = new Set(['overview']);
		for (const n of content.children) {
			if (n.matches('nav.prevnext, .game-setup')) continue;
			if (n.matches('h2[id]')) cur = tabOf[n.id] || 'overview';
			n.dataset.ohgTab = cur;
			present.add(cur);
		}
		const tabs = TABS.filter(([id]) => present.has(id));
		if (tabs.length < 2) return;
		// Where: the notes about chances and times are the long page's; a phone keeps the places
		for (const n of content.querySelectorAll(':scope > [data-ohg-tab="where"]')) if (n.matches('p.small, details.enc-help')) n.classList.add('ohg-m-aside');
		for (const li of content.querySelectorAll(':scope > ul.pokemon-acquisitions > li')) {
			const kind = li.querySelector(':scope > strong');
			if (!kind) continue;
			const head = document.createElement('div');
			head.className = 'ohg-m-acq-head not-content';
			head.innerHTML = `<span class="ohg-m-acq-kind">${kind.textContent.trim()}</span>`;
			// the level and the place follow the kind on the same line: "(Lv. 15): Route 5 House."
			const lead = document.createElement('span');
			lead.className = 'ohg-m-acq-lead';
			let n = kind.nextSibling;
			while (n && !(n.nodeType === 1 && n.matches('p'))) { const next = n.nextSibling; lead.append(n); n = next; }
			lead.innerHTML = lead.innerHTML.replace(/^\s*\(Lv\.?\s*([^)]+)\)\s*:\s*/, '<span class="ohg-m-acq-level">Lv. $1</span> ').replace(/^\s*:\s*/, '').replace(/\.\s*$/, '');
			head.append(lead);
			// what a trade asks for ("Give Raticate in exchange") goes on its own line under the place
			const placeLink = lead.querySelector('a');
			if (placeLink?.nextSibling) {
				const offer = document.createElement('span');
				offer.className = 'ohg-m-acq-offer';
				while (placeLink.nextSibling) offer.append(placeLink.nextSibling);
				if (offer.firstChild?.nodeType === 3) offer.firstChild.data = offer.firstChild.data.replace(/^[\s.]+/, '');
				if (offer.textContent.trim()) head.append(offer);
			}
			li.classList.add('ohg-m-acq');
			kind.classList.add('ohg-m-acq-strong');
			kind.after(head);
		}
		// Wild encounters: one block per place, each encounter a line (how, level, chance). The table stays for wider
		// screens; the filter above it still works because each line follows its row's hidden state.
		const wildTable = content.querySelector('#wild-encounters-table');
		const wild = wildTable && (wildTable.closest('.table-scroll') || wildTable);
		if (wild && wild.parentElement === content) {
			const el = (tag, cls, text) => { const n = document.createElement(tag); n.className = cls; if (text != null) n.textContent = text; return n; };
			const list = el('div', 'ohg-m-wild not-content');
			list.dataset.ohgTab = 'where';
			const places = new Map(); // place -> its block
			const pairs = []; // [table row, its line]
			for (const tr of wildTable.tBodies[0]?.rows || []) {
				const [loc, how, level, chance] = tr.cells;
				if (!chance) continue;
				const key = `${loc.querySelector('a')?.getAttribute('href') || ''}|${loc.textContent.trim()}`;
				let place = places.get(key);
				if (!place) {
					place = el('section', 'ohg-m-wild-place');
					const head = el('div', 'ohg-m-wild-head');
					head.innerHTML = loc.innerHTML;
					place.append(head);
					places.set(key, place);
					list.append(place);
				}
				const line = el('div', 'ohg-m-wild-row');
				const what = el('span', 'ohg-m-wild-how');
				what.innerHTML = how.innerHTML;
				// the icons do the separating: "Grass/cave, morning and day" reads as three marks, a detail after a
				// colon follows a dot, and a Safari line doesn't repeat the area its block is named after
				const area = loc.textContent.trim().match(/^Safari Zone: (.+)$/)?.[1];
				const lead = what.firstElementChild;
				if (area && lead?.dataset.encounterHint === 'safari' && lead.nextSibling?.nodeType === 3 && lead.nextSibling.data.trim() === `: ${area} area selected,`) { lead.nextSibling.remove(); lead.remove(); }
				for (const n of [...what.childNodes]) {
					if (n.nodeType !== 3) continue;
					n.data = /^\s*(,|and|, and)?\s*$/.test(n.data) ? ' ' : n.data.replace(/^\s*[:,]\s*/, n.previousSibling ? ' · ' : '');
				}
				const lv = level.textContent.trim();
				const lvl = el('span', 'ohg-m-wild-lv');
				if (lv && lv !== '—') lvl.append(el('span', 'ohg-m-wild-unit', 'Lv'), ` ${lv}`); else lvl.textContent = '—';
				line.append(what, lvl, el('span', 'ohg-m-wild-pct', chance.textContent.trim()));
				place.append(line);
				pairs.push([tr, line]);
			}
			const sync = () => {
				for (const [tr, line] of pairs) line.hidden = tr.hidden;
				for (const place of places.values()) place.hidden = !place.querySelector('.ohg-m-wild-row:not([hidden])');
			};
			sync();
			if (typeof MutationObserver !== 'undefined') new MutationObserver(sync).observe(wildTable, { attributes: true, attributeFilter: ['hidden'], subtree: true });
			const band = el('div', 'ohg-m-band not-content');
			band.dataset.ohgTab = 'where';
			band.append(el('span', '', 'Wild encounters'), el('span', 'ohg-m-band-meta', places.size === 1 ? '1 place' : `${places.size} places`));
			(content.querySelector(':scope > .table-filter[data-table="wild-encounters-table"]') || wild).before(band);
			wild.before(list);
			wild.classList.add('ohg-m-wild-src');
			if (wild.nextElementSibling?.matches('.table-scroll-hint')) wild.nextElementSibling.classList.add('ohg-m-wild-src');
		}
		// Evolution: the sentences become a chain of sprites (the names come from /sprites.json, see decorateSprites)
		const evo = [...content.querySelectorAll(':scope > [data-ohg-tab="evolution"]')].filter((n) => !n.matches('h2'));
		if (evo.length) {
			const chain = document.createElement('div');
			chain.className = 'ohg-m-evo not-content';
			const me = document.querySelector('.pokemon-overview img[data-art]');
			const myName = document.querySelector('h1')?.textContent.replace(/^#\d+\s*/, '').trim() || '';
			const entries = []; // { dir: 'from' | 'into', name, href, how }
			const entry = (dir, node) => {
				const a = node.querySelector('a[href*="/pokemon/"]');
				if (!a) return;
				const clone = node.cloneNode(true);
				clone.querySelector('a[href*="/pokemon/"]')?.remove();
				const how = clone.textContent.replace(/^\s*Evolves (into|from)\b/i, '').replace(/^[\s:.,]+|[\s.]+$/g, '').replace(/\s+/g, ' ').trim();
				entries.push({ dir, name: a.textContent.trim(), href: a.href, how });
			};
			let dir = 'into';
			for (const n of evo) {
				if (n.matches('p')) {
					dir = /from/i.test(n.textContent.split(/<a|:/)[0].slice(0, 40)) && /^\s*Evolves from/i.test(n.textContent) ? 'from' : 'into';
					if (n.querySelector('a[href*="/pokemon/"]')) entry(dir, n);
				} else if (n.matches('ul, ol')) {
					for (const li of n.children) entry(dir, li);
				}
				n.classList.add('ohg-m-evo-text');
			}
			if (entries.length) {
				const node = (name, href, id) => `<${href ? 'a' : 'div'} class="ohg-m-evo-node"${href ? ` href="${href}"` : ''}>${id ? `<img class="ohg-m-evo-sprite" src="${SPRITES}/pokemon/${id}.png" width="96" height="96" alt="" loading="eager" decoding="async">` : '<span class="ohg-m-evo-blank"></span>'}<span>${name}</span></${href ? 'a' : 'div'}>`;
				const render = (names) => {
					const id = (n) => names?.p?.[n] || names?.p?.[n.replace(/\s*\(.*\)$/, '')] || '';
					const from = entries.filter((e) => e.dir === 'from');
					const into = entries.filter((e) => e.dir === 'into');
					const step = (e) => `<div class="ohg-m-evo-step"><span class="ohg-m-evo-arrow" aria-hidden="true"></span><span class="ohg-m-evo-how">${e.how || 'evolves'}</span></div>`;
					chain.innerHTML = from.map((e) => node(e.name, e.href, id(e.name)) + step(e)).join('') +
						node(myName, '', me?.dataset.art?.replace(/\D/g, '') || id(myName)) +
						(into.length ? `<div class="ohg-m-evo-branches${into.length > 2 ? ' ohg-m-evo-grid' : ''}">${into.map((e) => `<div class="ohg-m-evo-branch">${step(e)}${node(e.name, e.href, id(e.name))}</div>`).join('')}</div>` : '');
					chain.querySelector('.ohg-m-evo-node:not([href])')?.classList.add('ohg-m-evo-me');
				};
				render(null);
				spriteNames ||= fetch(base + 'sprites.json').then((r) => r.ok ? r.json() : null).catch(() => null);
				spriteNames.then((names) => names && render(names));
				chain.dataset.ohgTab = 'evolution';
				evo[0].before(chain);
			}
		}
		// Moves: three tabs at the top (level-up, TMs and HMs with the tutors, egg moves), each its own fitted table
		const kinds = { moves: 'level', tm: 'tm', tutors: 'tm', egg: 'egg' };
		const names = { level: 'Level-up', tm: 'TMs / HMs', egg: 'Egg moves' };
		let kind = '';
		let pick = null, syncTurns = () => {};
		const seen = new Set();
		for (const n of content.querySelectorAll(':scope > [data-ohg-tab="moves"]')) {
			if (n.matches('h2[id]')) kind = kinds[n.id] || kind;
			if (!kind) continue;
			n.dataset.ohgMoves = kind;
			seen.add(kind);
		}
		if (seen.size > 1) {
			const sub = document.createElement('div');
			sub.className = 'ohg-m-subtabs not-content';
			sub.setAttribute('role', 'tablist');
			sub.dataset.ohgTab = 'moves';
			sub.innerHTML = ['level', 'tm', 'egg'].filter((k) => seen.has(k)).map((k) => `<button type="button" role="tab" data-kind="${k}" aria-selected="false">${names[k]}</button>`).join('');
			pick = (k) => { content.dataset.ohgMovesActive = k; sub.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.kind === k))); syncTurns(); };
			sub.addEventListener('click', (e) => { const b = e.target.closest('button[data-kind]'); if (b) pick(b.dataset.kind); });
			content.querySelector(':scope > h2[data-ohg-tab="moves"]').before(sub);
			pick(seen.has('level') ? 'level' : [...seen][0]);
			content.dataset.ohgMovesTabs = '';
			// a link to a kind's heading (…/#egg) picks its tab
			window.addEventListener('hashchange', () => { const k = kinds[location.hash.slice(1)]; if (k) pick(k); });
			const k0 = kinds[location.hash.slice(1)]; if (k0) pick(k0);
		}
		// Previous and next Pokémon sit at the ends of the bar (from the page's own links at the bottom, which a phone
		// then leaves out); they open the neighbour on the tab that is open here ("#tab=moves:tm").
		const turns = [...content.querySelectorAll(':scope > nav.prevnext > a')];
		const turn = (rel, a) => {
			const chevron = `<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${rel === 'prev' ? 'm15 6-6 6 6 6' : 'm9 6 6 6-6 6'}"/></svg>`;
			if (!a) return `<span class="ohg-m-tabs-turn" aria-hidden="true">${chevron}<span>&nbsp;</span></span>`;
			const name = a.textContent.replace(/[←→]/g, '').trim();
			return `<a class="ohg-m-tabs-turn" data-turn="${rel}" href="${a.getAttribute('href')}" data-href="${a.getAttribute('href')}" aria-label="${rel === 'prev' ? 'Previous' : 'Next'} Pokémon: ${name.replace(/"/g, '&quot;')}">${chevron}<span>${(name.match(/^#\d+/) || [''])[0]}</span></a>`;
		};
		const prevLink = turns.find((a) => a.textContent.includes('←')), nextLink = turns.find((a) => a.textContent.includes('→'));
		const hasTurns = !!(prevLink || nextLink);
		if (hasTurns) content.querySelector(':scope > nav.prevnext').classList.add('ohg-m-trim');
		const bar = document.createElement('nav');
		bar.className = 'ohg-m-tabs not-content';
		bar.setAttribute('aria-label', 'Page sections');
		bar.innerHTML = (hasTurns ? turn('prev', prevLink) : '') + tabs.map(([id, label]) => `<button type="button" data-tab="${id}" aria-pressed="false"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${ICON[id]}</svg><span>${label}</span></button>`).join('') + (hasTurns ? turn('next', nextLink) : '');
		document.body.append(bar);
		syncTurns = () => {
			const tab = content.dataset.ohgTabActive, kind = content.dataset.ohgMovesActive;
			const hash = !tab || tab === 'overview' ? '' : `#tab=${tab}${tab === 'moves' && kind ? `:${kind}` : ''}`;
			bar.querySelectorAll('a.ohg-m-tabs-turn').forEach((a) => { a.href = a.dataset.href + hash; });
		};
		document.documentElement.setAttribute('data-ohg-tabbed', '');
		const show = (id, scroll) => {
			content.dataset.ohgTabActive = id;
			bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === id)));
			syncTurns();
			if (scroll) {
				const top = content.getBoundingClientRect().top + window.scrollY - 72;
				window.scrollTo({ top: Math.max(0, top), behavior: 'auto' });
			}
		};
		bar.addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) show(b.dataset.tab, true); });
		// a link into a section (…/#where, …/#egg) opens that tab
		const follow = () => {
			// from a neighbour's bar: the same tab (and kind of move), the page still at its top so the name shows
			const kept = location.hash.match(/^#tab=([a-z]+)(?::([a-z]+))?$/);
			if (kept) {
				show(present.has(kept[1]) ? kept[1] : 'overview', false);
				if (kept[2] && seen.has(kept[2])) pick?.(kept[2]);
				return;
			}
			let t = null;
			try { t = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { /* bad hash */ }
			const sec = t && content.contains(t) ? (t.closest('[data-ohg-tab]') || t) : null;
			if (sec?.dataset.ohgTab) { show(sec.dataset.ohgTab, false); t.scrollIntoView(); } else if (!content.dataset.ohgTabActive) show('overview', false);
		};
		follow();
		window.addEventListener('hashchange', follow);
	}
	// A quest's link, in parts a phone can lay out: "Cherrygrove City: the Wooper and the lost Poké Ball (→ Focus Band)"
	// becomes the place (left out where the card or page already names it), the title, and the note in brackets on
	// its own line. The text itself does not change, so wider screens read it as before.
	function questLink(a, place = '') {
		if (a.querySelector('.ohg-m-q-title')) return;
		const m = a.textContent.match(/^(.*?:\s+)?(.*?)(\s*\([^()]*\))?\s*$/s);
		if (!m || !m[2]) return;
		let pre = m[1] || '', title = m[2];
		const name = place.trim().toLowerCase(), first = name.split(/[\s,]+/)[0];
		const named = name && (pre.toLowerCase().includes(name) || (first.length >= 4 && !['route', 'the'].includes(first) && pre.toLowerCase().includes(first)));
		if (pre && !named) { title = pre + title; pre = ''; }
		const part = (cls, text) => { const span = document.createElement('span'); span.className = cls; span.textContent = text; return span; };
		a.textContent = '';
		if (pre) a.append(part('ohg-m-q-pre', pre));
		a.append(part('ohg-m-q-title', title));
		if (m[3]) a.append(part('ohg-m-q-note', m[3]));
	}
	// A list entry as a card (an item's source, a place's gift or scripted Pokémon). What follows the leading link
	// stays as written for wider screens (ohg-m-src-orig); the phone shows a copy (ohg-m-src-rest) with each detail on
	// its own line and the quests it names as rows under them, instead of one long run of links.
	function sourceCard(li) {
		if (li.classList.contains('ohg-m-src')) return;
		const lead = li.firstElementChild?.matches('a') && li.firstChild === li.firstElementChild ? li.firstElementChild : null;
		const orig = document.createElement('span');
		orig.className = 'ohg-m-src-orig';
		let n = lead ? lead.nextSibling : li.firstChild;
		while (n) { const next = n.nextSibling; orig.append(n); n = next; }
		li.classList.add('ohg-m-src');
		if (!orig.textContent.trim()) { orig.remove(); return; }
		li.append(orig);
		const rest = document.createElement('span');
		rest.className = 'ohg-m-src-rest';
		// "(costs ₽300) · see …" loses its brackets; a bracket later in the text ("… King's Rock (day)") keeps both
		const lines = orig.innerHTML.replace(/^\s*·\s*/, '').replace(/\s*·\s*/g, '<br>');
		rest.innerHTML = /^\s*\(/.test(lines) ? lines.replace(/^\s*\(\s*/, '').replace(/\s*\)\s*(<br>|$)/, '$1') : lines;
		const quests = [...rest.querySelectorAll('a[href*="/guide/"]')];
		if (quests.length) {
			// the place the card is about: its own link to a location, else the page (a location's own lists)
			const place = (lead?.matches('a[href*="/locations/"]') ? lead : li.querySelector('a[href*="/locations/"]'))?.textContent || document.querySelector('h1')?.textContent || '';
			const box = document.createElement('span');
			box.className = 'ohg-m-questlinks';
			for (const a of quests) { questLink(a, place); box.append(a); }
			// the "see" and the commas that joined the links go with them
			rest.innerHTML = rest.innerHTML.replace(/(?:<br>\s*)?\b[Ss]ee\b[\s,;]*(?=<br>|<\/p>|$)/g, '').replace(/(?:<br>\s*)+$/, '');
			rest.append(box);
		}
		// an entry with no leading link starts with its kind ("Gift: …", "Trade: …"): that becomes its label
		if (!lead) rest.innerHTML = rest.innerHTML.replace(/^\s*([A-Z][^:<]{2,40}):\s*/, '<span class="ohg-m-acq-kind">$1</span> ');
		li.append(rest);
	}
	// An item's page on a phone: the sprite with the pocket and prices at the top, each kind of source under a band,
	// each source a block with the place first and the rest (quantity, price, the quest) under it.
	function setupMobileItem() {
		const m = String(location.pathname || '').match(/\/items\/([^/]+)\/?(index\.html)?$/);
		const content = document.querySelector('.sl-markdown-content');
		if (!m || !content) return;
		document.documentElement.setAttribute('data-ohg-item', '');
		const meta = content.querySelector(':scope > p.small.muted');
		const hero = document.createElement('div');
		hero.className = 'ohg-m-item-hero not-content';
		const facts = (meta?.textContent || '').split(/\s*·\s*|,\s+(?=sells)/).map((t) => t.trim()).filter(Boolean);
		hero.innerHTML = `<img class="ohg-m-sprite ohg-m-item-art" src="${SPRITES}/items/${m[1]}.png" width="30" height="30" alt="" loading="eager" decoding="async">` +
			`<div class="ohg-m-item-facts">${facts.map((f) => `<span>${f.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c])}</span>`).join('')}</div>`;
		content.prepend(hero);
		meta?.classList.add('ohg-m-aside');
		content.querySelectorAll(':scope > p.small').forEach((p) => p.classList.add('ohg-m-aside'));
		// the holders' names get their sprites
		const holders = [...content.querySelectorAll('table.ohg-m-fit td a[href*="/pokemon/"]')];
		if (holders.length) {
			spriteNames ||= fetch(base + 'sprites.json').then((r) => r.ok ? r.json() : null).catch(() => null);
			spriteNames.then((names) => names && holders.forEach((a) => {
				const id = names.p[a.textContent.trim()];
				if (id) a.insertAdjacentHTML('beforebegin', `<img class="ohg-m-sprite ohg-m-sprite-mon ohg-m-fit-sprite" src="${SPRITES}/pokemon/${id}.png" width="40" height="40" alt="" loading="lazy" decoding="async">`);
			}));
		}
		for (const li of content.querySelectorAll(':scope > ul > li')) sourceCard(li);
		content.querySelector(':scope > p:last-child > a[href$="/items/"]')?.classList.add('ohg-m-back');
	}
	// On a phone the page head hides a reference page's content (<html data-ohg-pending>) until its phone layout is
	// built, so the wide layout never shows first; the head lifts it by itself if this script fails.
	// A bar along the bottom that splits a page into tabs, like a Pokémon's page. `order` lists the tabs ([id, label,
	// icon]); `tabOf(node)` names the tab a top-level node starts (nothing: it stays in the current one). A link into a
	// section opens its tab.
	const TAB_ICON = {
		overview: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h0"/>',
		level: '<path d="M4 19h16M7 15l4-4 3 3 5-6M15 8h4v4"/>',
		disc: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.5"/>',
		person: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
		egg: '<path d="M12 3c3.5 0 7 5.5 7 10a7 7 0 0 1-14 0c0-4.5 3.5-10 7-10Z"/>',
		pin: '<path d="M12 21s6-5.2 6-11a6 6 0 0 0-12 0c0 5.8 6 11 6 11Z"/><circle cx="12" cy="10" r="2.2"/>',
		gift: '<rect x="4" y="11" width="16" height="9" rx="1.5"/><path d="M3 7h18v4H3zM12 7v13M12 7c-2-4-6-3-5-1 1 1 3 1 5 1Zm0 0c2-4 6-3 5-1-1 1-3 1-5 1Z"/>',
		bag: '<path d="M6 8h12l1 12H5L6 8Z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/>',
		swap: '<path d="M6 8h12l-3-3M18 16H6l3 3"/>',
		trophy: '<path d="M8 4h8v5a4 4 0 0 1-8 0V4ZM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M8 20h8"/>',
		tree: '<path d="M10 21v-5H6a4 4 0 0 1-2-7 5 5 0 0 1 4-6 5 5 0 0 1 8 0 5 5 0 0 1 4 6 4 4 0 0 1-2 7h-4v5M8 21h8"/>',
		coin: '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M10 10h4M10 14h4"/>',
		grass: '<path d="M4 20h16M7 20C7 14 5 10 3 8c5 1 8 5 9 12 0-8 3-14 8-17-2 6-3 12-3 17"/>',
		uses: '<path d="M14 6a4 4 0 0 0 5 5l-8 8a2.1 2.1 0 0 1-3-3l8-8Z"/><path d="M14 6l2-2 4 4-2 2"/>',
		ball: '<circle cx="12" cy="12" r="9"/><path d="M3 12h6m6 0h6"/><circle cx="12" cy="12" r="3"/>',
		bolt: '<path d="M13 3 5 14h6l-1 7 8-11h-6l1-7Z"/>',
		list: '<path d="M8 6h12M8 12h12M8 18h12M4 6h0M4 12h0M4 18h0"/>',
		spark: '<path d="M12 3l2.2 5.6L20 9.5l-4.4 3.9 1.3 5.8L12 16.2l-4.9 3 1.3-5.8L4 9.5l5.8-.9L12 3Z"/>',
		hidden: '<path d="M3 12s3.5-6 9-6 9 6 9 6-3.500 6-9 6-9-6-9-6Z"/><circle cx="12" cy="12" r="2.5"/>',
	};
	const tabButtons = (tabs) => tabs.map(([id, label, ic]) => `<button type="button" data-tab="${id}" aria-pressed="false"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${TAB_ICON[ic]}</svg><span>${label}</span></button>`).join('');
	function sectionTabs(content, order, tabOf, hashTab, start = order[0][0]) {
		let cur = start; // '' leaves what comes before the first named tab out of the tabs: it shows in all of them
		const present = new Set();
		const nodes = [];
		// the links that close a page ("← All moves · TMs and HMs") belong to no tab: the short link paragraphs at its very end
		const closing = new Set();
		for (let n = content.lastElementChild; n && n.matches('p') && n.querySelector(':scope > a') && n.textContent.trim().length < 60; n = n.previousElementSibling) closing.add(n);
		for (const n of content.children) {
			if (closing.has(n)) break;
			const t = tabOf(n);
			if (t) cur = t;
			if (!cur) continue;
			n.dataset.ohgTab = cur;
			present.add(cur);
			nodes.push(n);
		}
		const tabs = order.filter(([id]) => present.has(id));
		if (tabs.length < 2) { nodes.forEach((n) => delete n.dataset.ohgTab); return null; }
		const bar = document.createElement('nav');
		bar.className = 'ohg-m-tabs not-content';
		bar.setAttribute('aria-label', 'Page sections');
		bar.innerHTML = tabButtons(tabs);
		document.body.append(bar);
		document.documentElement.setAttribute('data-ohg-tabbed', '');
		const show = (id, scroll) => {
			content.dataset.ohgTabActive = id;
			bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === id)));
			let first = true;
			for (const n of content.children) {
				if (!n.dataset.ohgTab) continue;
				const on = n.dataset.ohgTab === id;
				n.toggleAttribute('data-ohg-off', !on);
				// the first thing a tab shows sits right under the title
				const lead = on && first && !n.matches('.ohg-m-item-hero') && getComputedStyle(n).display !== 'none';
				n.toggleAttribute('data-ohg-first', lead);
				if (lead) first = false;
			}
			if (scroll) window.scrollTo({ top: Math.max(0, content.getBoundingClientRect().top + window.scrollY - 72), behavior: 'auto' });
		};
		bar.addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) show(b.dataset.tab, true); });
		const follow = () => {
			let t = null;
			try { t = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { /* bad hash */ }
			const named = t && hashTab?.(t);
			const sec = t && content.contains(t) ? (t.closest('[data-ohg-tab]') || t) : null;
			if (named && present.has(named)) show(named, false);
			else if (sec?.dataset.ohgTab) { show(sec.dataset.ohgTab, false); t.scrollIntoView(); }
			else if (!content.dataset.ohgTabActive) show(tabs[0][0], false);
		};
		follow();
		window.addEventListener('hashchange', follow);
		return { present, show };
	}
	const pageIs = (re) => re.test(String(location.pathname || '').replace(/index\.html$/, '').slice(base.length));
	// A move: Overview (effect, numbers, changes) and one tab per way of learning it, instead of every list down one page.
	function setupMobileMoveTabs() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^moves\/[^/]+\/$/)) return;
		const kinds = { level: 'level', tm: 'tm', tutor: 'tutor', egg: 'egg' };
		const tabs = sectionTabs(content, [['overview', 'Overview', 'overview'], ['level', 'Level-up', 'level'], ['tm', 'TMs / HMs', 'disc'], ['tutor', 'Tutors', 'person'], ['egg', 'Egg', 'egg']],
			(n) => n.matches('h3[id^="learners-"]') ? kinds[n.id.slice('learners-'.length)] : n.matches('h2#learners') ? 'overview' : '',
			(t) => t.id === 'learners' ? ['level', 'tm', 'tutor', 'egg'].find((k) => content.querySelector(`:scope > #learners-${k}`)) : '');
		if (!tabs) return;
		// "Pokémon that learn this move" is the tabs now; the TM line goes with the TMs
		const heading = content.querySelector(':scope > h2#learners');
		heading?.classList.add('ohg-m-trim');
		for (let n = heading?.nextElementSibling; n && n.matches('p'); n = n.nextElementSibling) {
			if (/^TM \/ HM/.test(n.textContent.trim()) && tabs.present.has('tm')) n.dataset.ohgTab = 'tm';
		}
		tabs.show(content.dataset.ohgTabActive, false);
	}
	// A row of choices that fits the width whatever their number: equal cells, three to a row at most (four make two
	// rows of two), and a shorter last row stretches across. `choices`: [id, label, count?]; `onPick(id)` runs on a tap.
	function segmented(choices, label, onPick) {
		const box = document.createElement('div');
		box.className = 'ohg-m-seg not-content';
		box.setAttribute('role', 'tablist');
		box.setAttribute('aria-label', label);
		const n = choices.length, perRow = n === 4 ? 2 : Math.min(n, 3);
		box.innerHTML = choices.map(([id, text, count], i) => {
			const inRow = Math.min(perRow, n - Math.floor(i / perRow) * perRow);
			return `<button type="button" role="tab" data-id="${id}" aria-selected="false" style="grid-column: span ${6 / inRow}"><b>${text}</b>${count != null ? `<span>${count}</span>` : ''}</button>`;
		}).join('');
		const pick = (id) => { box.querySelectorAll('button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.id === id))); onPick(id); };
		box.addEventListener('click', (e) => { const b = e.target.closest('button[data-id]'); if (b) pick(b.dataset.id); });
		return { box, pick };
	}
	// An item: Overview (what it does and, for a TM, its move), Get it, the wild Pokémon that hold it, what it is used
	// for, and a TM's compatible Pokémon. Get it shows one way of getting the item at a time (gifts, shops, hidden
	// items…): a picker at its top, in the page's order, chooses which.
	const ITEM_SOURCES = {
		'source-item-ball': 'Ground', 'source-hidden': 'Hidden', 'source-gift': 'Gifts', 'source-prize': 'Prizes', 'source-bought-exchanged': 'Exchange',
		'source-shop': 'Shops', 'source-automatic': 'Automatic', 'source-savings-reward': 'Savings', 'source-minigame-prize': 'Minigames', 'source-pickup': 'Pickup',
		'source-tree': 'Trees', 'source-stolen': 'Stolen', 'source-held-by-wild-pok-mon': 'Held',
	};
	function setupMobileItemTabs() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^items\/[^/]+\/$/)) return;
		const of = { 'wild-held': 'wild', forms: 'uses', 'needed-by': 'uses', 'author-reference': 'uses', 'related-uses': 'uses', 'compatible-pokemon': 'pokemon' };
		const tabs = sectionTabs(content, [['overview', 'Overview', 'overview'], ['get', 'Get it', 'pin'], ['wild', 'Wild', 'grass'], ['uses', 'Uses', 'uses'], ['pokemon', 'Pokémon', 'ball']],
			(n) => !n.matches('h2[id]') ? '' : /^source-/.test(n.id) ? 'get' : (of[n.id] || ''));
		const heads = [...content.querySelectorAll(':scope > h2[id^="source-"]')];
		if (!tabs || heads.length < 2) return;
		// each source's nodes (its heading and what follows, up to the next one) carry its id
		let src = '';
		for (const n of content.querySelectorAll(':scope > [data-ohg-tab="get"]')) {
			if (n.matches('h2[id^="source-"]')) src = n.id;
			if (src) n.dataset.ohgSrc = src;
		}
		const { box: row, pick } = segmented(heads.map((h) => [h.id, ITEM_SOURCES[h.id] || h.textContent.trim(), content.querySelectorAll(`:scope > ul[data-ohg-src="${h.id}"] > li`).length || null]), 'Ways to get it', (id) => {
			for (const n of content.querySelectorAll(':scope > [data-ohg-src]')) {
				n.toggleAttribute('data-ohg-src-off', n.dataset.ohgSrc !== id);
				n.toggleAttribute('data-ohg-src-first', n.id === id);
			}
		});
		row.dataset.ohgTab = 'get';
		heads[0].before(row);
		// a link to one source (…/#source-shop) opens Get it on that source
		const fromHash = () => { const id = location.hash.slice(1); if (heads.some((h) => h.id === id)) pick(id); };
		window.addEventListener('hashchange', fromHash);
		pick(heads[0].id);
		fromHash();
		tabs.show(content.dataset.ohgTabActive, false);
	}
	// An ability: Overview (effect, changes), the moves it affects, and the Pokémon that have it as a regular or a hidden ability.
	function setupMobileAbilityTabs() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^abilities\/[^/]+\/$/)) return;
		const tabs = sectionTabs(content, [['overview', 'Overview', 'overview'], ['affected', 'Moves', 'bolt'], ['regular', 'Regular', 'spark'], ['hidden', 'Hidden', 'hidden']],
			(n) => n.matches('h2#applicability') ? 'affected' : n.matches('h2#holders') ? 'overview' : n.matches('h3') && /^Regular ability/.test(n.textContent) ? 'regular' : n.matches('h3') && /^Hidden ability/.test(n.textContent) ? 'hidden' : '');
		if (!tabs) return;
		if (tabs.present.has('regular') || tabs.present.has('hidden')) content.querySelector(':scope > h2#holders')?.classList.add('ohg-m-trim');
		tabs.show(content.dataset.ohgTabActive, false);
	}
	// A Pokémon's, item's, move's, ability's or location's page on a phone: every Pokémon and item it names gets its
	// sprite beside the name, as in the walkthrough.
	function setupMobileRefSprites() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^(pokemon|items|moves|abilities|locations)\/[^/]+\/$/)) return;
		const mq = matchMedia('(max-width: 50rem)');
		const run = () => { if (mq.matches) decorateSprites(content, true); };
		mq.addEventListener ? mq.addEventListener('change', run) : mq.addListener(run);
		run();
	}
	// The Locations list: one region at a time, chosen from a picker above the list; a search looks through all of them.
	function setupMobileLocationList() {
		const list = document.querySelector('.sl-markdown-content > #loc-list');
		if (!list || typeof matchMedia === 'undefined' || !pageIs(/^locations\/$/)) return;
		const regions = [...list.querySelectorAll(':scope > h2')].map((h, i) => ({ id: `region-${i}`, h, ul: h.nextElementSibling }));
		if (regions.length < 2) return;
		const { box, pick } = segmented(regions.map((r) => [r.id, r.h.textContent.trim(), r.ul?.children.length ?? null]), 'Region', (id) => {
			for (const r of regions) { r.h.toggleAttribute('data-ohg-seg-off', r.id !== id); r.ul?.toggleAttribute('data-ohg-seg-off', r.id !== id); }
		});
		list.before(box);
		pick(regions[0].id);
	}
	// A location's page: Quests, Pokémon (wild, calendar, gifts and trades), Trainers, Items, Shops and Tutors, each in
	// its own tab; the region above them shows in all.
	function setupMobileLocationTabs() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^locations\/[^/]+\/$/)) return;
		document.documentElement.setAttribute('data-ohg-location', '');
		const of = { quests: 'quests', wild: 'pokemon', calendar: 'pokemon', special: 'pokemon', trainers: 'trainers', items: 'items', shops: 'shops', tutors: 'tutors' };
		sectionTabs(content, [['quests', 'Quests', 'list'], ['pokemon', 'Pokémon', 'ball'], ['trainers', 'Trainers', 'person'], ['items', 'Items', 'bag'], ['shops', 'Shops', 'coin'], ['tutors', 'Tutors', 'level']],
			(n) => n.matches('h2[id]') ? (of[n.id] || '') : '', null, '');
		// its lists as cards: a quest is a row that opens it; a gift or a scripted Pokémon keeps its details, with the
		// quests it names as rows under them
		const here = document.querySelector('h1')?.textContent || '';
		for (const li of content.querySelectorAll(':scope > ul > li')) {
			const only = li.children.length === 1 && li.firstElementChild.matches('a[href*="/guide/"]') && li.textContent.trim() === li.firstElementChild.textContent.trim();
			if (only) { questLink(li.firstElementChild, here); li.classList.add('ohg-m-src', 'ohg-m-quest'); } else sourceCard(li);
		}
		// one of an item says nothing: the quantity shows from two up
		for (const td of content.querySelectorAll('table.ohg-m-loot td[data-label="Qty"]')) if (td.textContent.trim() === '1') td.dataset.one = '';
	}
	// The Trainers page: Find (the directory with its search) and Battle guide, which shows one group of battles at a
	// time (Gym Leaders, the Elite Four…) from a picker at its top. The introduction and its section links leave the phone.
	function setupMobileTrainers() {
		const page = document.querySelector('.sl-markdown-content > .trainer-directory-page');
		if (!page || typeof matchMedia === 'undefined' || !pageIs(/^trainers\/$/)) return;
		const tabs = sectionTabs(page, [['find', 'Find a trainer', 'person'], ['guide', 'Battle guide', 'spark']],
			(n) => n.matches('.trainer-browser') ? 'find' : n.matches('.trainer-reading-note, .trainer-guide-section') ? 'guide' : '', null, '');
		const sections = [...page.querySelectorAll(':scope > .trainer-guide-section')];
		if (!tabs || sections.length < 2) return;
		const labels = [...page.querySelectorAll(':scope > .trainer-categories a strong')].map((n) => n.textContent.trim());
		const { box, pick } = segmented(sections.map((sec, i) => [String(i), labels[i] || sec.querySelector('h2')?.textContent.trim() || `Group ${i + 1}`, null]), 'Battle group', (id) => {
			sections.forEach((sec, i) => sec.toggleAttribute('data-ohg-seg-off', String(i) !== id));
		});
		box.dataset.ohgTab = 'guide';
		sections[0].before(box);
		// a link into a group (…/#elite-four, a gym's heading) picks it
		const fromHash = () => {
			let t = null;
			try { t = location.hash ? document.getElementById(decodeURIComponent(location.hash.slice(1))) : null; } catch { /* bad hash */ }
			const at = t ? sections.findIndex((sec) => sec.contains(t) || sec.previousElementSibling === t) : -1;
			if (at >= 0) { pick(String(at)); tabs.show('guide', false); t.scrollIntoView(); }
		};
		window.addEventListener('hashchange', fromHash);
		pick('0');
		tabs.show(page.dataset.ohgTabActive, false);
		fromHash();
	}
	// The damage calculator: its panels as tabs (Opponent, Your team, Results, Tools). The calculator moves between
	// its panels by putting the focus in them (adding a Pokémon, opening a matchup, editing a set), so a panel that is
	// not showing stays focusable, and the tab follows the focus.
	function setupMobileCalc() {
		const app = document.querySelector('#team-builder.tb-calc-page');
		if (!app || typeof matchMedia === 'undefined' || !pageIs(/^damage-calc\/$/)) return;
		const root = document.documentElement;
		const mq = matchMedia('(max-width: 50rem)');
		const bar = document.createElement('nav');
		bar.className = 'ohg-m-tabs not-content';
		bar.setAttribute('aria-label', 'Calculator panels');
		bar.innerHTML = tabButtons([['opponent', 'Opponent', 'person'], ['team', 'Your team', 'ball'], ['results', 'Results', 'level'], ['tools', 'Tools', 'uses']]);
		document.body.append(bar);
		root.setAttribute('data-ohg-tabbed', '');
		const show = (id, scroll) => {
			root.dataset.ohgCalc = id;
			bar.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tab === id)));
			if (scroll && mq.matches) requestAnimationFrame(() => window.scrollTo({ top: Math.max(0, app.getBoundingClientRect().top + window.scrollY - 72), behavior: 'auto' }));
		};
		bar.addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) show(b.dataset.tab, true); });
		const follow = (at) => {
			const panel = at?.closest?.('.tb-bc > *');
			if (!panel || !mq.matches) return;
			const tab = panel.matches('.tb-bc-opponent') ? 'opponent' : panel.matches('#tb-bc-team') ? 'team' : panel.matches('#tb-bc-overview, #tb-bc-matchup') ? 'results' : at.closest('#tb-bc-set') ? 'team' : 'tools';
			if (tab !== root.dataset.ohgCalc) show(tab, true);
		};
		document.addEventListener('focusin', (e) => follow(e.target));
		// a page that is not the focused window moves the focus without the event: look after each tap as well
		app.addEventListener('click', () => { for (const wait of [0, 200]) setTimeout(() => follow(document.activeElement), wait); });
		// a link that carries a battle opens where the work is: the results with a team, else the team to pick
		const state = new URLSearchParams(location.hash.slice(1));
		show(state.get('battle') ? (state.get('team') ? 'results' : 'team') : 'opponent', false);
	}
	// The Move tutors list on a phone: a tutor's card opens its move on the Tutors tab.
	function setupMobileTutors() {
		if (typeof matchMedia === 'undefined' || !pageIs(/^tutors\/$/)) return;
		const mq = matchMedia('(max-width: 50rem)');
		document.addEventListener('click', (e) => {
			const a = e.target.closest?.('#tutor-table td:first-child > a[href*="/moves/"]');
			if (a && mq.matches && !a.hash) a.hash = 'learners-tutor';
		}, true);
	}
	// The TM and HM list: the list itself first, the new and changed ones in a second tab.
	function setupMobileTmTabs() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || typeof matchMedia === 'undefined' || !pageIs(/^tms\/$/)) return;
		sectionTabs(content, [['all', 'All TMs & HMs', 'list'], ['changed', 'New & changed', 'spark']],
			(n) => n.matches('h2#changes') ? 'changed' : n.matches('h2#tm-list') ? 'all' : '');
		// "TM93 · Psyshock · New TM in v4": the dots and the note get their own elements, so a phone can lay the line
		// out as a tile (number and a short note above, the move under them); the text itself stays as written
		for (const li of content.querySelectorAll(':scope > ul.reference-link-list > li')) {
			for (const n of [...li.childNodes]) {
				if (n.nodeType !== 3 || !n.data.trim()) continue;
				const note = n.data.replace(/^[\s·]+/, '').trim();
				const span = document.createElement('span');
				if (note) { span.className = 'ohg-m-tm-note'; span.dataset.short = /^New/.test(note) ? 'New' : 'Changed'; }
				else span.className = 'ohg-m-tm-sep';
				span.textContent = n.data;
				n.replaceWith(span);
			}
		}
	}
	// Notes that explain how to read a page rather than say something about its subject: a phone leaves them out
	// (.ohg-m-trim), like the back links at the very end, which the floating button replaces.
	const BOILERPLATE = [
		/^Check (each Pokémon’s )?availability/, /Pokémon and forms can learn this move\./, /^“(var\.|—)” /, /^“On evolution” moves/,
		/^These Pokémon appear on specific dates/, /^Click a trainer to see their team/, /^Some gifts depend on/, /^You get one of these at a time/,
		/^These are the ordinary encounter tables/, /^These are the candidate Pokémon/, /^These wild Pokémon can carry/, /^Locations are in rough story order/,
		/^Some of these depend on your starter/, /^A trainer['’]s held item/, /^Follow the linked quests/, /^Conditions can depend on story progress/,
	];
	// where a page's list is: [label, path under the site's base]
	const LISTS = { pokemon: ['Pokédex', 'pokemon/'], items: ['Items', 'items/'], moves: ['Moves', 'moves/'], abilities: ['Abilities', 'abilities/'], locations: ['Locations', 'locations/'], trainers: ['Trainers', 'trainers/'] };
	function setupMobileTrim() {
		const content = document.querySelector('.sl-markdown-content');
		if (!content || !/\/(pokemon|items|moves|abilities|locations|trainers)\/.+/.test(String(location.pathname || ''))) return;
		for (const p of content.querySelectorAll('p')) {
			if (p.closest('.ohg-m-row, .ohg-m-sheet, li, td, details')) continue;
			const text = p.textContent.replace(/\s+/g, ' ').trim();
			if (BOILERPLATE.some((re) => re.test(text)) || (p.parentElement === content && /^(←|Browse all trainers)/.test(text))) p.classList.add('ohg-m-trim');
		}
	}
	// Every page on a phone: a button that goes back to the top once the page has been scrolled, and on a page that
	// belongs to a list (a move, an item, a Pokémon…) a button back to that list, both always in reach.
	function setupMobileFloat() {
		if (typeof matchMedia === 'undefined' || !document.body) return;
		const here = String(location.pathname || '').replace(/index\.html$/, '');
		const m = here.slice(base.length).match(/^(pokemon|items|moves|abilities|locations|trainers)\/.+/);
		const box = document.createElement('div');
		box.className = 'ohg-m-float not-content';
		const list = m && LISTS[m[1]];
		box.innerHTML = (list ? `<a class="ohg-m-float-back" href="${base + list[1]}"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 6-6 6 6 6"/></svg><span>${list[0]}</span></a>` : '<span></span>') +
			'<button type="button" class="ohg-m-float-top" aria-label="Back to top" hidden><svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5m-6 6 6-6 6 6"/></svg></button>';
		const top = box.querySelector('.ohg-m-float-top');
		top.addEventListener('click', () => window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' }));
		// coming from the list itself, going back returns to it as it was left (its filters and place)
		box.querySelector('.ohg-m-float-back')?.addEventListener('click', (e) => {
			let from = '';
			try { const r = new URL(document.referrer); if (r.origin === location.origin) from = r.pathname.replace(/index\.html$/, ''); } catch { /* no referrer */ }
			if (from === base + list[1] && history.length > 1) { e.preventDefault(); history.back(); }
		});
		let queued = false;
		const update = () => { queued = false; top.hidden = window.scrollY < 600; };
		window.addEventListener('scroll', () => { if (!queued) { queued = true; requestAnimationFrame(update); } }, { passive: true });
		update();
		document.body.append(box);
	}
	const init = () => {
		try { setupQuests(); setupFilters(); setupTableScroll(); setupMobileGuide(); setupMobileMenu(); setupItemSprites(); setupMobileReference(); setupMobileItem(); setupMobileTrim(); setupMobileTabs(); setupMobileMoveTabs(); setupMobileItemTabs(); setupMobileAbilityTabs(); setupMobileTmTabs(); setupMobileLocationList(); setupMobileLocationTabs(); setupMobileTrainers(); setupMobileCalc(); setupMobileTutors(); setupMobileRefSprites(); setupMobileFloat(); }
		finally { document.documentElement.removeAttribute?.('data-ohg-pending'); }
	};
	document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', init) : init();
})();
