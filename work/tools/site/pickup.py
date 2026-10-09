"""Pickup table in the untouched CN v4.0.3 ROM (overlay 14).

See work/notes/chinese_source_rom_verify_common.md, COM-05. Weights are
conditional on the separate 10% activation gate, not per-battle chances.
"""
import struct

ITEMS_ADDRESS = 0x0224E3AC
WEIGHTS_ADDRESS = 0x0224E3D8
GATE_ADDRESS = 0x0222BD2A
ITEM_COUNT = 22
BAND_COUNT = 10


def parse_table(data, base):
    """Read the reviewed overlay layout and reject shifted or invalid tables."""
    if data[GATE_ADDRESS - base:GATE_ADDRESS - base + 2] != b'\x0a\x20':
        raise ValueError('Pickup activation gate differs from reviewed 10% code')
    start = WEIGHTS_ADDRESS - base
    weights = data[start:start + ITEM_COUNT * BAND_COUNT]
    if len(weights) != ITEM_COUNT * BAND_COUNT:
        raise ValueError('Truncated Pickup weights')
    ids = struct.unpack_from('<22H', data, ITEMS_ADDRESS - base)
    if 0 in ids or len(set(ids)) != ITEM_COUNT:
        raise ValueError('Invalid Pickup item IDs')
    rows = [dict(item=item, rates=list(weights[i * BAND_COUNT:(i + 1) * BAND_COUNT]))
            for i, item in enumerate(ids)]
    if any(sum(row['rates'][band] for row in rows) != 100 for band in range(BAND_COUNT)):
        raise ValueError('Pickup level-band weights must total 100')
    return dict(activationPercent=10,
                bands=[dict(min=10 * band + 1, max=10 * band + 10) for band in range(BAND_COUNT)],
                items=rows)


def read_table(rom_path):
    """Read fresh bytes; overlay 14 is not in the general documentation cache."""
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)
    overlay = rom.loadArm9Overlays([14])[14]
    return parse_table(overlay.data, overlay.ramAddress)
