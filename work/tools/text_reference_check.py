"""Prove text reference inventories were preserved; do not assume dynamic targets resolve."""
import importlib.util
from pathlib import Path

import msgtool as m


def compare_references(source_scripts, candidate_scripts, source_map, candidate_map,
                       source_std, candidate_std, source_counts, candidate_counts):
    errors, gaps, baseline = [], [], []
    if source_scripts != candidate_scripts:
        errors.append({'code': 'script_archive_changed'})
    for label, before, after in (('map', source_map, candidate_map), ('standard', source_std, candidate_std)):
        if before != after:
            errors.append({'code': 'message_bank_mapping_changed', 'mapping': label})
        for index, (script, bank) in enumerate(before):
            if not 0 <= bank < len(source_counts) or not 0 <= script < len(source_scripts):
                baseline.append({'code': 'source_mapping_out_of_range', 'mapping': label,
                                 'index': index, 'script': script, 'bank': bank})
    if source_counts != candidate_counts:
        errors.append({'code': 'message_id_inventory_changed'})
    if not source_scripts or not source_counts or not source_map or not source_std:
        gaps.append({'code': 'empty_reference_inventory'})
    gaps.append({'code': 'dynamic_targets_unresolved', 'reason':
        'Exact script bytes and ordered message inventories preserve existing references; dynamic targets, menu branch counts and original invalid references are not proven safe.'})
    return {'status': 'failed' if errors else 'incomplete', 'errors': errors, 'gaps': gaps,
            'preservation_status': 'failed' if errors else ('passed' if source_scripts and source_counts and source_map and source_std else 'incomplete'),
            'baseline_findings': baseline, 'counts': {'scripts': len(source_scripts),
                'map_mappings': len(source_map), 'standard_mappings': len(source_std)}}


def inspect_references(source, candidate, source_counts, candidate_counts):
    path = Path(__file__).resolve().parents[1] / 'translate/scripts/build_bank_maps.py'
    spec = importlib.util.spec_from_file_location('text_reference_bank_maps', path)
    maps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(maps)
    def inspect(rom):
        arm = maps.load_arm9(rom)
        offset = maps.find_map_headers(arm)
        zone = [maps.unpack_header(arm, offset + 24*i) for i in range(maps.N_ZONES)]
        _, std = maps.find_script_bank_mapping(arm)
        scripts = m.Narc.parse(m.get_file(rom, 'a/0/1/2')).files
        return scripts, [(z['scripts_bank'], z['msg_bank']) for z in zone], [(s,b) for _,s,b in std]
    a, b = inspect(source), inspect(candidate)
    return compare_references(a[0], b[0], a[1], b[1], a[2], b[2], source_counts, candidate_counts)
