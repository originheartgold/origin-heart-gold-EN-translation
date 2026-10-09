// Minimal .zip reader for the patcher: finds the .nds files in an archive the player picked and streams one
// out, without loading the whole archive. Stored (0) and Deflate (8) entries, Zip64 included; deflate is
// decoded by the browser's own DecompressionStream('deflate-raw'). Works on any Blob/File (browser and Node).
// Used by worker.js and work/tools/site/test_patcher.mjs.

const u16 = (v, o) => v.getUint16(o, true);
const u32 = (v, o) => v.getUint32(o, true);
const u64 = (v, o) => u32(v, o) + u32(v, o + 4) * 0x100000000;

function checkRange(blob, offset, size) {
	if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(size) || offset < 0 || size < 0 || offset + size > blob.size) {
		throw zipError('This .zip file is damaged or incomplete (invalid file bounds). Unzip it yourself and choose the .nds.');
	}
}

async function bytes(blob, offset, size) {
	checkRange(blob, offset, size);
	return new Uint8Array(await blob.slice(offset, offset + size).arrayBuffer());
}

export function zipError(message) {
	return Object.assign(new Error(message), { kind: 'zip' });
}

/** True when the file starts like a zip archive (local file header or an empty archive). */
export async function isZip(blob) {
	if (blob.size < 4) return false;
	const h = await bytes(blob, 0, 4);
	return h[0] === 0x50 && h[1] === 0x4b && ((h[2] === 3 && h[3] === 4) || (h[2] === 5 && h[3] === 6));
}

/**
 * List the archive's files.
 * @returns {Promise<Array<{name: string, method: number, encrypted: boolean, crc32: string, size: number, csize: number, localOffset: number}>>}
 */
export async function listZip(blob) {
	// End of central directory: the last 22 bytes plus up to 64 KB of comment.
	const tailLen = Math.min(blob.size, 22 + 65535);
	const tail = await bytes(blob, blob.size - tailLen, tailLen);
	const tv = new DataView(tail.buffer);
	let eocd = -1;
	for (let i = tail.length - 22; i >= 0; i--) if (u32(tv, i) === 0x06054b50 && i + 22 + u16(tv, i + 20) === tail.length) { eocd = i; break; }
	if (eocd < 0) throw zipError("This .zip file is damaged or incomplete (no end of archive found). Download or create it again, or unzip it yourself and choose the .nds.");
	if (u16(tv, eocd + 4) !== 0 || u16(tv, eocd + 6) !== 0 || u16(tv, eocd + 8) !== u16(tv, eocd + 10)) throw zipError('Multi-volume .zip archives are unsupported. Unzip it yourself and choose the .nds.');
	let count = u16(tv, eocd + 10);
	let cdSize = u32(tv, eocd + 12);
	let cdOffset = u32(tv, eocd + 16);
	// Zip64: the locator sits right before the EOCD record and points at the Zip64 EOCD.
	if (eocd >= 20 && u32(tv, eocd - 20) === 0x07064b50) {
		const z = new DataView((await bytes(blob, u64(tv, eocd - 12), 56)).buffer);
		if (u32(z, 0) !== 0x06064b50 || u32(z, 16) !== 0 || u32(z, 20) !== 0 || u64(z, 24) !== u64(z, 32)) throw zipError('Invalid or multi-volume Zip64 archive.');
		count = u64(z, 32); cdSize = u64(z, 40); cdOffset = u64(z, 48);
	}
	if (!Number.isSafeInteger(count) || count > Math.floor(cdSize / 46) || cdOffset + cdSize > blob.size - tailLen + eocd) throw zipError('This .zip file has an invalid file list.');
	const cd = await bytes(blob, cdOffset, cdSize);
	const v = new DataView(cd.buffer);
	const utf8 = new TextDecoder('utf-8');
	const cp437 = new TextDecoder('latin1');
	const entries = [];
	for (let p = 0, n = 0; n < count; n++) {
		if (p + 46 > cd.length) throw zipError('This .zip file has a truncated file list.');
		if (u32(v, p) !== 0x02014b50) throw zipError('This .zip file is damaged (bad file list). Unzip it yourself and choose the .nds.');
		const flags = u16(v, p + 8);
		const nameLen = u16(v, p + 28), extraLen = u16(v, p + 30), commentLen = u16(v, p + 32);
		if (p + 46 + nameLen + extraLen + commentLen > cd.length) throw zipError('This .zip file has a truncated file entry.');
		if (u16(v, p + 34) !== 0) throw zipError('Multi-volume .zip archives are unsupported.');
		let csize = u32(v, p + 20), size = u32(v, p + 24), localOffset = u32(v, p + 42);
		const nameBytes = cd.subarray(p + 46, p + 46 + nameLen);
		const name = (flags & 0x800 ? utf8 : cp437).decode(nameBytes);
		// Zip64 extended information: only the fields that overflowed are present, in this order.
		for (let e = p + 46 + nameLen, end = e + extraLen; e + 4 <= end; ) {
			const id = u16(v, e), len = u16(v, e + 2);
			if (e + 4 + len > end) throw zipError('This .zip file has a truncated extra field.');
			if (id === 0x0001) {
				let q = e + 4;
				const fields = [size, csize, localOffset].filter(n => n === 0xffffffff).length;
				if (len < fields * 8) throw zipError('This .zip file has a truncated Zip64 entry.');
				if (size === 0xffffffff) { size = u64(v, q); q += 8; }
				if (csize === 0xffffffff) { csize = u64(v, q); q += 8; }
				if (localOffset === 0xffffffff) { localOffset = u64(v, q); q += 8; }
			}
			e += 4 + len;
		}
		if ([size, csize, localOffset].some(n => !Number.isSafeInteger(n) || n < 0 || n === 0xffffffff)) throw zipError('This .zip file has invalid Zip64 sizes.');
		checkRange(blob, localOffset, 30 + csize);
		entries.push({
			name,
			method: u16(v, p + 10),
			encrypted: !!(flags & 1),
			crc32: u32(v, p + 16).toString(16).toUpperCase().padStart(8, '0'),
			size,
			csize,
			localOffset,
		});
		p += 46 + nameLen + extraLen + commentLen;
	}
	return entries;
}

/** The .nds files in the archive (macOS resource forks and folders left out). */
export function ndsEntries(entries) {
	return entries.filter((e) => /\.nds$/i.test(e.name) && !/(^|\/)__MACOSX\//.test(e.name) && !/(^|\/)\._/.test(e.name));
}

/**
 * Stream one entry's uncompressed bytes.
 * @param {(chunk: Uint8Array) => void} onChunk  called with each piece, in order
 */
export async function readEntry(blob, entry, onChunk) {
	if (entry.encrypted) throw zipError(`"${entry.name}" in this .zip is password-protected. Unzip it yourself and choose the .nds.`);
	if (entry.method !== 0 && entry.method !== 8) {
		throw zipError(`"${entry.name}" in this .zip uses a compression method this page can't open (method ${entry.method}). Unzip it yourself and choose the .nds, or re-zip it as a normal .zip.`);
	}
	const lv = new DataView((await bytes(blob, entry.localOffset, 30)).buffer);
	if (u32(lv, 0) !== 0x04034b50) throw zipError('This .zip file is damaged (bad file header). Unzip it yourself and choose the .nds.');
	const start = entry.localOffset + 30 + u16(lv, 26) + u16(lv, 28);
	checkRange(blob, start, entry.csize);
	let stream = blob.slice(start, start + entry.csize).stream();
	if (entry.method === 8) {
		if (typeof DecompressionStream !== 'function') throw zipError("This browser can't unzip files. Unzip it yourself and choose the .nds, or use a recent browser.");
		try {
			stream = stream.pipeThrough(new DecompressionStream('deflate-raw'));
		} catch {
			throw zipError("This browser can't unzip files. Unzip it yourself and choose the .nds, or use a recent browser.");
		}
	}
	const reader = stream.getReader();
	let done = 0;
	try {
		for (;;) {
			const r = await reader.read();
			if (r.done) break;
			done += r.value.length;
			if (done > entry.size) throw zipError('This .zip entry expands beyond its advertised size.');
			onChunk(r.value);
		}
	} catch (e) {
		if (e?.kind) throw e;
		throw zipError(`"${entry.name}" in this .zip couldn't be unpacked (${e?.message || e}). The archive is probably damaged.`);
	}
	finally {
		await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
	if (done !== entry.size) throw zipError(`"${entry.name}" in this .zip unpacked to ${done} bytes instead of ${entry.size}. The archive is probably damaged.`);
}
