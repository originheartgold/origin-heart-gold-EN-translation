# Instructions for AI agents

This repo is the English translation of 起源心金 (Pokémon Origin HeartGold) v4.0.3, a Simplified Chinese hack of Pokémon HeartGold. Run every command from the repo root. All project files live under `work/`.

## Rules for every agent

- **Never commit or publish game data.** Keep ROMs (`*.nds`), the hack's `.delta` patches, `work/extract/`, `work/build/`, `work/release/`, `work/snapshots/` and the seeding inputs (`work/translate/ref/`, `us_ref.json`, `us_reuse.jsonl`, `tm_v3.jsonl`, `tm_v4_matches.jsonl`) out of git. `.gitignore` already covers them. Don't `git add -f` around it. If a new file holds official game text or third-party text and the tools don't need it, add it to `.gitignore` too.
- **Never download anything** (ROMs, patches, tools, datasets) without the user asking for it.
- **Don't build ROMs or change tools/scripts** unless that is your task. Translator agents never do either.
- **Canon English for anime/manga quotes (user decision D-1436):** the hack is built on canon events. Where the Chinese quotes the Chinese dub of the anime or the Chinese manga (mottos, catchphrases, famous lines), use the official English dub/manga wording, not invented wording. Team Rocket's motto and "blasting off again" line are in D-1437/D-1438. Use only canon wording you can verify; if unsure, translate the Chinese and add a question. Hack-original lines and the hack's own variations are still translated from the Chinese.
- **Song lyrics:** never translate or quote song lyrics: replace them with a hum or a description line and record that as a content decision (D-0368). Don't paste official text from other games outside the rules in STYLE.md.
- **Faithful tone (user decision D-0627):** never tone down or sanitise, and never avoid adult (21+) content. Swearing, insults, innuendo, sex, violence, and dark or political jokes keep their full strength. Don't add crudeness that isn't in the source.

## Project decisions made by the user

These are settled. Don't reopen them without asking the user. Each one is recorded in the decision register (`python3 work/tools/decisions.py show <id>`).

- **English only.** No preparation for other languages (no XLIFF/PO export, no multi-language glossaries).
- **Behaviour fidelity (D-1002):** the reference for gameplay behaviour is the untouched Chinese hack (`work/rom/origin_v4.0.3_cn.nds`), not vanilla HeartGold. When something looks wrong in game, first check whether the Chinese hack does the same. If it does, it's intended: leave it. Change behaviour only where English requires it (e.g. the naming keyboard, name lengths) or where our build differs from the hack.
- **Match the Chinese exactly; log suspected hack bugs:** translate what the hack says even where it looks wrong (wrong Pokémon, name, speaker label, place, number, gender, contradictions). If the Chinese is ambiguous, keep the English ambiguous. Never silently correct. Record each suspected bug as a finding: `python3 work/tools/decisions.py add --type question --subtype hack-finding --ref <bank#id> --en "<what looks wrong>"`. The only exception is a pure character typo with no other meaning (e.g. 官材 for 棺材): translate the intended word, and still log it.
- **Obvious text errors are fixed only with the user's approval (D-1496, amends D-1195):** where the hack's text is obviously wrong and the right English is unambiguous (e.g. the script's cry and the trainer's party prove which Pokémon is meant), the English may be corrected, but only after the user explicitly approves that specific case. Agents never fix on their own: log the finding with the evidence and a proposed English line. After an approved fix, cite the finding id in the string's `notes` and resolve the finding (`decisions.py resolve <id> --answer "..." --decision-id D-1496`). A fix only replaces the wrong part: never delete text the Chinese has and never invent content (D-1500). Take the replacement from the Chinese itself, the Japanese/US original the hack translated, or official text for the right Pokémon, move or item. If a correct line would need either, keep the line and leave the finding open.
- **Pronouns and ship name:** where the Chinese uses 他 for a player who may be female, keep the English gender-neutral (D-1224). 水绿号 is "S.S. Aqua" wherever the Chinese says so, and 圣安努号 is "S.S. Anne" (D-1223).
- **Hack gameplay bugs are reported, never fixed (D-1337):** bugs in the original hack's logic (e.g. the weekday-sibling ribbon freeze, out-of-range flags, the Blackthorn tutor teaching Flail) stay as they are, in the translation patch and with no separate bugfix patch. They go into `HACK_FINDINGS.md` / `work/notes/softlock_audit.md` and the release notes.
- **Name lengths (D-0858):** US limits restored via code patches in `work/translate/hardcoded/code_patches.json`: 7 characters for trainers, 10 for Pokémon.
- **Graphics (D-0768):** translate every graphic with baked-in Chinese text, rare screens included; battle and first-hour screens first.
- **Title logo (D-0767):** bilingual. Keep the hack's 起源心金 logo and add a small "Origin HeartGold" subtitle in original lettering (the game's own font). Never copy or trace official Pokémon/HeartGold logo art.
- **Graphics are sourced, never generated:** don't draw or generate sprites, icons or labels. Search for existing assets, in this order: the user's US ROM, hg-engine, then other public, openly licensed ROM-hacking/decomp repositories and shared asset packs. Only fetch from public source repositories, check the licence, and record source, commit and licence in `work/graphics/CREDITS.md`. If nothing suitable exists, leave it unfixed and ask the user. User-approved exceptions: the bilingual title subtitle (D-0767), the in-battle panel labels composed from the game's own letter tiles (D-1109; shipped as 'Ⓑ EXIT' / '✚✚ SWAP', because 'SWITCH' does not fit the panel), the Pokédex 详细 tab label 'DATA' composed from the USA ROM's letters (D-1542), and six earlier composed graphics the user chose to keep (Pokédex type list, weather labels, naming tabs, Pokédex header, trainer card and link-capture labels). Any new exception needs the user's approval.
- **Names use mixed case** (Bulbasaur, Poké Ball), and modern official names from the glossary override US/v3 text. Menu labels follow the US all-caps style (POKéMON, CANCEL).
- **Releases are xdelta patches only,** against Pokémon HeartGold (USA), CRC32 `C180A0E9`. Never distribute a ROM.
- **Credits:** original hack by 雁南飞TB (romanised "Yannanfei TB"), v4 by Alex, Chinese patches packaged by u/riap0526, partial v3 English by u/Shake69 (reused with their permission), graphics from hg-engine (non-commercial, credits required). See `work/notes/credits_and_sources.md`.

## Read first

- `work/translate/STYLE.md`: the style rules. Follow them.
- `work/translate/decisions/DIGEST.md`: every decided name, rule and character voice. Reuse names exactly. It isn't committed: generate it first with `python3 work/tools/decisions.py render-progress --out work/translate/decisions/DIGEST.md`. Look up a term with `python3 work/tools/decisions.py list --search <zh or en>`.
- `work/translate/PROGRESS.md` → Done: which batches are finished.
- `work/notes/text_metrics.md` (box sizes, break codes), plus `python3 work/tools/qa.py --help` and `python3 work/tools/ws.py --help`.
- `work/notes/decisions_workflow.md`: how to record decisions.
- Glossary: `work/glossary/*.json`.
- Batches: `work/translate/manifest_playorder.json` → `batches[]`, ids R001–R069 in real play order. Each batch has `parts: [{bank: "a027/NNNN", ids: [first, last]}]`. The old `manifest.json` (B ids) is history only and isn't committed.
- `work/translate/bank_maps.json` says which in-game maps really use each bank. Trust it over any map label, which is only a hint.

## Translating a batch

Go through every string in the batch's bank/id ranges in `work/translate/banks/<narc>/<NNNN>.json`:

- `status` "todo", or `en` is null → translate it. Set `en`, `status: "draft"`, `origin: "agent"`.
- `status` "tm" (US text or the v3 fan translation, already QA-clean) → read it against the Chinese. If it is correct and natural, set `status: "draft"` and keep the origin. If it is wrong, stale (the hack changed the line) or clumsy, rewrite it and set origin "agent". If the hack rewrote the Chinese of a US line, retranslate it from the Chinese.
- Official US lines survive only where the hack's Chinese still says the same thing. Modernise their names to the glossary.
- `status` "draft" from an earlier agent → leave it unless it is clearly wrong.
- `origin: "copy"` (English leftovers, dashes, empty strings) → leave it unless it is Chinese.
- `zh` is `[zh redacted: song lyrics; sha256:…]` → a placeholder for song lyrics kept out of git (`work/tools/zh_redact.py`). Leave it as is; the tools fill in the real text from the local dump.

Translate from the Chinese, in context: read the whole bank in order so you know the speakers and the scene. Search the workspace for the same Chinese before you translate a recurring line, and reuse the existing English for identical Chinese. Mark route, partner or gender branches in the string's `notes` and in one context-note decision.

### Editing bank files safely

- Edit the JSON with small Python scripts. Load the file, change only the `en`/`status`/`origin`/`notes` fields of your ids, and dump with `ensure_ascii=False` and the file's existing indent.
- Never touch other fields, other banks, or ids outside your batch.
- Before your first write, copy every bank file you will touch to your scratchpad as a backup. Work only inside your own scratchpad subfolder named after your batch (e.g. `<scratchpad>/R052/`). The scratchpad is shared with other agents, so never run or overwrite scripts outside your own subfolder.
- Write atomically: write to a temp file, then rename it. Never leave a bank file empty or truncated.

### Layout

- Write plain prose, then run `python3 work/tools/qa.py wrap` on your strings to insert line breaks. Wrap per id, or use `--in-place` on a bank only if no other batch shares it. Use `--mode scroll --which max`.
- Paragraphs → `{SCROLL}`, overflow → `{CLEAR}`. Split at sentence ends. Leave no one-word `{CLEAR}` orphans: rebalance by hand.
- Keep "Mt.", "Prof.", "S.S.", "Lt.", "Mr." and "Dr." on the same line as the name that follows.
- Keep every `{...}` tag.
- Name buffers are US length: 7 characters for trainers, 10 for Pokémon. Trainer names in bank 0719 are stored compressed and may use 10 characters (D-1326); QA enforces both limits.
- English only.

## Gate

Run `python3 work/tools/qa.py check work/translate/banks/<narc>/<NNNN>.json` for every bank you touched. **It must report 0 errors.** Fix warnings that are real problems: glossary mismatches, missing numbers, lines that overflow.

Then reread your English in order, as a player would. Check flow, consistent names and tone, and the right voice for each speaker. Fix anything that's off.

If a batch runs long, finish whole banks and report exactly which ids remain. Don't rush.

## Finish

1. Append the batch ids you completed to `work/translate/PROGRESS.md` → Done.
2. Record every NEW name, term, rule or character voice with `python3 work/tools/decisions.py add ... --source agent:<your batch ids>`. Use one call per item with a one-line `--rationale`. Use `--confidence low` for invented or uncertain names. Record anything uncertain as `add --type question --ref <bank/id> --en "<issue>"`.
3. Never edit `decisions.jsonl` by hand, and never add decisions to PROGRESS.md.
4. Report: counts (translated / accepted US / accepted v3 / rewritten), what the scenes really are, 3 sample lines (zh → en), the decision ids you added, and any open questions.

Don't use `decisions.py rename`, `set` on other people's records, or `import-csv`. Those are for the user and the coordinator.
