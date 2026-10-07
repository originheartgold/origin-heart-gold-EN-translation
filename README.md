# Pokémon Origin HeartGold: English translation

An English fan translation of **起源心金 (Pokémon Origin HeartGold) v4.0.3**, a Chinese ROM hack of Pokémon HeartGold. The hack retells the story with characters from Pokémon Origins, the anime and Pokémon Adventures.

## Play it

[Patch your game here](https://originheartgold.github.io/origin-heart-gold-EN-translation/patch/) and run on any emulator.
Real Nintendo hardware is **not** supported and might result in strange and unexpected behavior.

Stuck on a quest? The [quest guide]([guide/README.md](https://originheartgold.github.io/origin-heart-gold-EN-translation/guide/)) covers side quests, puzzles and easy-to-miss events, region by region.

Cannot find a Pokémon? Check the [full reference](https://originheartgold.github.io/origin-heart-gold-EN-translation/pokemon/) including movesets including egg, and moveset, evolution level or method, location, and more.

**Status: release candidate (v1.0.0-rc5).** All 67,078 translatable strings are in English and pass the automated checks. The event scripts have been audited (softlocks, trades, gifts, passwords; see [CHANGELOG.md](CHANGELOG.md)), and game documentation generated from the ROM's own data is in [work/docs/](work/docs/README.md). Please report anything odd.

## How it works

The translation lives as JSON files in `work/translate/banks/`: one file per message bank, holding the Chinese source and the English for each string. Python tools in `work/tools/` check the text against the DS text boxes, wrap lines, record naming decisions, and build the ROM and patch. Every other change to the Chinese ROM (graphics, font glyphs, code patches) is a documented fix in `work/patches/` ([FIXES.md](work/patches/FIXES.md)). See [CONTRIBUTING.md](CONTRIBUTING.md) to help out.

Most of the first-draft English was written by AI agents working from the Chinese, following [the style guide](work/translate/STYLE.md) and [AGENTS.md](AGENTS.md). Humans review it. Official US HeartGold text is reused wherever the hack didn't change a line.

## Generated files

Run every command from the repo root. Never edit generated files by hand: change the source and regenerate.

**Not committed, rebuilt from the repo alone:**

| File | Command |
|---|---|
| `work/translate/decisions/DIGEST.md` (names and rules for translators) | `python3 work/tools/decisions.py render-progress --out work/translate/decisions/DIGEST.md` |
| `work/translate/decisions/DECISIONS.md` + `decisions.csv` | `python3 work/tools/decisions.py report` |
| `work/translate/decisions/HACK_FINDINGS.md` | `python3 work/tools/findings_report.py` |
| `site/src/content/docs/guide/` (website guide pages) | `python3 work/tools/site/sync_guide.py` (CI runs it too) |

**Not committed, need your own ROMs** (set up `work/rom/` as in [CONTRIBUTING.md](CONTRIBUTING.md#building-the-rom-optional)):

| File | Command |
|---|---|
| `work/extract/` (text dumped from the ROMs) | `python3 work/tools/msgtool.py extract …` (see CONTRIBUTING.md, step 2) |
| Pokédex banks `a027/0793-0797`, `0804-0813` | `python3 work/tools/ws.py init --narc a027` |
| `work/graphics/generated/`, `weather_en/`, `dex_type_list_en.png`, `naming_labels_en.png` | `python3 work/tools/gfx.py regenerate` (`build.py` runs it) |
| `work/build/` (English ROM and `.xdelta` patch) | `python3 work/tools/build.py` |
| `work/glossary/src/` (PokéAPI CSVs) | `python3 work/glossary/build_glossary.py --download` |
| `work/rom/preview_*.json` | `python3 work/tools/msgtool.py patch-preview <patch.delta> <out.nds> --report <out.json>` |
| Seeding intermediates in `work/translate/` (`manifest.json`, `bank_map_*.json`, `char_fold_v3.json`, `tm_*.json`, `us_reuse_summary.json`) | the `work/translate/scripts/` pipeline, in order: `align_v3_v4.py`, `build_tm.py`, `align_us_v4.py`, `apply_tm.py`, `us_reuse.py`, `build_manifest.py`. These also need the v3 hack ROMs and the `work/translate/ref/` inputs. Only those scripts read them. |

**Committed although generated.** They need a ROM, and CI or the tools rely on them:

| File | Command | Why it's committed |
|---|---|---|
| `site/src/data/*.json` (website game data) | `python3 work/tools/site/build.py --content` | the site build in CI has no ROM |
| `site/src/data/primo.json` | `python3 work/tools/primo_passwords.py --site` (needs the English build) | same |
| `work/save-editor/src/generated-reference.ts` | `(cd work/save-editor && npm run build) && node work/save-editor/scripts/generate-reference.mjs work/build/origin_hg_v4.0.3_en_wip.nds` | CI tests the save editor |
| `work/docs/*.md` (game documentation) | `python3 work/tools/docs/gen_docs.py` | linked from this README and the guide |
| `work/tools/font_widths.json` | `python3 work/tools/textmetrics.py build-widths <rom>` | `qa.py` reads it on every check |
| `work/translate/bank_maps.json` | `python3 work/translate/scripts/build_bank_maps.py` (also needs `work/translate/ref/hgss_map_constants.json`) | used by the tools and translators |
| `work/glossary/*.json` | `python3 work/glossary/build_glossary.py` (also needs the hack author's spreadsheets) | used by `qa.py` and the other tools |

`work/translate/play_order.json` and `manifest_playorder.json` were generated once and are now frozen records of the batch plan; rerunning `build_playorder.py` gives a different plan. The translation banks (`work/translate/banks/`) were seeded by scripts but hold the translation itself, so they are the source, not output.

## Credits

- **起源心金 (Origin HeartGold):** original hack by [雁南飞TB](https://space.bilibili.com/1461403176) (Yannanfei TB). v4.0.x by [Alex](https://youhua.baidu.com/home/main?lp=home_follow_main&un=chendelpiero), built on [hg-engine](https://github.com/BluRosie/hg-engine), with special thanks from Alex to 耿耿耿耿鬼酱, 叶师傅 and 呱呱. Official channels: QQ group 1055021987 and the [起源心金 Tieba](https://tieba.baidu.com/f?kw=%E8%B5%B7%E6%BA%90%E5%BF%83%E9%87%91).
- **hg-engine** and its contributors: engine, plus the FAIRY type icons and weather banner letters used here. See [their credits](https://github.com/BluRosie/hg-engine/blob/main/CREDITS.md).
- **u/Shake69:** the partial v3 English translation, reused as translation memory with permission.
- **u/riap0526:** packaged the Chinese patches and docs.
- **Xzonn:** the Gen 4 Chinese character table.
- **[pret/pokeheartgold](https://github.com/pret/pokeheartgold)**, **[ndspy](https://github.com/RoadrunnerWMC/ndspy)** and **[PokéAPI](https://pokeapi.co/)** (official English names).

Full source notes: [work/notes/credits_and_sources.md](work/notes/credits_and_sources.md) and [work/graphics/CREDITS.md](work/graphics/CREDITS.md).

## License

This is a free, non-commercial fan project and is not affiliated with or endorsed by Nintendo, Creatures Inc., GAME FREAK inc. or The Pokémon Company. Pokémon and all related names, text and graphics belong to them. The Chinese hack belongs to its authors. This repo contains no ROMs.

- **Tools and scripts** (`work/tools/`, `work/translate/scripts/`, `work/glossary/*.py`): [Apache 2.0](LICENSE).
- **Our own translation work and docs:** [CC0 1.0](LICENSE-CONTENT). Use them however you like, as far as the rights are ours to give.
- **`work/tools/charmaps/charmap_zh_xzonn_gen4.tsv`:** [GPL-3.0](work/tools/charmaps/LICENSE-GPL-3.0.txt), from [Xzonn/PokemonChineseTranslationRevise](https://github.com/Xzonn/PokemonChineseTranslationRevise). `charmap_en.tsv` comes from pret's `charmap.txt`.
- **Not covered by these licenses:** official Nintendo text and graphics, the hack's Chinese text, u/Shake69's v3 lines, the graphics in `work/graphics/` that are derived from the US ROM or from hg-engine (including the hg-engine assets in `work/graphics/vendor/`, free and non-commercial only, with credit), the vendored xdelta-wasm in `site/public/vendor/xdelta-wasm/` (Apache-2.0, see its `LICENSE.txt`; the Emscripten runtime inside it is MIT, see `LICENSE-emscripten.txt`) and the GPL-3.0 Chinese character table above. Each keeps its own owner's terms.

Releases must stay free: no paywalls and no donation links. hg-engine requires this.
