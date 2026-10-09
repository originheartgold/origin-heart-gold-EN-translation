"""Conservative source comparators. Agreement means configured data, never a play test."""
import re
import unicodedata


def key(value):
    # Gender signs distinguish the two Nidoran species; apostrophe variants do not.
    value = str(value).replace('♀', 'female').replace('♂', 'male')
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value).lower())


def species_match(name, lookup):
    """Canonical names win over truncated game aliases shared by all forms."""
    raw = str(name)
    raw=re.sub(r'^(.+) \(Hisuian\)$',r'Hisuian \1',raw)
    regional = re.match(r'^(.*?) (Alolan|Galarian|Hisui|Hisuian)$', raw)
    if regional:
        raw = ('Hisuian' if regional[2] == 'Hisui' else regional[2]) + ' ' + regional[1]
    aliases = {'Rotom Heat': 'Heat Rotom', 'Rotom Wash': 'Wash Rotom', 'Rotom Frost': 'Frost Rotom',
        'Rotom Fan': 'Fan Rotom', 'Rotom Mow': 'Mow Rotom', 'Wormadam Plant Cloak': 'Wormadam',
        'Cherrim Overcast': 'Cherrim', 'Cherrim Sunshine': 'Cherrim (Sunshine Form)',
        'Meloetta Aria Forme': 'Meloetta', 'Aegislash Shield Forme': 'Aegislash',
        'Hoopa Confined': 'Hoopa', 'Basculin Red': 'Basculin', 'Basculegion Male': 'Basculegion'}
    raw = aliases.get(raw, raw)
    rows = {r['id']: r for r in lookup.get(key(raw), [])}
    canonical = [r for r in rows.values() if key(r['name']) == key(raw)]
    if len(canonical) == 1:
        return canonical[0]
    bases = [r for r in rows.values() if r.get('formId', 0) == 0]
    if len(bases) == 1:
        return bases[0]
    return next(iter(rows.values())) if len(rows) == 1 else None


def evolution_compare(note, target, item_lookup, move_lookup):
    """Compare the constraints actually supplied, preserving outgoing/incoming ambiguity.

    A bare item names an evolution requirement without specifying use vs hold.
    Compound alternatives must EACH have a matching edge. Dates and breeding
    claims are kept separate; numeric levels are not treated as item IDs.
    """
    edges = [(direction, e) for direction in ('evoTo', 'evoFrom') for e in target[direction]]
    checks = []
    for part in str(note).split(' / '):
        text = key(part)
        candidates = edges
        required = []
        numbers = re.findall(r'\d+', part)
        if text.isdigit():
            required.append(('level', int(part)))
        else:
            level = re.match(r'^(\d+)\s*/?', part)
            if level:
                required.append(('level', int(level[1])))
            if 'friendship' in text:
                required.append(('friendship', None))
                if numbers:
                    required.append(('friendship-threshold', int(numbers[-1])))
            for kval in ('night', 'day'):
                if kval in text:
                    required.append(('time', kval))
            if 'female' in text:
                required.append(('gender', 'female'))
            elif 'male' in text:
                required.append(('gender', 'male'))
            # Every linked requirement must match; do not accept an item merely
            # because the Pokémon can hold it outside an evolution.
            names = sorted(item_lookup, key=len, reverse=True)
            found_item = next((k for k in names if len(k) > 3 and k in text), None)
            if found_item:
                ids = {r['id'] for r in item_lookup[found_item]}
                if len(ids) == 1:
                    required.append(('item', ids.pop()))
                    # Preserve explicit operations; a bare item stays ambiguous.
                    if re.search(r'\blevel[ -]?up\b.*\bhold(?:ing)?\b', part, re.I):
                        required.append(('operation', 'level-up-holding'))
                    elif re.search(r'\bhold(?:ing)?\b', part, re.I):
                        required.append(('operation', 'holding'))
                    elif re.search(r'\bus(?:e|ing)\b', part, re.I):
                        required.append(('operation', 'use'))
            names = sorted(move_lookup, key=len, reverse=True)
            found_move = next((k for k in names if len(k) > 4 and k in text), None)
            if found_move and not found_item:
                ids = {r['id'] for r in move_lookup[found_move]}
                if len(ids) == 1:
                    required.append(('move', ids.pop()))
            if 'attackequalsdefense' in text:
                required.append(('equal-stats', None))
            if 'fairytypemove' in text:
                required.append(('fairy-move', None))
            if 'breed' in text or 'holdcharizardite' in text or re.match(r'^\d+\.\d+', part):
                return dict(equal=None, claim=note, reason='breeding, transformation or calendar claim; separate from evolution table')
            if ('dusk' in text and 'duskstone' not in text) or '5–8' in part:
                return dict(equal=None, claim=note, reason='time window is not equivalent to the generated evolution conditions')
        if not required:
            return dict(equal=None, claim=note, reason='no conservative constraint parser for this source wording')
        def fits(edge):
            conds = edge.get('conds', [])
            words = ' '.join(c['text'] for c in conds).lower()
            for typ, value in required:
                if typ == 'level' and not any(c['text'] == 'at Lv %d' % value for c in conds): return False
                if typ in ('item', 'move') and not any(c.get(typ) == value for c in conds): return False
                if typ == 'operation':
                    item_conds = [c['text'].lower() for c in conds if c.get('item') is not None]
                    if value == 'use' and not any(t.startswith('using ') for t in item_conds): return False
                    if value in ('holding', 'level-up-holding') and not any(t.startswith('holding ') for t in item_conds): return False
                    if value == 'level-up-holding' and not edge['how'].lower().startswith('level up holding '): return False
                if typ == 'friendship' and 'friendship' not in words: return False
                if typ == 'friendship-threshold' and not re.search(r'friendship[^\d]*%d\b' % value, words): return False
                if typ == 'time' and (('at night' if value == 'night' else 'during the day') not in words): return False
                if typ == 'gender' and value + ' only' not in words: return False
                if typ == 'equal-stats' and 'attack equal to defense' not in words: return False
                if typ == 'fairy-move' and 'fairy-type move' not in words: return False
            return True
        matches = [(d, e) for d, e in candidates if fits(e)]
        checks.append(dict(claim=part, constraints=required, matchingEdges=[dict(direction=d,id=e['id'],how=e['how']) for d,e in matches]))
    return dict(equal=all(c['matchingEdges'] for c in checks), claim=note, alternatives=checks,
        configured=[dict(direction=d,id=e['id'],how=e['how']) for d,e in edges],
        evidence=dict(kind='rom-data',source='a/0/3/4#%d; generated evoTo/evoFrom conditions'%target['id']))


def place_matches(text, rows, areas):
    """Match explicit place names only; room detail remains an author claim."""
    aliases = {'Resort Area': 'Resort Zone', 'Nature Park': 'National Park', 'Ghost Tower': 'Pokémon Tower',
        'Dragon’s Den Cave': "Dragon's Den", 'Cycling Route': 'Cycling Road'}
    for before, after in aliases.items(): text = str(text).replace(before,after)
    k = key(text)
    area_names = {key(a['name']):a['slug'] for a in areas}
    candidates = [slug for name,slug in area_names.items() if len(name)>4 and name in k]
    # Longest explicit route number must win: Route 2 is not Route 25.
    route = re.search(r'route\s*(\d+)', str(text), re.I)
    if route:
        candidates = [a['slug'] for a in areas if a['name'] == 'Route '+route[1]]
    return sorted({r.get('area') for r in rows if r.get('area') and (r.get('area') in candidates or
        (len(key(r.get('place',''))) > 4 and (key(r.get('place','')) in k or k in key(r.get('place','')))))})


def cost_compare(note, costs):
    if note is None: return None
    n = key(note)
    if n in ('none','free'): return any(c == [] for c in costs)
    for c in costs:
        if c is None: continue
        raw = ', '.join(c) if isinstance(c,list) else str(c)
        if key(raw) == n: return True
        if isinstance(c,list) and len(c)==1:
            value = re.sub(r'\s*[×x]\s*1$', '', raw)
            if key(value)==n: return True
            quantity = re.match(r'^(\d+) (.+)$', str(note))
            if quantity and key(quantity[2]+' ×'+quantity[1])==key(raw): return True
        money = re.search(r'(\d+)\s*(?:Pokédollars|[₽$])', str(note), re.I)
        if not money: money = re.search(r'[₽$]\s*(\d+)', str(note))
        if money and re.search(r'\b%s\b'%money[1], raw): return True
    return None


def table_field(table, field):
    if field == 'radio': return table['hoenn']+table['sinnoh']
    if field.startswith('special.'):
        name={'special.swarm':'land','special.water':'surf','special.fishing_night':'night_fish','special.fishing':'fish'}[field]
        return [table['swarm'][name]]
    return table.get(field, [])


def summary_compare(values, table, lookup):
    """Compare every supplied species per method, preserving distinct forms."""
    fields=['morning','day','night','radio','surf','rock','old','good','super']
    checks={}
    def parse_species(name):
        name=name.strip()
        form=re.search(r'\s*\(Form (\d+)\)$',name,re.I)
        if form: name=name[:form.start()]
        hisui=re.match(r'^(.+) \(Hisuian\)$',name)
        if hisui: name='Hisuian '+hisui[1]
        found=species_match(name,lookup)
        return (found['baseSpeciesId'] | ((int(form[1]) if form else found['formId'])<<11)) if found else None
    for field, note in zip(fields,values):
        supplied={parse_species(name) for name in str(note).split(',')} if note else set()
        slots=table_field(table,field)
        rate=table['rates'].get('walk' if field in ('morning','day','night','radio') else field,0)
        configured={slot[0] if isinstance(slot,(list,tuple)) else slot for slot in slots} if rate else set()
        checks[field]=dict(equal=supplied==configured,claimed=sorted(x for x in supplied if x is not None),
            configured=sorted(configured),unknownNames=None in supplied)
    special=values[9] if len(values)>9 else None
    if special:
        for clause in str(special).split(';'):
            label,name=clause.split(':',1)
            field={'Mass Outbreak':'special.swarm','Special Water':'special.water','Night Fishing':'special.fishing_night','Special Fishing':'special.fishing'}[label.strip()]
            supplied=parse_species(name)
            checks[field]=dict(equal=supplied==table_field(table,field)[0],claimed=supplied,configured=table_field(table,field)[0])
    else:
        checks['special']=dict(equal=not any(table['swarm'].values()),configured=table['swarm'])
    return checks
