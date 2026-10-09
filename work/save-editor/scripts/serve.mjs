import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve, extname, sep } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const coreRoot = fileURLToPath(new URL('../../save-core/dist/', import.meta.url));
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
const port = Number(process.env.PORT ?? 4173);
const server = createServer(async (req, res) => {
  try {
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      res.writeHead(405).end(); return;
    }
    const path = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
    // Only compiled browser modules, never the worker, source data or local fixtures.
    const coreModule = /^\/save-core\/dist\/[\w-]+\.js$/.test(path);
    if (!(coreModule || path === '/' || path === '/index.html' || path === '/src/style.css' || /^\/dist\/[\w/-]+\.js$/.test(path))) {
      res.writeHead(404).end('Not found'); return;
    }
    const allowedRoot = coreModule ? coreRoot : root;
    const file = coreModule ? resolve(coreRoot, path.slice('/save-core/dist/'.length)) : resolve(root, '.' + (path === '/' ? '/index.html' : path));
    if (!file.startsWith(allowedRoot.endsWith(sep) ? allowedRoot : allowedRoot + sep)) {
      res.writeHead(403).end(); return;
    }
    const data = await readFile(file);
    res.writeHead(200, {
      'Content-Type': mime[extname(file)] ?? 'application/octet-stream',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
      'Content-Security-Policy': "default-src 'self'; connect-src 'none'; img-src 'self'; object-src 'none'; base-uri 'none'",
    });
    res.end(req.method === 'HEAD' ? undefined : data);
  } catch {
    res.writeHead(404).end('Not found');
  }
});
server.listen(port, '127.0.0.1', () => console.log(`Origin Save Editor: http://127.0.0.1:${server.address().port}`));
