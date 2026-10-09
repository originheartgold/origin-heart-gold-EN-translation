# Origin badge layout

Origin v4.0.3 uses a different first-badge offset from the US HGSS profile. Profile starts at general-block `+0x64`; badge IDs 0–7 use profile `+0x1c` (general `+0x80`), and IDs 8–15 use profile `+0x1f` (general `+0x83`). Origin's gym scripts award Kanto IDs 0–7 and Johto IDs 8–15 (`work/notes/softlock_audit.md`).

Verified by reading the user's local English rc5 ROM's native ARM9 code, without changing the ROM. The ARM9 header maps the image at `0x02000000`. The relevant Thumb instructions are:

| Address | Instruction bytes | Meaning |
|---|---|---|
| `0x02029434` | `03 7f` | `ldrb r3, [r0, #0x1c]` — first badge bank reader |
| `0x02029444` | `c3 7f` | `ldrb r3, [r0, #0x1f]` — second badge bank reader |
| `0x02029460` | `03 7f` | first badge bank setter reads `+0x1c` |
| `0x0202946a` | `01 77` | `strb r1, [r0, #0x1c]` — first badge bank writer |
| `0x0202946e` | `c3 7f` | second badge bank setter reads `+0x1f` |
| `0x0202947a` | `c1 77` | `strb r1, [r0, #0x1f]` — second badge bank writer |

The earlier editor read/wrote first-bank badges at `+0x7e`. Nonzero unrelated profile bytes therefore appeared as earned badges. Correcting the offset fixes both rendering and editing; no badges are inferred from party level, gym progress, defaults, or prior sessions. Badge state comes only from the newest checksum-valid general block selected by the save reader.

Regression tests use nonzero neighboring fields, zero earned badges, and an older mirror with all badges. They check both mirrors, all sixteen individual bits, read immutability, and preservation of unrelated bytes when editing.

Native reader/setter region `0x0202942a–0x02029480` SHA-256: `6f95d1027d6d22704d5a5d5309858ee6841f04ac34c83a0390e57da88be8ed02`.
