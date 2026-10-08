# Five Island code investigation — 2026-10-08

This independent static audit explains why sprite 349 with movement type 17 can make the same invalid texture request in Five Island and Rocket HQ. It does not change the experimental patch, ROMs, saves, or production build scripts. Local reproducible assertions are in ignored `work/build/five-code/audit.py`, with results in `static_chain.json`.

## Resource assignment

All addresses in this section are the original Chinese v4.0.3 runtime addresses, after decompression of overlay 1.

| Stage | Address | Result |
|---|---|---|
| Sprite lookup table | `02206398` | Six-byte rows, lookup routine `021F8324` |
| Sprite 349 row | `02206848` | u16 values `(349, 243, 0x5C00)` |
| Descriptor lookup | `021F928C` | Extracts packed field bits 10–15, yielding descriptor 23 |
| Descriptor 23 | `022062C0` | bytes `00 00 05 00 FC 5F 20 02` |
| Model selector map | `02206184` | Selector 5 maps to `a/0/8/1` member 269 |
| Animation selector map | `022061BC` | Selector 0 maps to member 280 |
| Direction ranges | `02205FFC` | Four triples `(0,15,0)`, `(16,31,0)`, `(32,47,0)`, `(48,63,0)` |

The descriptor assigns the ordinary generic direction/frame animation to this barrier. This resolves the previous 280-versus-286 byte-match ambiguity at the static configuration level: its default is member 280. Both members contain identical bytes.

The same sprite row, descriptor values, model selector mapping, animation selector mapping, and direction ranges exist in vanilla USA at relocated addresses (`02207958`, `022073D0`, `022072A0`, `022072CC`, `022070D8` respectively). Members 243, 269, 280 and 286 are byte-identical between Chinese and USA. Thus the evidence does not support corrupted artwork or a translation change to this resource configuration.

## Why movement 17 fails while movement 0 does not

Movement type here is the map object's behavior field, not a scripted movement action number.

The Chinese ARM9 movement callback pointer table is at `020F9FFC`. Index 17 points to descriptor `020F9E38`; its initializer `0206086C` passes direction **3** to common initialization at `02060800`. Its update routine `02060824` applies that stored direction once through `0205E40C`. The latter writes the object's current facing at offset `0x28`, preserving the previous value at `0x30`, unless object flag `0x80` suppresses facing changes. Neighboring movement types 14, 15 and 16 select directions 0, 1 and 2 respectively.

Movement type 0 points to descriptor `020F9CD0`, whose callbacks at `0205EE30`, `0205EE34`, etc. simply return. It therefore leaves the event's initial facing intact. For the compared barrier records that initial facing is 0. Type 17 overrides it with direction 3.

Renderer `02024604` obtains animation time from render-object offset `0xB8`, taking bits 12–27, and passes it to `02027254`. The animation's 16 keys are at times 0, 4, 8, ..., 60. Their texture indices are `0,8,9,10,11,12,13,14,15,1,2,3,4,5,6,7`; every palette index is zero. The fourth directional range starts at time 48, selecting texture index **4**. Texture member 243 has only one texture, index **0**. The existing bounds check then takes the NULL-producing path to the load at `02024696`.

The map records independently identified by the static-map agent use the same combination: Five Island event member 149 object 12 at `(103,52)`, and Rocket HQ event member 233 object 13 at `(51,4)`, both sprite 349, movement 17, initial facing 0. Other HQ barriers use movement 0. The runtime agent independently observed index 4/count 1 on Five Island. These are mutually consistent code, configuration and runtime observations; this audit alone does not claim an end-to-end graphical reproduction.

## Fix assessment

Changing the two defective map object movement fields from 17 to 0 is a narrow data-level correction worth a separate fresh-map test: a static barrier needs no forced direction changes, and preserving its event initial facing 0 selects its only valid texture. It is narrower than altering a shared animation member, which also serves other sprites. No such data patch was made by this audit.

However, a data-only change is not sufficient evidence of compatibility with existing saves. The original game's save/restore code persists movement type and current/next facing in each saved map object and restores them directly. Consequently a save already containing the bad object can retain movement 17 and facing 3 even when its event template is changed. This is an inference from the [upstream save/restore implementation](https://github.com/pret/pokeheartgold/blob/master/src/map_object.c#L398-L449); a Chinese old-save comparison is still needed to establish the exact refresh behavior. Returning to the title screen is not a guaranteed substitute for recreating the map object.

The existing defensive ARM9 branch fix therefore remains the stronger compatibility candidate for already affected saves: it handles the invalid renderer request regardless of where movement/facing came from. It leaves valid updates, collision, event flags and story state untouched. Its broader behavior—preserving the previous binding for any invalid texture index—still merits regression coverage. A movement correction plus the guard could address both erroneous input and resilience, but this audit does not recommend shipping either without the root agent's runtime results.

## Limits

No full Five Island story progression, clothing variants, save migration, or additional sprite classes were tested by this agent. The callback and resource chain above is verified against the supplied Chinese ROM; symbolic names were cross-checked against the [upstream map-object implementation](https://github.com/pret/pokeheartgold/blob/master/src/map_object.c). No repository data or external tools were downloaded.
