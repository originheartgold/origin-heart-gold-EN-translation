// Build provenance is checked locally; this module never downloads or builds.
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { dirname, resolve, relative, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { PROTOCOL_VERSION } from '../cli/protocol.mjs';

export const CORE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const normalized = path => path.split(sep).join('/');
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
function files(root, directory) {
  return readdirSync(resolve(root, directory), { withFileTypes: true }).flatMap(entry => {
    const path = `${directory}/${entry.name}`;
    if (entry.isSymbolicLink()) throw Error(`Build identity refuses symbolic link: ${path}`);
    return entry.isDirectory() ? files(root, path) : entry.isFile() ? [path] : [];
  });
}
function digestFiles(root, paths) {
  return Object.fromEntries(paths.sort().map(path => [normalized(path), sha(readFileSync(resolve(root, path)))]));
}
export function buildInputs(root = CORE_ROOT) {
  return digestFiles(root, [
    ...files(root, 'src'), ...files(root, 'cli'), ...files(root, 'scripts'),
    'package.json', 'tsconfig.json', '../save-editor/package-lock.json',
  ]);
}
function outputs(root) {
  return digestFiles(root, files(root, 'dist').filter(path => path !== 'dist/build-identity.json' && !path.endsWith('.tmp')));
}
function identity(inputFiles, outputFiles) {
  return sha(JSON.stringify({ schema: 1, protocol: PROTOCOL_VERSION, inputs: inputFiles, outputs: outputFiles }));
}
export function writeBuildIdentity(root = CORE_ROOT, expectedInputs = undefined) {
  const inputFiles = buildInputs(root), outputFiles = outputs(root);
  if (expectedInputs !== undefined && JSON.stringify(expectedInputs) !== JSON.stringify(inputFiles)) {
    throw Error('Shared save core sources changed during compilation; rebuild before running the harness.');
  }
  const result = { schema: 1, protocol: PROTOCOL_VERSION, buildId: identity(inputFiles, outputFiles), inputs: inputFiles, outputs: outputFiles };
  const target = resolve(root, 'dist/build-identity.json');
  writeFileSync(`${target}.tmp`, JSON.stringify(result, null, 2) + '\n');
  renameSync(`${target}.tmp`, target);
  return result;
}
export function verifyBuildIdentity(root = CORE_ROOT) {
  try {
    const result = JSON.parse(readFileSync(resolve(root, 'dist/build-identity.json'), 'utf8'));
    if (!object(result) || result.schema !== 1 || result.protocol !== PROTOCOL_VERSION || !object(result.inputs) || !object(result.outputs)
        || typeof result.buildId !== 'string' || !/^[0-9a-f]{64}$/.test(result.buildId)) throw Error('invalid build manifest');
    const inputFiles = buildInputs(root), outputFiles = outputs(root);
    if (JSON.stringify(result.inputs) !== JSON.stringify(inputFiles)) throw Error('source, configuration, or worker changed');
    if (JSON.stringify(result.outputs) !== JSON.stringify(outputFiles)) throw Error('compiled output changed or is missing');
    if (result.buildId !== identity(inputFiles, outputFiles)) throw Error('invalid build fingerprint');
    return Object.freeze({ schema: result.schema, protocol: result.protocol, buildId: result.buildId });
  } catch (error) {
    const location = normalized(relative(process.cwd(), root));
    throw Error(`Shared save core build is stale or incomplete (${location}: ${error.message}). Run npm run build in work/save-editor; no runtime build is attempted.`);
  }
}
