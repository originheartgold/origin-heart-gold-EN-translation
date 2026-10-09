"""Export the game data behind work/docs/ as JSON for the website (site/src/data/).

Reuses gen_docs.py's readers and helpers, so the site and the Markdown docs always agree.
Reads the untouched CN ROM through romdata.Rom (cached in work/build/docs_cache.pkl).

    python3 work/tools/site/export_data.py            # writes site/src/data/*.json
    python3 work/tools/site/export_data.py --check    # exit 1 if a file would change
"""
import argparse
import collections
import calendar
import json
import itertools
import os
import re
import sys
import struct
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'docs'))
import gen_docs as G      # noqa: E402
import romdata as R       # noqa: E402
import landmarks as LM    # noqa: E402
import safari_held as SH  # noqa: E402
import battle_reference as BR  # noqa: E402

OUT = os.path.join(R.REPO, 'site', 'src', 'data')
# reviewed lists, shared with the docs (see gen_docs.reviewed and each file's _about): species, forms and items a
# player cannot get in normal play remain listed with a reason; verified sources and notes are added
NOT_IN_GAME = G.reviewed('not_in_game')
EXTRA = G.reviewed('extra_sources')
ITEMS_NOT_IN_GAME = G.reviewed('items_not_in_game')
ITEMS_EXTRA = G.reviewed('items_extra_sources')


def slugify(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    s = s.lower().replace('♀', '-f').replace('♂', '-m').replace("'", '')
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s or 'x'


class Slugs:
    """Unique slugs per namespace (two items can share a name)."""
    def __init__(self):
        self.used = collections.defaultdict(set)

    def make(self, ns, name, suffix):
        s = slugify(name)
        if s in self.used[ns]:
            s = '%s-%s' % (s, suffix)
        self.used[ns].add(s)
        return s


# ---------------------------------------------------------------- species ids inside generator text
MARK = re.compile(r'\x00(\d+):(\d+)\x00')


class MarkedNames:
    """Temporarily make ctx.sp() return a marker, so generator helpers that only
    produce names (encounter_sections, merge_slots) give us species ids too."""
    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        self.orig = self.ctx.sp
        self.ctx.sp = lambda i, form=0: '\x00%d:%d\x00' % (i, form)
        return self

    def __exit__(self, *a):
        self.ctx.sp = self.orig


def species_index(ctx, sp, form):
    return G.form_index(ctx, sp, form) if form else sp


def unmark(ctx, s):
    """'\\x00sp:form\\x00 (Good Rod…)' -> (species index or None, display name)."""
    m = MARK.search(s)
    if not m:
        return None, s
    sp, fm = int(m.group(1)), int(m.group(2))
    if sp >= 2048:                      # raw encounter value with the form in the top bits
        sp, fm = R.split_species(sp)
    idx = species_index(ctx, sp, fm)
    return idx, MARK.sub(lambda _m: ctx.sp(sp, fm), s)


# ---------------------------------------------------------------- areas
def area_key(ctx, zid):
    z = ctx.zones[zid]
    return ctx._zbase(z)


def build_areas(ctx, slugs):
    areas = collections.OrderedDict()
    for z in sorted(ctx.zones, key=lambda z: ctx.zrank(z['zone_id'])):
        name = area_key(ctx, z['zone_id'])
        if not name or name.startswith('MAP_') or name == 'Mystery Zone':
            continue
        if name not in areas:
            areas[name] = dict(name=name, slug=slugs.make('area', name, z['zone_id']),
                               region=z.get('region') or '',   # regrouped in site/src/lib/data.ts
                               rank=list(ctx.zrank(z['zone_id']))[0], zones=[], maps=[],
                               encounters=[], encNotes=[], contest=None, headbutt=[], trainers=[], items=[], gifts=[],
                               shops=[], trades=[], statics=[])
        a = areas[name]
        a['zones'].append(z['zone_id'])
        a['maps'].append(dict(zone=z['zone_id'], name=ctx.zname(z['zone_id']), type=z['map_type'],
                              vanilla=z.get('vanilla_const', '')))
    zone_area = {}
    for a in areas.values():
        for zid in a['zones']:
            zone_area[zid] = a
    return areas, zone_area


def file_areas(ctx, zone_area, f):
    out = []
    for zid in sorted(set(ctx.file_zones.get(f, [])), key=ctx.zrank):
        a = zone_area.get(zid)
        if a and a not in out:
            out.append(a)
    return out


GUIDE = os.path.join(R.REPO, 'guide')
FILE_REF = re.compile(r'\bfiles?\s+(\d+(?:\s*(?:,|and|\+|/)\s*\d+)*)')


def gh_slug(s):
    """Heading id as Starlight (github-slugger) makes it."""
    s = s.strip().lower()
    s = re.sub(r'[^\w\- ]', '', s, flags=re.UNICODE)
    return s.replace(' ', '-')


def guide_quests():
    """script file -> [(quest {title, href}, player text of the quest)] for the guide quests whose *Source:*
    lines cite that script file."""
    out = collections.defaultdict(list)
    if not os.path.isdir(GUIDE):
        return out
    for fn in sorted(os.listdir(GUIDE)):
        if not re.match(r'\d+-.*\.md$', fn):
            continue                     # chapters only (not README or known issues)
        page = re.sub(r'^\d+-', '', fn[:-3])
        sections = re.split(r'\n(?=## )', open(os.path.join(GUIDE, fn), encoding='utf-8').read())
        for sec in sections:
            if not sec.startswith('## '):
                continue
            head = sec[3:sec.index('\n')].strip() if '\n' in sec else sec[3:].strip()
            text = '\n'.join(ln for ln in sec.split('\n') if '*Source:*' not in ln)
            files = set()
            for ln in sec.split('\n'):
                if '*Source:*' in ln:
                    for m in FILE_REF.finditer(ln):
                        files |= {int(n) for n in re.findall(r'\d+', m.group(1))}
            q = dict(title=head, href='/guide/%s/#%s' % (page, gh_slug(head)))
            for f in files:
                out[f].append((q, text))
    return out


def quests_for(gq, f, name=None, limit=3):
    """Guide quests that cite script file f and, when name is given, mention it in their player text
    (so a shared town script does not link every quest in town)."""
    qs = [q for q, text in gq.get(f, []) if name is None or name.lower() in text.lower()]
    return qs[:limit]


def landmark(ctx, zid, x, z, cache={}):
    """'3 steps north of the door to Celadon Poké Mart': the nearest door, never a coordinate."""
    if zid not in cache:
        cache[zid] = [t for t in LM.things(ctx, zid) if t[2] == 'door']
    doors = cache[zid]
    if not doors:
        return None
    t = min(doors, key=lambda t: abs(t[0] - x) + abs(t[1] - z))
    if abs(t[0] - x) + abs(t[1] - z) > 30:
        return None
    if (t[0], t[1]) == (x, z):
        return 'at the ' + t[3]
    return '%s of the %s' % (LM.steps(x - t[0], z - t[1]), t[3])


def short_method(title):
    """Encounter section title -> short method name for the Pokémon pages."""
    if title.startswith('Radio on '):
        return 'Radio (%s)' % title[len('Radio on '):].split(' (')[0]
    if title.startswith('Swarm'):
        return 'Swarm'
    return title


# Reviewed notes for tutors whose NPC and script disagree (hack findings, kept as the hack has them, D-1337).
TUTOR_NOTES = {
    (175, 944): dict(text='he says Play Rough, but the move he really teaches is Flail (a bug in the original hack)',
                     alias='Play Rough', href='/guide/known-issues/'),
    (268, 829): dict(text='suspected bug in the original hack: a Pokémon with a free move slot gets Charge instead of '
                          'Volt Switch', alias='Volt Switch', href='/guide/known-issues/'),
}


def game_alias(ctx, bank_name):
    """The in-game (shortened) spelling when the site shows a fuller name, else None."""
    return bank_name if bank_name and ctx.FULL.get(bank_name) else None


# ---------------------------------------------------------------- export
def player_place(place):
    """A place for the item pages. A script with no map becomes a plain phrase; the file number stays as
    a hidden technical reference."""
    if re.match(r'^script file \d+ \(no map\)$', place):
        return dict(place='place not identified', tech=place)
    return dict(place=place)


def evo_entry(ctx, sp, m, p, original=None, link=None):
    """One evolution as shown on the Pokémon pages; link = (from, to) for the extra_sources.json evoBlocked overrides."""
    e = dict(id=sp, how=G.evo_text(ctx, m, p), conds=G.evo_conds(ctx, m, p))
    blocked = EXTRA.get(link[0], {}).get('evoBlocked', {}).get(str(link[1])) if link else None
    if not G.evo_possible(m):
        e['never'] = True
        e['official'] = G.evo_official(m, p)
    elif not G.evo_works(m, p):
        e['never'] = True
        e['blocked'] = 'the item it needs, %s, can\'t be obtained' % ctx.it(p)
    elif blocked:
        e['never'] = True
        e['blocked'] = blocked
    if sp in NOT_IN_GAME:
        e['name'] = ctx.sp(sp)
    if original is not None:
        e['original'] = original[0]
    return e


def export_evolutions(ctx, sp_slug):
    """Every evolution in the game with what the untouched HeartGold (USA) does for #1-#493, so the Pokémon
    pages can mark the hack's changes."""
    van, us_items = R.vanilla_evos()
    full = G.full_names()

    def van_text(m, p):
        if m in (6, 7, 16, 17, 18, 19):
            name = us_items.get(p, 'item #%d' % p)
            return G.EVO_TEXT[m].replace('{item}', full.get(name, name)).format(p=p)
        if m in G.NEVER_EVO and m not in G.EVO_TEXT:
            return G.NEVER_EVO[m].format(p=p)
        return G.evo_text(ctx, m, p)

    def hack_text(m, p):
        return G.EVO_TEXT[m].format(p=p, item=ctx.it(p), move=ctx.mv(p), species=ctx.sp(p),
                                    type=ctx.ty(p) if p < 18 else p) if m in G.EVO_TEXT else G.NEVER_EVO[m].format(p=p)

    rows = []
    for sp in sorted(sp_slug, key=lambda s: (ctx.forms[s][0] if s in ctx.forms else s, s)):
        ev = [(m, p, G.evo_target(ctx, sp, t)) for m, p, t in ctx.evos[sp]]
        seen = set()
        for m, p, t in ev:
            if t not in sp_slug or (t, m, p) in seen:
                continue
            seen.add((t, m, p))
            row = dict(id=sp, to=t, how=G.evo_text(ctx, m, p))
            if not G.evo_works(m, p):
                row['never'] = True
            if sp in van:
                old = sorted(van_text(vm, vp) for vm, vp, vt in van[sp] if vt == t)
                new = sorted(hack_text(hm, hp) for hm, hp, ht in ev if ht == t)
                if old != new:
                    row['original'] = '; '.join(old) if old else None
            rows.append(row)
    return rows


def held_item_chances(items):
    """Ordinary wild held-item rolls; identical slots guarantee that item.

    Verified in the untouched CN v4.0.3 ARM9 roller at 0x0207138C:
    thresholds 45/95 at 0x020FE716 give 50%/5%. The roller reads form-aware
    personal fields 0x10/0x11. Compound Eyes' separate 20/80 thresholds are
    deliberately not used here: source pages show the unmodified chances.
    """
    common, rare = items
    if common == rare:
        return [(common, 100)] if common else []
    return [(item, chance) for item, chance in ((common, 50), (rare, 5)) if item]


def calendar_wild_rows(ctx, zone_area):
    """Actual date-locked slot-11 replacements from the CN encounter loader.

    See emu_calendar.py and chinese_source_rom_verify_calendar.md. Only maps
    with walk encounters are reachable (the Volcanion entry has no walk rate).
    """
    enc = ctx.enc_by_file[0]
    for month, day, zid, sp, form, period in struct.iter_unpack('<BBHHBB', ctx.rom.a9(0x020F6A64, 64)):
        area = zone_area.get(zid)
        if not area:
            continue
        bank = ctx.zones[zid]['wild_encounter_bank']
        if not 0 <= bank < len(enc) or not enc[bank]['rates']['walk']:
            continue
        idx = species_index(ctx, sp, form)
        when = 'any time' if period == 0 else 'morning' if period == 1 else 'night'
        method = 'Calendar encounter: %s %d, %s (replaces the 1%% grass/cave slot)' % (
            calendar.month_name[month], day, when)
        row = dict(id=idx, name=ctx.sp(idx), level=G.lvl(enc[bank]['levels'][11], enc[bank]['levels'][11]), pct=1)
        yield area, ctx.zname(zid), method, row


def safari_wild_rows(ctx, zone_area):
    """Candidate species with the selected area/object conditions kept explicit."""
    area = zone_area.get(357)
    if not area:
        return
    grouped = collections.OrderedDict()
    for source in SH.safari_rows(ctx.rom.path):
        key = tuple(source[k] for k in ('species', 'level', 'area', 'method', 'conditional'))
        times = grouped.setdefault(key, [])
        if source['time'] not in times:
            times.append(source['time'])
    for (species, level, safari_area, safari_method, conditional), times in grouped.items():
        sp, form = R.split_species(species)
        idx = species_index(ctx, sp, form)
        condition = '; object requirements vary' if conditional else ''
        when = 'all day' if len(times) == 3 else ' and '.join(times)
        method = 'Safari Zone: %s area selected, %s, %s%s' % (
            safari_area, safari_method, when, condition)
        row = dict(id=idx, name=ctx.sp(idx), level=G.lvl(level, level), pct=None)
        yield area, 'Safari Zone: ' + safari_area, method, row


def wild_held_sources(ctx, areas, species_ids, extra_rows=()):
    """Join actual encounter rows to form-aware personal data, never gift/trade availability.

    Reuse the displayed encounter tables so time, weekday, radio and tree conditions
    remain attached to their percentages. A percentage is conditional on its method,
    not the chance of finding that item on every step.
    """
    locations = collections.defaultdict(list)

    def add(area, place, method, row, rate):
        sp = row['id']
        if sp not in species_ids:
            return
        # Night fishing rows encode the applicable rod in their display name.
        name = ctx.sp(sp)
        detail = row.get('name', '')
        if detail.startswith(name + ' ('):
            method += ': ' + detail[len(name) + 1:]
        source = dict(area=area['slug'], place=place, method=method,
                      level=row['level'], encounterRate=rate)
        if source not in locations[sp]:
            locations[sp].append(source)

    for area in areas.values():
        for block in area['encounters']:
            for section in block['sections']:
                for row in section['rows']:
                    add(area, block['label'], section['title'], row, row['pct'])
        for block in area['headbutt']:
            for section in block['sections']:
                for row in section['rows']:
                    add(area, block['label'], 'Headbutt: ' + section['title'], row, row['pct'])
        if area['contest']:
            for group in area['contest']['sets']:
                for row in group['rows']:
                    add(area, area['name'], 'Bug-Catching Contest: ' + group['title'], row, row['rate'])
        for row in area.get('statics', []):
            if row['kind'] == 'static':
                # WildBattle rolls held items too, but these sources are not
                # random encounter tables and are not necessarily repeatable.
                add(area, area['name'], 'Scripted wild battle (may be one-time)', row, None)

    for area, place, method, row in extra_rows:
        add(area, place, method, row, row['pct'])

    sources = collections.defaultdict(list)
    for sp in sorted(locations):
        for item, chance in held_item_chances(ctx.personal[sp]['items']):
            sources[item].append(dict(species=sp, chance=chance, locations=locations[sp]))
    return sources


def export(ctx):
    pages, _cr, _findings = G.build_all(ctx)        # fills ctx caches (encounters, items, trainers, availability)
    gq = guide_quests()
    slugs = Slugs()
    areas, zone_area = build_areas(ctx, slugs)

    # ---- moves
    tm_of = collections.defaultdict(list)
    for i, m in ctx.tm.items():
        tm_of[m].append(R.tm_label(i))
    moves = []
    for m in range(1, len(ctx.moves)):
        d = ctx.moves[m]
        name = ctx.mv(m)
        unnamed = name.startswith('move #') or name in ('—', '-', '')
        if unnamed:
            name = 'Unnamed move #%d' % m
        t, cat, pw, acc, pp = G.move_row(ctx, m)
        moves.append(dict(id=m, name=name, slug=slugs.make('move', name, m), type=t, cat=cat, power=pw, acc=acc,
                          pp=pp, tm=sorted(tm_of.get(m, [])), game=game_alias(ctx, ctx.MV.get(m)), unnamed=unnamed))
    move_ids = {x['id'] for x in moves}

    # ---- species
    par = G.evo_parents(ctx)
    avail = ctx._avail
    tutors = ctx._tutors
    species = []
    sp_ids = ctx.species_ids()
    sp_slug = {}
    for sp in sp_ids:
        sp_slug[sp] = slugs.make('pokemon', ctx.sp(sp), sp)
    evolutions = export_evolutions(ctx, sp_slug)
    # (from, to, how) -> (HeartGold method or None,) for evolutions the hack changed
    orig = {(e['id'], e['to'], e['how']): (e['original'],) for e in evolutions if 'original' in e}
    for sp in sp_ids:
        p = ctx.personal[sp]
        t1, t2 = p['types']
        types = [ctx.ty(t1)] + ([] if t2 == t1 else [ctx.ty(t2)])
        evs = p['ev_yield']
        ev = [evs[0], evs[1], evs[2], evs[4], evs[5], evs[3]]
        region = next((t for lo, hi, t in G.RANGES if lo <= sp <= hi), '')
        tms = [i for i in ctx.tm_sorted if ctx.can_learn_tm(sp, ctx.tm[i])]
        species.append(dict(
            id=sp, name=ctx.sp(sp), slug=sp_slug[sp], region=region, types=types,
            abilities=list(dict.fromkeys(ctx.ab(a) for a in p['abilities'] if a)),
            hidden=ctx.ab(p['hidden_ability']) if p['hidden_ability'] else None,
            stats=list(R.personal_stats(p)), catch=p['catch_rate'], gender=G.gender_text(p['gender']),
            eggGroups=list(dict.fromkeys(R.EGG_GROUPS.get(g, str(g)) for g in p['egg_groups'])),
            growth=R.GROWTH[p['growth']] if p['growth'] < 6 else '?', ev=ev,
            held=[ctx.it(i) for i in p['items'] if i],
            evoFrom=list({(s, G.evo_text(ctx, m, q)): evo_entry(ctx, s, m, q, orig.get((s, sp, G.evo_text(ctx, m, q))), (s, sp))
                          for s, m, q in par.get(sp, []) if s in sp_slug}.values()),
            # All stored evolution targets retain their reference pages.
            evoTo=list({(t, G.evo_text(ctx, m, q)): evo_entry(ctx, t, m, q, orig.get((sp, t, G.evo_text(ctx, m, q))), (sp, t)) for m, q, t in
                        ((m, q, G.evo_target(ctx, sp, t)) for m, q, t in ctx.evos[sp])
                        if t in sp_slug or (t in NOT_IN_GAME and G.evo_possible(m) and not G.evo_works(m, q))}.values()),
            evoNotes=G.evo_notes(ctx, sp) + ([EXTRA[sp]['evoNote']] if 'evoNote' in EXTRA.get(sp, {}) else []),
            game=game_alias(ctx, ctx.SP.get(sp)),
            tmNote='The game\'s TM check rejects this species slot, the one it also uses for Eggs.' if sp == G.EGG_SPECIES else None,
            how=avail.get(sp, '') if sp not in NOT_IN_GAME else '',
            unavailableReason=NOT_IN_GAME.get(sp, {}).get('reason'),
            battleOnly=EXTRA.get(sp, {}).get('battle'),
            note=EXTRA.get(sp, {}).get('note'),
            levelup=[[lv, m] for lv, m in ctx.learn[sp] if m in move_ids],
            tms='all' if sp == G.MEW else [[R.tm_label(i), ctx.tm[i]] for i in tms],
            tutors=[m for m in G.tutor_compat_for(ctx, tutors, sp) if m in move_ids],
            egg=[m for m in (ctx.eggmoves[sp] if sp < len(ctx.eggmoves) else []) if m in move_ids],
        ))

    # ---- encounters per area
    enc, by_file = ctx.enc_by_file
    found_in = collections.defaultdict(list)         # species -> [(area slug, method)]
    weekday_block = {}                               # id(encounter block) -> (map title, weekday)
    with MarkedNames(ctx):
        for b in sorted(by_file, key=lambda b: min(ctx.zrank(z) for z in by_file[b])):
            secs = G.encounter_sections(ctx, enc[b])
            if not secs:
                continue
            zs = sorted(by_file[b], key=ctx.zrank)
            targets = []
            for zid in zs:
                a = zone_area.get(zid)
                if a and a not in targets:
                    targets.append(a)
            out_secs = []
            for title, rows in secs:
                rr = []
                for n, lv, pct in rows:
                    rr.append((n, lv, pct))
                out_secs.append((title, rr))
            for a in targets:
                # label from this area's own maps only (two areas can share one encounter record)
                label = ' / '.join(dict.fromkeys(ctx.zname(z) for z in zs if zone_area.get(z) is a))
                a['encounters'].append(dict(label=label, rates={k: v for k, v in enc[b]['rates'].items() if v},
                                            sections=[dict(title=t, rows=rr) for t, rr in out_secs]))
        # maps whose table changes with the weekday (Pal Park): one block per day
        for zid, days in ctx.enc_weekday.items():
            a = zone_area.get(zid)
            if not a:
                continue
            if G.ENC_WEEKDAY_NOTE not in a['encNotes']:
                a['encNotes'].append(G.ENC_WEEKDAY_NOTE)
            for day, b in days:
                rec = G.map_record(enc[b], zid)        # methods the park has no terrain for are off
                secs = G.encounter_sections(ctx, rec)
                if secs:
                    e = dict(label='%s: %s' % (G.ENC_WEEKDAY[zid], day),
                             rates={k: v for k, v in rec['rates'].items() if v},
                             sections=[dict(title=t, rows=list(rows)) for t, rows in secs])
                    a['encounters'].append(e)
                    weekday_block[id(e)] = (G.ENC_WEEKDAY[zid], day)
    # unmark after leaving the context (ctx.sp restored)
    for a in areas.values():
        for e in a['encounters']:
            for s in e['sections']:
                rows = []
                for n, lv, pct in s['rows']:
                    idx, name = unmark(ctx, n)
                    rows.append(dict(id=idx, name=name, level=lv, pct=pct))
                    if idx:
                        found_in[idx].append((a['slug'], short_method(s['title'])) + weekday_block.get(id(e), ()))
                s['rows'] = rows
    # maps whose wild Pokémon come from another system (Safari Zone areas, the Bug-Catching Contest)
    for zid, (_b, note) in sorted(ctx.enc_placeholders.items()):
        a = zone_area.get(zid)
        if a and note not in a['encNotes']:
            a['encNotes'].append(note)
        if a and zid == 487 and getattr(ctx, 'bug_contest', None):
            sets = []
            for i, rows in enumerate(ctx.bug_contest):
                rr = []
                for r in rows:
                    if r['species']:
                        rr.append(dict(id=r['species'], name=ctx.sp(r['species']), level=G.lvl(r['min'], r['max']),
                                       rate=r['rate'], score=r['score']))
                        found_in[r['species']].append((a['slug'], 'Bug-Catching Contest'))
                sets.append(dict(title='Set %d: %s' % (i + 1, G.CONTEST_SETS[i] if i < len(G.CONTEST_SETS) else 'unknown day'),
                                 rows=rr))
            a['contest'] = dict(note=G.CONTEST_NOTE, sets=sets)
    # headbutt
    for zid, b in enumerate(ctx.rom['headbutt']):
        h = R.parse_headbutt(b)
        a = zone_area.get(zid)
        if not h or not (h['trees'] or h['secret_trees']) or not a:
            continue
        tabs = []
        for k, t in (('common', 'Common trees'), ('rare', 'Rare trees'), ('secret', 'Special trees')):
            if k == 'secret' and not h['secret_trees']:
                continue
            with MarkedNames(ctx):
                rows = G.merge_slots(ctx, [(sp, lo, hi) for sp, lo, hi in h[k]], R.HEADBUTT_RATES)
            rr = []
            for n, lv, pct in rows:
                idx, name = unmark(ctx, n)
                rr.append(dict(id=idx, name=name, level=lv, pct=pct))
                if idx:
                    found_in[idx].append((a['slug'], 'Headbutt'))
            tabs.append(dict(title=t, rows=rr))
        a['headbutt'].append(dict(label=ctx.zname(zid), trees=h['trees'], special=h['secret_trees'], sections=tabs))

    # ---- static / gift Pokémon and trades
    static_q = collections.defaultdict(list)
    for kind, sp, fm, lv, f in G.static_mons(ctx):
        idx = G.form_index(ctx, sp, fm)
        for q in quests_for(gq, f, ctx.sp(idx)):
            if q not in static_q[idx]:
                static_q[idx].append(q)
        for a in file_areas(ctx, zone_area, f)[:1]:
            a['statics'].append(dict(kind=kind, id=idx, name=ctx.sp(idx), level=None if lv is None or lv >= 0x4000 else lv,
                                     quests=quests_for(gq, f, ctx.sp(idx))))
    tp = G.trade_places(ctx)
    loans = G.loan_trades(ctx)
    for i, b in enumerate(ctx.rom['trade']):
        t = R.parse_trade(b)
        for f in tp.get(i, []):
            for a in file_areas(ctx, zone_area, f)[:1]:
                a['trades'].append(dict(give=t['ask'], giveName=ctx.sp(t['ask']), get=t['give'], getName=ctx.sp(t['give']),
                                        nickname=ctx.TRADE_NAMES.get(i, ''), loan=i in loans))

    # ---- trainers
    tds, parties = G.load_trainers(ctx)
    loc = ctx.trainer_loc
    story = {t: G.story_group(t, td['cls'], ctx.TRN.get(t, '')) for t, td in enumerate(tds)}
    trainers = []
    for tid in range(1, len(tds)):
        mons = parties[tid]
        if not mons:
            continue
        td = tds[tid]
        places = []
        for zid, how, conds in loc.get(tid, []):
            a = zone_area.get(zid) if zid is not None else None
            places.append(dict(area=a['slug'] if a else None, map=ctx.zname(zid) if zid is not None else None,
                               how=how, conds=list(conds)))
        uniq = list({json.dumps(p, sort_keys=True): p for p in places}.values())
        team = []
        for m in mons:
            idx = species_index(ctx, m['species'], m['form'])
            team.append(dict(id=idx, name=ctx.sp(m['species'], m['form']), level=m['level'],
                             ability=ctx.ab(m['ability']) if m['ability'] else None, abilityId=m['ability'] or None,
                             itemId=m['item'] or None, moveIds=list(m['moves']),
                             item=ctx.it(m['item']) if m['item'] else None,
                             nature=R.NATURES[m['nature']] if m['nature'] is not None and m['nature'] < 25 else None,
                             ivs=m['ivs'], hpIvs=m['hp_ivs'], evs=m['evs'] if any(m['evs']) else None,
                             moves=[ctx.mv(x) for x in m['moves']]))
        cls_name = ctx.TRC.get(td['cls'], '').strip()
        tr = dict(id=tid, cls=cls_name, name=ctx.TRN.get(tid, '').strip() or ('' if cls_name else 'Unnamed trainer'),
                  double=bool(td['double']), items=[ctx.it(i) for i in td['items']], team=team, places=uniq,
                  group=story.get(tid), note=G.TRAINER_NOTES.get(tid))
        trainers.append(tr)
        for a_slug in dict.fromkeys(p['area'] for p in uniq if p['area']):
            next(a for a in areas.values() if a['slug'] == a_slug)['trainers'].append(tid)

    # ---- items
    fi = ctx._field
    price = lambda i: ctx.items[i]['price'] if i < len(ctx.items) else 0
    item_src = collections.defaultdict(list)
    fpos = getattr(ctx, 'field_pos', {})
    for zid, v in fi.items():
        a = zone_area.get(zid)
        for kind, key in (('item ball', 'ball'), ('hidden', 'hidden')):
            ps = fpos.get(zid, {}).get(key, [])
            for k, (it, q) in enumerate(v[key]):
                near = landmark(ctx, zid, *ps[k]) if k < len(ps) else None
                item_src[it].append(dict(kind=kind, area=a['slug'] if a else None, place=ctx.zname(zid), qty=q, near=near))
                if a:
                    a['items'].append(dict(id=it, name=ctx.it(it), qty=q, kind=kind, map=ctx.zname(zid), near=near))
    for g in ctx._gifts:
        aa = file_areas(ctx, zone_area, g['file'])
        # a menu, draw or vending-machine choice is a prize, never a plain purchase
        kind = 'prize' if g.get('choice') else 'bought/exchanged' if g['pay'] else 'gift'
        pay = G.gift_pay_text(g) if g.get('choice') else ', '.join(g['pay'])
        qs = quests_for(gq, g['file'], re.sub(r'^(TM|HM)\d+ ', '', ctx.it(g['item'])))
        item_src[g['item']].append(dict(kind=kind, area=aa[0]['slug'] if aa else None, **player_place(ctx.place_str(g['file'])),
                                        qty=g['qty'], pay=pay, quests=qs))
        if aa:
            aa[0]['gifts'].append(dict(id=g['item'], name=ctx.it(g['item']), qty=g['qty'], pay=pay, kind=kind, quests=qs))
    sm = ctx._sm
    shop_files = collections.defaultdict(list)
    for f, kind, mid in ctx._marts:
        if kind == 'special' and mid < len(sm):
            shop_files[mid].append(f)
    for mid, fs in shop_files.items():
        stock = [dict(id=it, name=ctx.it(it), price=price(it)) for it in sm[mid]]
        rooms = collections.OrderedDict()            # area -> rooms whose clerk opens this list
        for f in fs:
            for zid in sorted(set(ctx.file_zones.get(f, [])), key=ctx.zrank):
                a = zone_area.get(zid)
                if a:
                    rooms.setdefault(a['slug'], (a, []))[1].append(ctx.zname(zid))
        for a, rs in rooms.values():
            rs = list(dict.fromkeys(rs))
            a['shops'].append(dict(list=mid, room=', '.join(rs), stock=stock))
            for it in sm[mid]:
                item_src[it].append(dict(kind='shop', area=a['slug'], place=', '.join(rs), price=price(it)))
    for a in areas.values():                         # "counter 1/2" where one room has several shop lists
        per_room = collections.Counter(sh['room'] for sh in a['shops'])
        seen = collections.Counter()
        for sh in sorted(a['shops'], key=lambda sh: sh['list']):
            if per_room[sh['room']] > 1:
                seen[sh['room']] += 1
                sh['room'] = '%s, counter %d' % (sh['room'], seen[sh['room']])
    need = ctx.item_need
    wild_held = wild_held_sources(ctx, areas, set(sp_ids), itertools.chain(
        calendar_wild_rows(ctx, zone_area), safari_wild_rows(ctx, zone_area)))
    items = []
    for i in range(1, len(ctx.items)):
        name = ctx.it(i)
        if name.startswith('item #') or name in ('???', '—', ''):
            continue
        srcs = list({json.dumps(s, sort_keys=True): s for s in item_src.get(i, [])}.values())
        srcs += ITEMS_EXTRA.get(i, {}).get('sources', [])
        d = ctx.items[i]
        needed = {}
        for f in need.get(i, ()):
            for zid in ctx.file_zones.get(f, []):
                a = zone_area.get(zid)
                needed.setdefault(ctx.zname(zid), a['slug'] if a else None)
        items.append(dict(id=i, name=name, slug=slugs.make('item', name, i),
                          pocket=R.POCKETS[d['pocket']] if d['pocket'] < 8 else '?', price=d['price'],
                          sources=srcs if i not in ITEMS_NOT_IN_GAME else [], wildHeld=wild_held.get(i, []), game=game_alias(ctx, ctx.IT.get(i)),
                          unavailableReason=ITEMS_NOT_IN_GAME.get(i, {}).get('reason'),
                          neededBy=[dict(place=k, area=needed[k]) for k in sorted(needed)],
                          note=ITEMS_EXTRA.get(i, {}).get('note')))

    # ---- tutors and trades (global)
    tut = []
    for t in tutors:
        if t.get('kind', 'tutor') != 'tutor' or not t.get('move'):
            continue
        places = []
        for zid in sorted(set(ctx.file_zones.get(t.get('file'), [])), key=ctx.zrank):
            a = zone_area.get(zid)
            places.append(dict(place=ctx.zname(zid), area=a['slug'] if a else None))
        tut.append(dict(move=t['move'], moveName=ctx.mv(t['move']), game=game_alias(ctx, ctx.MV.get(t['move'])),
                        places=list({json.dumps(x, sort_keys=True): x for x in places}.values()),
                        cost=t.get('cost'), species='all' if t['species'] is None else (
                            'restricted' if t['species'] == 'restricted' else sorted(set(t['species']))),
                        quests=quests_for(gq, t.get('file'), ctx.mv(t['move'])), note=TUTOR_NOTES.get((t['move'], t.get('file')))))

    # species "found in" summary for the Pokémon pages
    for s in species:
        seen = collections.OrderedDict()             # area -> method -> weekdays (empty: any day)
        for slug, method, *day in found_in.get(s['id'], []):
            if day:                                  # a weekday table: one method per map, listing its days
                method = '%s: %s' % (day[0], method)
            days = seen.setdefault(slug, collections.OrderedDict()).setdefault(method, [])
            if day and day[1] + 's' not in days:
                days.append(day[1] + 's')
        s['foundIn'] = [dict(area=k, methods=[m + (' (%s)' % ('every day' if len(ds) == 7 else ', '.join(ds)) if ds else '')
                                              for m, ds in v.items()]) for k, v in seen.items()]
        s['quests'] = static_q.get(s['id'], [])

    area_list = list(areas.values())
    for a in area_list:
        for k in ('items', 'gifts', 'statics', 'trades'):
            a[k] = list({json.dumps(x, sort_keys=True): x for x in a[k]}.values())
    meta = dict(game='Origin HeartGold (起源心金) v4.0.3', generator='work/tools/site/export_data.py',
                encExplainer=G.ENC_EXPLAINER, rateNames=G.RATE_NAMES,
                counts=dict(species=len(species), moves=len(moves), items=len(items), areas=len(area_list),
                            trainers=len(trainers)))
    return BR.enrich(ctx, dict(species=species, moves=moves, items=items, areas=area_list, trainers=trainers, tutors=tut, meta=meta,
                trainer_guide=G.trainer_page_sections(ctx, tds, parties, loc)), R, slugs)


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), sort_keys=False) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=OUT)
    ap.add_argument('--check', action='store_true')
    a = ap.parse_args(argv)
    data = export(G.Ctx(R.Rom()))
    changed = []
    for k, v in data.items():
        path = os.path.join(a.out, k + '.json')
        text = dump(v)
        old = open(path, encoding='utf-8').read() if os.path.exists(path) else None
        if old != text:
            changed.append(path)
            if not a.check:
                os.makedirs(a.out, exist_ok=True)
                with open(path + '.tmp', 'w', encoding='utf-8') as fh:
                    fh.write(text)
                os.replace(path + '.tmp', path)
    for p in changed:
        print(('would change: ' if a.check else 'wrote: ') + os.path.relpath(p, R.REPO))
    print('%d data files, %d changed' % (len(data), len(changed)))
    return 1 if (a.check and changed) else 0


if __name__ == '__main__':
    sys.exit(main())
