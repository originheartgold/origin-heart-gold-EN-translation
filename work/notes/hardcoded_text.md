# Hardcoded text (outside the message NARCs)

**Status (reviewed 2026-09-29): current.**

Status: 2026-09-29. ROM: `origin_v4.0.3_cn.nds`, which is built on the **Japanese** HeartGold (game code IPKJ, 120 overlays). The USA ROM has 129 overlays, so overlay numbers differ from the USA and pret numbers.

## Survey

We scanned these for Chinese text:
- arm9;
- all 120 y9 overlays (the hack has no extra overlay files, and every FAT file has a name);
- every other ROM file, every NARC member, and the LZ10-compressed members.

Files and members that are byte-identical to the USA ROM were skipped. `a/0/2/7` and `battle_string.narc` were excluded.

The scan looked for text in three forms:
- **The hack's charmap:** 16-bit runs in `0x0001–0x1C9B` / `0xE000`, ending in `0xFFFF`, with at least 2 hanzi. At least 60 % of their hanzi pairs must also occur in the game's own message text.
- **UTF-16LE, GB2312 and UTF-8:** runs with the same plausibility test.

To re-run it: `python3 work/tools/hardcoded.py scan ROM [--base USA_ROM] [--code-only]`.

**Player-facing results: 4 strings, all in overlay 58.** Overlay 58 is the hack's outfit chooser, shown in Oak's speech after "boy or girl".

| id | zh | slot | referenced by | en |
|---|---|---|---|---|
| overlay58:0x6F0 | 确认 | 2 chars + end | literal at +0x4E4 | OK (in place) |
| overlay58:0x6F6 | 形象1 | 3 + end | table +0x7C0 | Outfit 1 (relocated) |
| overlay58:0x6FE | 形象3 | 3 + end | table +0x7C8 | Outfit 3 (relocated) |
| overlay58:0x706 | 形象2 | 3 + end | table +0x7C4 | Outfit 2 (relocated) |

How the chooser uses these strings:
- The strings are packed back to back with no padding.
- The code copies each one into a `String` of capacity 16. This is `String_New(0x10)` followed by `CopyU16ArrayToString`, so a relocated label may be up to 15 characters long.
- The labels sit in a list menu in an 11×10-tile window, with the text starting at x=8 (about 80 px wide).

**Everything else the scan reported is noise:** move and tutor tables, sound data, and sprite data. The only other real Chinese in the ROM:
- `test/battle_test.narc`: UTF-8 descriptions from hg-engine's battle-test harness (for example 测试1: 降雨的正常触发). This is debug-only and not player-facing, so it is not in the pipeline.
- `pbr/msg.narc`: Japanese kana (the PBR link messages from the JP base). It is not Chinese and is not shown in normal play.

## Pipeline

The pipeline has four parts:
- **Data:** the fix `work/patches/outfit-chooser-strings/fix.toml`: one `[[string]]` entry per label (zh, en, slot size, pointers, relocation limit; translators edit `en` here, and `text_consumer_check.py` / `text_safety_check.py` read it through `hardcoded.load()`), and `[[grow]]` with `max = 64` for overlay 58.
- **Code:** the armips source `outfit-chooser-strings.asm` in the same folder writes the bytes; `work/tools/asmpatch.py` assembles it like every code and data fix (see `toolchain.md`). `work/tools/hardcoded.py` keeps the entry view, `RomView` and the survey `scan`.
- **Build:** stage 3c in `build.py` (`asmpatch.apply`), with its checks in `verify_rom` (`asmpatch.verify`).
- **Tests:** `work/tools/test_asmpatch.py` (the assembled overlay against golden SHA-1s, growth and string checks) and `work/tools/test_hardcoded.py` (the entries, the scan).

How the source writes each string:
- **Fits in place:** `.string` at the slot, the rest of the slot filled with `0xFFFF` (`OK`).
- **Too long for the slot:** appended to overlay 58 at its old end (`.org`, guard `expect_end`), the pointers repointed (`.word` behind a guard on the old target), the old slot blanked. The build updates the y9 `ramSize`.
- **Length class:** fitting in place or being relocated is written in the asm, not decided by the build. A new `en` that moves a label from one class to the other (longer than its slot, or short enough to fit it again) needs the matching change in `outfit-chooser-strings.asm`; with only fix.toml changed, the build refuses.
- **Refusals.** The build stops with an error when:
  - the ROM no longer holds the `zh` text, or a pointer no longer points at its slot (fix.toml and the asm's guards);
  - the asm's `.string` literals differ from the `en` values (`fixes.py check`), or the bytes read back are not `en`;
  - the English does not encode (armips: `Failed to encode`);
  - the English is longer than the slot in place, or than `reloc_max_units` relocated;
  - the growth is larger than the `[[grow]]` max, or leaves the overlay a size that is not a multiple of 4;
  - the overlay has .bss;
  - another overlay starts inside the grown range.

In-game check: the chooser shows the English labels, the cursor works, and OK leads to the naming screen. Screenshots: `work/build/screens/hardcoded_*.png`.

## Name lengths

The naming-screen limit is the `maxLen` argument of `NamingScreen_CreateArgs` (hack address `0x02081DA4`; the USA address is `0x020830D8`).

| Name | Hack | USA | Call sites (hack) |
|---|---|---|---|
| Player | 5 | 7 | ov49 +0x4E (Oak's speech); arm9 0x02042862 (script) |
| Rival | 5 | 7 | ov49 +0x66; arm9 0x02042892 |
| Pokémon nickname | 5 | 10 | arm9 0x0204291E (script nickname); arm9 0x02090944 (egg hatch). The battle-capture call was not found statically (USA ov12). |
| Group | 5 | 7 | arm9 0x020490DA |
| Kind 7 | 5 | 7 | ov44 +0x2E6C |
| Box | 8 | 8 | unchanged |

**Default names.** When the name is left empty, the naming screen fills it from bank 0247:
- male player: a random entry from #0–17;
- female player: a random entry from #18–35;
- rival: #84.

These are **not** cut to `maxLen`. They are copied into `nameInputFlat[10]` and then into the save's 8-unit player-name buffer (7 characters). The current English defaults are all 5 characters or fewer: Red, Ash, Dummy, Heart, Green, Leaf, and Soul for the rival.

"Silver" (#37–49) and "NEW NAME" (#36, #78) are DP-era leftovers. No code reads them (the only load of bank 0xF7 is in the naming screen). Even if the game read them, 6 characters fit the 7-character buffer. **No default name needs shortening.**

The patches that raise the limits to the USA values are the fix `work/patches/namelen/` (`namelen.asm`, regions `namelen-*` in `fix.toml`; armips, see `toolchain.md`). They are **enabled**: the user checked in melonDS that trainer names take 7 characters and nicknames 10.

## Naming keyboard (English)

The hack's keyboard (Japanese base) has four tabs. Page N uses the rows `sKeyboardLayoutPtrs[N][0..4]` (pointer table at arm9 `0x0210F688`, 5 pages × 5 rows; each row is 13 keys + `0xFFFF`). The screen opens on page 0.

| Tab | Hack | Now | How |
|---|---|---|---|
| 1 (page 0, opens first) | かな: pinyin IME. QWERTY letters go into a pinyin buffer (`data+0x5E4`); candidates from `a/0/3/1` #19/#20 fill rows 1–2 (lookup `0x020835E4`); picking one commits hanzi | **ABC**: the hack's ABC layout (A–M, N–Z, a–m, n–z, 0–9 . ,) in Western codes `0x0121–0x015E` | `naming-abc-row1..5` (`naming-keyboard.asm`); tab art = the hack's own "ABC" label |
| 2 (page 1) | カナ → a–z, A–Z, 0–9 (Western) | unchanged (**abc**) | – |
| 3 (page 2) | full-width ＡＢＣ (`0x00AC–0x00DF`, ０–９) | **QWE**: blank row, 1–0, QWERTYUIOP, ASDFGHJKL ' -, ZXCVBNM , . (Western) | `naming-qwe-row1..5`; tab art "QWE" |
| 4 (page 3) | 1/♪ full-width symbols | unchanged | – |

- **IME off:** `naming-ime-off` changes `bne 0x02083CF8` at `0x02083C24` (in the key handler `0x02083814`, the hack's `NamingScreen_HandleCharacterInput`) to `b`. Every key now takes the normal insert path, so the pinyin buffer stays empty and the candidate rows, ← → paging and the pinyin BACK path never run.
- **Why the full-width page went:** its glyphs are 9–11 px wide in message fonts 1/2/4 (Western letters 6–7 px), so names typed on it look spaced out in dialogue.
- **Why ABC is on page 0:** that makes it the default without touching the init code. Changing the default page would need 5+ patches (pageNum, layout, window fill `0x0D0D` with no literal in range, BG screen id, tab highlight).
- **Checked in DeSmuME** (`work/build/screens/naming_fix_*.png`): the screen opens on ABC, every tab types, BACK and d-pad + A work, and the entry buffer holds the Western codes. The dialogue shows "Your name is An1zQ5!?".

## Nickname prompt after a catch

**The hack removed it on purpose; our build matches.** The untouched Chinese ROM never asks "Give a nickname to the caught X?" after a catch.

Evidence:
- The battle overlay (ov14, `0x022007E0`) has no reference to the naming-screen template (`0x02101474`) or `NamingScreen_CreateArgs` (`0x02081DA4`).
- It also never loads message 0195#868 (`0x364`).
- The US battle overlay does both (ov12 `0x0224706C`, `0x02246CD2`). Every other naming caller kept its reference.
- The hack's own post-catch sequence (ov14 `0x0222FCDC`) prints battle_string 2#57 "…added to the Pokédex!", shows the Pokédex page, then prints 2#480 "…joined the party!" or 2#481 "…was sent to the PC box!".
- hg-engine has no option for this.
- Our ov14 is byte-identical to the Chinese ROM.

Players can still nickname at the Name Rater. Decision: D-1040.

