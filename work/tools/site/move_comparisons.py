"""Comparable move facts and optional import from the user's untouched US ROM.

Normal site generation reads the normalized JSON only. No ROM or text is bundled.
The 16-byte layout is documented in audit/verify_sheet_rows.py [pret-move].
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

HERE = Path(__file__).resolve().parent
TYPES = ['Normal', 'Fighting', 'Flying', 'Poison', 'Ground', 'Rock', 'Bug',
         'Ghost', 'Steel', '???', 'Fire', 'Water', 'Grass', 'Electric',
         'Psychic', 'Ice', 'Dragon', 'Dark']
CATEGORIES = ['Physical', 'Special', 'Status']
# Gen 4 and the hack use different target enums. Compare meanings, never IDs.
TARGETS = {0: 'Selected target', 4: 'All opponents', 16: 'User'}
FIELDS = [('type', 'Type'), ('category', 'Category'), ('power', 'Power'),
          ('accuracy', 'Accuracy'), ('pp', 'PP'), ('priority', 'Priority'),
          ('target', 'Target')]


def parse_original_move(raw):
    if len(raw) != 16:
        raise ValueError('HeartGold move record must be 16 bytes')
    if raw[2] >= len(CATEGORIES) or raw[4] >= len(TYPES):
        raise ValueError('invalid HeartGold category or type')
    return dict(typeId=raw[4], categoryId=raw[2], power=raw[3], accuracy=raw[5],
                pp=raw[6], secondaryChance=raw[7],
                targetId=struct.unpack_from('<H', raw, 8)[0],
                priority=struct.unpack_from('<b', raw, 10)[0])


def normalize_power(value):
    return '—' if value == 0 else 'var.' if value == 1 else str(value)


def normalize_accuracy(value):
    return '—' if value in (0, 101, '0', '101', '—') else str(value)


def compare_move(move, original, effects=()):
    changes = []
    if original:
        before = dict(type=TYPES[original['typeId']], category=CATEGORIES[original['categoryId']],
                      power=normalize_power(original['power']), accuracy=normalize_accuracy(original['accuracy']),
                      pp=str(original['pp']), priority=str(original['priority']),
                      target=TARGETS.get(original['targetId']))
        after = dict(type=move['type'], category=move['cat'], power=move['power'],
                     accuracy=normalize_accuracy(move['acc']), pp=str(move['pp']),
                     priority=str(move['priority']), target=move['target'])
        for key, label in FIELDS:
            if before[key] is not None and after[key] is not None and before[key] != after[key]:
                changes.append(dict(field=label, before=before[key], after=after[key]))
    return dict(baseline='Pokémon HeartGold' if original else None,
                fields=changes, effects=list(effects))


def load_comparisons():
    baseline = json.loads((HERE / 'move_original_facts.json').read_text(encoding='utf-8'))
    effects = json.loads((HERE / 'move_change_notes.json').read_text(encoding='utf-8'))
    return {r['id']: r for r in baseline['moves']}, {r['moveId']: r['changes'] for r in effects}


def import_original(rom_path, output):
    # Explicit, optional local import. CI and normal exporters never call this.
    import ndspy.narc
    import ndspy.rom
    raw = Path(rom_path).read_bytes()
    if zlib.crc32(raw) != 0xC180A0E9:
        raise ValueError('expected untouched Pokémon HeartGold (USA), CRC32 C180A0E9')
    archive = ndspy.narc.NARC(ndspy.rom.NintendoDSRom(raw).getFileByName('a/0/1/1'))
    if len(archive.files) != 471 or any(len(r) != 16 for r in archive.files):
        raise ValueError('unexpected original move table shape')
    facts = dict(baseline='Pokémon HeartGold', evidence=dict(kind='rom-data',
                 source='Pokémon HeartGold (USA), a/0/1/1', crc32='C180A0E9',
                 sha256=hashlib.sha256(raw).hexdigest(),
                 layout='work/tools/audit/verify_sheet_rows.py [pret-move]'),
                 excludedRecords=dict(ids=[0, 468, 469, 470],
                     reason='Dummy entry and trailing non-move records; original moves are IDs 1–467.'),
                 moves=[dict(id=i, **parse_original_move(archive.files[i])) for i in range(1, 468)])
    dest = Path(output)
    temp = dest.with_suffix('.tmp')
    temp.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(dest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--import-us-rom', required=True, help='explicitly import the existing local US ROM')
    parser.add_argument('--out', default=str(HERE / 'move_original_facts.json'))
    args = parser.parse_args()
    import_original(args.import_us_rom, args.out)


if __name__ == '__main__':
    main()
