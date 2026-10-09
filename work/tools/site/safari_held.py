"""Read Safari species candidates, retaining conditional object slots.

CN v4.0.3 a/2/3/0 is byte-identical to the user's USA ROM archive.
All twelve records are 912 bytes. The five header counts describe additional
slots for grass, Surf, and the three rods. Each method has three time tables
of ten ordinary slots, three tables of additional slots, then four bytes of
object requirements per additional slot. No encounter probability is inferred:
the selected area, placed objects, and their development affect the final table.

Area numbering: pret/pokeheartgold include/constants/safari.h.
https://raw.githubusercontent.com/pret/pokeheartgold/master/include/constants/safari.h
"""
import struct

AREA_NAMES = ('Plains', 'Meadow', 'Savannah', 'Peak', 'Rocky Beach', 'Wetland',
              'Forest', 'Swamp', 'Marshland', 'Wasteland', 'Mountain', 'Desert')
METHODS = ('Grass', 'Surfing', 'Old Rod', 'Good Rod', 'Super Rod')
TIMES = ('morning', 'day', 'night')
# Object categories in the native requirement reader (ARM9 02096B12–02096B38).
# Bank 0422 #10–13 describes these as Plains, Forest, Rocks and Water.
BLOCK_CATEGORIES = {1: 'Plains', 2: 'Forest', 3: 'Peak', 4: 'Waterside'}


def parse_safari_area(data, area):
    """Yield candidate rows, with effective block-point requirements on object slots.

    Points are not object counts: the native scorer increases each object's
    contribution as its area matures (02096BDC / 02096B98).
    """
    if len(data) < 8 or not 0 <= area < len(AREA_NAMES):
        raise ValueError('Invalid Safari area header')
    expected = 8 + sum(120 + 16 * count for count in data[:5])
    if len(data) != expected:
        raise ValueError('Safari area length disagrees with slot counts')
    offset = 8
    for method, count in zip(METHODS, data[:5]):
        requirements_offset = offset + 120 + 12 * count
        requirements = []
        for slot in range(count):
            req = []
            raw = data[requirements_offset + slot * 4:requirements_offset + slot * 4 + 4]
            for category, points in zip(raw[::2], raw[1::2]):
                if category == 0:
                    if points:
                        raise ValueError('Safari points without a block category')
                    continue
                if category not in BLOCK_CATEGORIES or not points:
                    raise ValueError('Invalid Safari object requirement')
                req.append(dict(category=BLOCK_CATEGORIES[category], points=points))
            requirements.append(req)
        for conditional, slots in ((False, 10), (True, count)):
            for time in TIMES:
                for slot in range(slots):
                    species, level = struct.unpack_from('<HH', data, offset)
                    offset += 4
                    if not 1 <= species <= 1025 or not 1 <= level <= 100:
                        raise ValueError('Invalid Safari species or level')
                    row = dict(species=species, level=level, area=AREA_NAMES[area],
                               method=method, time=time, conditional=conditional)
                    if conditional:
                        row['requirements'] = requirements[slot]
                    yield row
        offset += count * 4


def safari_rows(rom_path):
    """Read fresh ROM bytes; this archive is not part of the docs cache."""
    import ndspy.narc
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
    records = ndspy.narc.NARC(rom.getFileByName('a/2/3/0')).files
    if len(records) != len(AREA_NAMES):
        raise ValueError('Unexpected number of Safari areas')
    return [row for area, data in enumerate(records)
            for row in parse_safari_area(data, area)]
