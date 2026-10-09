// Minimal static server for local use: serves the page, stylesheet, assets and compiled
// modules only (the editor's and the shared save core's), never local saves, ROMs or the worker.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {extname, resolve, sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const coreRoot = fileURLToPath(new URL('../../save-core/dist/', import.meta.url));
const types = {'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.svg': 'image/svg+xml', '.map': 'application/json'};
const coreModule = p => /^\/save-core\/dist\/[\w-]+\.(js|map)$/.test(p);
const allowed = p => p === '/index.html' || p === '/styles.css' || p === '/favicon.svg' || /^\/assets\/badges\/[a-z]+-hgss\.png$/.test(p)
  || /^\/assets\/wallpapers\/box_wp\d\d(dp|hgss)\.png$/.test(p) || /^\/dist\/[\w/-]+\.(js|map)$/.test(p) || coreModule(p);
const port = Number(process.env.PORT ?? 4180);
const server = createServer(async (req, res) => {
  if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405).end(); return; }
  try {
    let path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (path === '/') path = '/index.html';
    if (!allowed(path)) { res.writeHead(404).end('Not found'); return; }
    const base = coreModule(path) ? coreRoot : root;
    const file = resolve(base, '.' + (coreModule(path) ? path.slice('/save-core/dist'.length) : path));
    if (!file.startsWith(base.endsWith(sep) ? base : base + sep)) { res.writeHead(403).end(); return; }
    const body = await readFile(file);
    res.writeHead(200, {'content-type': types[extname(path)] ?? 'application/octet-stream', 'cache-control': 'no-store',
      'content-security-policy': "connect-src 'none'; object-src 'none'; base-uri 'self'; form-action 'none'"});
    res.end(req.method === 'HEAD' ? undefined : body);
  } catch { res.writeHead(404).end('Not found'); }
});
server.on('error', error => {
  if (error.code !== 'EADDRINUSE') throw error;
  console.error(`Port ${port} is already in use. Stop the other server or run: PORT=${port + 1} npm start`);
  process.exit(1);
});
server.listen(port, '127.0.0.1', () => console.log(`Origin HG save editor → http://127.0.0.1:${server.address().port}`));
