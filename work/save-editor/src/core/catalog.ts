import { EditorError } from './errors.js';
/** English Origin names and metadata shared by the editor and developer ROM reader. */
export interface NamedChoice { readonly id: number; readonly name: string }
export interface MoveChoice extends NamedChoice { readonly basePp: number; readonly type: number; readonly power: number; readonly accuracy: number }
export interface MoveMetadata { readonly id: number; readonly name?: string | undefined; readonly basePp: number; readonly type: number; readonly power: number; readonly accuracy: number }
export interface NameCatalog {
  readonly moves: readonly MoveChoice[];
  readonly species: readonly NamedChoice[];
  readonly readiness: { readonly moves: number; readonly species: number; readonly items: number };
  getMove(id: number): MoveMetadata | undefined;
  getSpecies(id: number): NamedChoice | undefined;
}
export function usableName(name: string | undefined): name is string {
  return !!name && /[A-Za-zÀ-ÿ]/u.test(name);
}
export function createNameCatalog(moveNames: readonly (string | undefined)[], speciesNames: readonly (string | undefined)[], itemNames: readonly (string | undefined)[], moveRecords: readonly Uint8Array[]): NameCatalog {
  if (moveRecords.length !== 921 || moveRecords.some(r => r.length !== 40)) throw new EditorError('invalid-input', 'Invalid Origin move records.');
  if (moveNames.length !== 921 || speciesNames.length !== 1439 || itemNames.length !== 791) throw new EditorError('invalid-input', 'Invalid Origin name-bank sizes.');
  const metadata = moveRecords.map((r, id) => Object.freeze({id, name: usableName(moveNames[id]) ? moveNames[id] : undefined, basePp:r[5]!,type:r[0]!,power:r[3]!,accuracy:r[4]!}));
  const moves = metadata.filter((m): m is MoveChoice => m.id > 0 && m.name !== undefined && m.basePp > 0);
  const species = speciesNames.slice(1, 1026).flatMap((name,i) => usableName(name) ? [Object.freeze({id:i+1,name})] : []);
  const speciesMap = new Map(species.map(s => [s.id,s]));
  return Object.freeze({moves:Object.freeze(moves),species:Object.freeze(species),readiness:Object.freeze({moves:moves.length,species:species.length,items:itemNames.slice(1).filter(usableName).length}),getMove(id:number){return Number.isInteger(id) ? metadata[id] : undefined;},getSpecies(id:number){return speciesMap.get(id);}});
}
export function maxMovePp(move: Pick<MoveMetadata, 'basePp'>, ppUps: number): number {
  if (!Number.isInteger(ppUps) || ppUps < 0 || ppUps > 3) throw new EditorError('invalid-input', 'PP Ups must be between 0 and 3.');
  // Native Gen IV calculation, using Origin's live base PP. One-PP moves gain none.
  return move.basePp + Math.floor(move.basePp * ppUps / 5);
}
/** Validate explicitly edited slots only, so unknown existing records survive unchanged. */
export function validateMoveChoice(catalog: NameCatalog, id: number, pp: number, ppUps: number): void {
  if (id === 0) {
    if (pp !== 0 || ppUps !== 0) throw new EditorError('invalid-input', 'An empty move slot must have zero PP and PP Ups.');
    return;
  }
  const move = catalog.getMove(id);
  if (!move || !usableName(move.name) || move.basePp < 1) throw new EditorError('invalid-input', 'Choose a named move from the available choices.');
  const maximum = maxMovePp(move, ppUps);
  if (!Number.isInteger(pp) || pp < 0 || pp > maximum) throw new EditorError('invalid-input', `PP must be between 0 and ${maximum}.`);
}
