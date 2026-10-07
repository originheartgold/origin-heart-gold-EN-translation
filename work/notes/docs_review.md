# Documentation review (Phase B, step 6)

**Status (reviewed 2026-09-29): current.** Agent phaseB3. Every project documentation page was checked against the code, the data, the decision register and the build output. Fixes were made in our own docs and in the generators of the generated pages; no bank, ROM or release file was changed.

## Current facts the pages were checked against

| Fact | Value | How checked |
|---|---|---|
| Translation | 67,078 of 67,078 translatable strings done (100%), 76,862 strings in all | `ws.py stats` |
| Banks | 821: 817 in `a/0/2/7` + 4 in `battle_string.narc` | bank files; `qa.py check` summary |
| QA | 0 errors, 16,058 warnings on all 821 banks | `qa.py check work/translate/banks` |
| Release | v1.0.0-rc2 (`work/release/v1.0.0-rc2/`), 1.0.0 not released | release folder, CHANGELOG |
| Decisions | 1,352 records (D-0001–D-1352); 258 open questions (context notes excluded), 0 needs-review | register, `decisions.py report` |
| Hack findings | 158 register records (152 open, 6 resolved after this review) + import file = 258 in `HACK_FINDINGS.md` | `findings_report.py` |
| Tests | 86 (`unittest discover`) + 18 (`test_gen_docs.py`) = 104, all pass | run at the end of this review |
| Generated docs | 18 pages up to date (`gen_docs.py --check --refresh`) | run |
| Base ROM | USA `IPKE`, CRC32 `C180A0E9`, SHA-1 `4fcded0e…` | `msgtool.py check-base` |

Commands run from the docs (all worked): `ws.py stats [--by-bank]`, `qa.py check` (bank and workspace), `qa.py --help`, `qa.py wrap --help`, `decisions.py list --search 金婆婆`, `decisions.py report`, `decisions.py render-progress --out …/DIGEST.md`, `findings_report.py`, `gen_docs.py --check [--refresh]`, `gfx.py check` (166 members OK), `hardcoded.py check` (4 strings OK), `msgtool.py check-base`, `textmetrics.py width`, `--help` of `build.py`, `gfx.py`, `hardcoded.py`, `msgtool.py`, `emu_smoke.py`, `fill_names.py`, `textmetrics.py`, and both test commands.

## Per page

### Repo root

| Page | Status | Fixed | Open points |
|---|---|---|---|
| `README.md` | current | Status line said the script audit and the generated docs were still planned; both are done (Phase A in rc2, Phase B docs in `work/docs/`). The xdelta example used a file name no release has (`Origin_HeartGold_EN.xdelta`); now the rc2 file name. | "Humans review it": only 639 of 76,862 strings have status `reviewed` (observation, wording kept). |
| `CONTRIBUTING.md` | current | "Play a WIP patch" → the latest patch; "Translate" pointed at `todo` strings that no longer exist. | Build steps checked against `build.py` (defaults `work/rom/…`, `work/extract/v4`; the PNG reader is pure Python, so no Pillow is needed). |
| `AGENTS.md` | current | The battle-panel exception quoted 'B: EXIT' / '+: SWITCH'; the build ships 'Ⓑ EXIT' / '✚✚ SWAP' (D-1109, see Needs attention). "Pokédex type badges" → "Pokédex type list" (the composed asset is `dex_type_list_en.png`; the badges are copied from the USA ROM). Added that trainer names in 0719 are stored compressed and may be 10 characters (D-1326), which the "7 for trainers" line contradicted. | – |
| `CHANGELOG.md` | current | Added an [Unreleased] section for Phase B (docs, author notes, cross-checks; new hack findings D-1338, D-1339, D-1344, D-1347). rc1 said the naming tabs were composed from game glyphs; their QWE/abc letters are hand-drawn (`gfx.TAB_FONT`, as `graphics_inventory.md` and `CREDITS.md` say). | rc1's "236 findings" and "1,325 decisions" are that release's numbers; left as history. |
| `LICENSE`, `LICENSE-CONTENT` | current | – | Full Apache 2.0 (202 lines) and CC0 1.0 (122 lines) texts; they match the README's licence section. `work/tools/charmaps/LICENSE-GPL-3.0.txt` is the full GPL-3.0. See Needs attention 7 for the Xzonn table. |

### `work/translate/`

| Page | Status | Fixed | Open points |
|---|---|---|---|
| `STYLE.md` | current | The seeding files it cited (`us_reuse.jsonl`, `tm_v4_matches.jsonl`) are local-only now; the text now points at origins "us"/"tm_v3" in the banks. Tone rule now cites D-0627, money rule D-0008 (was "decided in PROGRESS.md"). The wrap command now has AGENTS.md's `--mode scroll --which max`. Name limits corrected to `qa_config.json`: natures 8 (was 7), locations warn above 18 (was 16), plus trainer names 10 and Frontier names 7. | – |
| `PROGRESS.md` (Done) | current | "The batch plan is in manifest.json" → B batches there (used to B059), then R001–R069 in `manifest_playorder.json`. | The Done log is complete: B001–B059, R001–R069, the sweep, follow-ups 1/3/4. The frozen sections below Done still hold pre-D-0627 softening notes (e.g. 0255 #10, 0331 #7); they're superseded by D-0627 and were not reviewed here. |
| `JOHTO_PROMPT.md`, `SIDE_PROMPT.md` | historical | Marked historical (all their batches are done). | – |
| `TRANSLATOR_BRIEF.md` | current | – | A correct pointer to `AGENTS.md`. |

### `work/notes/`

Each file now opens with a "Status (reviewed 2026-09-29)" line (`docs_crossref.md` gets it from its generator).

| Page | Status | Fixed | Open points |
|---|---|---|---|
| `tooling.md` | historical | §0 "base ROM not determined yet" annotated as settled (USA `C180A0E9`); §8's seven open questions answered in place; msgtool test count 20 → 23. | The §4.4 font-width paragraph keeps its inline correction. |
| `text_metrics.md` | current (engine facts) | `test_qa.py` 28 → 30 tests; the glyph-restore recommendation is marked done (build stage 3); §8 open points annotated. | Signposts (160 px) are still not checked: no string has category `sign` (Needs attention 1). `qa_config.json` says the US location maximum is 17; the US bank 0279 maximum is 16 (Valley Windworks, Verity Lakefront, Vista Lighthouse). |
| `tm_and_manifest.md` | historical | Status line only. | Says v4 0798 ↔ US 0810 (low confidence); the R060 translator used US 0805. The bank map is the low-confidence guess; the translation is what counts. |
| `play_order.md` | historical | Status line only. | – |
| `decisions_workflow.md` | current | Question subtypes now include hack-finding and integrity; `HACK_FINDINGS.md` added to the file table; the DIGEST command spelled out; `rewrap/` is created on demand (none yet). The cut-over sections are marked historical. | – |
| `credits_and_sources.md` | current | The saved Reddit thread path was wrong (`../`); it's in the repo root and local-only. Added that the hack ROM itself is `IPKJ` with the Japanese overlay layout, which reconciles it with `hardcoded_text.md`. | Needs attention 8 (u/Shake69's permission record). |
| `graphics_inventory.md` | current | Status line only. | P2 #21 and #31 are still open (probably unused title strips). |
| `hardcoded_text.md` | current | Status line only. | Checked against `code_patches.json` (19 patches, all enabled; since moved to `work/patches/*/fix.toml`) and `hardcoded.py check`. |
| `move_data_audit.md` | current | Status line only. | Its proposals are registered (D-1305–D-1317). |
| `integrity_audit_text.md` | current | "Trade #6 and #19 OT" mixed a trade number and a string id: it is the OT of trades 1 and 6 (bank strings #14 and #19). The arm9 row said "19 patches (6 namelen + IME + 10 keyboard rows)", which doesn't add up: the 75 arm9 byte runs (re-counted) fall in the 16 arm9 patches (5 namelen + IME + 10 rows); the other 3 of the 19 are in overlays 44 and 49. §6 marked as added to the checklist. | – |
| `softlock_audit.md` | current | Status line only. | Consistent with CHANGELOG rc2 and the checklist. |
| `docs_crossref.md` (generated) | current | Via the generator: status line; D-1340 entry and the unused-trade line now reflect the loan Pokémon (Needs attention 2). | – |
| `spreadsheet_crossref.md` | current | Status line only. | Findings D-1345–D-1352 match the register. Uses ₽ like the docs (Needs attention 9). |
| `ingame_checklist.md` | current | Added a signpost item (Needs attention 1). | Nothing is ticked yet. |
| `followups.md` | current | Every item marked done / partly done with date and evidence. | Phase A step 3: trades, Name Rater and passwords are not yet checked in game. 1.0.0 is not released. |

### `work/graphics/CREDITS.md`

Status: current. Fixed: the hg-engine weather-icon PNGs it listed as files in this folder are not in the repo; the row now names the files that are (`weather_en/battle_graphics_0033…0041.png`) and says where the source PNGs came from (Needs attention 5). Added the battle-panel labels to "the game's own font" list. hg-engine terms, commit `4d316b4e` and the FAIRY icon files check out.

### `work/docs/` (generated) and `work/docs/author_notes/`

`README.md` is current and matches its pages (`--check --refresh`: 0 changed before the fixes below). Spot checks against the ROM: Bulbasaur, Ivysaur and Charizard stats and abilities read straight from `a/0/0/2` match the pages (the stat order in the file is HP/Atk/Def/Spe/SpA/SpD). Generator fixes (`work/tools/docs/gen_docs.py`, tests still 18/18):
- Trades 6 and 8 were listed as "not used by any script". They are loan Pokémon (`GiveLoanMon`, scripts 115 and 172; `ReturnLoanMon` in 115, 240, 842, 913). The table now marks them "(loan)", species pages say "loan Pokémon", and the README coverage line reads "13 (13 used: 11 trades, 2 loan Pokémon)".
- The OT of trades 1 and 6 is a raw `{VAR:0103:0}` tag in bank 0198 (the Chinese has the same). The page now explains it instead of printing a bare tag.
- Several pages had repeated headings for different maps with the same name (items: 2× "Mt. Moon", 2× "Vermilion City"; encounters: Route 2, Route 16; trainers: Route 2, Indigo Plateau). Repeated headings now carry the map number.

`author_notes/README.md`: current; it describes the five static pages correctly.

### Generated reports

| Report | Internal consistency | Generator fixes |
|---|---|---|
| `DECISIONS.md` / `decisions.csv` | 1,352 records; header counts agree with the register (258 open questions, 0 needs-review). Regenerated after resolving D-1340. | – |
| `DIGEST.md` | Superseded records (D-0448, D-0485, D-0493, D-0824) are left out; the S.S. Anne / S.S. Aqua rule is D-1223 and the tone rule D-0627. | The header said `(?)` marks "not reviewed yet or disputed", but it only marks `needs-review` (0 records), so nothing is marked; the header now says so. The Open questions section now warns that hack-finding texts describe the string as it was when logged (Needs attention 6). |
| `HACK_FINDINGS.md` | Kind table adds up to 258; up to date with the register. The total happens to equal the 258 open questions in the digest; they are different sets. | Six data findings with no string ref had empty headings (`###  (open, D-1341)`); they now read "No string (data finding)". The file was written with mode 0600 (mkstemp); now 0644 like the other reports. |

## Needs attention

1. **Signposts may overflow (translation/QA gap).** Script signposts with a map or route graphic (`DirectionSignpost` type 0/1) use a 160-px box (`text_metrics.md` §2). There are 62 such uses, but no string is assigned the `sign` category, so QA checks them at 216 px. Measured with `textmetrics`, four English lines are wider than 160 px: Lavender Town sign `a027/0468#4` (215 px; script file 765), Saffron "pocket dimension… -Sabrina" `0533#10` (214 px; file 838), Cinnabar welcome sign `0511#21` (210 px; file 812), and a Pewter City line `0453#20` shown in a sign box (183 px; file 748). The Chinese of `0468#4` is 162 px, so the box may be a little wider than 160 or the Chinese overflows too. What it is: a gap in the width gate, not in the text. Next step: check in melonDS (added to `ingame_checklist.md`), then set `"category": "sign"` on the signpost strings and rewrap the ones that fail.
2. **D-1340 was a false positive (fixed).** The Phase B1 cross-reference said trade records 6 (Pidgeot) and 8 (Misty's Gyarados) are unused because it only looked for `LoadNPCTrade`. `integrity_audit_text.md` §2 already knew they're loan Pokémon. The script index shows `GiveLoanMon` for trade 6 in script 115 (Viridian Forest) and trade 8 in script 172 (Celadon City). Resolved in the register (`decisions.py resolve`, by agent:phaseB3) and fixed in `gen_docs.py`.
3. **The battle-panel labels differ from the user decision's wording.** D-1109 (user) says to compose 'B: EXIT' / '+: SWITCH'. The build ships 'Ⓑ EXIT' / '✚✚ SWAP' (`gfx.py` `BPANEL_LABELS`). `graphics_inventory.md` row 26 explains why: 22 px after Ⓑ and 24 px after the crosses; "SWITCH" needs 34 px, and the colon doesn't fit. The deviation is reasoned but was never put back to the user. Ask the user to confirm SWAP, or to choose NEXT or single-cross "Switch".
4. **The rc2 release notes are stale and miss a licence obligation.** `work/release/v1.0.0-rc2/README.txt` still says "The script/quest integrity audit … is still to come", although rc2 includes the Phase A results (CHANGELOG rc2, "Verified (Phase A)"). It also credits hg-engine contributors but doesn't link or reproduce hg-engine's CREDITS.md, which `work/graphics/CREDITS.md` lists as an obligation for the release readme or post. It's a local, gitignored release file and may already be published, so I didn't edit it. For the next release, drop the audit sentence and add `https://github.com/BluRosie/hg-engine/blob/4d316b4eff0bd9f2869c86c8785878eaf3d7d367/CREDITS.md`. The README's own link to hg-engine's CREDITS.md covers the repo.
5. **The hg-engine weather-letter sources aren't in the repo.** `CREDITS.md` listed `vendor/hg-engine/weather_icons/8_346_sun.png` and four more as files here, and `gfx.py make-weather-banners` reads them from that folder by default. The folder doesn't exist; only the finished banners (`weather_en/*.png`, used by the build) are kept. The build works, but the banners can't be regenerated without fetching the five PNGs again from hg-engine commit `4d316b4e`. `CREDITS.md` is corrected. Whether to vendor them again is the user's call (never download without asking).
6. **Hack-finding texts in the register are stale for strings retranslated under D-1195.** Many findings record how the agent handled the line before D-1195. Examples: D-0582 says "English uses Glameow throughout", but `0331` now says Skitty where the Chinese says 向尾喵 (#4, #6, #8…) and Glameow only at #5/#19. D-0564 says "English uses him", but `0324#89` now says "her". D-0583 says "US ‘Zapdos’ kept", but `0334#7` is now "Jolteon". `DIGEST.md` and `DECISIONS.md` repeat these texts. `HACK_FINDINGS.md` prints the current English, so it's the reliable view, and the digest now says so. Updating the record texts is a coordinator task: `set … --reason`, on other agents' records.
7. **Xzonn character table: licence and attribution.** README says `charmap_zh_xzonn_gen4.tsv` is GPL-3.0 (from Xzonn/PokemonChineseTranslationRevise, `files/CharTable.txt`). `tm_and_manifest.md` says the Xzonn *texts* are CC BY-NC-SA 3.0. The TSV itself carries only `# imported from xz_CharTable.txt`: no upstream URL, commit, author or licence line. I couldn't check upstream offline. Confirm which licence covers `files/CharTable.txt`, and add a source/commit/licence comment line to the TSV (the loader skips `#` lines).
8. **u/Shake69's permission is recorded only second-hand.** `credits_and_sources.md` says the permission was "confirmed by the user, 2026-09-28". The saved thread (`reddit-thread-1wsbpj6.md`) holds no written permission. Keep a copy or link of the actual message with the project notes.
9. **Currency symbol in the docs.** The generated docs, author notes and cross-check use ₽ (on 427 lines of `items.md`), but the game's English shows "$" (D-0008). This is cosmetic, but the docs say their names "match the English patch". The fix is a one-line generator change plus the static author notes, and it's the user's call.
10. **The OT of trades 1 and 6 is a raw placeholder in the hack's data.** Bank 0198 #14 and #19 are `{VAR:0103:0}` (a player-name tag) instead of a name, in the Chinese too. Trade 1 gives back the player's Butterfree, so the intended OT is the player. The trade code reads the text as stored, so the OT probably shows blank or odd. Hack data, harmless for the build (integrity audit §2). How it shows in game is unverified; the in-game trade check in the checklist covers it.
11. **Minor, for the record.**
    - QA still warns on 114 full-width strings, all deliberate: ideographic-space padding such as 0189 #172, and debug banks 0161, 0163, 0173 and 0290.
    - `qa_config.json` states the US location maximum as 17; it is 16.
    - Notes cite screenshots in `work/build/screens/`, which is gitignored, so they won't exist in a fresh clone.
    - `HACK_FINDINGS.md` and the digest's open-question count are both 258 by coincidence.
