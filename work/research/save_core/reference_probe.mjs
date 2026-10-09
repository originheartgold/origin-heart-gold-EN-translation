// Read-only reference comparison. Prints identities/counts; never game text or assets.
import { readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { loadOriginData } from '../../save-editor/dist/core/rom.js';
import { loadBundledOriginData } from '../../save-editor/dist/core/bundled-data.js';
import { bundledReference } from '../../save-editor/dist/core/generated-reference.js';

if (process.argv.length !== 3) throw Error('Usage: node work/research/save_core/reference_probe.mjs LOCAL_EN_ROM');
const rom = Uint8Array.from(await readFile(process.argv[2]));
const native = await loadOriginData(rom);
const bundled = loadBundledOriginData();
const different = (a, b) => JSON.stringify(a) !== JSON.stringify(b);
const changedIds = (a, b) => a.filter((x, i) => different(x, b[i])).map(x => x.id);
const report = {
  localRomSha256: createHash('sha256').update(rom).digest('hex'),
  bundledRomSha256: bundledReference.provenance.romSha256,
  moveIdsDifferent: changedIds(bundled.catalog.moves, native.catalog.moves),
  speciesIdsDifferent: changedIds(bundled.catalog.species, native.catalog.species),
  itemIdsDifferent: changedIds(bundled.inventory.items, native.inventory.items),
  itemPocketDifferences: bundled.inventory.items.filter((item, i) => item.pocket !== native.inventory.items[i]?.pocket).length,
  readiness: { bundled: bundled.catalog.readiness, local: native.catalog.readiness },
  personalFormPairsCompared: 0,
  personalFormPairsDifferent: 0,
};
for (let species = 1; species <= 1025; species++) {
  for (let form = 0; form <= 255; form++) {
    report.personalFormPairsCompared++;
    if (different(bundled.getPersonal(species, form), native.getPersonal(species, form))) report.personalFormPairsDifferent++;
  }
}
console.log(JSON.stringify(report, null, 2));
