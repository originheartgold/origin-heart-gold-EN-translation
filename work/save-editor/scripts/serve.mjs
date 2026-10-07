// Minimal static server for local use: serves the page, stylesheet and compiled modules only.
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {extname, normalize, join} from 'node:path';
const root = new URL('..', import.meta.url).pathname;
const types = {'.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png', '.svg': 'image/svg+xml', '.map': 'application/json'};
const allowed = p => p === '/index.html' || p === '/styles.css' || p === '/favicon.svg' || /^\/assets\/badges\/[a-z]+-hgss\.png$/.test(p) || (p.startsWith('/dist/') && /\.(js|map)$/.test(p));
const port = Number(process.env.PORT) || 4180;
const server = createServer(async (req, res) => {
  let path = normalize(decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (path === '/') path = '/index.html';
  if (!allowed(path)) { res.writeHead(404).end('Not found'); return; }
  try {
    const body = await readFile(join(root, path));
    res.writeHead(200, {'content-type': types[extname(path)] ?? 'application/octet-stream', 'cache-control': 'no-store'}).end(body);
  } catch { res.writeHead(404).end('Not found'); }
});
server.on('error', error => {
  if (error.code !== 'EADDRINUSE') throw error;
  console.error(`Port ${port} is already in use. Stop the other server or run: PORT=${port + 1} npm start`);
  process.exit(1);
});
server.listen(port, '127.0.0.1', () => console.log(`Origin HG save editor → http://127.0.0.1:${port}`));
