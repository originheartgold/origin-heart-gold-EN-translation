# Text metrics, box limits and the QA gate

**Status (reviewed 2026-09-29): current for the engine facts (fonts, boxes, control codes, placeholder widths); §7 (the name-bank pilot) and §8 (open points) are historical and annotated.**

Status date: 2026-09-28. Measured on `work/rom/origin_v4.0.3_cn.nds` (the real v4.0.3 build) and on
`work/rom/Pokemon - HeartGold Version (USA).nds`. The engine facts come from pret/pokeheartgold, which
builds the same USA ROM; its font files are byte-identical to the USA ROM's font NARC.

Files:
- `work/tools/font_widths.json`: per-character advance widths for fonts 0/1/2/4, in two sets
  (`hack_v4` and `vanilla_us`), plus a diff between them.
- `work/tools/textmetrics.py`: shared metrics library. `build-widths` regenerates the JSON; `width`
  measures a string.
- `work/tools/qa_config.json`: box categories, the bank → category map, placeholder width estimates
  and glossary settings.
- `work/tools/qa.py`: `check` (the QA gate) and `wrap` (automatic line breaking).
- `work/tools/ws.py`: the workspace (`init` / `export` / `stats` / `import` / `set`).
- `work/tools/fill_names.py` (removed 2026-10-09): pilot that filled the name banks from the glossary.
- `work/tools/test_qa.py`: 47 tests (28 when this note was written). Run them with `python3 -m unittest -v work/tools/test_qa.py`.

## 1. Font (`a/0/1/6`)

| file | role (pret `FontID`) | notes |
|---|---|---|
| 0 | FONT_SYSTEM: menus and UI | 7332 glyphs (Latin + kana + 6813 hanzi) |
| 1 | FONT_MESSAGE: dialogue and battle messages | used by `DialogBox`/`RenderText` with fontId 1 |
| 2 | FONT_SPECIAL | Latin is 1 px wider (7 px) |
| 3 | vanilla-size 509-glyph font | not used for text |
| 4 | other UI font | the hack **redrew** the Latin glyphs here; see below |

- **Advance width** is the width-table byte and includes the 1-px shadow column.
- **Spacing:** `letterSpacing` = 0 and `lineSpacing` = 0 for fonts 0–4 (pret `src/font.c` `sFontInfos`).
- **Line width** is therefore just the sum of the advances. Line height is 16 px.
- **Hanzi** sit outside the 512-entry width table. They advance a fixed 12 px (13 px in font 4).

### The hack's half-width Latin is the vanilla Latin
The tooling notes said the Latin glyphs were "condensed 5–6 px". **They are not condensed.**
- In fonts 0, 1 and 2, the glyph bitmaps and widths for `0–9 A–Z a–z` (0x0121–0x015E) and ordinary punctuation (all but `~` in fonts 1 and 2) are **byte-identical to the USA ROM**. That holds for the half-width Latin range only: the table below lists every code that differs (checked against the USA ROM, all codes 0x0001–0x01FD, 2026-10-08).
- The vanilla US font is itself near-monospaced: almost every letter is 6 px, with i=3, l=4, f=5, j=5, space=4, `, . : ;`=5 and `’ ‘`=5.

The differences between hack and vanilla are all in `latin_width_diffs_hack_vs_vanilla` in the JSON:

| code | char | vanilla | hack (fonts 0/1/2) | impact |
|---|---|---|---|---|
| 01AF | … | 6 | **12** | redrawn as a CJK-width ellipsis |
| 01B4/01B5 | “ ” | 6 | **12** | redrawn as CJK-width quotes |
| 01B7/01B8 | 《 》 | 6 | 12 | Chinese book-title marks |
| 0177 | Ø | 6 | 7 (font 0) | – |
| 0197 | ø | 6 | 6, another glyph (font 0) | – |
| 01C3 | ~ | 6/7 | same width, another glyph (fonts 1, 2) | – |
| font 1 | Æ Ð Ø Þ æ ð ø þ ° _ ＿ | 5–10 | **0 (blank)** | glyphs removed from the message font |
| font 1 | Œ œ | 10 | 7/8 | – |
| font 1 | Ş ş | 6 | 6, other glyphs | – |
| 00E1–00F9 | full-width punctuation (part) | 5–11 | 12 (fonts 0–2), 13 (font 4) | CJK-width; 00E1–00E4, 00EC, 00ED, 00F5–00F7, 00F9 in every font, all of 00E1–00F9 in font 1 |
| 00CC | ｇ | – | another glyph (font 0) | – |
| font 1 | 0002–0120 | – | redrawn (kana, full-width) | not used by the English |
| 01E3–01E7 | (spacing codes) | 1–16 | 0 (font 1) | – |
| 01EB, 01EC | (spacing codes) | 2–5 | 0 (fonts 0–2, 4) | – |
| 01F0–01FD | – | 0 (empty in the USA font) | 12 (13 in font 4) | added by the hack |
| font 4 | all Latin redrawn | 7 | 7 (same widths) | Ã Å Õ Ý ÿ Ş ş ₧ ₦ ° _ etc. blank; space 5 → 7 |

`é` (Pokémon) is intact in every font.

**Which widths to target:** the QA default is `"font_set": "vanilla_us"`, following the plan to restore the vanilla Latin glyphs. The vanilla widths are the ones the official US text was laid out against (§3). This choice only matters for the few characters in the table above:
- **`…`, `“` and `”`:** under the default, QA also re-measures every line with the hack widths. It emits `needs_vanilla_glyphs` (warning) where the line fits only if those glyphs are restored.
- **To gate against the ROM as shipped:** use `--font-set hack_v4`.
- **Missing glyphs:** under `hack_v4`, `Æ Ø` etc. in dialogue are an error (`missing_glyph`).

**Recommendation for the build (done: `build.py` stage 3 restores … “ ” in fonts 0/1/2/4 from the USA font):** restore at least glyphs + widths for codes `0x01AF`, `0x01B4` and `0x01B5` (… “ ”) in fonts 0/1/2 from the US font, once no Chinese text uses them. Also restore font 1's blank accented glyphs if any name or text needs them.

## 2. Boxes

| box | source | size | usable | lines per view |
|---|---|---|---|---|
| field / script dialogue | pret `src/dialog_box.c` `DIALOG_BOX_X/Y/W/H` = 2, 19, **27, 4** tiles | 216 × 32 px | **216 px**, printed at x=0 | **2** |
| signpost with a map graphic (dialog types 0/1) | same file: x += 7, w = 27 − 7 | 20 × 4 tiles | **160 px** | 2 |
| battle message box | `ov12` `AddWindowParameterized(bg1, 2, 0x13, 0x1B, 4, …)` | 27 × 4 tiles | **216 px** | 2 |
| most app message windows (options, naming, berry pots, …) | `AddWindowParameterized(…, 2, 19, 27, 4, …)` | 27 × 4 tiles | 216 px | 2 |

Chinese source check: the longest Chinese dialogue lines are 18 hanzi × 12 px = **216 px**, so the hack uses the same box.

### Control codes: behaviour (pret `src/render_text.c`)

| msgtool tag | code | pret | what the printer does |
|---|---|---|---|
| `{NEWLINE}` | E000 | `\n` | x = 0, y += 16 |
| `{SCROLL}` | 25BC | `\r` | wait for A, **clear the box**, restart on line 1 (new page) |
| `{CLEAR}` | 25BD | `\f` | wait for A, **scroll up one line**, continue on the *current* (bottom) line |

The msgtool tag names are the opposite of the behaviour. The tooling notes (§3.3) say `{SCROLL}` = "scroll one line", which is wrong; the table above follows the engine code. Tags are only labels, so nothing is broken, but translators should read `{SCROLL}` as "new page" and `{CLEAR}` as "scroll one line".

Consequences:
- **After a `{CLEAR}`, the next break must be `{CLEAR}` or `{SCROLL}`.** A `{NEWLINE}` would open a third line.
- **Page model** (`textmetrics.page_lines`): `y` starts at 0. `NEWLINE` adds 1 to `y`. `SCROLL` sets `y` to 0. `CLEAR` keeps `y`. A trailing `NEWLINE` with nothing printed after it does not count. Checked against the data:
  - **US:** 8,146 of 8,147 US dialogue strings stay within 2 lines. The one exception is the 3-line Aprijuice sign, bank 0021.
  - **Chinese:** 17,702 of 17,754 v4 Chinese dialogue strings stay within 2 lines. The 52 exceptions are source bugs or bigger boxes; QA then only warns.

### Measured screen limits (emulator, 2026-10-05)

These come from the emulator harness on the English build, not from the US text, and live in
`qa_config.json`. QA reports them with the codes in brackets.

| screen | category | limit | how it was measured |
|---|---|---|---|
| Bag / Poké Mart item description (a027/0218, pocket descriptions 0010 #120–127) | `item_desc` | 3 lines; **215 px** error (window edge), **200 px** warning [`line_past_frame`]; **114 stored units** incl. the terminator [`too_many_units`] | The window is 27×6 tiles at x=40 (template `02 05 12 1B 06` in overlay 3, identical in the US ROM). The grey panel ends at x=239, then the frame starts. A line of *w* px covers x=40…39+*w*, so 200 px is the widest line that clears the frame (D-1512). Vanilla US uses the same window and panel graphics (`a/0/1/5` files 7–9 identical), and its own lines reach 215 px, so wider lines are a warning, not an error. The bag, the shop and an overlay-9 consumer allocate `String_New(114)` (`item_description_fix_proposal.md`): a longer description shows a blank panel (D-1507: 113 units plus the terminator show, longer ones are blank). `qa.py wrap` wraps at 200 px when three lines still suffice, else at 215 px. |
| Pokédex entry page, category (a027/0803) | `dex_category` | font px + characters ≤ **125** | The category (with " Pokémon") is drawn at x=120 with 1 px between characters; the last visible column is x=246 (127 px). On all 709 entries the rendered width was font px + characters + 2 (D-1520). New key `char_spacing` adds 1 px per character to the measured width. |
| Pokégear map card, place description (a027/0266 #9–117) | `gear_map` | 2 lines, **208 px** | Window 26×4 tiles at x=24 (hack overlay 92 template `05 03 0E 1A 04`). The hack is built on the Japanese ROM; US widened this window to 28 tiles at x=8 (`05 01 0E 1C 04`), so US lines up to 218 px no longer fit (D-1524). |
| Pokégear map card, towns and cities (0266 #10–29, #31) | `gear_map_town` | **168 px** | The town picture starts at x=193; text starts at x=24. Picture seen on 14 towns in a cursor sweep over the map (the rest of #10–31 are assumed to have one too); routes, caves and Lake of Rage have none. |
| Battle window, a string that waits with a prompt (`{VAR:0200:..}`: the command prompt, YES/NO; battle_string 2#32, #64, #73, #479) | `battle` + `prompt_px` | **195 px** on the lines of that view [`prompt_icon_overlap`] | Two prompt icons are drawn at x=211–228 of the battle window (text origin x=16). 2#32 'Should another move be forgotten to' (197 px) ran its 'o' under them (emulator sweep, `emu_sweeps.py battle`, 2026-10-06). |
| Battle window buffers (battle_string) | `var_widths.by_narc` | move {VAR:0107} and ability {VAR:0106} 48/72 px (typ/max), nickname {VAR:010C} 54/60 | The battle's own buffer kinds differ from a027's (0107 is a move, not a 7-px-per-char stat). Seen cut at the window edge: 'Maximilian wants to learn DragonBreath..', 'The wild Kangarooey took the Future Sig'. Numbers print with the full-width digit codes (7–8 px each, as in the Chinese ROM; D-1567). |
| Summary, skills page: move description (a027/0738) | `move_desc` | 5 lines, **120 px** | Read back on all 903 described moves (`emu_sweeps.py desc`): text starts at x=136 on the bottom screen's ruled panel and the panel ends at the screen edge (120 px). Agrees with QA. |
| Summary, skills page: ability description (a027/0712) | `ability_desc` | 2 lines, **139 px** visible (QA keeps 136) | Text at x=8, y=152 and 168 on the top screen; the divider starts at x=147. All 327 descriptions read back; QA's 136 px (US maximum) stays the limit. |

Per-string categories for banks that mix screens are in `qa_config.json` → `string_categories`
(`{"a027/0266": {"9-117": "gear_map", "10-29,31": "gear_map_town"}}`; later keys win, a string's own
`category` field wins over both).

## 3. Calibration against the official US text (`work/extract/us/a027`)

| measure | result |
|---|---|
| dialogue lines (strings with `{SCROLL}`/`{CLEAR}`), no placeholder | 33,031 lines, **max 216 px**, none over (vanilla widths) |
| same, lines with placeholders, typical estimates | 3,405 lines, max 208 px, 0 over 216 |
| same, worst-case placeholder estimates | 3 lines over 216 (221 px) → QA warning level only |
| pret gmm cross-check (36,436 dialogue lines) | p50 128 px, p99 213 px, max 216 px |
| US name maxima (chars) | species 10 (bank 0237), items 12 (0222), moves 12 (0750), abilities 12 (0720), types 8 (0735), natures 7 (0034), locations 16 (0279) |

The 216-px limit is therefore exact. The US localisers filled lines right up to it.

## 4. Placeholder widths

`{VAR:01KK:…}` is STRVAR_1, where KK is the kind; the estimates live in `qa_config.json` (`var_widths`), with 6 px per character:

| kind | used for (pret usage) | typ | max |
|---|---|---|---|
| 00, 01, 02 | species / nickname / battle Pokémon | 54 | 60 |
| 03 | player / trainer name (7 chars) | 36 | 42 |
| 04 | location | 66 | 102 |
| 05, 06, 08, 09 | ability / move / item | 60 | 72 |
| 0D | stat | 42 | 60 |
| 0E | trainer class | 60 | 78 |
| 0F | type | 36 | 48 |
| 32–3B | numbers | digits × 6, where digits = kind − 49 | – |

- **Unknown kinds** default to typ 48 / max 72.
- **`02xx` and `FFxx`** (YESNO, PAUSE, WAIT, CURSOR, ALIGN, COLOR, SIZE) are 0 px.
- **`0203` CURSOR_X** sets x absolutely.
- **`FF01` SIZE** changes glyph height, not advance width, in this hack. At 200%, one line occupies the full 32 px dialogue height. See `heap_audit.md` and the native renderer evidence in `work/build/text-exception-verification/native-size-semantics.json`.
- **battle_string** has its own table: 0100 = trainer name/class, 0102 = Pokémon.
- **Thresholds:** `line_too_wide` is raised at *typ*; `line_may_overflow` (warning) at *max*.

## 5. QA gate (`qa.py check`)

**Categories:**
- **Bank → category** comes from `qa_config.json` `banks`.
- **Otherwise**, a bank is `dialogue` if any zh string contains `{SCROLL}`/`{CLEAR}` (553 banks), else `ui` (257 banks).
- **`ui` banks** have no known box, so QA only warns when an English line is wider than the widest Chinese line in that bank, or has more lines than the Chinese.
- **Overrides:** a workspace bank file can set a top-level `"category"`, and a single string can too (e.g. `"sign"`).
- **Larger source boxes:** if the zh string itself has a line wider than the box, the box is evidently larger, and an overflow up to that width is downgraded to a warning.

For the list of error and warning codes, see the docstring of `work/tools/qa.py`.
- **Exit status:** 1 if there are any errors.
- **Output:** `--json FILE|-` writes a machine-readable report `{summary, issues:[{narc,bank,id,level,code,msg,category}]}`.
- **Suppression:** per string with `"qa_ignore": ["glossary:术语", "number_missing", …]`.

### Warning interpretation (reviewed 2026-10-04)

A zero-error exit is not translation acceptance. Existing warnings remain a
review backlog; an unchanged count is not a waiver. The warning inventory tool
can reconcile reports and independent reviews without adding any `qa_ignore`.

Whitespace checking preserves printed placeholders as occupied text and removes
only nonprinting controls. It must not invent a leading/trailing/double space
by deleting a player name or number placeholder. Numeric matching reads literal
tokens separately, so digits separated by layout or variable tags do not merge
into a fictitious number. It still warns for unmatched counts and spelled-out
numbers: an English number word alone does not establish the correct referent
or ordinal meaning. Currency checks distinguish actual amounts from the word
元气 (including the Revive item names).

Prose glossary matching recognizes the exact route number in the `Route N`
template and the count-noun plurals `Berries`/`Candies`, preserving full named
item identity. Atomic name banks still require their exact allowed names.
Generic-word collisions, abbreviations, source legacy names and decision-scope
exceptions remain contextual review work, not blanket ignored categories.

Relative UI width/height warnings do not prove fit or overflow. Those categories
lack a measured screen-specific box; retain the warning until actual window
evidence or a reviewed categorization establishes the appropriate limit.

**Validation run:**
- **Setup:** the QA was run over the whole official US text as if it were a translation (en = zh = US).
- **Result:** 0 tag, encoding, width or line errors, apart from 1,906 `cjk` errors on the Japanese dummy strings that the US ROM still contains. So the checker raises no false positives on shipped, correctly laid-out English.

## 6. Auto-wrap (`qa.py wrap`)

Translators write plain prose. `wrap` then computes the breaks:
- **Blank line (`\n\n`):** paragraph break. When the number of paragraphs matches the zh's internal `{SCROLL}`/`{CLEAR}` breaks, paragraph *k* ends with the zh's *k*-th break type. Otherwise every paragraph break uses the default.
- **Single `\n`:** forced line break.
- **Filling lines:** words fill each line greedily up to 216 px, with placeholders at their typical width. `{NEWLINE}` is used while the box has room.
- **Overflow:** continues with the continuation break. `--mode page` gives `{SCROLL}` (new box), `scroll` gives `{CLEAR}` (scroll one line), and `auto` uses `{CLEAR}` if the zh uses only `{CLEAR}` breaks, else `{SCROLL}`.
- **Trailing tags:** the zh's trailing layout tags (e.g. a final `{NEWLINE}`) are appended.
- **Quotes and dashes:** ASCII `'` and `"` become `’ ‘ “ ”`, and `—`/`–` become `-`. The font has no ASCII quotes, so they are unencodable.
- **Bank mode:** `qa.py wrap translate/banks/a027/NNNN.json --in-place` wraps every string whose `en` has no layout tags yet. `--reflow` redoes the ones that already have tags.

## 7. Pilot: name banks (glossary fill)

| bank | content | strings | filled | how |
|---|---|---|---|---|
| a027/0232 | species (dex 1–1025, then forms that repeat the base name) | 1439 | 1438 + 1 placeholder copy | glossary 1058, PokéAPI name 354, index 26, abbreviated 40 |
| a027/0739 | moves (index = move id) | 921 | 902 + 19 empty/dash copies | glossary 390, PokéAPI name 495 (incl. Z-moves `<species>Ｚ<name>`), index 14, agent 3, abbreviated 170 |
| a027/0711 | abilities (customs after 310) | 327 | 326 + 1 dash copy | glossary 248, PokéAPI name 74, agent 4 |
| a027/0219 | items (Gen 4 index ≤ 536, hack additions after) | 791 | 791 | glossary 396, PokéAPI name 214, rule (TM/HM/Data Card/???) 166, index 7, agent 8 |
| a027/0724 | types (Gen 4 order, Fairy in the ??? slot) | 18 | 18 | glossary 15, index 3 |
| a027/0033 | natures (Gen 4 order) | 25 | 25 | index 25 |

- **Status:** everything is `draft`. The origin records the source (`glossary`, `pokeapi-name`, `pokeapi-index`, `rule`, `index`, `agent`, with `+abbrev` where shortened), and the notes carry the evidence for index or agent decisions.
- **QA result:** 0 errors and 0 warnings on all six banks. Every name is within its limit (species 10, moves/items/abilities 12, types/natures 8), is encodable, and matches the glossary.

**Index fallback** is used only when both conditions hold:
1. the nearest name-matched neighbours on both sides sit at their official ids;
2. the hack's zh shares at least one character with the official zh name.

The second condition rejects repurposed slots. For example, slot 324 is 凹凸头盔, which is Rocky Helmet, not Dubious Disc; the glossary resolves it correctly.

**Abbreviations:**
- The glossary README table (`manual_overrides.ABBREV`) comes first.
- Then `LOCAL_ABBREV` (first in `fill_names.py`, now in `work/glossary/manual_overrides.py`), 265 new ones in the same Gen 4/5 style, e.g. `Iron Valiant → IronValint`, `Hyperspace Hole → HyprspceHole` and `Ability Capsule → AbilityCapsl`. The glossary owner may want to merge these into `manual_overrides.py`.

**Agent-chosen names that need review** (see the `notes` field):
- items: 114 钢铁铠甲 "Steel Armor", 438 防水服 "Wetsuit", 440 装徽章的袋子 "Badge Case", 479 战利品 "Spoils", 744 连锁记录仪 "Chain Logger", 745 能力分配器 "EV Allocator", 761 忍者卷轴 "Ninja Scroll";
- move 920 岩石风暴 "Rock Storm";
- Embody Aspect's four form entries → "EmbodyAspect".

## 8. Open points

Review 2026-09-29: 1 is decided (mixed case, glossary); 2 is moot, because the English is wrapped to 216 px and QA gates it; 3 stays open (only strings found so far carry `"category": "sign"`); 4 is solved for script menus (follow-up 1 measured their real widths, categories `menu_*` in `qa_config.json`), other UI labels still get relative warnings.

1. **Species capitalisation.** Gen 4 US shows species (and types) in CAPS: `BULBASAUR`, `FIGHTING`. The glossary uses modern mixed case, and the pilot follows the glossary. This is a style decision; widths are unaffected, because caps are also 6 px.
2. **v3 Eng overflows.** The v3 Eng patch has 866 dialogue lines wider than 216 px, up to 885 px. Either v3 Eng simply overflowed, or the hg-engine-based v4 renderer auto-wraps. The Chinese text is hand-broken at ≤216 px, which suggests no auto-wrap. **Verify in an emulator** before relaxing any limit.
3. **Signposts** (160 px) and other special windows can't be told apart by bank. Assign `"category": "sign"` per string when found (DSPRE script/sign data).
4. **`ui` banks** get only relative warnings. Menu and label box sizes need per-screen measurement if they turn out to matter.
