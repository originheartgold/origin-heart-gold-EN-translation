# Translation tool environment

Run commands from the repository root. This project uses uv 0.12.23, Python 3.14.8, Ruff
0.16.10, mypy 2.4.0, and ndspy 4.2.0. `work/uv.lock` records the complete
dependency resolution. `work/.venv` is isolated from the existing root `.venv`,
which remains the environment for emulator and runtime analysis tools.

The user approved these dependency downloads. For a fresh checkout, obtain
permission before downloading tools or dependencies as required by `AGENTS.md`.

The system uv 0.12.10 predates the Python 3.14.8 download catalogue. A local
bootstrap installation avoids changing the system uv or the root environment:

```sh
UV_CACHE_DIR="$PWD/work/build/uv" uv pip install --target work/build/uv-bootstrap uv==0.12.23
UV_CACHE_DIR="$PWD/work/build/uv" UV_PYTHON_INSTALL_DIR="$PWD/work/build/python" work/build/uv-bootstrap/bin/uv sync --project work --locked
```

Run the focused gate without any automatic downloads:

```sh
work/.venv/bin/python work/tools/check_translation.py
```

The gate checks the context extractor, evidence packager, evaluation harness,
their synthetic tests, and the runner itself. It runs Ruff lint and formatting
checks, strict mypy, and the standard-library unittest suite. Missing target
files fail the gate. It does not modify files, build a ROM, contact a service,
or require local game data. Existing `qa`, `text_catalog`, and `docs.romdata`
imports are explicit untyped boundaries; this change does not expand checks to
all legacy tools.

To check one tool while working on it:

```sh
work/.venv/bin/python -m mypy --config-file work/pyproject.toml work/tools/translation_eval.py work/tools/test_translation_eval.py
work/.venv/bin/python -m ruff check --config work/pyproject.toml work/tools/translation_eval.py work/tools/test_translation_eval.py
work/.venv/bin/python -m ruff format --check --config work/pyproject.toml work/tools/translation_eval.py work/tools/test_translation_eval.py
```

Only format files you own. Do not run a repository-wide auto-fix. Generated
indexes, packages, evaluation results, Python installations, and caches belong
under ignored `work/build/`; installed dependencies belong in ignored
`work/.venv/`. Neither the environment nor the lockfile distributes game data.

The [translation workflow](../translate/text_catalog/README.md#script-context-and-independent-review-packages)
documents script extraction, review packages, and blind evaluation commands.
The [annotation report workflow](../translate/text_catalog/README.md#readable-annotation-reports)
shows contextual reviews beside automatic evidence, with explicit draft/reviewed
provenance and stale-source separation. Rebuild the completed local meaning review
with `python3 work/build/meaning-review-20261008/stage6/build_report.py` and open
`work/build/meaning-review-20261008/review.html`. Its 30 cases include 22 applied
corrections, six retains and two evidence holds; human benchmark ratings remain
zero. Catalogue rendering has its own synthetic gate:
`python3 -m unittest work/tools/test_text_catalog.py -v`.
The original prepared evaluation is identified by `work/build/translation_eval/latest.json`.
The LLM-only strengthening run is under
`work/build/translation-strengthening-20261008/`; its `plan.json` records stage status.
It preserves all 200 cases: 120 development, 40 regression and 40 held out,
including all 23 approved correction examples. Deeper static extraction gives
all 63 field-dialogue cases bounded script paths (12 more than the original
pilot). The other 137 cases use category and structural context, with unresolved
native consumers and speaker identities recorded explicitly.

The run contains 200 fresh source-only candidates, 200 fresh context-informed
candidates, and 200 anonymous three-way LLM reviews against the existing English.
DeepL is excluded. Candidate generation and review use fresh subagents with the
same inherited session model; these results compare workflows, not providers.
LLM judgments are provisional. Human benchmark ratings remain zero.

The experiment uses the exact historical inputs in `frozen-project/`, with
fingerprints in `frozen-inputs/manifest.json`. The live decision register changed
during generation; the matching earlier snapshot was recovered and validated.
Validate this historical dataset against its frozen root, not the evolving live
repository. No candidate or review automatically changes a bank or an approval.
The completed reconciliation and reusable evidence are under `stage4/`, with
`review.html` as the browser-tested discussion page. All 180 upstream uncertainties
are accounted for; 1,918 evidence records cover all 200 cases. The default loader
returns 464 verified or scoped approved records and excludes 1,454 proposals or
unresolved records. Validate or query the local evidence without changing banks:

```sh
work/.venv/bin/python work/build/translation-strengthening-20261008/stage4/load_knowledge.py --validate
work/.venv/bin/python work/build/translation-strengthening-20261008/stage4/load_knowledge.py --ref a027/0054#47
```

Rebuild the page with `stage4/build.py` using the same Python environment.
`stage4/SCHEMA.md` documents provenance, partial approvals, and reproduction.
New open questions D-2044–D-2050 are linked from the report; they are not approvals.

The focused examples in `work/build/translation_context/examples/` and the
independent audit in `work/build/translation_context/INDEPENDENT_AUDIT.md` show
the Gold, Archie and Griseous Orb cases. The audit checks static ROM evidence;
it does not claim emulator validation or complete path coverage.

Version sources: [uv 0.12.23](https://pypi.org/project/uv/0.12.23/),
[Python 3.14.8](https://www.python.org/downloads/release/python-3148/),
[Ruff 0.16.10](https://pypi.org/project/ruff/0.16.10/), and
[mypy 2.4.0](https://pypi.org/project/mypy/2.4.0/).
