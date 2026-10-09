// Patcher worker (module worker). Everything stays in this browser tab: files are read from disk with
// FileReaderSync, the patch is fetched from this website, and the result is handed back as a Blob.
//   {cmd: 'hash', file, preferCrc}                        -> {type: 'hashed', crc32, sha1, size, title, code, source?, entryName?}
//     A .zip is unpacked here: its .nds (the one whose CRC32 is preferCrc, else the biggest) is hashed as it
//     streams out and returned as `source`, a Blob to patch from. A plain .nds is hashed in place.
//   {cmd: 'patch', source, patchUrl, patchSize, expectSha1} -> {type: 'done', blob, sha1, size, verified}
// Progress: {type: 'progress', phase: 'hash' | 'download' | 'patch', done, total}. Errors: {type: 'error', kind, message}.
import createXdelta3Module from '../vendor/xdelta-wasm/xdelta3.js';
import { applyPatch } from './xdelta-run.js';
import { Crc32, Sha1 } from './hash.js';
import { isZip, listZip, ndsEntries, readEntry, zipError } from './zip.js';

const reader = new FileReaderSync();
const readBlob = (blob, offset, size) => {
	const end = Math.min(blob.size, offset + size);
	if (end <= offset) return new Uint8Array(0);
	return new Uint8Array(reader.readAsArrayBuffer(blob.slice(offset, end)));
};

let lastPost = 0;
function progress(phase, done, total, force = false) {
	const now = Date.now();
	if (!force && now - lastPost < 100) return;
	lastPost = now;
	postMessage({ type: 'progress', phase, done, total });
}

function hashFile(file) {
	const crc = new Crc32(), sha = new Sha1();
	const step = 8 * 1024 * 1024;
	const head = readBlob(file, 0, 16);
	for (let off = 0; off < file.size; off += step) {
		const b = readBlob(file, off, step);
		crc.update(b);
		sha.update(b);
		progress('hash', off + b.length, file.size);
	}
	progress('hash', file.size, file.size, true);
	return { type: 'hashed', crc32: crc.hex(), sha1: sha.hex(), size: file.size, title: ascii(head, 0, 12), code: ascii(head, 12, 16) };
}

const ascii = (head, a, b) => String.fromCharCode(...head.subarray(a, b)).replace(/[^\x20-\x7e]/g, '').trim();

async function hashZip(file, preferCrc) {
	const all = await listZip(file);
	const nds = ndsEntries(all);
	if (!nds.length) {
		const kinds = all.filter((e) => !e.name.endsWith('/')).map((e) => e.name.split('/').pop()).slice(0, 5);
		throw zipError(`This .zip has no .nds file inside${kinds.length ? ` (it holds ${kinds.join(', ')}${all.length > 5 ? ', …' : ''})` : ''}. Choose the .zip or .nds that holds your HeartGold game.`);
	}
	const entry = nds.find((e) => e.crc32 === preferCrc) || nds.reduce((a, b) => (b.size > a.size ? b : a));
	if (entry.size > 512 * 1024 * 1024) throw zipError('This .nds entry is larger than a Nintendo DS cartridge. Unzip it yourself and check the file.');
	const crc = new Crc32(), sha = new Sha1();
	const head = new Uint8Array(16);
	const parts = [];
	let pending = [], pendingBytes = 0, done = 0;
	await readEntry(file, entry, (chunk) => {
		if (done < 16) head.set(chunk.subarray(0, 16 - done), done);
		crc.update(chunk);
		sha.update(chunk);
		pending.push(chunk);
		pendingBytes += chunk.length;
		done += chunk.length;
		if (pendingBytes >= 16 * 1024 * 1024) { parts.push(new Blob(pending)); pending = []; pendingBytes = 0; }
		progress('hash', done, entry.size);
	});
	parts.push(new Blob(pending));
	progress('hash', entry.size, entry.size, true);
	const source = new Blob(parts, { type: 'application/octet-stream' });
	return {
		type: 'hashed', crc32: crc.hex(), sha1: sha.hex(), size: source.size, title: ascii(head, 0, 12), code: ascii(head, 12, 16),
		source, entryName: entry.name.split('/').pop(), ndsCount: nds.length,
	};
}

async function download(url, expectedSize) {
	let res;
	try {
		res = await fetch(url);
	} catch (e) {
		throw Object.assign(new Error('The patch could not be downloaded from this website. Check your connection and try again.'), { kind: 'download' });
	}
	if (!res.ok) throw Object.assign(new Error(`The patch could not be downloaded (HTTP ${res.status}).`), { kind: 'download' });
	const total = Number(res.headers.get('content-length')) || expectedSize || 0;
	const parts = [];
	let done = 0;
	const body = res.body.getReader();
	for (;;) {
		const { done: end, value } = await body.read();
		if (end) break;
		parts.push(value);
		done += value.length;
		progress('download', done, total);
	}
	progress('download', done, total, true);
	if (expectedSize && done !== expectedSize) {
		throw Object.assign(new Error(`The downloaded patch is ${done} bytes, not ${expectedSize}. The download was cut short; try again.`), { kind: 'download' });
	}
	return new Blob(parts);
}

async function patch({ source, patchUrl, patchSize, expectSha1 }) {
	const patchBlob = await download(patchUrl, patchSize);
	const sha = new Sha1();
	const parts = [];
	let pending = [], pendingBytes = 0, size = 0;
	const res = await applyPatch(createXdelta3Module, {
		readSource: (offset, n) => readBlob(source, offset, n),
		readPatch: (offset, n) => readBlob(patchBlob, offset, n),
		onProgress: (pos) => progress('patch', pos, patchBlob.size),
		onOutput: (bytes) => {
			sha.update(bytes);
			size += bytes.length;
			pending.push(bytes);
			pendingBytes += bytes.length;
			// Fold finished blocks into Blobs as we go, so the browser can keep them out of the JS heap.
			if (pendingBytes >= 64 * 1024 * 1024) { parts.push(new Blob(pending)); pending = []; pendingBytes = 0; }
		},
	});
	if (!res.ok) throw Object.assign(new Error(res.message), { kind: res.oom ? 'memory' : 'xdelta' });
	progress('patch', patchBlob.size, patchBlob.size, true);
	parts.push(new Blob(pending));
	const sha1 = sha.hex();
	const blob = new Blob(parts, { type: 'application/octet-stream' });
	return { type: 'done', blob, sha1, size, verified: !expectSha1 || sha1 === expectSha1.toLowerCase() };
}

onmessage = async (event) => {
	const msg = event.data || {};
	try {
		if (msg.cmd === 'hash') postMessage((await isZip(msg.file)) ? await hashZip(msg.file, msg.preferCrc) : hashFile(msg.file));
		else if (msg.cmd === 'patch') postMessage(await patch(msg));
	} catch (e) {
		const memory = e instanceof RangeError || e?.name === 'QuotaExceededError' || /memory|allocation failed/i.test(String(e?.message));
		postMessage({ type: 'error', kind: e?.kind || (memory ? 'memory' : 'other'), message: String(e?.message || e) });
	}
};
