"""Bounded reference models of reviewed CN constructor and sampler decisions.

These do not simulate RNG, map dispatch, team completion or all facility modes.
Selection functions return (accept, updated_conflict_counter).
"""
from facilities_verify import evs  # noqa: F401  (re-exported to facilities_test.py)

def unpack_form(stored_word):
    return stored_word & 31

def packed_ivs(supplied_value):
    return sum((supplied_value & 31) << (5*i) for i in range(6))

def standard_trainer_iv(trainer_id):
    if trainer_id < 100: return 3
    if trainer_id < 220: return 6 + 3*((trainer_id-100)//20)
    return 31

def materialized_level(level):
    return {120:50,121:100}.get(level,level)

def legacy_candidate(species,item,selected,excluded_species=(),excluded_items=(),conflicts=0):
    """ARM9 0204AFCC / ov77 02232414. External lists are caller-bounded."""
    if species in [s for s,i in selected] or species in excluded_species:
        return False,conflicts
    if conflicts < 50:
        if item != 0 and (item in [i for s,i in selected] or item in excluded_items):
            return False,conflicts+1
    return True,conflicts

def shared_candidate(species,item,selected,excluded_pairs=(),conflicts=0):
    """ov77 02226634: internal conflicts stay strict, zero items included."""
    if any(species==s or item==i for s,i in selected):
        return False,conflicts
    if conflicts < 50 and any(species==s or item==i for s,i in excluded_pairs):
        return False,conflicts+1
    return True,conflicts


def factory_rental_candidate(species,item,selected,excluded_pairs=()):
    """ov77 02232C04: strict internal and external duplicate rejection."""
    return not any(species==s or item==i for s,i in (*selected,*excluded_pairs))
