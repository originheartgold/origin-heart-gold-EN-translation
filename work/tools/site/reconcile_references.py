"""Reconcile supplied local author workbooks without copying raw attachments.

Run with the bundled Python (openpyxl), from repo root:
  python work/tools/site/reconcile_references.py --source-dir /path/to/local/workbooks
Inputs are never downloaded. Output facts are notes, not tested gameplay. Every
nonempty data/note row has a coverage entry. Headers and blank rows are excluded.
Machine comparisons never imply that a person reviewed all acquisition/effect text.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import sys
import openpyxl
from reference_compare import key, species_match, evolution_compare, place_matches, cost_compare, summary_compare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'docs'))
import romdata as R

FILES = {'pokemon': 'Pokemon Origin HeartGold v4.0.3 EN List of Pokemon.xlsx',
         'encounters': 'Pokemon Origin HeartGold v4.0.3 EN Encounters.xlsx',
         'items': 'Pokemon Origin HeartGold v4.0.3 EN Items.xlsx'}
# Workbook aliases only. Site display names continue to come from project banks.
ABILITY_ALIASES = {'Blazing Fear': 311, 'Blazing Fire': 313, 'Desert Eagle': 326,
    'Dragon Skin': 324, 'Fiery Mane': 322, 'Focus': 316, 'Light Screen': 314,
    'Mega Tough Claws': 312, 'Moonlight Guardian': 327, 'Super Solar': 321, 'Thunderclap': 315, 'Water Skin': 318}
MOVE_ALIASES = {'Fate Claw': 827, 'Ancient Power': 246, 'Extreme Speed': 245,
                'Grass Whistle': 320}
AUDITS = ['work/notes/spreadsheet_crossref.md', 'work/notes/sheet_mismatch_verification.md',
          'work/notes/move_data_audit.md']


def index(rows):
    out = collections.defaultdict(list)
    for row in rows:
        out[key(row['name'])].append(row)
        if row.get('game'):
            out[key(row['game'])].append(row)
    return out


def match(value, lookup):
    rows = {r['id']: r for r in lookup.get(key(value), [])}
    return next(iter(rows.values())) if len(rows) == 1 else None


def red(cell):
    color = cell.font.color
    if not color or color.type != 'rgb':
        return False
    rgb = color.rgb[-6:]
    return int(rgb[:2], 16) > 180 and int(rgb[2:4], 16) < 80 and int(rgb[4:], 16) < 80


def highlights(cells, headers):
    result = []
    for c, label in zip(cells, headers):
        # Store the semantic field plus exact visual cue; no changed-before claim.
        fill = c.fill
        if red(c) or (fill.patternType == 'solid' and fill.fgColor.type == 'rgb' and
                      fill.fgColor.rgb[-6:] not in ('FFFFFF', '000000')):
            result.append(str(label or c.column_letter))
    return result


def source(book, sheet, row, columns=None):
    return dict(kind='author-note', workbook=book, sheet=sheet, row=row,
                **({'columns': columns} if columns else {}))


def build(directory, data_dir):
    data = {name: json.loads((data_dir / (name+'.json')).read_text())
            for name in ('species', 'moves', 'items', 'abilities', 'tms', 'areas', 'tutors')}
    lookups = {k: index(data[k]) for k in ('species', 'moves', 'items', 'abilities')}
    byid = {k: {r['id']: r for r in data[k]} for k in ('species', 'moves', 'items', 'abilities')}
    tm_labels = {r['label']: r for r in data['tms']}
    zone_area = {z: a for a in data['areas'] for z in a['zones']}
    editorial = json.loads((HERE/'reference_content.json').read_text())
    item_editorial = {x['itemId']: x for x in editorial['itemNotes']}
    tutor_editorial = {x['sourceRow']: x for x in editorial['tutorNotes']}
    mechanics=(ROOT/'site/src/lib/verified-mechanics.ts').read_text()
    calendar=[]
    for line in mechanics.splitlines():
        m=re.search(r'month: (\d+), day: (\d+).*?zone: (\d+), area: [\"\']([^\"\']+).*?pokemon: (\d+)',line)
        if m: calendar.append(dict(month=int(m[1]),day=int(m[2]),zone=int(m[3]),area=m[4],pokemon=int(m[5])))
    transformations=[dict(base=int(m[1]),result=int(m[2]),item=int(m[3])) for m in re.finditer(r'base: (\d+), result: (\d+), item: (\d+)',mechanics)]
    rom = R.Rom()
    enc = [R.parse_encounter(b) for b in rom['encounter']]
    zones = json.loads((ROOT/'work/translate/bank_maps.json').read_text())['_zones']
    facts = dict(schemaVersion=1, evidencePolicy='Author notes, game text and ROM data are separate; none means tested gameplay.',
                 moveChanges=[], abilityChanges=[], applicability=[], newTms=[], itemEffects=[], tutorNotes=[],
                 itemReference=[], pokemonNotes=[], encounterNotes=[], mapNotes=[], unmappedEncounterTables=[], itemLegend=editorial['legend'], tradeGoodsNote=editorial['tradeGoodsNote'])
    coverage, sources = [], []
    for book, filename in FILES.items():
        path = directory / filename
        sources.append(dict(id=book, filename=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        wb = openpyxl.load_workbook(path, data_only=True)
        for sheet in wb:
            header_row = 2 if book == 'encounters' else 1
            headers = [sheet.cell(header_row, col).value for col in range(1, min(sheet.max_column, 26)+1)]
            rows = []
            for cells in sheet.iter_rows(min_row=header_row+1, max_col=min(sheet.max_column, 26)):
                values = [c.value for c in cells]
                if not any(v is not None and v != '' for v in values):
                    continue
                row = cells[0].row
                rec = dict(source=book, sheet=sheet.title, row=row, status='unresolved', refs=[],
                           comparison='not-compared', unresolvedFields=[])
                provenance = source(book, sheet.title, row)
                if book == 'pokemon' and sheet.title == '4.0 Pokémon Data':
                    target = species_match(values[1], lookups['species'])
                    # Row 822 duplicates Greninja's name for its Ash form. Exact
                    # stats and three Ninja Bond slots identify this one row.
                    if row == 822 and values[1] == 'Greninja' and list(values[7:13]) == byid['species'][1194]['stats']:
                        target = byid['species'][1194]
                        rec['identityEvidence'] = 'Ash-Greninja #1194: exact six stats and three Ninja Bond #323 slots'
                    if target:
                        rec['refs'] = ['species:%d' % target['id']]
                        checks = dict(stats=list(values[7:13]) == target['stats'],
                            types=[x for x in values[5:7] if x] == target['types'])
                        names = [x for x in values[2:4] if x]
                        ability_ids = []
                        for name in names:
                            found = match(name, lookups['abilities'])
                            ability_ids.append(found['id'] if found else ABILITY_ALIASES.get(name))
                        checks['abilities'] = list(dict.fromkeys(ability_ids)) == target['abilityIds']
                        hidden = match(values[4], lookups['abilities']) if values[4] else None
                        checks['hidden'] = (hidden['id'] if hidden else ABILITY_ALIASES.get(values[4])) == target['hiddenAbilityId']
                        rec['comparison'] = checks
                        rec['unresolvedFields'] = [field for field, equal in checks.items() if not equal]
                        if values[14] is not None:
                            evo = evolution_compare(values[14], target, lookups['items'], lookups['moves'])
                            if str(values[14]).startswith('Hold '):
                                held=match(str(values[14])[5:],lookups['items'])
                                native=[t for t in transformations if target['id'] in (t['base'],t['result'])]
                                if held and native:
                                    evo=dict(equal=any(t['item']==held['id'] for t in native),claim=values[14],matchingTransformation=native,
                                        evidence=dict(kind='rom-data',source='site/src/lib/verified-mechanics.ts; existing chinese_source_rom_verify_mechanics audit'))
                            date=re.match(r'^(\d+)\.(\d+)\s',str(values[14]))
                            if date:
                                matches=[c for c in calendar if c['pokemon']==target['id'] and (c['month'],c['day'])==(int(date[1]),int(date[2]))]
                                source_place=str(values[14])[date.end():].replace('Fuchsia Forest', 'Fuchsia City').replace('Nature Park','National Park').replace('Mt. Silver Entrance','Mt. Silver')
                                matches=[c for c in matches if place_matches(source_place,[dict(area=c['area'])],data['areas'])]
                                evo=dict(equal=bool(matches),claim=values[14],matchingCalendar=matches,
                                    evidence=dict(kind='rom-data',source='site/src/lib/verified-mechanics.ts; existing chinese_source_rom_verify_calendar audit'))
                            checks['evolution'] = evo
                            if evo['equal'] is not True: rec['unresolvedFields'].append('evolution')
                        if rec['unresolvedFields']:
                            facts['pokemonNotes'].append(dict(speciesId=target['id'], sourceAlias=values[1],
                                note='The author row differs from, or cannot be fully compared with, configured data: '+', '.join(rec['unresolvedFields'])+'.',
                                fields=dict(stats=list(values[7:13]), types=[x for x in values[5:7] if x],
                                    abilities=names, hidden=values[4], evolution=values[14]),
                                comparison=checks, evidence=provenance))
                        rec['status'] = 'included' if not rec['unresolvedFields'] else 'unresolved'
                    else:
                        rec['unresolvedFields'] = ['species-identity', 'stats', 'abilities', 'evolution']
                elif book == 'pokemon' and sheet.title in ('4.0 Move Changes', '4.0 New TMs'):
                    is_tm = sheet.title == '4.0 New TMs'
                    if not isinstance(values[0], int):
                        locator_text=re.sub(r'Floors? \d+[–-]\d+', '', str(values[0]))
                        numbers = [int(n) for n in re.findall(r'\b\d+\b',locator_text)]
                        linked = sorted({zone_area[n]['slug'] for n in numbers if n in zone_area})
                        rec['refs'] = ['area:'+a for a in linked]
                        rec['comparison'] = dict(mapIds=numbers, areas=linked, evidence='bank_maps.json _zones → generated area.zones')
                        expected_label=re.split(r'\d|Department Store',str(values[0]))[0].strip()
                        label_match=all(key(expected_label) in key(zone_area[n]['name']) for n in numbers if n in zone_area) or expected_label=='Battle Frontier'
                        rec['comparison']['locationLabelMatch']=label_match
                        rec['status'] = 'included' if linked and all(n in zone_area for n in numbers) and label_match else 'unresolved'
                        rec['unresolvedFields'] = [] if rec['status']=='included' else ['source-location-label-conflict']
                        facts['mapNotes'].append(dict(note=values[0], areaSlugs=linked, locationLabelMatch=label_match, evidence=provenance))
                    else:
                        move_id = values[0]
                        target = byid['moves'].get(move_id)
                        off = 1 if is_tm else 0
                        claim = dict(moveId=move_id, changeKind='new-TM' if is_tm else 'changed', before=None,
                            fields=dict(type=values[2+off], category=values[3+off], power=values[4+off],
                                        accuracy=values[5+off], pp=values[6+off], target=values[8+off]),
                            effectNote=values[7+off], highlightedFields=highlights(cells, headers), evidence=provenance)
                        if target:
                            checks = dict(type=claim['fields']['type']==target['type'],
                                category=claim['fields']['category']==target['cat'],
                                power=str(claim['fields']['power'])==str(target['power']),
                                accuracy=str(claim['fields']['accuracy'])==str(target['acc']),
                                pp=str(claim['fields']['pp'])==str(target['pp']))
                            rec['comparison'] = checks
                            rec['refs'] = ['move:%d' % move_id]
                            # Variable/status/never-miss notation is equivalent only
                            # to the explicit configured sentinel, never guessed.
                            if claim['fields']['power'] in ('Varies', '—', None): checks['power'] = target['power'] in ('var', 'var.', None, '—')
                            if claim['fields']['accuracy'] in ('—', None): checks['accuracy'] = target['acc'] in ('never', None, '—')
                            wanted = {'Single Target':0, 'Both Opponents':5, 'Both Foes':5, 'Double Target':5, 'Self':7}.get(claim['fields']['target'])
                            checks['target'] = wanted == target['targetId'] if wanted is not None else None
                            rec['unresolvedFields'] = [k for k,v in checks.items() if v is not True]+['effect-runtime']
                            claim['configuredFields']=dict(type=target['type'],category=target['cat'],power=target['power'],accuracy=target['acc'],pp=target['pp'],target=target['target'] or 'Target meaning not decoded')
                            claim['comparison'] = checks
                            rec['status']='included' if all(v is True for v in checks.values()) else 'unresolved'
                        if is_tm:
                            tm = tm_labels.get(values[1])
                            if tm:
                                claim.update(itemId=tm['itemId'], label=tm['label'], locationNote=values[10])
                                rec['refs'].append('item:%d' % tm['itemId'])
                                rec['comparison']['tmMapping'] = tm['moveId']==move_id
                            else: rec['unresolvedFields'].append('TM-identity')
                            if tm:
                                shops = [x for x in byid['items'][tm['itemId']]['sources'] if x['kind']=='shop']
                                areas = place_matches(values[10] or '', shops, data['areas'])
                                claim['acquisitionComparison'] = dict(status='configured-shop-match' if areas else 'unmatched', areas=areas,
                                    configuredShops=[dict(area=x.get('area'),place=x['place']) for x in shops],
                                    evidence=dict(kind='rom-data',source='reachable SpecialMartBuy sources; sheet_mismatch_verification.md sections 5–6'))
                                rec['comparison']['acquisition'] = bool(areas)
                                if not areas: rec['unresolvedFields'].append('acquisition')
                            else: rec['unresolvedFields'].append('acquisition')
                            if not rec['comparison'].get('acquisition'): rec['status']='unresolved'
                            facts['newTms'].append(claim)
                        else: facts['moveChanges'].append(claim)
                elif book == 'pokemon' and sheet.title == '4.0 Ability Changes':
                    found = match(values[0], lookups['abilities'])
                    ident = found['id'] if found else ABILITY_ALIASES.get(values[0])
                    text = (values[1] or '').replace('Water Ring','Aqua Ring')
                    kind = 'added' if text.startswith('Added:') else 'changed' if text.startswith('Changed:') else 'custom'
                    facts['abilityChanges'].append(dict(abilityId=ident, sourceAlias=values[0],
                        changeKind=kind, baseline='Gen 8 (workbook comparison)', before=None,
                        effectNote=re.sub(r'^(Added|Changed):\s*','',text), highlightedFields=highlights(cells, headers), evidence=provenance))
                    rec.update(status='included' if ident else 'unresolved',
                               refs=['ability:%d'%ident] if ident else [],
                               unresolvedFields=['battle-behavior'] + ([] if ident else ['ability-identity']))
                elif book == 'pokemon' and sheet.title == 'Ability Applicability':
                    for col, name, ability in [(1,'Mega Launcher',178),(2,'Sharpness',292)]:
                        if not values[col]: continue
                        found = match(values[col], lookups['moves'])
                        ident = found['id'] if found else MOVE_ALIASES.get(values[col])
                        flag = bool(ident and 'slicing' in byid['moves'][ident]['flags']) if ability==292 else None
                        claim = dict(abilityId=ability, moveId=ident, sourceAlias=values[col],
                            addedInHack=red(cells[col]), evidence=source(book,sheet.title,row,cells[col].column_letter),
                            comparison='slicing-flag-present' if flag else 'unverified', verifiedGameplay=False)
                        facts['applicability'].append(claim)
                        rec['refs'] += ['ability:%d'%ability]+(['move:%d'%ident] if ident else [])
                    rec.update(status='included', comparison='author-list; Sharpness flag compared; Mega Launcher unverified',
                               unresolvedFields=['battle-behavior'])
                elif book == 'items':
                    itemmatch = re.match(r'0_(\d+):',str(values[0]))
                    if itemmatch:
                        ident = int(itemmatch[1]); target = byid['items'].get(ident)
                        rec['refs'] = ['item:%d'%ident] if target else []
                        content = item_editorial.get(ident)
                        rec['comparison'] = dict(identity='item-slot-linked' if target else 'no-exported-item',
                            fieldInventory=[str(headers[i]) for i,v in enumerate(values) if v is not None],
                            palette='editorial palette metadata; not an item acquisition/effect claim' if values[2] else None)
                        if target and content:
                            note = dict(content)
                            note['evidence'] = provenance
                            note['editorialEvidence'] = editorial['source']
                            clauses = [c.strip() for c in (note.get('acquisitionNote') or '').split(';') if c.strip()]
                            compared = []
                            for clause in clauses:
                                areas = place_matches(clause, target['sources'], data['areas'])
                                regular = 'regular shops' in clause.lower() and any(s['kind']=='shop' and 'Poké Mart' in s['place'] for s in target['sources'])
                                compared.append(dict(claim=clause, status='configured-source-in-area' if areas or regular else 'author-only', areas=areas))
                            note['acquisitionComparison'] = compared
                            rec['comparison']['acquisitionClauses'] = compared
                            rec['comparison']['includedClaims'] = [k for k in ('changeNote','rarity','effectNote','acquisitionNote','useNote') if note.get(k)]
                            rec['comparison']['normalization'] = 'Existing translated Chinese survey; source priority is newer acquisition/use cell, falling back to older cells. Claims remain author notes.'
                            facts['itemReference'].append(note)
                            if note.get('effectNote') or note.get('changeNote'):
                                facts['itemEffects'].append(dict(itemId=ident,effectNote=note.get('effectNote'),changeNote=note.get('changeNote'),before=None,evidence=provenance))
                            rec['unresolvedFields'] = (['effect-runtime'] if note.get('effectNote') else [])
                            if note.get('rarity'): rec['unresolvedFields'].append('repeatability-author-claim')
                            if any(c['status']=='author-only' for c in compared): rec['unresolvedFields'].append('acquisition-author-claim')
                            rec['comparison']['legacyOriginalGameColumn']='included as a separate original-game source claim; not current hack availability' if values[5] else 'empty'
                            rec['comparison']['legacyRoleColumn']='normalized legacy use note included' if values[8] else 'empty'
                            rec['status']='included'
                        elif target:
                            rec['status']='included'
                            rec['comparison']['includedClaims']=['identity; no normalized gameplay note in the prior survey']
                            rec['unresolvedFields']=['legacy-source-fields'] if any(values[i] and str(values[i])!='None' for i in (1,4,5,6,7,8,9,10,11)) else []
                        elif ident == 0:
                            rec.update(status='included',refs=['page:reference-sources'],comparison='legend and trade-goods note retained; slot zero is not a usable item',unresolvedFields=[])
                        elif ident < len(rom['item']):
                            rec.update(status='included',disposition='reserved-unnamed-slot',comparison=dict(itemSlot=ident,evidence='a/0/1/7#%d; unnamed project name slot'%ident,reason='Unnamed reserved item slot; no gameplay notes in the source survey.'),unresolvedFields=[])
                        else: rec['unresolvedFields']=['item-identity']
                    elif row in tutor_editorial:
                        original = tutor_editorial[row]
                        found = match(values[0],lookups['moves'])
                        ident = found['id'] if found else MOVE_ALIASES.get(values[0])
                        old = match(original['sourceName'],lookups['moves'])
                        configured_id = old['id'] if old else MOVE_ALIASES.get(original['sourceName'])
                        # Prior verified v4 bug: the claimed Play Rough tutor actually teaches Flail.
                        if row == 585: configured_id = 175
                        candidates = [t for t in data['tutors'] if t['move']==configured_id]
                        areas = place_matches(original['locationNote'] or '',[p for t in candidates for p in t['places']],data['areas'])
                        costs = cost_compare(values[11],[t['cost'] for t in candidates])
                        claim = dict(moveId=ident, configuredMoveId=configured_id, sourceAlias=values[0],
                            locationNote=original['locationNote'],costNote=original['costNote'],note=original['note'],
                            evidence=provenance, comparison=dict(locationAreas=areas,cost=costs,identityMatches=ident==configured_id),
                            priorAuditNote=original['priorAuditNote'])
                        if str(row) in editorial['englishTutorCostConflicts']:
                            claim['sourceConflictNote']=editorial['englishTutorCostConflicts'][str(row)]
                        facts['tutorNotes'].append(claim)
                        rec['refs']=['move:%d'%i for i in dict.fromkeys([ident,configured_id]) if i]
                        rec['comparison']=claim['comparison']
                        rec['comparison']['evidence']='configured tutor script tables; prior translated Chinese survey; sheet_mismatch_verification.md section 4.7'
                        rec['status']='included' if candidates else 'unresolved'
                        rec['unresolvedFields']=([] if areas else ['location'])+([] if costs is True else ['cost-or-access-condition'])+(['source-move-identity-conflict'] if ident!=configured_id else [])
                    else:
                        rec['status']='included'
                        rec['refs']=['page:reference-sources']
                        rec['comparison']='Standalone source note retained separately from usable item records'
                        rec['unresolvedFields']=['legacy-source-claim']
                        # Two distinct source notes above the tutor list, not missing item records.
                        facts['mapNotes'].append(dict(note='The author lists an older Azure Flute slot 678.' if row==539 else 'The author reports a Radio Card gift from a Vermilion City resident.',evidence=provenance))
                elif book == 'encounters':
                    mapmatch = re.match(r'(\d+):',str(values[0]))
                    mapname=re.sub(r'^Water Route ', 'Route ',str(values[0]))
                    mapname={'Seafoam Islands Cave':'Seafoam Islands','Seafoam Islands Forest':'Seafoam Islands'}.get(mapname,mapname)
                    area = zone_area.get(int(mapmatch[1])) if mapmatch else next((a for a in data['areas'] if key(a['name']) == key(mapname)), None)
                    if area: rec['refs']=['area:'+area['slug']]
                    if sheet.title == 'Encounter Details' and mapmatch:
                        zid=int(mapmatch[1]); zone=zones[zid] if zid<len(zones) else None
                        bank=zone['wild_encounter_bank'] if zone else 255
                        found=species_match(values[4],lookups['species'])
                        expected=None
                        field_alias = {'ground.morning':'morning', 'ground.day':'day', 'ground.night':'night',
                            'old_rod':'old', 'good_rod':'good', 'super_rod':'super', 'rock_smash':'rock'}
                        field = field_alias.get(values[6], values[6])
                        if bank<len(enc) and isinstance(values[3],int):
                            table=enc[bank]
                            if field=='ground.radio':slots=table['hoenn']+table['sinnoh']
                            elif isinstance(field,str) and field.startswith('special.'):
                                swarm_field={'special.swarm':'land','special.water':'surf',
                                    'special.fishing_night':'night_fish','special.fishing':'fish'}[field]
                                slots=[table['swarm'][swarm_field]]
                            else:slots=table.get(field,[])
                            if isinstance(slots,list) and values[3]<len(slots):
                                expected=slots[values[3]]
                                if isinstance(expected,tuple):expected=expected[0]
                        actual=found['baseSpeciesId'] | (int(values[5] or 0)<<11) if found else None
                        equal=expected is not None and actual==expected
                        rec.update(status='included' if equal else 'unresolved', comparison='ROM-slot-match' if equal else 'ROM-slot-unmatched',
                                   unresolvedFields=[] if equal else ['slot-species-form'])
                        if found:rec['refs'].append('species:%d'%found['id'])
                        if not equal:
                            sp,fm=R.split_species(expected) if expected is not None else (None,None)
                            configured=next((s for s in data['species'] if s['baseSpeciesId']==sp and s['formId']==fm),None)
                            if configured:rec['refs'].append('species:%d'%configured['id'])
                            rec['comparison']=dict(status='source-identity-conflict' if configured and found else 'unmatched',
                                claimedSpecies=values[4],claimedForm=values[5] or 0,configuredId=configured['id'] if configured else None,
                                configuredSpecies=configured['name'] if configured else None,configuredForm=fm,
                                evidence='a/0/3/7#%d %s slot %s'%(bank,field,values[3]))
                            facts['encounterNotes'].append(dict(areaSlug=area['slug'] if area else None,
                                note='Author lists %s (form %s); configured %s slot %s contains %s.'%(values[4],values[5] or 0,field,values[3],configured['name'] if configured else 'an unidentified entry'),
                                speciesId=configured['id'] if configured else None,evidence=provenance))
                    elif sheet.title in ('Map Overview','Encounter Index') and area:
                        fields=values[1:11] if sheet.title=='Map Overview' else values[4:14]
                        zids=[int(mapmatch[1])] if mapmatch else area['zones']
                        candidates=[]
                        for zid in zids:
                            bank=zones[zid]['wild_encounter_bank']
                            if bank<len(enc):
                                checks=summary_compare(fields,enc[bank],lookups['species'])
                                candidates.append((sum(v['equal'] for v in checks.values()),bank,checks))
                        if candidates:
                            _,bank,checks=max(candidates,key=lambda c:c[0])
                            rec['comparison']=dict(encounterBank=bank,candidateBanks=[dict(bank=b,matchingFields=score) for score,b,_ in candidates],fields=checks,evidence='bank_maps.json wild_encounter_bank → a/0/3/7 method sets')
                            if sheet.title=='Encounter Index':
                                configured=set()
                                for field,check in checks.items():
                                    val=check['configured']
                                    if isinstance(val,list):configured.update(val)
                                    elif isinstance(val,int):configured.add(val)
                                configured.discard(0)
                                checks['speciesCount']=dict(equal=values[2]==len(configured),claimed=values[2],configured=len(configured))
                            rec['unresolvedFields']=[f for f,v in checks.items() if not v['equal']]
                            rec['status']='included' if not rec['unresolvedFields'] else 'unresolved'
                            if sheet.title=='Map Overview' and values[11]:
                                rec['comparison']['sharedIndexNote']=dict(claim=values[11],evidence='Map header encounter-bank sharing; label retained as author note')
                                facts['encounterNotes'].append(dict(areaSlug=area['slug'],note=values[11],evidence=provenance))
                        else: rec['unresolvedFields']=['no-configured-encounter-bank']
                    else:
                        rec['comparison']='Source omits a direct map reference; no location is guessed.' if not values[0] else 'Source map label has no mapped location in the current catalog.'
                        rec['unresolvedFields']=['missing-map-reference'] if not values[0] else ['unmapped-source-location-label']
                        if sheet.title=='Encounter Details':
                            tables=facts['unmappedEncounterTables']
                            if not tables or (values[6]=='ground.morning' and values[3]==0):
                                tables.append(dict(key='unmapped-%d'%(len(tables)+1),rows=[],evidence=provenance,note='The source provides no map reference, rates or levels. This table is not assigned to an in-game location.'))
                            found=species_match(values[4],lookups['species'])
                            tables[-1]['rows'].append(dict(row=row,method=values[6],slot=values[3],speciesId=found['id'] if found else None,sourceName=values[4],form=values[5] or 0))
                            if found:rec['refs'].append('species:%d'%found['id'])
                rows.append(rec)
            coverage.extend(rows)
    duplicates = [dict(filename=name, status='duplicate', comparison='supplied-task-context; workbook text preferred', source='pokemon', sheet=sheet)
        for name, sheet in [('Move Changes 1','4.0 Move Changes'),('Move Changes 2','4.0 Move Changes'),
            ('New TMs 1','4.0 New TMs'),('New TMs 2','4.0 New TMs'),
            ('Ability Changes 1','4.0 Ability Changes'),('Ability Changes 2','4.0 Ability Changes'),
            ('Ability Changes 3','4.0 Ability Changes'),('inclusions to Mega Launcher and Sharpness','Ability Applicability')]]
    facts['legacyItemSources']=editorial['legacySourceNotes']
    facts['legacyItemUses']=editorial['legacyRoleNotes']
    facts['coverageSummary']=dict(reservedUnnamedItemRows=sum(r.get('disposition')=='reserved-unnamed-slot' for r in coverage), sources=sources, audits=AUDITS, duplicateAttachments=duplicates, methodology='Field-level deterministic comparisons plus existing translated source survey. Included is source-accounted, not tested or a blanket human-review verdict. Unresolved fields remain explicit.',
        sheets=[dict(source=book,sheet=sheet,rows=len(group),statuses=dict(collections.Counter(r['status'] for r in group)))
                for (book,sheet),group in itertools_group(coverage)])
    return facts, dict(schemaVersion=1, sources=sources, audits=AUDITS, duplicateAttachments=duplicates, rows=coverage)


def itertools_group(rows):
    groups=collections.OrderedDict()
    for r in rows:groups.setdefault((r['source'],r['sheet']),[]).append(r)
    return groups.items()


def write(path, value, check):
    text=json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n'
    changed=not path.exists() or path.read_text()!=text
    if changed and not check:
        temp=path.with_suffix('.tmp');temp.write_text(text);temp.replace(path)
    return changed


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-dir',type=Path,required=True)
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    facts,coverage=build(args.source_dir,ROOT/'site/src/data')
    changed=write(HERE/'reference_facts.json',facts,args.check)
    changed=write(HERE/'reference_coverage.json',coverage,args.check) or changed
    print('%d source rows; %s'%(len(coverage['rows']), 'would change' if args.check and changed else 'changed' if changed else 'unchanged'))
    return int(args.check and changed)

if __name__=='__main__':
    raise SystemExit(main())
