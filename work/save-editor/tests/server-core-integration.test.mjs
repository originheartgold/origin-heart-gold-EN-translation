import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('standalone editor serves the complete shared-core module graph but excludes private paths', {timeout:15000}, async t => {
  const child = spawn(process.execPath, [fileURLToPath(new URL('../scripts/serve.mjs', import.meta.url))], {
    env:{...process.env, PORT:'0'}, stdio:['ignore','pipe','pipe'],
  });
  t.after(() => child.kill());
  let errors = '';
  child.stderr.on('data', chunk => { errors += chunk; });
  const origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(Error(`Server failed to start: ${errors}`)), 5000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', code => { clearTimeout(timer); reject(Error(`Server exit ${code}: ${errors}`)); });
    child.stdout.on('data', chunk => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
  const page = await fetch(origin);
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-security-policy'), /connect-src 'none'/);
  assert.match(await page.text(), /dist\/ui\/app\.js/);
  const visited = new Set();
  async function visit(path) {
    const url = new URL(path, origin);
    if (visited.has(url.pathname)) return;
    visited.add(url.pathname);
    assert.equal(url.origin, origin);
    const response = await fetch(url);
    assert.equal(response.status, 200, url.pathname);
    assert.match(response.headers.get('content-type'), /javascript/);
    const code = await response.text();
    for (const match of code.matchAll(/\b(?:from\s*|import\s*)['"]([^'"]+)['"]/g)) {
      assert.ok(match[1].startsWith('.'), `Non-relative browser dependency ${match[1]}`);
      await visit(new URL(match[1], url).pathname);
    }
  }
  await visit('/dist/ui/app.js');
  for (const module of ['save','pokemon','stats','inventory','save-container','errors','transaction']) {
    assert.ok(visited.has(`/save-core/dist/${module}.js`), `${module} must come from the shared core`);
  }
  for (const path of ['/save-core/cli/worker.mjs', '/save-core/src/save.ts', '/local/fixture.sav',
    '/package.json', '/save-core/dist/../cli/worker.mjs', '/save-core/dist/%2e%2e%2fcli%2fworker.mjs']) {
    assert.equal((await fetch(new URL(path, origin))).status, 404, path);
  }
  const head = await fetch(new URL('/save-core/dist/save.js', origin), {method:'HEAD'});
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal((await fetch(origin, {method:'POST'})).status, 405);
});
