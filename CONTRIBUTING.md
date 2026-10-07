# Contributing

Thanks for helping! The most useful things right now:

1. **Play and report.** Play the latest patch from [Releases](../../releases) and [open an issue](../../issues) for anything wrong: mistranslations, awkward lines, text running off the box, leftover Chinese, or a crash. Include a screenshot and where you were in the game.
2. **Review text.** Read the English against the Chinese in `work/translate/banks/`. You don't need to know Chinese to catch unnatural English, typos or inconsistent names.
3. **Translate.** Every string is translated now, so this means fixing lines rather than filling gaps. `python3 work/tools/ws.py stats --by-bank` lists each bank's `todo` count, in case strings reappear (for example after a source update).

## Ground rules

- **Never commit ROMs, patches of the original hack, or text dumped from a ROM.** `.gitignore` covers the usual paths. Don't force-add anything past it.
- **Keep the hack's tone.** Swearing, crude jokes and dark humour stay at full strength (decision D-0627). Don't soften them, and don't add crudeness that isn't there.
- **Use the established names.** Check `work/translate/decisions/DIGEST.md` (generate it with `python3 work/tools/decisions.py render-progress --out work/translate/decisions/DIGEST.md`) and `work/glossary/` before naming anything. To propose a new name or rename an existing one, open an issue rather than changing it everywhere.
- **Anime and manga quotes use the canon English wording** (decision D-1436), and song lyrics are never quoted. Details are in [STYLE.md](work/translate/STYLE.md).
- If you use AI tools, tell us in the PR. The same rules apply, and [AGENTS.md](AGENTS.md) has instructions you can give the tool.

## Editing text

Each string in `work/translate/banks/<narc>/<NNNN>.json` looks like this:

```json
{"id": 12, "zh": "…", "en": "…", "status": "draft", "origin": "agent", "notes": ""}
```

Edit `en`, set `status` to `draft` (or `reviewed` if you are reviewing), and put anything uncertain in `notes`. Then wrap and check the bank:

```sh
python3 work/tools/qa.py wrap --in-place --mode scroll --which max work/translate/banks/a027/0460.json
python3 work/tools/qa.py check work/translate/banks/a027/0460.json   # must report 0 errors
```

A dialogue box holds two lines of 216 px. `qa.py` measures the real font widths, so trust it over character counts. Keep every `{...}` tag.

## Building the ROM (optional)

To build, you need Python 3.12+, `pip install ndspy`, `xdelta3`, [armips](https://github.com/Kingcom/armips) **v0.11.0** (on `PATH`, or `ARMIPS=/path/to/armips`; build steps in [work/notes/toolchain.md](work/notes/toolchain.md)), your own USA HeartGold dump and the Chinese v4.0.3 patch.

```sh
# 1. Put your USA dump at work/rom/Pokemon - HeartGold Version (USA).nds, then create the Chinese base:
xdelta3 -d -s "work/rom/Pokemon - HeartGold Version (USA).nds" "Pokémon Origin HeartGold v4.0.3 Cn.delta" work/rom/origin_v4.0.3_cn.nds

# 2. Extract the Chinese text the build merges into:
python3 work/tools/msgtool.py extract work/rom/origin_v4.0.3_cn.nds work/extract/v4/a027 \
  --charmap work/tools/charmap_en.tsv --charmap work/tools/charmaps/charmap_zh_xzonn_gen4.tsv --narc a/0/2/7
python3 work/tools/msgtool.py extract work/rom/origin_v4.0.3_cn.nds work/extract/v4/battle_string \
  --charmap work/tools/charmap_en.tsv --charmap work/tools/charmaps/charmap_zh_xzonn_gen4.tsv --narc battle/string/battle_string.narc

# 3. Regenerate the workspace banks the repo doesn't publish (the official foreign-language
#    Pokédex data, a027/0793-0797 and 0804-0813). Run this before qa.py, build.py or the text checks:
python3 work/tools/ws.py init --narc a027

# 4. Build the ROM and patch into work/build/:
python3 work/tools/build.py
```

A few strings that quote song lyrics store `[zh redacted: song lyrics; sha256:…]` instead of their Chinese. The tools fill in the real text from your `work/extract/v4` dump when the hash matches (`work/tools/zh_redact.py`), so leave the marker as it is. Redact another lyric string with `python3 work/tools/ws.py redact a027 <bank> <id>...`.

The build also regenerates the English graphics (`work/graphics/generated/`, `weather_en/` and two PNG sheets) from your two ROMs. They contain Nintendo and hack artwork, so they are git-ignored and never committed; see `work/notes/graphics_inventory.md` → Build step.

Everything the build changes in the Chinese ROM besides the message text (font glyphs, graphics, the hardcoded outfit-chooser strings and the code patches) is a *fix*: one folder per fix in `work/patches/<fix-id>/fix.toml`, with why it is needed, what it changes, its decisions and the bytes it checks and writes. Code and data fixes are armips sources (`work/patches/<fix-id>/<fix-id>.asm`): fix.toml declares the regions and original bytes, the `.asm` writes the new bytes and guards the old ones, and the build refuses any change outside the declared regions (see [work/notes/toolchain.md](work/notes/toolchain.md)). [work/patches/FIXES.md](work/patches/FIXES.md) lists them all; regenerate it with `python3 work/tools/fixes.py docs --out work/patches/FIXES.md` after editing a fix, and check the registry with `python3 work/tools/fixes.py check`. `python3 work/tools/build.py --without <fix-id>` builds without one fix (`--only` builds with just the ones named); a fix that another one `requires` cannot be left out alone.

Run the tool tests with `python3 -m unittest discover -s work/tools -p 'test_*.py'` (the armips tests are skipped unless armips v0.11.0 is on `PATH` or in `ARMIPS`).

## The guide website

The quest guide (`guide/*.md`) and the generated game docs are published as a website from `site/`. See [site/README.md](site/README.md) for how it is built and how to write guide entries.

## Pull requests

Keep PRs small: one area, a few banks, or one fix. Say what you changed and why. PRs must pass `qa.py check` with 0 errors on every bank they touch.

By contributing, you agree that your contributions are released under this repo's licenses (Apache 2.0 for code, CC0 for translation text and docs). See the [README](README.md#license).
