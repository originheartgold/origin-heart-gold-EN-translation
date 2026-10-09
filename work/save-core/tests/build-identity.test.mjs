import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { CORE_ROOT, buildInputs, verifyBuildIdentity, writeBuildIdentity } from '../scripts/build-identity.mjs';

function copiedBuild(fn) {
  const temporary = mkdtempSync(join(tmpdir(), 'save-core-identity-'));
  const root = join(temporary, 'save-core');
  try {
    mkdirSync(root);
    for (const path of ['src', 'cli', 'scripts', 'dist', 'package.json', 'tsconfig.json']) cpSync(join(CORE_ROOT, path), join(root, path), { recursive: true });
    mkdirSync(join(temporary, 'save-editor'));
    cpSync(join(CORE_ROOT, '../save-editor/package-lock.json'), join(temporary, 'save-editor/package-lock.json'));
    return fn(root);
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
}

test('build identity is deterministic across checkout paths and includes every emitted module', () => copiedBuild(root => {
  const actual = verifyBuildIdentity(root);
  assert.deepEqual(actual, verifyBuildIdentity());
  assert.deepEqual(writeBuildIdentity(root).buildId, actual.buildId);
  const manifest = JSON.parse(readFileSync(join(root, 'dist/build-identity.json')));
  for (const path of ['dist/fixture.js', 'dist/pokemon.js', 'dist/save.js']) assert.match(manifest.outputs[path], /^[0-9a-f]{64}$/);
}));

for (const [name, change] of [
  ['edited source', root => writeFileSync(join(root, 'src/save.ts'), '// stale')],
  ['new source', root => writeFileSync(join(root, 'src/new.ts'), 'export const added = 1;')],
  ['deleted source', root => rmSync(join(root, 'src/save.ts'))],
  ['worker change', root => writeFileSync(join(root, 'cli/worker.mjs'), '// stale')],
  ['configuration change', root => writeFileSync(join(root, 'tsconfig.json'), '{}')],
  ['compiler lock change', root => writeFileSync(join(root, '../save-editor/package-lock.json'), '{}')],
  ['changed compiled bytes', root => writeFileSync(join(root, 'dist/save.js'), 'throw Error("must never execute");')],
  ['missing compiled module', root => rmSync(join(root, 'dist/save.js'))],
  ['extra compiled module', root => writeFileSync(join(root, 'dist/obsolete.js'), '// stale')],
  ['missing manifest', root => rmSync(join(root, 'dist/build-identity.json'))],
  ['invalid manifest', root => writeFileSync(join(root, 'dist/build-identity.json'), '{')],
  ['forged fingerprint', root => {
    const path = join(root, 'dist/build-identity.json'), data = JSON.parse(readFileSync(path));
    data.buildId = '0'.repeat(64); writeFileSync(path, JSON.stringify(data));
  }],
  ['wrong protocol', root => {
    const path = join(root, 'dist/build-identity.json'), data = JSON.parse(readFileSync(path));
    data.protocol++; writeFileSync(path, JSON.stringify(data));
  }],
  ['source symlink', root => symlinkSync(join(root, 'src/save.ts'), join(root, 'src/link.ts'))],
]) {
  test(`build identity rejects ${name}`, () => copiedBuild(root => {
    change(root);
    assert.throws(() => verifyBuildIdentity(root), /stale or incomplete.*Run npm run build/);
  }));
}

test('build cannot seal output compiled while its input sources changed', () => copiedBuild(root => {
  const before = buildInputs(root);
  writeFileSync(join(root, 'src/added.ts'), 'export const newSource = true;');
  assert.throws(() => writeBuildIdentity(root, before), /sources changed during compilation/);
  assert.throws(() => verifyBuildIdentity(root), /stale or incomplete/);
}));

test('worker verifies stale compiled modules before importing them or handling requests', () => copiedBuild(root => {
  writeFileSync(join(root, 'dist/pokemon.js'), 'process.stdout.write("UNSAFE_IMPORT\\n"); throw Error("UNSAFE_IMPORT");');
  const result = spawnSync(process.execPath, [join(root, 'cli/worker.mjs')], {
    input: JSON.stringify({ version: 1, id: 1, op: 'handshake' }) + '\n', encoding: 'utf8', timeout: 5000,
  });
  assert.notEqual(result.status, 0);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, /stale or incomplete/);
  assert.doesNotMatch(result.stderr, /UNSAFE_IMPORT/);
}));

test('worker handshake returns sealed build identity and rejects unexpected payloads', () => {
  const packets = [{}, { bytes: 'AA==' }, { args: { unexpected: true } }].map((extra, id) => ({ version: 1, id, op: 'handshake', ...extra }));
  const result = spawnSync(process.execPath, [join(CORE_ROOT, 'cli/worker.mjs')], {
    input: packets.map(packet => JSON.stringify(packet)).join('\n') + '\n', encoding: 'utf8', timeout: 5000,
  });
  assert.equal(result.status, 0, result.stderr);
  const responses = result.stdout.trim().split('\n').map(line => JSON.parse(line));
  assert.deepEqual(responses[0].result, verifyBuildIdentity());
  assert.ok(responses.slice(1).every(response => response.error.code === 'invalid-input'));
});

for (const reseal of [false, true]) test(`worker rejects output changes during imports, resealed=${reseal}`, () => copiedBuild(root => {
  const modulePath = join(root, 'dist/pokemon.js');
  // A copied compiled module simulates a concurrent build at the exact import
  // boundary, avoiding timing-dependent sleeps or production test hooks.
  const sideEffect = String.raw`
const raceFs = await import('node:fs');
const raceTarget = new URL('./stats.js', import.meta.url);
raceFs.writeFileSync(raceTarget, raceFs.readFileSync(raceTarget, 'utf8') + '\n// concurrent build\n');
${reseal ? "(await import('../scripts/build-identity.mjs')).writeBuildIdentity();" : ''}
`;
  writeFileSync(modulePath, readFileSync(modulePath, 'utf8') + sideEffect);
  const initial = writeBuildIdentity(root);
  const result = spawnSync(process.execPath, [join(root, 'cli/worker.mjs')], {
    input: JSON.stringify({ version: 1, id: 1, op: 'handshake' }) + '\n', encoding: 'utf8', timeout: 5000,
  });
  assert.notEqual(result.status, 0, result.stderr);
  assert.equal(result.stdout, '');
  assert.match(result.stderr, reseal ? /changed while loading/ : /stale or incomplete/);
  if (reseal) assert.notEqual(verifyBuildIdentity(root).buildId, initial.buildId);
}));
