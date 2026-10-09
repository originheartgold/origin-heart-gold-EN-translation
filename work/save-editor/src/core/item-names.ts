import { EditorError } from './errors.js';
/** Decode only the Latin subset used by the English build. Unknown encodings
 * return undefined rather than displaying invented or partial item names. */
export function readItemNames(bytes: Uint8Array): (string | undefined)[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.length < 4) throw new EditorError('invalid-reference', 'Truncated item-name bank.');
  const count = view.getUint16(0, true), seed = view.getUint16(2, true);
  if (count > 4096 || 4 + count * 8 > bytes.length) throw new EditorError('invalid-reference', 'Invalid item-name table.');
  const result: (string | undefined)[] = [];
  let previousEnd = 4 + count * 8;
  for (let i = 0; i < count; i++) {
    const half = (seed * 0x2fd * (i + 1)) & 0xffff;
    const key = (half | half << 16) >>> 0;
    const offset = (view.getUint32(4 + i * 8, true) ^ key) >>> 0;
    const length = (view.getUint32(8 + i * 8, true) ^ key) >>> 0;
    if (offset !== previousEnd || length < 1 || length > 256 || offset + length * 2 > bytes.length) throw new EditorError('invalid-reference', 'Invalid item-name record.');
    previousEnd = offset + length * 2;
    let cipher = (0x91bd3 * (i + 1)) & 0xffff;
    let name = '', supported = true, terminated = false;
    for (let j = 0; j < length; j++) {
      const code = view.getUint16(offset + j * 2, true) ^ cipher;
      cipher = (cipher + 0x493d) & 0xffff;
      if (code === 0xffff) { terminated = true; break; }
      let character: string | undefined;
      if (code >= 0x121 && code <= 0x12a) character = String.fromCharCode(48 + code - 0x121);
      else if (code >= 0x12b && code <= 0x144) character = String.fromCharCode(65 + code - 0x12b);
      else if (code >= 0x145 && code <= 0x15e) character = String.fromCharCode(97 + code - 0x145);
      else if (code >= 0x15f && code <= 0x19e) character = String.fromCharCode(192 + code - 0x15f);
      else character = ({0x1de:' ',0x1ac:'?',0x1ae:'.',0x1be:'-',0x1b3:'’',0x1b1:'/',0x1bd:'+',0x1c2:'&',0x1b9:'(',0x1ba:')',0x1bb:'♂',0x1bc:'♀',0x1c4:':'} as Record<number,string>)[code];
      if (character === undefined) supported = false;
      else name += character;
    }
    if (!terminated) throw new EditorError('invalid-reference', 'Unterminated item name.');
    result.push(supported && name.trim() ? name : undefined);
  }
  return result;
}
