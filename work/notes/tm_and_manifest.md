# Translation memory, bank maps and manifest (v4.0.3)

**Status (reviewed 2026-09-29): historical.** Describes how the translation memory, bank maps and the first batch plan (`manifest.json`, B001–B142) were built on 2026-09-28. The translation is finished; the R batches in `manifest_playorder.json` replaced the plan, and the seeding files it describes are local-only (see `.gitignore`). The seeding scripts were removed on 2026-10-09 (cleanup); `git log --diff-filter=D -- work/translate/scripts` finds them.

Status date: 2026-09-28. Everything described here lives in `work/translate/`. Scripts are in `work/translate/scripts/`; all of them read `work/extract/` and never write there.

## 0. Headline numbers

| | value |
|---|---|
| v4 text to translate | 60,821 CJK strings, 1,053,280 CJK chars. a027 has 57,951 / 1,025,066 and battle_string has 2,870 / 28,214 |
| v3→v4 bank map | 814 v3 banks map to v4 0–813 with **offset 0 everywhere**. 810 high, 4 medium/structural. v4 814–816 are new |
| v4→US bank map | 814 banks matched: 592 high, 201 medium, 21 low. 15 US-only banks, 3 v4-only banks |
| TM pairs (v3 Cn/v3 Eng) | 17,489 pairs, 15,453 unique zh keys. 16,696 are "clean". 611 zh keys have more than one English variant |
| TM exact on v4 | **19,193 strings (31.6%) / 214k chars (20.3%)**, plus 224 exact_loose (tags differ) |
| TM fuzzy on v4 (review only) | 372 at ≥0.90 and 765 at 0.80–0.90 |
| Official US text reusable (a027) | likely: 21,037 strings (36.3%) / 251k chars (24.5%); possible: 1,224 more |
| TM exact ∪ US-likely | **28,258 strings (46.5%) / 356k chars (33.8%)** already have a usable English draft |
| Batches | **142** (P0 14, P1 17, P2 75, P3 27, P4 9), all ≤600 strings and ≤15k CJK chars |

## 1. Files

| file | content |
|---|---|
| `bank_map_v3_v4.json` | v3 bank → v4 bank with `content_sim`, `containment_v3_in_v4`, `same_id_ratio`, `confidence` |
| `char_fold_v3.json` | 12 variant/mis-decoded characters, v3 ACG table → v4 (丟→丢, 掠→探, 泳→唦 …). Used only for matching |
| `tm_v3.jsonl` | One record per v3 bank/id: `{zh, en, v3_bank, id, zh_key, flags, en_variants, quality}` |
| `tm_v3_stats.json` | TM harvest statistics and flag counts |
| `tm_v4_matches.jsonl` | One record per v4 CJK string that has a TM hit: `{narc, bank, id, zh, tier, score, candidates[], tm_zh}`. Candidates are grouped by English, same-position ones first, then clean, then most frequent |
| `tm_v4_coverage.json` | Coverage summary and per-bank tier counts |
| `bank_map_us_v4.json` | v4 bank → US bank guess, with evidence (`content`, `tag_cos`, `count_sim`, `entity_sim`, `jp_name`, `jp_us_tag_agree`, `map_code_match`) |
| `us_reuse.jsonl` | One record per v4 a027 CJK string: `{bank, id, us_bank, us_id, verdict, xz_ratio, tags_match_jp, pages_match_jp, name_match, tm_us_sim, us_text}` |
| `us_reuse_summary.json` | Verdict totals and per-bank counts |
| `manifest.json` | Per-bank manifest (a027 + battle_string), category and priority totals, and the batch plan |
| `us_ref.json` | pret/pokeheartgold US bank metadata: gmm name, map code and map constants, source files that reference the bank, row ids, strings |
| `ref/jp_a027.json` | Vanilla **Japanese** HGSS a/0/2/7 (814 banks), decoded from Xzonn's `original_files` |
| `ref/vanilla_hgss.json` | Vanilla **Chinese** HGSS text (Xzonn's revision of the ACG translation) plus the JP dev bank names (`album`, `atkmsg`, `t07r0401`…) |

`work/translate/banks/` was not created by this pass, and nothing here touches it.

**Rebuild order:**
1. `align_v3_v4.py`
2. `build_tm.py`
3. `apply_tm.py`
4. `align_us_v4.py`
5. `us_reuse.py`
6. `build_manifest.py`

**One-off reference builders** (each needs a clone):
- `build_us_ref.py <pokeheartgold clone>`
- `build_vanilla_ref.py <PokemonChineseTranslationRevise clone>`
- `extract_jp_ref.py <…/original_files/HGSS/data/a/0/2/7>`

Every step runs in under 10 s.

**Licence note:** the Xzonn texts are CC BY-NC-SA 3.0. `ref/vanilla_hgss.json` is a local matching and reference aid; do not ship it.

## 2. Method

### 2.1 Normalisation (`common.norm`)
The match key is built in this order:
1. NFKC.
2. Fold 〜→~ and ⋯→….
3. Drop `{NEWLINE}`/`{SCROLL}`/`{CLEAR}` and all whitespace.
4. Apply the v3 character fold.

The *loose* key also replaces every `{VAR..}`/`{U+..}` tag with `§` and strips trailing punctuation/`~`. We translate into English and rewrap anyway, so line-break positions are irrelevant for matching.

### 2.2 v3 → v4 banks
- **Scoring:** the multiset overlap of normalised strings, taken from an inverted index, plus count similarity.
- **Alignment:** a monotone Needleman–Wunsch alignment.
- **Result:** the identity map for 0–813. v4 appended banks 814 (chain/shiny UI), 815 (stat labels) and 816 (the hack's intro, licence and credits notice).
- **Lower-confidence banks:** a few are rewritten in place: 233/236 TV scripts, 361/528/725 single strings, and 791, where the Pokédex text was replaced by 1,441 modern entries.
- **Character fold:** learned from aligned same-length strings that differ in 1–2 characters. A character is kept only if it (almost) never occurs in v4, which removes real edits such as 鳄→大.

### 2.3 TM harvest
Pairs are taken at the same bank/id from v3 Cn and v3 Eng.

**A pair is kept if all of these hold:**
- zh has CJK;
- en has no CJK;
- en ≠ zh after normalisation;
- en is not blank. 169 strings that v3 Eng blanked with spaces were skipped.

**Pairs dropped and why:**
- 34,464 v3 CJK strings are still Chinese in v3 Eng.

**Flags** (kept, not dropped):

| flag | count | meaning |
|---|---|---|
| `conflict` | 1,946 | same zh key, different English |
| `page_breaks_lost` | 297 | |
| `broken_tags` | 225 | `{U+…}` in en |
| `fullwidth_chars` | 216 | |
| `var_mismatch` | 213 | `{VAR}` command multiset differs from zh, colour ignored |
| `suspiciously_long` | 54 | often a misaligned or copied US string |
| `kana_leftover` | 45 | |
| `suspiciously_short` | 36 | |
| `format_tag_mismatch` | 29 | |
| `zh_unknown_codes` | 23 | |
| `literal_var_text` | 8 | e.g. "v0103" |

`quality = clean` means no flags other than conflict, fullwidth or format.

**Conflicts:** all variants are kept. `en_variants` counts them. Typical conflicts are UI words used in different contexts (返回 → Cancel/Back/Exit/Return) and CAPS vs mixed case.

### 2.4 Applying the TM to v4
Tiers, first hit wins:
1. **exact** (normalised key)
2. **exact_loose** (tags masked; the tags need re-checking)
3. **fuzzy90** / **fuzzy80**: difflib ratio on the loose key. Candidates come from a bigram index, with lengths within ±25–33%. Fuzzy hits are **never auto-accepted**; `tm_zh` shows the Chinese they were matched against.

**Coverage by NARC:**
- **a027:** 19,137 exact, 122 loose, 288 fuzzy90, 557 fuzzy80.
- **battle_string:** 56 exact, 102 loose and 292 fuzzy. It is a hack-only file, so the hits come from similar vanilla battle lines. The fuzzy hits are mostly `{VAR:0101}`→`{VAR:0102}` changes.

**Where the hits sit:** 16,180 of the exact hits are at the same bank/id as their v3 source. 3,013 are the same text in another bank (duplicates).

### 2.5 v4 → US banks
Vanilla chain: v4 bank b (0–813) is JP/CN bank b, because the layout is identical. The US ROM has 829 banks because it adds localisation banks.

**US-only banks** (15, found by the alignment):
- plural/article variants of names: 16, 217, 223, 224, 238, 731;
- ALL-CAPS easy-chat copies: 721, 751;
- Voltorb Flip: 39;
- month abbreviations: 239;
- map banks 511 (T07SP0101) and 603 (T25SP0101);
- Pokédex slots 811, 822, 828.

**Method:** a DP over a non-decreasing offset of 0–15. The pair score combines:
- **map code:** the JP dev name (`t07r0401`) must equal the pret gmm suffix. This is decisive.
- **same-id command agreement** between the JP and US strings;
- English evidence: v4 Latin leftovers, v3 Eng lines, and glossary names matched against US text;
- names mentioned in the text (species, towns, trainer names);
- count similarity;
- a small penalty for ALL-CAPS easy-chat banks.

**Offset steps** (at v4 bank → US − v4):

| v4 bank | 16 | 38 | 215 | 220 | 233 | 504 | 595 | 712 | 721 | 740 | 799 | 809 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| US − v4 | 1 | 2 | 3 | 5 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |

**Anchors checked:** species 232→237, items 219→222, item descriptions 218→221, abilities 711→720, trainer text 718→728, trainer names 719→729, trainer classes 720→730, moves 739→750, move descriptions 738→749, locations 272→279, HG Pokédex text 791→803.

### 2.6 Per-string US reuse (`us_reuse.jsonl`)
The hack's Chinese is based on the **ACG** translation. Our vanilla Chinese reference is **Xzonn's revision** of it: 宝可梦 instead of 精灵, new move names, reworded lines. Exact equality with the vanilla text is therefore rare even for untouched strings. The verdict combines several signals.

**Signals:**
- `xz_ratio`: difflib ratio against the vanilla zh, after folding 宝可梦→精灵 and similar. If the same id scores below 0.6, the best string anywhere in the bank is used, for banks of ≤400 strings.
- `tags_match_jp` / `pages_match_jp`: the command multiset and the `{CLEAR}`+`{SCROLL}` count equal the vanilla JP string. The ACG translation kept the JP structure.
- `name_match`: for name lists, the glossary English equals the US name (case-insensitive).
- `tm_us_sim`: the v3 Eng line is ≥0.7 similar to the US line. Shake69 often reused official text.

**Verdicts:**
- **likely:** name_match, or xz ≥0.8, or tm_us_sim ≥0.7, or (xz ≥0.6 and tags and pages agree).
- **possible:** strings longer than 4 characters with weaker structural agreement.
- **no_us:** no US counterpart. This covers ids beyond the vanilla count (hack additions), blank or unused US slots, JP-language US banks, and the hack-new banks.

**Spot checks:** likely hits were correct in samples. For example, 455/2 "{VAR} received the Boulder Badge from Brock!" and 476/10 "Vermilion City / The Port of Exquisite Sunsets".

**Result for a027:** 21,037 likely, 1,224 possible, 5,520 unlikely and 30,170 no_us strings. Most no_us strings are hack additions in rewritten map banks.

## 3. Manifest (`manifest.json`)

### 3.1 Per-bank fields

| group | fields |
|---|---|
| identity and size | `key`, `strings`, `cjk_strings`, `cjk_chars`, `latin_only_strings` |
| classification | `category`, `priority`, `jp_name`, `map_code`, `map_group`, `region` |
| origin | `origin` + `origin_basis`, `vanilla_count` |
| US mapping | `us_bank_guess`, `us_file`, `us_confidence` |
| v3 mapping | `v3_bank`, `v3_confidence` |
| coverage | `tm{exact, exact_loose, fuzzy90, fuzzy80, exact_chars}`, `us_reuse{likely, possible, unlikely, no_us, likely_chars}`, `cjk_strings_without_exact_tm` |
| batch plan | `batches` |
| other | `sample` |

### 3.2 How categories and priorities are assigned
**Categories** come from the vanilla JP dev bank name. That is authoritative for 0–813, e.g. `monsname`, `wazainfo`, `trmsg`, `tel_p_gl_kasumi`, `radio_p_drama`, `t25r1201`. The hack banks and battle_string are labelled by hand. Banks 151–176 and 430/431 have no dev name and are grouped as `debug_or_unlisted`.

**Priorities:**

| tier | contents |
|---|---|
| P0 | name lists: species, moves, items, abilities, types, natures, trainer classes and names, locations, berries, Pokédex categories |
| P1 | hack notice banks, menus/UI, common script text, battle messages (including battle_string), battle and Pokédex UI |
| P2 | map scripts in story order, trainer battle text, walking-Pokémon reactions, move/item/ability descriptions |
| P3 | Pokédex entries, phone, radio, TV, Battle Frontier, Pokéathlon, easy chat, mail, minigames |
| P4 | link/Wi-Fi, debug |
| skip | 42 banks with no CJK (foreign-language Pokédex, heights/weights, debug kana) |

**Origin labels:**

| origin | banks | CJK strings |
|---|---|---|
| vanilla-derived, mostly untouched | 284 | 14,929 |
| vanilla-derived, partly rewritten/extended | 61 | 5,823 |
| vanilla + hack-extended | 31 | 9,013 |
| hack-rewritten | 98 | 3,253 |
| hack-rewritten + extended | 298 | 24,893 |
| hack-new (814–816 + battle_string) | 7 | 2,910 |

Almost every map script bank was rewritten and heavily expanded. For example, Mt. Moon d02r0101 has 2 vanilla strings and 154 in v4.

### 3.3 Category totals (CJK)

| category | banks | CJK strings | CJK chars | TM exact | TM fuzzy | US likely | US possible |
|---|---|---|---|---|---|---|---|
| map_script | 400 | 26,386 | 652,807 | 4,707 | 652 | 2,257 | 183 |
| pokedex_entries | 3 | 2,426 | 67,711 | 484 | 20 | 436 | 104 |
| pokegear_phone | 78 | 1,660 | 49,878 | 563 | 24 | 1,579 | 18 |
| battle_messages_hack | 4 | 2,870 | 28,214 | 158 | 292 | 0 | 0 |
| tv_news | 11 | 353 | 24,811 | 31 | 4 | 12 | 0 |
| trainer_battle_text | 1 | 1,707 | 24,382 | 1,702 | 5 | 712 | 44 |
| link_wifi | 56 | 3,126 | 22,908 | 217 | 14 | 2,331 | 53 |
| battle_frontier_trainer_text | 2 | 1,840 | 21,299 | 21 | 3 | 590 | 460 |
| battle_messages | 2 | 2,676 | 20,865 | 2,648 | 13 | 2,647 | 1 |
| move_descriptions | 1 | 902 | 18,374 | 449 | 9 | 451 | 3 |
| side_features_minigames | 73 | 1,978 | 16,293 | 591 | 9 | 1,262 | 65 |
| menus_ui_system | 42 | 1,725 | 14,496 | 808 | 16 | 885 | 207 |
| item_descriptions | 1 | 756 | 14,065 | 511 | 5 | 511 | 0 |
| pokegear_radio_map | 15 | 328 | 11,346 | 8 | 0 | 284 | 2 |
| battle_frontier | 18 | 1,103 | 8,815 | 557 | 11 | 806 | 47 |
| pokeathlon | 8 | 649 | 8,660 | 33 | 6 | 563 | 6 |
| common_script_text | 12 | 915 | 8,526 | 685 | 5 | 500 | 22 |
| pokedex_categories | 1 | 1,441 | 5,902 | 556 | 0 | 494 | 0 |
| walking_pokemon_reactions | 1 | 759 | 5,495 | 757 | 1 | 759 | 0 |
| ability_descriptions | 1 | 327 | 4,818 | 115 | 16 | 148 | 4 |
| species_names | 1 | 1,438 | 4,753 | 548 | 0 | 493 | 0 |
| debug_or_unlisted | 43 | 953 | 3,071 | 358 | 0 | 293 | 0 |
| move_names | 1 | 902 | 2,988 | 311 | 0 | 467 | 0 |
| item_names | 1 | 768 | 2,712 | 514 | 31 | 512 | 0 |
| trainer_names | 1 | 1,007 | 2,132 | 1,000 | 0 | 659 | 0 |
| easy_chat_words | 15 | 509 | 1,443 | 155 | 0 | 468 | 3 |
| location_names | 4 | 332 | 1,229 | 315 | 0 | 320 | 0 |
| ability_names | 1 | 326 | 1,023 | 142 | 0 | 127 | 0 |
| others (berry desc/names, types, natures, trainer classes, battle/dex UI, mail, hack UI/intro, debug, dex measurements) | 24 | 659 | 4,264 | | | | |

**By priority:**

| priority | banks | CJK strings | CJK chars |
|---|---|---|---|
| P0 | 14 | 6,448 | 21k |
| P1 | 64 | 8,453 | 74k |
| P2 | 405 | 30,837 | 720k |
| P3 | 221 | 10,946 | 212k |
| P4 | 75 | 4,137 | 26k |

### 3.4 Batch plan
There are 142 batches, `B001`…`B142`, in `manifest.json["batches"]`. Each batch lists `parts` of the form `{bank: "a027/0444", ids: [from, to], cjk_strings, cjk_chars}`.

**How batches are built:**
- Each group is split into balanced chunks of ≤600 CJK strings and ≤15k CJK chars. Cuts prefer bank boundaries.
- Small groups of the same priority and kind are merged. Map groups merge with the next group in story order, e.g. "ROUTE_25 + ROUTE_5 + ROUTE_6".

**Order and groups:**
1. **P0 name lists** (B001–B014).
2. **P1** (B015–B031):
   - hack intro/credits, menus, common scripts, battle messages, battle_string;
3. **P2 map scripts** (B032–B096), grouped per map-code prefix (town + interiors, route + gatehouses, dungeon floors) in story order:
   - **Kanto first:** Pallet → Viridian → Viridian Forest → Pewter → Mt. Moon → Cerulean → … → Indigo → Mt. Silver.
   - **Then Johto:** New Bark → … → Blackthorn → Sinjoh.
4. **P2 other text** (B097–B106):
   - trainer text, walking-Pokémon reactions, move/item/ability descriptions;
5. **P3** (B107–B133).
6. **P4** (B134–B142).

**Why Kanto first:** the hack starts in Pallet Town (the Origins story), and v3 Eng translated Pallet→Cerulean first.

## 4. Caveats

- **v3 Eng quality:** Shake69's work is mixed. It is often official text, sometimes machine-like ("I want to remember the new Mega Kick"). It has typos ("Pokmemon"), broken commands and occasional misalignment, i.e. a US line pasted into a slot whose Chinese differs. Pokédex slots are the worst case. Treat every TM hit as a draft; check the `flags` and `candidates`.
- **Official US text is vanilla, the hack's facts may not be:**
  - A "likely" verdict means the *Chinese line* looks unmodified. It does not guarantee the surrounding game facts are unchanged: move power, item effects, NPC gifts.
  - Descriptions of hack-changed moves and items need a check against the glossary and the hack's spreadsheets.
  - US names are Gen-4 style (BULBASAUR, DoubleSlap, POKé BALL). The glossary policy (modern names) overrides them.
- **Repurposed maps:** map names come from the vanilla map that owns each bank. The hack reuses maps; e.g. Red's house 2F (t01r0102) text talks about Three Island, and the Mt. Moon, Rocket and Sevii content has moved around. The labels are grouping hints, not locations in the hack.
- **Pokédex:** there are three CJK entry banks:

  | bank | size | US slot | text |
  |---|---|---|---|
  | 791 | 1,441 | 803 (HG) | modern text |
  | 792 | 494 | 804 (SS) | |
  | 798 | 494 | 810 (JP) | old text |

  792 and 798 may be unused in a HeartGold build. Check in-game before translating them; they are 30k chars.
- **Move names differ by bank:** battle messages (bank 3) still use ACG-era move names (拍打/手刀). The move-name bank 739 uses the new names (拍击/空手劈). Translate move names from the glossary, not literally per bank.
- **Map-bank alignment:** alignments that only placed a bank between anchors (`medium (between anchors…)`) are structurally sound. Map banks, however, are hack-rewritten, so us_reuse falls to no_us/unlikely for most of their strings. That is expected.
- **US-only picks are uncertain:** 511 (T07SP0101) and 603 (T25SP0101) are the least certain US-only choices. The JP/US Game Corner banks differ.
- **Trainer names (719) and classes (720):** the hack reorders and extends them. The US-likely verdicts there rely on the xz similarity of short names; verify them against the trainer data.
- **Fuzzy tiers:** fuzzy80 hits are often template variants that differ in the embedded name, e.g. "can't learn Tail Glow" vs "…Shell Smash". They are useful as a pattern, but the name must be replaced.
- **Batches and pre-filled drafts:** batch sizes count all CJK strings, including ones with TM/US drafts. Batches with high draft coverage (P0, battle messages, trainer text, phone) will go much faster than the map batches.
