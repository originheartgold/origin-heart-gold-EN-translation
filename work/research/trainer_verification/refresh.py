"""Refresh the complete corrected trainer research bundle from local ROMs.

Run from the repository root with .venv/bin/python. Does not build or modify a
ROM. Every data/disassembly output stays under ignored work/build/.
"""
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import export_index as E
import reachability
import validate_index


def main():
    if Path.cwd().resolve() != ROOT:
        raise SystemExit('Run this command from the repository root.')
    out = ROOT / 'work/build/difficulty-trainers-v3'
    out.mkdir(parents=True, exist_ok=True)
    ctx = E.G.Ctx(E.R.Rom(cache=str(out / 'docs_cache.pkl'), refresh=True))
    data = E.export(ctx)
    supplement = reachability.build(ctx)
    data['reachability'] = supplement
    data['phone_rematches'] = supplement['phone_rematches']
    linkage = {(e['script'], e['pc']): e for e in supplement['encounters']}
    assert len(linkage) == len(data['encounters'])
    for encounter in data['encounters']:
        encounter['entry_linkage'] = linkage[encounter['script'], encounter['pc']]
    data['summary']['entry_linkage_summary'] = supplement['summary']
    data['summary']['provenance']['reachability_sha256'] = E.sha((HERE / 'reachability.py').read_bytes())
    for name, value in data.items():
        E.write_json(out / (name + '.json'), value)

    # The facility inventory is a separate namespace, with its own CN/US provenance.
    completed = subprocess.run([sys.executable, str(HERE / 'export_facilities.py')],
                               check=True, capture_output=True, text=True)
    (out / 'facilities-validation.log').write_text(completed.stdout)
    import facilities_verify
    runtime = facilities_verify.verify()
    assert runtime['source_rom_sha256'] == data['summary']['provenance']['rom_sha256']
    E.write_json(out / 'facilities_runtime.json', runtime)

    validation = validate_index.check(out, Path('/private/tmp/poke-difficulty-research/work/build/difficulty-trainers-v2'))
    E.write_json(out / 'validation.json', validation)
    files = sorted(out.glob('*.json'))
    manifest = dict(schema_version=3, source_rom_sha256=data['summary']['provenance']['rom_sha256'],
                    scripts={p.name: E.sha(p.read_bytes()) for p in sorted(HERE.glob('*.py'))},
                    artifacts={p.name: E.sha(p.read_bytes()) for p in files if p.name != 'manifest.json'},
                    limits=['entry linkage is not full world-state reachability',
                            'facility runtime supplement covers reviewed paths, not every facility mode'])
    E.write_json(out / 'manifest.json', manifest)
    print(json.dumps(dict(output=str(out), roster=data['summary']['summary'],
                          linkage=supplement['summary'], validation=validation['status']), indent=2))


if __name__ == '__main__':
    main()
