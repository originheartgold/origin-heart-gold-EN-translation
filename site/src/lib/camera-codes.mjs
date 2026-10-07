// Action Replay codes for the overworld camera (Origin HeartGold v4.0.3, English rc5 and the Chinese original).
// Evidence and test log: work/cheats/CAMERA_CHEATS.md. Plain JS so node can test it.

// The camera preset table in overlay 1: 17 rows of 0x24 bytes.
export const TABLE = 0x022053ac;
export const ROW = 0x24;
// Guard: a code word of the camera builder, so table writes happen only while the overworld code is loaded.
export const GUARD = '521E9C54 B084B5F8';
// Force the current map's preset: play-time pointer -> location block + 0x6A in the save.
export const forceCode = (preset) =>
	['621CFF30 00000000', 'B21CFF30 00000000', `20001308 ${hex(preset)}`, 'D2000000 00000000'];

// Raw rows: distance (fx32), tilt (u16 angle), projection (0 3D, 1 flat), half FOV (u16 angle), near, far (fx32),
// look-at shift x, y, z (fx32). Identical to US HeartGold.
export const PRESETS = [
	[0x29aec1, 0xdd62, 0, 0x5c1, 0x96000, 0x4b0000, 0, 0, 0],
	[0x19465c, 0xe383, 0, 0x981, 0x86000, 0x4b0000, 0, 151552, -61440],
	[0x29aec1, 0xe3c2, 0, 0x5c1, 0x96000, 0x4b0000, 0, 0, 0],
	[0x29aec1, 0xf242, 0, 0x5c1, 0x96000, 0x4b0000, 0, 125381, -49353],
	[0x61b89b, 0xdc82, 1, 0x281, 0x96000, 0x6c7000, 0, 0, 0],
	[0x1d19f6, 0xdda2, 0, 0x881, 0x96000, 0x488000, 0, 0, -98304],
	[0x29aec1, 0xdfe2, 0, 0x5c1, 0x96000, 0x5dc000, 0, 0, 0],
	[0x29aec1, 0xe1e2, 0, 0x5c1, 0x96000, 0x4b0000, 0, 97371, -92702],
	[0x20374c, 0xd922, 0, 0x770, 0x96000, 0x384000, 0, 0, 0],
	[0x29bec1, 0xd582, 0, 0x5c1, 0x96000, 0x4b0000, 0, 0, 0],
	[0x13c805, 0xdf42, 0, 0xc81, 0x96000, 0x6a4000, 0, 50673, -154740],
	[0x215c29, 0xe3c2, 0, 0x741, 0x96000, 0x4b0000, 0, -32768, 0],
	[0x29aec1, 0xdfe2, 0, 0x5c1, 0x96000, 0x6a4000, 0, 0, -131072],
	[0x29aec1, 0xf242, 0, 0x5c1, 0x96000, 0x6a4000, 0, 125381, -123081],
	[0x29aec1, 0xd4c2, 0, 0x5c1, 0x96000, 0x4b0000, 0, 0, 0],
	[0x61b89b, 0xdc82, 1, 0x281, 0x96000, 0x6c7000, 0, 0, -188416],
	[0x29aec1, 0xd602, 0, 0x5c1, 0x96000, 0x384000, 0, 0, 0],
];

// What each preset looks like, and the maps that use it.
export const PRESET_NAMES = [
	'normal outdoor camera', 'Violet Gym', 'lower angle (Goldenrod Gym)', 'very low (Lighthouse)',
	'flat interior camera', 'Azalea Gym', 'slightly lower', 'Pokéathlon Dome', 'Battle Frontier',
	'top-down (Vermilion Gym)', 'wide lens (Whirl Islands)', 'unused', 'Lugia’s cave', 'Bell Tower roof',
	'most top-down (Fuchsia Gym)', 'flat (Dance Theater)', 'Battle Tower',
];

export function hex(n) {
	return ((n >>> 0).toString(16).toUpperCase()).padStart(8, '0');
}

// Player-facing units <-> raw values.
export const toSettings = (row) => ({
	distance: Math.round(row[0] / 4096),
	tilt: Math.round(((0x10000 - row[1]) * 360) / 65536),
	fov: Math.round((row[3] * 2 * 360) / 65536),
	flat: row[2] === 1,
	far: Math.round(row[5] / 4096),
});
export const tiltRaw = (deg) => (0x10000 - Math.round((deg * 65536) / 360)) & 0xffff;
export const fovRaw = (deg) => Math.round(((deg / 2) * 65536) / 360) & 0xffff;
export const fx = (units) => Math.round(units * 4096);

// Lines writing one table row. Settings equal to the base row's (after rounding) keep its exact raw value.
// `full` also writes near clip and look-at shift (from the base row).
function rowLines(index, s, base, full) {
	const a = TABLE + ROW * index;
	const b = toSettings(base);
	const dist = s.distance === b.distance ? base[0] : fx(s.distance);
	const tilt = s.tilt === b.tilt ? base[1] : tiltRaw(s.tilt);
	const fov = s.fov === b.fov ? base[3] : fovRaw(s.fov);
	const far = s.far === b.far ? base[5] : fx(s.far);
	const lines = [
		`${hex(a)} ${hex(dist)}`,
		`${hex(a + 4)} ${hex(tilt)}`,
		`${hex(a + 0xc)} ${hex(((fov << 16) | (s.flat ? 1 : 0)) >>> 0)}`,
	];
	if (full) lines.push(`${hex(a + 0x10)} ${hex(base[4])}`);
	lines.push(`${hex(a + 0x14)} ${hex(far)}`);
	if (full) for (let k = 0; k < 3; k++) lines.push(`${hex(a + 0x18 + 4 * k)} ${hex(base[6 + k])}`);
	return lines;
}

/** scope 'everywhere': write unused preset 6 and force it on every map.
 *  scope 'interiors': rewrite the two flat interior presets (4 and 15), keeping their look-at shift. */
export function buildCode(scope, s, basePreset = 0) {
	const base = PRESETS[basePreset];
	if (scope === 'interiors') {
		return [GUARD, ...rowLines(4, s, PRESETS[4], false), ...rowLines(15, s, PRESETS[15], false), 'D2000000 00000000'];
	}
	return [GUARD, ...rowLines(6, s, base, true), 'D2000000 00000000', ...forceCode(6)];
}
