# Text catalogue and Mandarin analysis

The catalogue brings the bank text, its existing English, Mandarin pronunciation,
word meanings, character meanings, and game context into one local SQLite database.
It imports every bank under `work/translate/banks/` plus the four labels in
`work/translate/hardcoded/strings.json`.

**Existing bank JSON remains the build input.** The catalogue is a lossless,
rebuildable index and an annotation workspace. This first migration does not switch
the ROM builder or translation tools to a new source of truth. Nothing rewrites
the English, Chinese, wrapping, QA exceptions, or decisions during import.

Run all commands from the repository root.

## Use it

```sh
# Rebuild entirely offline using the approved local dictionary/package downloads.
python3 work/tools/text_catalog.py build \
  --cedict work/translate/text_catalog/vendor/cedict_1_0_ts_utf-8_mdbg.txt.gz \
  --pypinyin-path work/translate/text_catalog/vendor/python

# Read a line and its full word/character breakdown as JSON.
python3 work/tools/text_catalog.py show 'a027/0047#14'

# Inspect every dictionary reading/sense, or locate uses in Chinese/English.
python3 work/tools/text_catalog.py lookup 行
python3 work/tools/text_catalog.py search 超音蝠
python3 work/tools/text_catalog.py search 'Zubat' --limit 5

# Generate a portable HTML review with expandable dictionary definitions.
python3 work/tools/text_catalog.py report 'a027/0047#14' 'hardcoded#overlay58:0x6F0' \
  --out work/build/text_catalog/review.html

# Coverage, missing character definitions, integrity, and workspace freshness.
python3 work/tools/text_catalog.py stats
python3 work/tools/text_catalog.py verify

# Exact original bank files, including formatting, into a NEW directory.
python3 work/tools/text_catalog.py export work/build/text_catalog/roundtrip

python3 -m unittest work/tools/test_text_catalog.py -v
```

The default database is `work/build/text_catalog/catalog.sqlite3`. Put `--db PATH`
before the subcommand to use another database. `build` without optional dictionary
arguments works without dependencies; it explicitly leaves missing pronunciation
and meanings unresolved. The tool never downloads anything. A rebuild replaces
only the generated database, atomically; a failed rebuild preserves its predecessor.

## Data model

| Layer | Stored data | Why it is separate |
|---|---|---|
| File | Exact input bytes, SHA-256, bank metadata, map context | Byte-for-byte recovery and retention of unknown fields |
| Source text | Chinese, source SHA-256, language classification, suggested analysis | Identical Chinese in the same language shares one analysis |
| Text occurrence | Stable `narc/bank#id`, English, translation status/origin, full original entry, batch context | Identical Chinese can have different speakers, branches, and English |
| Dictionary reading | Simplified form, traditional form, numbered Pinyin, tone-marked Pinyin, provenance | Multiple readings and merged traditional forms stay distinct |
| Dictionary sense | Stable ID, reading ID, ordered English gloss group | One reading can have several meanings; synonyms stay grouped |
| Project term | Chinese, official/project English, scope, glossary or decision reference | A Pokémon name is not its literal component meanings |
| Review annotation | Occurrence reference, source hash, spans, selected readings/senses, notes, reviewer | A contextual interpretation is distinct from dictionary possibilities |

`schema.sql` is the executable schema. SQLite stores definitions once and indexes
occurrences and dictionary forms. Bank context is stored once per file. Analysis
is compressed JSON in `sources.analysis` (zlib + UTF-8); the CLI expands it and
joins shared dictionary definitions on demand. This avoids repeating full character
dictionaries in 76,000 bank entries. The FTS5 table supports English/Pinyin SQL
queries; CLI `search` uses literal substrings so a single Chinese character works.

Stable reading and sense IDs are hashes of their source content. A dictionary
change that alters a definition gets a new ID; an old selected sense cannot
silently acquire a different meaning. The source dictionaries and their actual
headers/version are recorded in `dictionary_sources`; the pinned download
information is in `sources.lock.json` and `CREDITS.md`.

## What a breakdown means

Pinyin is **pronunciation**, not an English translation. Store these separately:

1. Exact Chinese, including control codes and punctuation.
2. Suggested full-line Pinyin, with tones and original tags.
3. Existing natural English translation, with its own game layout.
4. Suggested word spans and their dictionary meanings or project names.
5. Each character, its source offset, contextual Pinyin suggestion, and all available
   dictionary readings with their separate sense groups.
6. Optional reviewed choices, literal explanation, grammar notes, speaker/branch
   notes, or a full-line pronunciation correction.

For a synthetic example, **银行** is *yín háng*, “bank.” **行** separately has readings
such as *háng* and *xíng*. The sentence should not be interpreted by substituting
every possible English meaning of each character. Likewise, a project name’s
component meanings explain its construction but do not replace its official name.

The `show` output provides `words`, `characters`, and the original `translation`
payload. In each reading, `senses` holds independently selectable gloss groups.
CC-CEDICT slash boundaries are retained; semicolon-separated glosses within a
group are preserved verbatim. Older dictionary entries do not consistently separate
synonyms from genuinely different senses, so these remain **source sense groups**,
not a claim of exhaustive linguistic classification.

`suggested_pinyin` is a context-based automatic proposal. `pinyin_candidates` and
`pronunciation_candidates` retain alternatives. `reading_conflict` means the
automatic word reading differs from its dictionary candidates. A dictionary hit
does not select a meaning. Nulls and missing definitions remain explicit.

An empty candidate list means comparison is **unknown/unavailable**, even when
`reading_conflict` is false. In particular, a registered phrase can lack a whole
phrase dictionary reading. The HTML report explicitly distinguishes missing
comparison, a match to a candidate, and a differing reading; none proves a
contextual interpretation correct. Automatic pypinyin uses `tone_sandhi=False`,
but its phrase data can still differ from a reviewer's citation-tone convention.
Older snapshots labelled “citation tones” do not guarantee that convention. The
report preserves their automatic output and labels rather than normalising it.

### Readable annotation reports

`report` renders source-current annotations before a separate, expandable
automatic comparison. It shows contextual full-line Pinyin, literal explanation,
grammar/idioms, clauses, uncertainties, character → contextual Pinyin → English
role tables, word-span notes and selected dictionary senses. Selected sense IDs
are resolved against the shared dictionary; alternatives and source/reading IDs
remain available in the automatic tables. Raw alternative definitions need not
be copied into tracked annotations. Additional annotation fields are escaped and
available as evidence rather than silently discarded.

`review_status`, `reviewer_kind` and reviewer identity remain visible. Drafts are
proposals; an LLM-reviewed annotation is not human approval or ground truth.
Missing fields display as unknown/unavailable. A stale or unverified annotation
appears separately as historical evidence with both hashes, and its offsets or
pronunciation never replace current source/automatic data. Entries without an
annotation retain the source, automatic Pinyin, English, word and character
layers. Reports are local HTML with case navigation, text search and expandable
evidence, without external assets or network requests.

For custom review delivery, the Python API remains `render_report(db, refs)` and
also accepts keyword-only `summary` and `case_notes` JSON data. `case_notes` maps
references to evidence such as outcomes, before/after English and rationale.
These are rendered as escaped text, never HTML; nested evidence is collapsible.
The caller must verify that its evidence and catalogue match the live workspace.
`build(root, ...)` now defaults to the annotation store under the supplied root;
an explicit `annotations` path takes precedence. The CLI retains the live-project
default. `inspect` derives annotation state from the database, ignoring any
payload field that tries to override it.

The completed 30-case meaning review has a reproducible local builder:

```sh
python3 work/build/meaning-review-20261008/stage6/build_report.py
```

It checks source hashes, current English, bank freshness and annotation-store
freshness before writing `work/build/meaning-review-20261008/review.html`.
It includes optional `coordinator-reconciliation.json` on each rebuild and writes
input hashes and structural validation under `stage6/`. Stages 1–5 stay frozen.
The report distinguishes 22 corrections across 21 banks, six retained cases,
two evidence holds and zero human benchmark ratings. It is an LLM review of
selected cases, not a population accuracy estimate or proof of method superiority.

## Review workflow

Durable reviews live in `annotations.jsonl`, outside the generated database. Create
one JSON file with a complete review for a single reference; obtain its source hash,
reading IDs, sense IDs, and character offsets from `show`. For example:

```json
{
  "ref": "a027/NNNN#ID",
  "source_sha256": "copy the source_sha256 from show",
  "review_status": "draft",
  "reviewer": "reviewer name",
  "literal_english": "Optional close explanation, distinct from the game translation",
  "grammar_notes": "Optional particles, idiom, ambiguity, or sentence construction",
  "tokens": [
    {
      "start": 0,
      "end": 2,
      "reading_id": "copy a matching dictionary reading ID",
      "sense_id": "copy a sense belonging to that reading",
      "note": "Why this interpretation fits the scene"
    }
  ]
}
```

Offsets are **zero-based Unicode code-point offsets in the exact original Chinese**,
with an exclusive end. They are not byte or UTF-16 offsets. Current review spans
must not overlap or include game tags. A custom token `pinyin` and `note` can
represent a missing dictionary reading; do not invent a dictionary sense ID.
Review notes and literal explanations must still obey the project's translation
rules, including the lyrics policy. This is an English-only annotation workflow.

```sh
python3 work/tools/text_catalog.py annotate work/build/text_catalog/my-review.json
# Then rerun the build command above to refresh the derived database.
```

`annotate` validates the reference, source hash, live bank freshness, spans, and
selected reading/sense relationships before writing atomically under a file lock.
It replaces that reference's **complete** review, preserving other references.
`review_status: reviewed` requires a named reviewer. Existing translation status
(`draft`/`reviewed`) is independent of linguistic review status.

A changed Chinese source marks the annotation `stale` on rebuild. `show` displays
stale annotations separately; it never applies them to the new text. Removed
references and invalid dictionary IDs cause an explicit rebuild failure instead
of dropping reviews. Reviews currently appear beside automatic suggestions;
they do not rewrite the bank text or silently replace automatic analysis.

## Boundaries and remaining review

- The initial word boundaries use deterministic longest dictionary/project-term
  matching. They are suggestions, not a grammatical parser. Full-line Pinyin uses
  pypinyin's phrase data and may disagree with these word boundaries.
- The dictionaries are not exhaustive. Slang, dialect, fictional names, names
  borrowed from Japanese, wordplay, and context-dependent readings need review.
- Pinyin stores dictionary/citation tones. Spoken tone sandhi and detailed audio
  pronunciation are outside this first format.
- Simplified and traditional dictionary forms are retained separately. The source
  Chinese is never normalised or silently corrected.
- Layout tags can split a word. Automatic analysis removes layout tags while
  retaining an exact map back to source offsets. Variables/control codes are word
  boundaries. Full-line Pinyin preserves the original tags.
- Known foreign-language passthrough banks and kana-containing strings are
  catalogued but not automatically pronounced as Mandarin. Language detection is
  conservative, not a linguistic certification. Punctuation such as `・・・` alone
  is not treated as Japanese.
- Lyric placeholders are preserved and never hydrated or analysed. Repeated
  placeholders may share a source row, while every occurrence remains present.
- This imports message banks and registered hardcoded labels. Baked-in graphics
  and arbitrary text inside binaries are outside the text catalogue.
- No banks were rewritten, so this migration requires integrity/round-trip tests,
  not a new ROM or changes to existing bank QA exceptions.

The database, exported snapshots, reports, and downloaded dictionaries stay in
ignored local directories. They include game text and must not be committed or
published. Track the tool, schema, annotation records, documentation, and source
provenance; regenerate the local database when the banks change.

## Script context and independent review packages

The typed Python analysis environment is documented in
[`work/translation-tools/README.md`](../../translation-tools/README.md). It is
separate from the existing ROM/runtime environment. Run these commands from the
repository root after the documented environment setup:

```sh
# Read the untouched Chinese ROM; build an ignored context index, not a ROM.
work/.venv/bin/python work/tools/translation_context.py build
work/.venv/bin/python work/tools/translation_context.py show 'a027/0054#47'

# Deepen a specific scene using the script-file number found in the index.
work/.venv/bin/python work/tools/translation_context.py build \
  --root-file 18 --max-states 5000 \
  --out work/build/translation_context/gold-focused.json

# Existing English, relevant decisions, linguistic data and script evidence.
work/.venv/bin/python work/tools/translation_package.py 'a027/0054#47' \
  --out work/build/translation_context/gold-review.json

# Fresh translator input: existing English, notes, annotations and target-specific
# decisions are excluded. Glossary English and applicable general rules remain.
work/.venv/bin/python work/tools/translation_package.py 'a027/0054#47' \
  --mode independent --out work/build/translation_context/gold-independent.json

# Lint, formatting, strict typing of the new tools, and synthetic tests; offline.
work/.venv/bin/python work/tools/check_translation.py
```

The index records precise message operands, branches, local/standard calls,
variable and name-buffer provenance, event bindings, and preceding-message
alternatives. Packages attach the corresponding Chinese and possible following
messages. A declared script entry or static path does not prove a playable scene:
world-state feasibility remains unproven. Unknown instructions clear assumptions;
unsupported operations, unresolved values and exploration limits are diagnostic
data. Missing context does not prove a line is unused. A party-slot number does
not establish which Pokémon occupies it. NPC event bindings do not automatically
identify the speaker.

The default traversal is bounded to 250 states per entry root and eight stored
path contexts per physical message site. A separate operand scan records direct
message references that traversal did not reach, labelled `instruction-only`.
That label supplies a script location without asserting a predecessor, speaker
or playable path. Omitted contexts and exhausted budgets are counted. For deeper
investigation, repeat `--root-file` for relevant caller files and raise
`--max-states`; callees remain available. A focused index describes only its
declared scope. Pass it to the packager with `--context-index`.

Context is separate from the catalogue because its provenance includes ROM bytes,
decoder, opcode table, map bindings and extractor version. A changed dependency
invalidates the index. Packages also check bank freshness, include policy/glossary
fingerprints, and hash the complete payload. Source Chinese remains unchanged.
Both artifacts are local evidence, not translation approvals.

By default a package shows at most 12 script occurrences, successor alternatives
per occurrence, and event bindings per root, plus 20 identical-source occurrences.
Distinct roots and message sites are shown before repeated branch variants.
Counts and truncation warnings are explicit;
use `--occurrence-limit` and `--related-limit` or inspect the complete index when
more alternatives are needed. Identical Chinese is linked, never automatically
assumed to share meaning or speaker.

## Translation evaluation

`work/tools/translation_eval.py` prepares deterministic local evaluation datasets,
imports independently generated candidates, produces anonymous paired reviews,
and validates human scores. It makes no API calls and cannot declare a translator
better merely because its wording differs from the baseline.

```sh
work/.venv/bin/python work/tools/translation_eval.py sample \
  --size 200 --out work/build/translation_eval/my-sample
work/.venv/bin/python work/tools/translation_eval.py --help
```

After generating independent packages for the sample refs, pass their directory
with `--context-dir`. Candidate JSONL rows require `ref`, `dataset_id`,
`source_sha256`, and `en`. The provenance JSON requires `provider`, `model`,
timezone-bearing `generated_at`, `prompt_sha256`, and `input_sha256`; these are
recorded claims, not proof of which provider produced the text.

```sh
work/.venv/bin/python work/tools/translation_eval.py import-candidates \
  --dataset work/build/translation_eval/my-sample \
  --input work/build/translation_eval/candidates.jsonl --name alternative \
  --provenance work/build/translation_eval/provenance.json
work/.venv/bin/python work/tools/translation_eval.py blind \
  --dataset work/build/translation_eval/my-sample \
  --out work/build/translation_eval/blind-review \
  --left baseline --right alternative --split heldout
```

Share only the relevant split's input file with the translator. Give reviewers
the anonymous review, rubric and independent context; keep the baseline,
candidate provenance, dataset metadata and `answer-key.jsonl` private. Use
`score` to validate completed human ratings and `report` to summarise them.

Development, regression and held-out samples are kept separate. Whole banks stay
in one split; cross-bank repeated Chinese is excluded from ordinary sampling.
Approved regression examples can be supplied separately with `--regression-refs`.
This is a diagnostic sample that intentionally includes difficult categories,
not an unbiased estimate of all game text. Scenes spanning banks and paraphrased
duplicates still need contextual review before a formal benchmark.

Independent input files exclude the baseline English. A `--context-dir` can attach
validated independent packages, including their hashes. Current English lives in
a separate baseline artifact. Candidate imports record provider/model/prompt
provenance and validate source freshness and protected tags. Risk flags for
numbers, negation, sensitive wording and disagreement are questions, not verdicts.
Blind reviews keep candidate identities in a separate coordinator key. Human
scores cover meaning, omissions, additions, tone, terminology and fluency; reports
identify unscored cases instead of treating them as successful translations.
