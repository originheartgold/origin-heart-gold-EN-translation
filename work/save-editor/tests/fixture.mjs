import { existsSync, readFileSync } from 'node:fs';
// Real saves stay local and are never committed. Set OHG_SAVE_FIXTURE to run these cases.
const path = process.env.OHG_SAVE_FIXTURE || new URL('../local/fixture.sav', import.meta.url);
export const fixture = existsSync(path) ? new Uint8Array(readFileSync(path)) : undefined;
