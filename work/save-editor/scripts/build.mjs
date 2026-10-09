// Compile the shared core first so the browser and Python worker use the same JS.
// Uses installed development dependencies only; never downloads or installs tools.
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

const check = process.argv.slice(2);
if (check.length > 1 || (check.length === 1 && check[0] !== '--check')) {
  throw Error('Usage: node work/save-editor/scripts/build.mjs [--check]');
}
const compiler = fileURLToPath(new URL('../node_modules/typescript/bin/tsc', import.meta.url));
if (!existsSync(compiler)) {
  throw Error('TypeScript is not installed in work/save-editor/node_modules. Install the pinned development dependencies before building. No automatic installation was attempted.');
}
function run(args) {
  const result = spawnSync(process.execPath, args, { stdio: 'inherit' });
  if (result.error) throw result.error;
  if (result.status !== 0) throw Error(`TypeScript command failed (exit ${result.status ?? 1}).`);
}
if (check.length === 1) {
  // Check the actual sources, never stale generated declarations. Browser imports
  // deliberately name dist, so a private source-only tree maps that runtime path
  // to the current core sources. No live build is removed, written, or needed.
  run([compiler, '-p', fileURLToPath(new URL('../../save-core/tsconfig.json', import.meta.url)), '--noEmit']);
  const temporary = mkdtempSync(join(tmpdir(), 'origin-save-typecheck-'));
  try {
    for (const [source, destination] of [
      ['../src', 'save-editor/src'], ['../package.json', 'save-editor/package.json'],
      ['../../save-core/src', 'save-core/dist'], ['../../save-core/package.json', 'save-core/package.json'],
    ]) cpSync(fileURLToPath(new URL(source, import.meta.url)), join(temporary, destination), {recursive: true});
    const config = JSON.parse(readFileSync(new URL('../tsconfig.json', import.meta.url), 'utf8'));
    config.compilerOptions.rootDir = '..';
    config.compilerOptions.noEmit = true;
    const path = join(temporary, 'save-editor/tsconfig.json');
    writeFileSync(path, JSON.stringify(config));
    run([compiler, '-p', path, '--noEmit']);
  } finally {
    rmSync(temporary, {recursive: true, force: true});
  }
} else {
  run([fileURLToPath(new URL('../../save-core/scripts/build.mjs', import.meta.url))]);
  run([compiler, '-p', fileURLToPath(new URL('../tsconfig.json', import.meta.url))]);
}
