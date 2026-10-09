#!/usr/bin/env python3
"""Compare shared-core selection with completed native loader probe observations."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'work/tools'))
import save_core
from native_loader_probe import CASES, fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path, nargs='+')
    args = parser.parse_args()
    summary = []
    for path in args.report:
        report = json.loads(path.read_text())
        assert report['inputs_unchanged']
        source = Path(report['inputs'][1]['path']).read_bytes()
        assert hashlib.sha256(source).hexdigest() == report['inputs'][1]['sha256']
        assert len(report['rows']) == len(CASES)
        for row in report['rows']:
            name = row['case']
            counters, storage_counters, corrupt = CASES[name]
            data = fixture(source, counters, storage_counters, corrupt, identical=name == 'equal_identical')
            assert hashlib.sha256(data).hexdigest() == row['fixture_sha256']
            try:
                selected = save_core.request('inspectSave', data)['base'] // 0x40000
            except save_core.CoreError as error:
                assert error.code == 'invalid-save'
                selected = None
            assert selected == row['selected_mirror'], (name, selected, row['selected_mirror'])
        summary.append({'rom_sha256':report['inputs'][0]['sha256'],'cases':len(report['rows']),'status':'passed'})
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
