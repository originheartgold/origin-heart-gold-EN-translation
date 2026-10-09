// Independent test-only constructors. These invented bytes are not playable saves.
// The production cipher uses Math.imul; this oracle deliberately uses BigInt.
export const view = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
export function rng(seed = 0x1eafcafe) {
  return () => { seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5; return seed >>> 0; };
}
function permutations(values) {
  return values.length ? values.flatMap(value => permutations(values.filter(x => x !== value)).map(rest => [value, ...rest])) : [[]];
}
const orders = permutations([0, 1, 2, 3]);
export function xorWords(bytes, seed) {
  const result = Uint8Array.from(bytes), data = view(result);
  let state = BigInt(seed);
  for (let offset = 0; offset < bytes.length; offset += 2) {
    state = (state * 1103515245n + 24691n) & 0xffffffffn;
    data.setUint16(offset, data.getUint16(offset, true) ^ Number(state >> 16n), true);
  }
  return result;
}
export function encodeOracle(logical, pid, tail, flags = 0) {
  const payload = new Uint8Array(128), record = new Uint8Array(tail ? 236 : 136), data = view(record);
  orders[((pid >>> 13) & 31) % 24].forEach((index, position) => payload.set(logical.subarray(index * 32, index * 32 + 32), position * 32));
  let sum = 0;
  for (let i = 0; i < 128; i += 2) sum = (sum + view(payload).getUint16(i, true)) & 65535;
  data.setUint32(0, pid, true); data.setUint16(4, flags, true); data.setUint16(6, sum, true);
  record.set(xorWords(payload, sum), 8);
  if (tail) record.set(xorWords(tail, pid), 136);
  return record;
}
export function decodeOracle(record) {
  const data = view(record), pid = data.getUint32(0, true), payload = xorWords(record.subarray(8, 136), data.getUint16(6, true));
  const logical = new Uint8Array(128);
  orders[((pid >>> 13) & 31) % 24].forEach((index, position) => logical.set(payload.subarray(position * 32, position * 32 + 32), index * 32));
  let sum = 0;
  for (let i = 0; i < 128; i += 2) sum = (sum + view(payload).getUint16(i, true)) & 65535;
  return {pid, logical, checksumOk: sum === data.getUint16(6, true), tail: record.length === 236 ? xorWords(record.subarray(136), pid) : undefined};
}
export function pokemonFixture(selector = 0, length = 236, seed = 1) {
  const next = rng(seed), logical = Uint8Array.from({length: 128}, () => next() & 255), data = view(logical);
  data.setUint16(0, 25, true); data.setUint32(8, 125, true);
  logical.fill(0, 16, 22);
  for (let i = 0; i < 4; i++) { data.setUint16(32 + 2 * i, 20 + i, true); logical[40 + i] = 5 + i; logical[44 + i] = i; }
  data.setUint32(48, 0x12345678, true); data.setUint32(52, 0, true); logical[56] = 0; data.setUint16(58, 9, true);
  const tail = new Uint8Array(100); view(tail).setUint32(0, 0, true); tail[4] = 5;
  for (let i = 6; i < 20; i += 2) view(tail).setUint16(i, 20, true);
  const pid = ((selector << 13) | (next() & 0xfffc1fff)) >>> 0;
  return encodeOracle(logical, pid, length === 236 ? tail : undefined);
}
// Reflected polynomial table avoided: bit division independent of implementation loop.
export function crcOracle(bytes) {
  let remainder = 65535;
  for (const byte of bytes) for (let bit = 7; bit >= 0; bit--) {
    const carry = ((remainder >>> 15) ^ (byte >>> bit)) & 1;
    remainder = (remainder << 1) & 65535;
    if (carry) remainder ^= 0x1021;
  }
  return remainder;
}
export function refreshBlock(bytes, base = 0, offset = 0, size = 0xf7cc) {
  const footer = base + offset + size - 16;
  view(bytes).setUint16(footer + 14, crcOracle(bytes.subarray(base + offset, footer)), true);
}
export function saveFixture({counters = [10, 9], count = 2, storageCounters = counters} = {}) {
  const bytes = new Uint8Array(0x80000), data = view(bytes);
  for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 13 + 71) & 255;
  [0, 0x40000].forEach((base, index) => {
    data.setUint32(base + 0x90, 6, true); data.setUint32(base + 0x94, count, true);
    for (let slot = 0; slot < 6; slot++) bytes.set(pokemonFixture(slot, 236, slot + 1), base + 0x98 + slot * 236);
    bytes.fill(0, base + 0x644, base + 0xeac); bytes.fill(0, base + 0xeac, base + 0x1320);
    bytes.fill(0, base + 0x2480, base + 0x2480 + 64 * 0x50);
    for (const [offset, size, id, counter] of [[0, 0xf7cc, 0, counters[index]], [0xf800, 0x18408, 1, storageCounters[index]]]) {
      const footer = base + offset + size - 16;
      data.setUint32(footer, counter, true); data.setUint32(footer + 4, size, true);
      data.setUint32(footer + 8, 0x20060623, true); data.setUint16(footer + 12, id, true);
      refreshBlock(bytes, base, offset, size);
    }
  });
  return bytes;
}
