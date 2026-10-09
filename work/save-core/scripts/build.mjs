// Always compile with installed, pinned dependencies and seal the complete build.
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { CORE_ROOT, buildInputs, writeBuildIdentity } from './build-identity.mjs';

const compiler = resolve(CORE_ROOT, '../save-editor/node_modules/typescript/bin/tsc');
if (!existsSync(compiler)) throw Error('TypeScript is not installed in work/save-editor/node_modules. Install pinned dependencies explicitly; no automatic installation was attempted.');
const installed = JSON.parse(readFileSync(resolve(CORE_ROOT, '../save-editor/node_modules/typescript/package.json'), 'utf8')).version;
const pinned = JSON.parse(readFileSync(resolve(CORE_ROOT, '../save-editor/package-lock.json'), 'utf8')).packages['node_modules/typescript'].version;
if (installed !== pinned) throw Error(`TypeScript ${installed} differs from pinned ${pinned}; install pinned dependencies explicitly.`);
// dist is wholly generated; removing it also prevents removed sources surviving a build.
const inputFiles = buildInputs();
rmSync(resolve(CORE_ROOT, 'dist'), { recursive: true, force: true });
const result = spawnSync(process.execPath, [compiler, '-p', resolve(CORE_ROOT, 'tsconfig.json')], { stdio: 'inherit' });
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status ?? 1);
writeBuildIdentity(CORE_ROOT, inputFiles);
