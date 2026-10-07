import { EditorError } from './errors.js';
import { bundledReference } from './generated-reference.js';
import { usableName, type MoveMetadata, type MoveChoice, type NamedChoice } from './catalog.js';
import { POCKETS, type ItemMetadata } from './inventory.js';
import type { OriginData } from './rom.js';
export const BUNDLED_GAME_VERSION = 'origin-heartgold-english-v4.0.3';
/** Validate at startup; cryptographic provenance is checked by tests and the offline generator. */
export function validateBundledReference(input: unknown): asserts input is typeof bundledReference {
  const bad = (): never => { throw new EditorError('invalid-reference', 'Invalid bundled English Origin reference data.'); };
  const keys = (v: unknown, required: string[], optional: string[] = []): boolean => !!v && typeof v === 'object' && !Array.isArray(v) && required.every(k => Object.hasOwn(v,k)) && Object.keys(v).every(k => required.includes(k) || optional.includes(k));
  const name = (v: unknown): v is string => typeof v === 'string' && usableName(v);
  if (!keys(input,['schemaVersion','gameVersion','provenance','payload'])) bad();
  const r = input as typeof bundledReference, p = r.payload;
  const integer = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isInteger(v) && v >= min && v <= max;
  if (!keys(p,['personal','growth','forms','moves','species','items','readiness']) || !keys(r.provenance,['romSha256','payloadSha256','sources']) || !keys(r.provenance.sources,['a/0/0/2','a/0/0/3','a/0/1/7','extra/new_move_data.narc','a/0/2/7#219','a/0/2/7#232','a/0/2/7#739','arm9#forms']) || Object.values(r.provenance.sources).some(v => typeof v !== 'string' || !/^[a-f0-9]{64}$/.test(v))) bad();
  if (r.schemaVersion !== 1 || r.gameVersion !== BUNDLED_GAME_VERSION || !r.provenance || !/^[a-f0-9]{64}$/.test(r.provenance.romSha256) || !/^[a-f0-9]{64}$/.test(r.provenance.payloadSha256) || !p) bad();
  if (!Array.isArray(p.personal) || p.personal.length !== 1441 || p.personal.some(r => !Array.isArray(r) || r.length !== 7 || r.slice(0,6).some(v => !integer(v,0,255)) || !integer(r[6],0,5))) bad();
  if (!Array.isArray(p.growth) || p.growth.length !== 8 || p.growth.some(r => !Array.isArray(r) || r.length !== 101 || r.some(v => !integer(v,0,0xffffffff)))) bad();
  if (!Array.isArray(p.forms) || p.forms.length !== 415 || p.forms.some(r => !Array.isArray(r) || r.length !== 3 || !integer(r[0],0,1025) || !integer(r[1],0,1440) || !integer(r[2],0,255))) bad();
  if (!Array.isArray(p.moves) || p.moves.length !== 921 || p.moves.some((r,i) => !keys(r,['id','basePp','type','power','accuracy'],['name']) || r.id !== i || (r.name !== undefined && !name(r.name)) || [r.basePp,r.type,r.power,r.accuracy].some(v => !integer(v,0,255)))) bad();
  if (!Array.isArray(p.species) || p.species.length !== 1025 || p.species.some((r,i) => !keys(r,['id','name']) || r.id !== i+1 || !name(r.name))) bad();
  if (!Array.isArray(p.items) || p.items.length !== 790 || p.items.some((r,i) => !keys(r,['id','name','pocket']) || r.id !== i+1 || typeof r.name !== 'string' || !POCKETS.some(p => p.id === r.pocket))) bad();
  if (!keys(p.readiness,['moves','species','items']) || p.readiness.moves !== 902 || p.readiness.species !== 1025 || p.readiness.items !== 768 || p.readiness.species !== p.species.length || p.readiness.moves !== p.moves.filter(m => m.id > 0 && m.name !== undefined && m.basePp > 0).length || p.readiness.items !== p.items.filter(i => usableName(i.name)).length) bad();
}
export type BundledOriginData = OriginData & Required<Pick<OriginData, 'catalog' | 'inventory'>>;
export function loadBundledOriginData(): BundledOriginData {
  validateBundledReference(bundledReference);
  const p = bundledReference.payload;
  const metadata: readonly MoveMetadata[] = Object.freeze(p.moves.map(m => Object.freeze({...m, name: m.name})));
  const moves = Object.freeze(metadata.filter((m): m is MoveChoice => m.id > 0 && m.name !== undefined && m.basePp > 0));
  const species: readonly NamedChoice[] = Object.freeze(p.species.map(s => Object.freeze({...s})));
  const items: readonly ItemMetadata[] = Object.freeze(p.items.map(i => Object.freeze({...i, pocket: i.pocket as ItemMetadata['pocket']})));
  const speciesMap = new Map(species.map(s => [s.id,s])), itemMap = new Map(items.map(i => [i.id,i]));
  const forms = new Map<string,number>();
  for (const [species,index,form] of p.forms) { const key = `${species}/${form}`; if (!forms.has(key)) forms.set(key,index!); }
  const growth = p.growth.map(r => Object.freeze([...r]));
  return Object.freeze({
    catalog: Object.freeze({moves,species,readiness:Object.freeze({...p.readiness}),getMove(id:number){return Number.isInteger(id) ? metadata[id] : undefined;},getSpecies(id:number){return speciesMap.get(id);}}),
    inventory: Object.freeze({items,getItem(id:number){return itemMap.get(id);}}),
    getPersonal(speciesId:number,form:number) {
      if (!Number.isInteger(speciesId) || speciesId < 1 || speciesId > 1025 || !Number.isInteger(form) || form < 0 || form > 255) throw new EditorError('invalid-reference', 'Unsupported species or form.');
      const r = p.personal[form === 0 ? speciesId : forms.get(`${speciesId}/${form}`) ?? speciesId]!;
      return {baseStats: r.slice(0,6) as [number,number,number,number,number,number],growthRate:r[6]!,growthThresholds:growth[r[6]!]!};
    }
  });
}
