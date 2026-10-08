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


def parse_safari_area(data, area):
    """Yield {species, level, area, method, time, conditional} candidate rows."""
    if len(data) < 8 or not 0 <= area < len(AREA_NAMES):
        raise ValueError('Invalid Safari area header')
    expected = 8 + sum(120 + 16 * count for count in data[:5])
    if len(data) != expected:
        raise ValueError('Safari area length disagrees with slot counts')
    offset = 8
    for method, count in zip(METHODS, data[:5]):
        for conditional, slots in ((False, 10), (True, count)):
            for time in TIMES:
                for _ in range(slots):
                    species, level = struct.unpack_from('<HH', data, offset)
                    offset += 4
                    if not 1 <= species <= 1025 or not 1 <= level <= 100:
                        raise ValueError('Invalid Safari species or level')
                    yield dict(species=species, level=level, area=AREA_NAMES[area],
                               method=method, time=time, conditional=conditional)
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
