// Compile the shared core first so the browser and Python worker use the same JS.
// Uses installed development dependencies only; never downloads or installs tools.
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const check = process.argv.slice(2);
if (check.length > 1 || (check.length === 1 && check[0] !== '--check')) {
  throw Error('Usage: node work/save-editor/scripts/build.mjs [--check]');
}
const compiler = fileURLToPath(new URL('../node_modules/typescript/bin/tsc', import.meta.url));
if (!existsSync(compiler)) {
  throw Error('TypeScript is not installed in work/save-editor/node_modules. Install the pinned development dependencies before building. No automatic installation was attempted.');
}
for (const args of [
  [fileURLToPath(new URL('../../save-core/scripts/build.mjs', import.meta.url))],
  [compiler, '-p', fileURLToPath(new URL('../tsconfig.json', import.meta.url)), ...(check.length === 1 ? ['--noEmit'] : [])],
]) {
  const result = spawnSync(process.execPath, args, { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}
