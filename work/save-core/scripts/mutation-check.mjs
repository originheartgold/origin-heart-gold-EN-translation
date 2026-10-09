#!/usr/bin/env node
// Dependency-free, bounded semantic mutation testing. Never changes working
// source or dist. Every mutant builds from one captured source snapshot and
// runs the identical test file; missing anchors and infrastructure failures fail.
import {mkdtemp, cp, readFile, writeFile, mkdir, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {resolve, dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {createHash} from 'node:crypto';

const core = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const compiler = resolve(core, '../save-editor/node_modules/typescript/bin/tsc');
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--report')) throw new Error('Usage: node work/save-core/scripts/mutation-check.mjs [--report PATH]');
const mutations = [
  {id: 'save-crc-bypass', file: 'save.ts', test: 'save block CRC rejection',
    from: 'crc16(bytes.subarray(offset, footer)) !== data.getUint16(footer + 14, true)',
    to: 'crc16(bytes.subarray(offset, footer)) !== data.getUint16(footer + 14, true) && false'},
  {id: 'pokemon-checksum-bypass', file: 'pokemon.ts', test: 'Pokemon checksum rejection',
    from: 'if (!diagnostic && !checksumOk)', to: 'if (!diagnostic && !checksumOk && false)'},
  {id: 'saved-flag-off-by-one', file: 'transaction.ts', test: 'native saved flag upper boundary',
    from: "integer(op.flag,1,SAVED_FLAG_COUNT-1,'Saved flag')", to: "integer(op.flag,1,SAVED_FLAG_COUNT,'Saved flag')"},
  {id: 'inactive-party-off-by-one', file: 'transaction.ts', test: 'shrunken inactive party slot rejection',
    from: "integer(op.slot,0,partyCount-1,'Active party slot');const at=base+PARTY_OFFSET+op.slot*PARTY_STRIDE;",
    to: "integer(op.slot,0,partyCount,'Active party slot');const at=base+PARTY_OFFSET+op.slot*PARTY_STRIDE;"},
  {id: 'mirror-order-reversed', file: 'save.ts', test: 'ordinary native mirror ranking',
    from: 'return a > b;', to: 'return a < b;'},
  {id: 'rollover-unrecognized', file: 'save.ts', test: 'exact native counter rollover',
    from: 'if(a === 0 && b === 0xffffffff) return true;', to: 'if(a === 0 && b === 0xffffffff) return false;'},
  {id: 'transaction-crc-wrong', file: 'transaction.ts', test: 'transaction writes independent CRC',
    from: 'crc16(bytes.subarray(base,base+GENERAL_FOOTER)),true)',
    to: '(crc16(bytes.subarray(base,base+GENERAL_FOOTER)) ^ 1),true)'},
  {id: 'caller-bytes-alias', file: 'save.ts', test: 'caller ownership after transaction',
    from: 'const bytes = Uint8Array.from(input);', to: 'const bytes = input;'},
];
const report = {schemaVersion: 1, node: process.version, baseline: null, mutations: [], passed: false};
const temporary = await mkdtemp(join(tmpdir(), 'save-core-mutation-'));
function command(args, cwd) {
  const result = spawnSync(process.execPath, args, {cwd, encoding: 'utf8', timeout: 30000, maxBuffer: 2 * 1024 * 1024});
  const output = `${result.stdout ?? ''}${result.stderr ?? ''}`;
  if (result.error || result.signal || result.status === null) throw new Error(`Infrastructure failure: ${result.error?.message ?? result.signal}\n${output.slice(-4000)}`);
  return {status: result.status, output};
}
try {
  const baseline = join(temporary, 'baseline');
  await mkdir(join(baseline, 'tests'), {recursive: true});
  await cp(join(core, 'src'), join(baseline, 'src'), {recursive: true});
  await cp(join(core, 'tsconfig.json'), join(baseline, 'tsconfig.json'));
  await writeFile(join(baseline, 'package.json'), '{"type":"module"}\n');
  for (const name of ['fixtures.mjs', 'mutation-contracts.test.mjs']) await cp(join(core, 'tests', name), join(baseline, 'tests', name));
  const build = command([compiler, '-p', 'tsconfig.json'], baseline);
  if (build.status !== 0) throw new Error(`Baseline did not compile:\n${build.output}`);
  const tests = command(['--test', '--test-reporter=tap', 'tests/mutation-contracts.test.mjs'], baseline);
  report.baseline = {compiled: true, passed: tests.status === 0};
  if (tests.status !== 0) throw new Error(`Unmodified baseline did not pass:\n${tests.output}`);
  for (const mutation of mutations) {
    const directory = join(temporary, mutation.id);
    await cp(baseline, directory, {recursive: true});
    const path = join(directory, 'src', mutation.file), original = await readFile(path, 'utf8');
    if (original.split(mutation.from).length !== 2) throw new Error(`${mutation.id}: source anchor must occur exactly once in ${mutation.file}. Update this explicit mutation for the new implementation.`);
    await writeFile(path, original.replace(mutation.from, mutation.to));
    const build = command([compiler, '-p', 'tsconfig.json'], directory);
    const item = {id: mutation.id, file: mutation.file, originalSha256: createHash('sha256').update(original).digest('hex'), compiled: build.status === 0, killed: false};
    report.mutations.push(item);
    if (build.status !== 0) throw new Error(`${mutation.id}: compile failures never count as killed mutants:\n${build.output}`);
    const tests = command(['--test', '--test-reporter=tap', `--test-name-pattern=^mutation contract: ${mutation.test}$`, 'tests/mutation-contracts.test.mjs'], directory);
    // Require the intended test's assertion failure, not a syntax/import error,
    // timeout, or unrelated test crash. Baseline ran these exact tests above.
    item.killed = tests.status === 1 && new RegExp(`not ok \\d+ - mutation contract: ${mutation.test}`).test(tests.output) && tests.output.includes("code: 'ERR_ASSERTION'") && /# fail 1\b/.test(tests.output);
    if (!item.killed) throw new Error(`${mutation.id}: survived or failed without the intended assertion:\n${tests.output}`);
  }
  report.passed = true;
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await rm(temporary, {recursive: true, force: true});
  if (args[1]) {
    const output = resolve(args[1]);
    await mkdir(dirname(output), {recursive: true});
    await writeFile(output, `${JSON.stringify(report, null, 2)}\n`);
  }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
}
