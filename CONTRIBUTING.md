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

Everything the build changes in the Chinese ROM besides the message text (font glyphs, graphics, the hardcoded outfit-chooser strings and the code patches) is a *fix*: one folder per fix in `work/patches/<fix-id>/fix.toml`, with why it is needed, what it changes and its decisions. For graphics and font fixes fix.toml also holds the operations and the bytes they check. Code, data and hardcoded-string fixes are armips sources (`work/patches/<fix-id>/<fix-id>.asm`): fix.toml declares only the regions and their original bytes (and, for strings, the Chinese and English of each one); the `.asm` writes the new bytes and guards the old ones, and the build refuses any change outside the declared regions (see [work/notes/toolchain.md](work/notes/toolchain.md)). To change the English of a hardcoded string, edit both its `en` in fix.toml and its `.string` in the `.asm`; `fixes.py check` refuses them when they differ. If the new English no longer fits the string's slot (or now fits where it did not), that is an asm change too: the source decides whether a string is written in place or appended and repointed, and the build refuses a mismatch. [work/patches/FIXES.md](work/patches/FIXES.md) lists them all; regenerate it with `python3 work/tools/fixes.py docs --out work/patches/FIXES.md` after editing a fix, and check the registry with `python3 work/tools/fixes.py check`. `python3 work/tools/build.py --without <fix-id>` builds without one fix (`--only` builds with just the ones named); a fix that another one `requires` cannot be left out alone.

Run the tool tests with `python3 -m unittest discover -s work/tools -p 'test_*.py'` (the armips tests are skipped unless armips v0.11.0 is on `PATH` or in `ARMIPS`).

## Checks

One command runs the checks of the tools and the fixes:

```sh
pip install -r work/tools/requirements-dev.txt   # once: ruff, pinned
python3 work/tools/check.py                      # fast, about 6 s: no ROM (armips only for the synthetic assembly)
python3 work/tools/check.py --full               # also assembles the fixes, checks the snapshots and the USA
                                                 # claims, and builds the ROM (about 30-40 s)
```

The fast check runs `fixes.py check` (the fix registry and the asm lint: a header naming the fix and its decisions, every write inside an `.area`, a guard before every area's first write, every area inside the regions fix.toml declares, lines of at most 120 characters, every USA address written as a `US <file> 0x…` citation with its `[[us_ref]]`), checks that `work/patches/FIXES.md` is current, runs `ruff check` (config: `ruff.toml`), the synthetic assembly (`asmpatch.py synthetic`: every armips source assembled without the ROM, over zero-filled stand-ins of the binaries sized from `work/patches/sizes.toml`, with the guards off; it catches syntax errors, `.area` overflows, writes outside the declared regions and strings that differ from fix.toml, not wrong bytes; skipped when armips is not found) and the unit tests with armips hidden. `--full` needs armips v0.11.0, both ROMs, `xdelta3` and the pinned capstone (`requirements-dev.txt`); it adds `asmpatch.py check`, the disassembly snapshots (every code, data or strings fix has `work/patches/<id>/<id>.listing`, its edits old → new; a stale one fails: regenerate it with `python3 work/tools/asmpatch.py listing --write <id>` and review the diff), the USA cross-checks (every `US <file> 0x…` citation in a source or fix.toml has a `[[us_ref]]` in fix.toml, checked against the USA ROM by `usref.py`), the unit tests with armips (the per-binary golden hashes) and a full build compared with `work/patches/expected.toml`: the hash of everything outside the message banks must match (it moves with a fix, the graphics, the code or a hardcoded string's English, e.g. outfit-chooser-strings); the text, ROM and patch hashes move with every translation change, so they are only reported (`--strict-release` fails on them too). After a change that moves them on purpose, review the build and record the new hashes with `python3 work/tools/check.py --full --update-expected` in the same commit. `--full` warns about an xdelta3 other than 3.2.0 (the patch bytes differ between xdelta3 versions; `--strict-release` refuses it), a Python other than 3.14 or other ndspy / pillow versions than `requirements-runtime.txt`. `--repro` (implied by `--strict-release`, so required for a release) recompiles the text-speed payload with the pinned clang (`work/patches/text-speed/fix.toml` `[native] compiler`: another vendor or major version is refused, another Apple clang 21 build warns and the byte comparison decides) and builds a second time in another folder, under other file names, working directory, time zone, locale and hash seed: the ROM, the patch and the build report must be byte-identical (about 30 s more). Details: [work/notes/toolchain.md](work/notes/toolchain.md) → Checks.

**CI.** `.github/workflows/patches.yml` checks the patch toolchain on GitHub, but only in a repository that holds `work/patches/`: the published repository once the patch toolchain is published with it (its `main` is a separate, curated history without `work/patches/` today). Until then the gate is running `python3 work/tools/check.py` (and `--full` before merging) yourself. Once it runs, it triggers on every push and pull request that touches `work/patches/`, `work/tools/`, `ruff.toml`, the decision register (`work/translate/decisions/decisions.jsonl`, which the registry check reads) or the workflow, and by hand (workflow_dispatch): on ubuntu-24.04 with Python 3.14 it installs the pinned packages (`requirements-dev.txt`, `requirements-runtime.txt` without py-desmume), builds armips v0.11.0 from source at its pinned commit (cached per commit and image) and runs `check.py --fast --armips …`, so the synthetic assembly cannot be skipped there. It has no ROM and downloads no game data: the ROM tests skip, and everything `--full` adds (the sources against the Chinese ROM, the snapshots, the USA claims, GOLDEN, the full build and `expected.toml`) stays a local check before merging. A run takes about 2 minutes, 3-4 when armips is built.

**Pre-commit hook.** `.githooks/pre-commit` runs `check.py --staged` (the check on the staged files, exported to a temp folder): the whole fast check when the commit touches Python, `work/patches/`, `ruff.toml`, `work/tools/requirements*` or `.githooks/`; only the registry step (`--registry-only`, under a second) when the only such file is the decision register (`work/translate/decisions/decisions.jsonl`, e.g. a translation batch); nothing for translation-only commits. It uses `$POKE_PYTHON` if set, else the shared clone's `.venv/bin/python` if there is one, else `python3`, and needs Python 3.11 or newer.

It is not active by itself, and `core.hooksPath` must not be set: the clone's shared `.git/hooks/` already holds the `pre-commit` and `pre-push` hooks of the author identity guard (`originheartgold_identity.py`), and `core.hooksPath` would switch them off in every worktree. To activate it, the shared `.git/hooks/pre-commit` becomes a dispatcher that runs the identity guard first and then the repository's hook of the worktree being committed, if it exists and is executable:

```sh
#!/bin/sh
# .git/hooks/pre-commit (shared by every worktree): the identity guard, then the repo's own check
python3 "$(git rev-parse --git-common-dir)/hooks/originheartgold_identity.py" commit "$@" || exit $?
hook="$(git rev-parse --show-toplevel)/.githooks/pre-commit"
if [ -x "$hook" ]; then
    exec "$hook" "$@"
fi
```

`git commit --no-verify` skips both for one commit.

## The guide website

The quest guide (`guide/*.md`) and the generated game docs are published as a website from `site/`. See [site/README.md](site/README.md) for how it is built and how to write guide entries.

## Pull requests

Keep PRs small: one area, a few banks, or one fix. Say what you changed and why. PRs must pass `qa.py check` with 0 errors on every bank they touch.

By contributing, you agree that your contributions are released under this repo's licenses (Apache 2.0 for code, CC0 for translation text and docs). See the [README](README.md#license).
