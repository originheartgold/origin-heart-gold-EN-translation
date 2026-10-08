# Full re-review: brief for reviewer agents

You review one batch of `work/translate/review/rereview_plan.json` (ids RV001…). The coordinator gives you
the batch id and a scratch folder. Read `AGENTS.md` and `work/translate/STYLE.md` first; this brief adds to them.

## The goal (the user's words, in short)

- Stay authentic to the original Chinese text and to the intention of its authors (雁南飞TB, Alex).
- **Never change the meaning.** Don't soften threats, violence, insults, sex, or heavy and dark adult
  content: keep the strength of the Chinese, Fallout/GTA style where the Chinese is like that (D-0627). Don't
  add crudeness the Chinese doesn't have either.
- Where the Chinese quotes the Chinese anime dub or manga, use the official English dub/manga wording
  (D-1436, D-1437, D-1438), but only canon wording you can verify. If unsure, translate the Chinese and add
  a question.

Earlier passes failed by **dropping words, clauses and context**, by **paraphrasing into something smoother
but different**, and by **flattening a character's voice**. Those are the faults you are hunting.

## What to check, for every string in your batch

Every string with Chinese is in scope: `origin` `us` (official US text), `tm_v3`, `agent`, `glossary`,
everything except `copy`. Don't trust a line because it is official US text: the hack often rewrote the
Chinese at the same position, so the US line can say something else.

Compare the English with the Chinese **clause by clause**:

1. **Meaning**: same facts, same who-does-what-to-whom, same numbers, places, names, conditions, negations.
2. **Nothing dropped**: every clause, qualifier, aside, joke, insult, threat, interjection and speaker label
   in the Chinese is in the English. A Chinese idiom may become an English idiom of the same meaning and force.
3. **Nothing added**: no invented content, explanation or extra jokes.
4. **Strength and tone**: the same force. 弄死 is "kill", not "deal with"; 滚 is not "please leave"; 妈的 is a
   real curse. Mild Chinese stays mild.
5. **Voice**: the speaker's register, self-reference and verbal tics. Tone words (可恶, 滚, 老娘, 本大爷, 老子,
   insults) are chosen **per line** from the scene and the speaker (D-2081). The register's earlier renderings
   and voice records are precedents to consult, not rules to apply. A swaggering self-reference such as
   老娘 / 本大爷 is a deliberate voice marker: carry it into the English in a way that fits that speaker and line.
6. **Who is addressed and who speaks**: use the scene packet. Keep a gendered insult gendered when the target
   is known (臭丫头 to a girl). Player of unknown gender: gender-neutral English (D-1224).
7. **Names**: glossary and register names exactly. Don't rename anything; if a name looks wrong, add a question.
8. **Natural English**: fix English that is ungrammatical, unclear or clearly unnatural. Do **not** rewrite a
   correct, faithful line for taste. No churn.

## Inputs (all under `work/build/`, never commit them)

```sh
python3 work/tools/scene.py packet a027/NNNN --out work/build/rereview/RVxxx/NNNN.md   # per bank in your batch
python3 work/tools/scene.py show 'a027/NNNN#ID'                                       # one line in its scene
python3 work/tools/omission_check.py a027/NNNN --min-score 1                          # flags to examine
python3 work/tools/decisions.py list --search <zh or en>                              # names, voices, precedents
```

Don't run `scene.py build`. The cache is already built. Read the whole packet of a bank before you change
anything in it. Every omission flag and every line in `work/translate/review/d2081_tone_queue.json` that
falls in your batch must be looked at; flags are questions, not verdicts.

If you need to see how the same Chinese is translated elsewhere: `grep -rl '<zh>' work/translate/banks`.

## Rules you must not break

- **Only your batch:** only the ids in your batch's `parts`. Other agents work on other banks at the same time.
- **Fields:** change only `en`, `notes` and, when you rewrite a line, `origin` → `"agent"`. Leave `status`
  as it is (`draft`). Never touch `zh` or any other field. Strings with `status: "reviewed"` were approved
  earlier: don't edit them; if one is wrong, add a question.
- **Hack errors (D-1496, D-1500):** translate what the hack says. Never fix the hack's wrong Pokémon, name,
  number or speaker on your own: log a finding with the evidence and a proposed English line
  (`decisions.py add --type question --subtype hack-finding ...`).
- **Song lyrics (D-0368):** never translate or quote lyrics. Redacted `[zh redacted: ...]` strings stay as they are.
- **No new rules.** Don't add `style`, `term` or `voice` decisions and don't change existing ones. Everything
  you would want to make general goes in a question: `python3 work/tools/decisions.py add --type question
  --subtype rereview --ref <bank#id> --en "<issue and proposed English>" --source agent:RVxxx`.
- **Open questions on your lines:** the packet lists them. If your edit settles an open `fidelity-review`,
  `translation-quality` or `rereview` question, resolve it:
  `python3 work/tools/decisions.py resolve <id> --answer "Settled in RVxxx: <what you did>"`. Never resolve
  `hack-finding` questions or questions asking the user to decide; leave those open and mention them in your report.
- **No git commands** that change anything (no commit, add, checkout, stash, reset). `git diff` is fine.
- **No downloads, no ROM builds, no tool changes.**

## Editing safely

Work only inside the scratch folder the coordinator gives you. Before your first write, copy every bank
file you will touch into it as a backup. Edit with small Python scripts: load the JSON, change only your
fields, dump with `ensure_ascii=False`, `indent=1` (the workspace indent) and a trailing newline as the file
has it, write to a temp file and `os.replace` it. Never leave a bank empty or truncated.

For every changed line, append to its `notes`: ` | RVxxx: <category>: <short reason>`. Categories: `meaning`,
`omission`, `addition`, `softened`, `voice`, `addressee`, `canon`, `name`, `grammar`, `layout`.

Write plain English, then wrap the ids you changed:

```sh
python3 work/tools/qa.py wrap a027/NNNN --ids 12,15,40 --mode scroll --which max --reflow --in-place
```

Paragraphs → `{SCROLL}`, overflow → `{CLEAR}`; no one-word orphans; keep every `{...}` tag; keep
"Mt.", "Prof.", "S.S.", "Lt.", "Mr.", "Dr." with the following name. Check the layout of description banks
against their box (QA reports overflow).

## Gate

`python3 work/tools/qa.py check work/translate/banks/<narc>/<NNNN>.json` must report **0 errors** for every
bank you touched. Fix real warnings you caused. Then reread your changed lines in their scenes, as a player.

## Report

Write `work/build/rereview/RVxxx/report.md`: lines reviewed, lines changed per category, the 5–10 most
important changes (ref, Chinese, old English, new English, why), every question id you added, and anything
you could not finish (exact ids). Your final reply to the coordinator: the same in at most 250 words.
