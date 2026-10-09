// Research-only adapter to the unchanged browser modules. No save files are written.
import { createInterface } from 'node:readline';
import { readSave, patchPartyRecord } from '../../save-editor/dist/save.js';
import { decodePokemon, patchPokemonMoves } from '../../save-editor/dist/pokemon.js';
import { unwrapSave, wrapSave } from '../../save-editor/dist/save-container.js';

function run(request) {
  const bytes = Uint8Array.from(Buffer.from(request.bytes, 'base64'));
  switch (request.op) {
    case 'save': {
      const save = readSave(bytes);
      return { base: save.generalOffset, tied: save.tied, count: save.partyCount };
    }
    case 'pokemon': return decodePokemon(bytes);
    case 'moves': return { bytes: Buffer.from(patchPokemonMoves(bytes, request.moves)).toString('base64') };
    case 'patch-invalid': {
      const result = patchPartyRecord(bytes, 0, new Uint8Array(136));
      try { decodePokemon(readSave(result).party[0]); }
      catch (error) { return { accepted: true, recordError: error.message }; }
      return { accepted: true, recordError: null };
    }
    case 'containers': {
      const raw = Buffer.from(bytes);
      const split = unwrapSave(raw);
      split.bytes[0] ^= 1;
      const aliasesInput = raw[0] !== bytes[0];
      const notice = Buffer.from('|<--Snip above here to create a raw sav by excluding this DeSmuME savedata footer:');
      const footer = Buffer.concat([notice, Buffer.alloc(24), Buffer.from('|-DESMUME SAVE-|')]);
      footer.writeUInt32LE(524288, notice.length + 4);
      const dsv = wrapSave(bytes, { kind: 'desmume', footer: Uint8Array.from(footer) });
      const validUint8 = unwrapSave(dsv).container.kind;
      let bufferDsv;
      try { bufferDsv = unwrapSave(Buffer.from(dsv)).container.kind; }
      catch (error) { bufferDsv = error.message; }
      return { aliasesInput, validUint8, bufferDsv };
    }
    default: throw Error(`Unknown research operation: ${request.op}`);
  }
}
for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
  try { process.stdout.write(JSON.stringify({ ok: true, result: run(JSON.parse(line)) }) + '\n'); }
  catch (error) { process.stdout.write(JSON.stringify({ ok: false, code: error.code, message: error.message }) + '\n'); }
}
