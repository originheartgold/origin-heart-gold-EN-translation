"""Reviewed acquisition restrictions, shared by the Pokédex and location exports.

The raw script scan proves a command exists, not that its NPC can appear.
Keep that scan intact for audits and join these reviews before publishing sources.
"""
import json
from pathlib import Path

REVIEWS = Path(__file__).resolve().parents[1] / 'site'


def reviews():
    entries = []
    for name in ('acquisition_kanto', 'acquisition_other'):
        path = REVIEWS / (name + '.json')
        if path.exists():
            entries.extend(json.loads(path.read_text())['entries'])
    return entries


def key(row):
    return row['species'], row.get('form', 0), row['file'], row['kind'], row.get('level')


def scripted_sources(ctx, raw_rows):
    """Join reviews by acquisition identity; never infer access from species alone."""
    by_key = {}
    for review in reviews():
        k = key(review)
        if k in by_key:
            raise ValueError('Duplicate acquisition review: %r' % (k,))
        by_key[k] = review
    seen = set()
    for kind, species, form, level, file in raw_rows:
        row = dict(kind=kind, species=species, form=form, level=level, file=file)
        identity = key(row)
        if identity in seen:
            continue
        seen.add(identity)
        review = by_key.get(key(row))
        if review and review.get('excluded'):
            continue
        row['conditions'] = review.get('conditions', []) if review else [
            'The script contains this encounter, but its access requirements have not been verified.'
        ]
        row['reviewed'] = review is not None
        if review:
            for field in ('place', 'zone', 'quests', 'offsets'):
                if field in review:
                    row[field] = review[field]
        yield row


def fossil_review(species, item):
    path = REVIEWS / 'acquisition_kanto.json'
    rows = json.loads(path.read_text()).get('fossils', []) if path.exists() else []
    return next((row for row in rows if row['species'] == species and row['item'] == item), {})


def trade_review(index, file):
    path = REVIEWS / 'acquisition_trades.json'
    if not path.exists():
        return {}
    matches = [r for r in json.loads(path.read_text())['entries']
               if r['trade'] == index and r.get('file', file) == file]
    if len(matches) > 1:
        raise ValueError('Duplicate trade review: %r' % ((index, file),))
    return matches[0] if matches else {}
