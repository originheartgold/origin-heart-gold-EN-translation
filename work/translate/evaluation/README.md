# Dialogue quality trial

The first trial selects 24 difficult **development** cases from the prepared
200-case evaluation. It preserves the 40 regression and 40 held-out cases and
never writes a bank. Full Chinese, English candidates, prompts, blind packets,
answer keys and scores remain local under ignored `work/build/translation_eval/`.
This is a diagnostic sample, not a whole-game quality estimate.

## Reproduce preparation

Run from the repository root with the existing local inputs (no downloads):

```sh
python3 work/tools/translation_trial.py \
  --dataset work/build/translation_eval/context-pilot-v2 \
  --packages work/build/translation_eval/packages-v2 \
  --out work/build/translation_eval/dialogue-trial-24-new
```

The tool rejects stale banks/context dependencies, altered independent inputs,
held-out/regression selection, outputs outside `work/build`, and overwrite of an
existing trial. `source-only.jsonl` contains only Chinese and integrity IDs.
`context-enriched.jsonl` adds the same previously verified independent package's
static paths, explicit source speaker labels, and provisional phrase/scene
analysis in `dialogue-trial-notes.json`. The notes are not approved global rules.

The context includes branch predicates and buffer producers, with their exact
script file/PC. Unknown flags, unresolved buffers and world-state feasibility
stay unknown. Static successors remain possible alternatives. Map metadata is
not evidence of speaker identity. Whole-bank adjacency does not prove order.
A character breakdown does not establish a compound's meaning: each curated
phrase has a phrase-level sense, pronunciation and explanation as well.

This pilot covers dialogue only. Before sampling **menus**, supply menu-option
order, cursor/result bindings, cancellation behavior and category-specific
width limits. Before sampling **Pokédex** prose, supply the species/form mapping,
entry category, glossary names and applicable source-version facts. Do not
invent dialogue speakers or social relationships for either category. These
other strata remain unmeasured by the 24-case pilot.

## Candidate generation and blindness

Generate source-only and context-enriched candidates in separate fresh model
sessions with no baseline or shared history. Preserve `ref`, `dataset_id`,
`source_sha256`, every protected tag, and add `en`. Save the exact generation
prompt and input hashes, provider/model (unknown if unexposed), time basis and
isolation limits. One sample per arm does not isolate stochastic variation;
repeat runs with fixed known model/settings before claiming a context effect.

The current local run is `work/build/translation_eval/dialogue-trial-24`.
It has 24 fresh Codex source-only and 24 fresh Codex enriched candidates, imported
as `trial-llm-source-only` and `trial-llm-context-enriched` into the prepared
dataset using the existing `translation_eval.py import-candidates` command.
The exact runtime model identifier is unavailable; provenance says so. The
model sessions were instructed to read only their assigned input files.

No DeepL credential is configured. **No DeepL result was produced.** Its arms
remain pending, not zero-scored or imitated by another LLM. Once access exists,
use the same Chinese for the source-only arm; any enriched arm must record the
actual provider-supported context and limits. Do not silently concatenate
context into the text to be translated. Import actual provider responses with
the existing provenance/tag checks. Missing arms must remain visible in reports.

The initial blind packet pools and shuffles three pairwise comparisons for the
same 24 refs: baseline/source, baseline/enriched and source/enriched (72 pairs).
The reviewer receives only `reviewer-packet/review.jsonl`, `context.jsonl`,
`rubric.json` and `score-template.jsonl`. The reviewer cannot read answer keys,
candidate provenance or baseline files. Both sides receive identical evaluation
context. Formatting/style can still reveal a candidate, and a single same-family
model reviewer is not independent human ground truth.

## Review, corrections and reusable evidence

Score meaning, omissions, additions, tone, terminology and fluency independently
on 0–4, using null for genuinely unassessed dimensions. Record Chinese evidence,
scene evidence and concrete alternatives for uncertain interpretations. Keep
all pairs, including ties, uncertain judgments and candidate failures.

The evaluation harness rejects explicit model rows and model artifacts at its human scoring/report boundaries. Legacy untyped human rows remain compatible.
For this trial's model reviewer, use the separate explicit LLM report path:

```sh
python3 work/tools/translation_trial.py \
  --dataset work/build/translation_eval/context-pilot-v2 \
  --review work/build/translation_eval/dialogue-trial-24/blind-source-context \
  --scores work/build/translation_eval/dialogue-trial-24/blind-source-context/llm-scores.jsonl \
  --out work/build/translation_eval/dialogue-trial-24/context-effect-report.json
```

Each score row must include `reviewer_kind: "llm"`; the report requires every
pair, fingerprints the evidence, reports `human_reviewed: 0`, and labels results
provisional. Partition the pooled scores by the original `review_id` before
running this command for each pairwise directory. Never feed model judgments to
the human-only report command or promote them to accepted regression truth.

Turn reviewed findings into decisions using `decisions.py add` (one phrase,
pronunciation, voice or canon finding per record, source `agent:quality-trial-24`),
with source refs, rationale and provisional/open status. Do this **after** locking
review artifacts: changes to the decision register intentionally invalidate
prepared context fingerprints. Existing 23 approved correction examples remain
in the original 40-case regression split. New uncertain findings stay pending;
only explicitly approved source-error corrections may change a bank.

For an approved correction: back up the bank, edit only its authorized fields
atomically, cite the finding in notes, wrap only the affected IDs using
`--mode scroll --which max`, and run `qa.py check` on every touched bank until
zero errors, resolving real number/tag/layout/glossary warnings. Preserve the
old failure and approved wording as a regression case tied to the decision ID.
Rebuild a fresh dataset snapshot after corrections, keeping old experiments
immutable. Then prioritize threats, insults, ambiguous subjects, branches and
verified canon references bank by bank; do not scale an unvalidated workflow.

## Verification

```sh
work/.venv/bin/python -m unittest discover -s work/tools -p test_translation_trial.py -v
work/.venv/bin/python -m ruff check --config work/pyproject.toml work/tools/translation_trial.py work/tools/test_translation_trial.py
work/.venv/bin/python -m mypy --config-file work/pyproject.toml work/tools/translation_trial.py work/tools/test_translation_trial.py
```

The synthetic tests cover source isolation, source/context tampering, held-out
exclusion, immutable ignored outputs, complete scoring and human/LLM separation.
No ROM build, download, bank modification or publication is part of this trial.

## First trial results (2026-10-07)

All 72 provisional model assessments are locked in the three `blind-*` folders
as `llm-report.json`. Against baseline, each fresh arm has 8 preferences, 1
baseline preference, 14 ties and 1 unsure. Direct source/enriched comparison has
3 preferences each and 18 ties. This run does not demonstrate an aggregate
context gain. It is one same-family model review of a purposive sample.

Three source-faithful translation revisions were applied (0066#87 neutral
implicit agent; 0123#31 and adjacent #33 omitted collecting conditions), each with backup, decision
and pending regression record. Both banks pass QA with zero errors. They are
agent corrections under the user's task authorization, not human-approved
regression truth. No speculative source typo, name or canon change was applied.

Questions D-2029–D-2034 and provisional phrase/pronunciation records
D-2035–D-2037 retain the uncertainties; revision records are D-2038–D-2040.
D-2041 qualifies the earlier gender-error claim: adjacent 0066#84–86 name Archer,
so baseline “he” is plausible and not a proven error without execution evidence.
The #33 follow-up was outside the 24-case scored sample; scores remain unchanged.
The ignored `findings-followup.json` has source evidence, alternatives,
dispositions, autonomous choices and exact results for the review page.
`next-review-queue.json` supplies the next investigation priorities.

The original dataset is now intentionally stale after register/bank changes;
keep its locked reports as historical evidence and prepare a new snapshot for
new experiments. DeepL and evaluation of the remaining cases/banks are pending.
