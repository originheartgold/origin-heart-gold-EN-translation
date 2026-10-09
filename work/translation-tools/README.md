# Translation tool environment

Run commands from the repository root. This project uses uv 0.12.23, Python 3.14.8, Ruff
0.16.10, mypy 2.4.0, and ndspy 4.2.0. `work/uv.lock` records the complete
dependency resolution. `work/.venv` is isolated from the existing root `.venv`,
which remains the environment for emulator and runtime analysis tools.

Two environments, two gates:

| Gate | Environment | Tools and pins |
| --- | --- | --- |
| `work/tools/check.py` (repo-wide: fix registry, `ruff check` with `ruff.toml`, unit tests, `--full` build) | root `.venv` | `work/tools/requirements-dev.txt`: ruff 0.16.8, capstone |
| `work/tools/check_translation.py` (translation tooling: ruff with `work/tools/ruff-translation.toml`, strict mypy with `work/pyproject.toml`, tests) | `work/.venv` | `work/uv.lock`: ruff 0.16.10, mypy 2.4.0, ndspy |

The ruff pins differ (0.16.8 in the root `.venv`, 0.16.10 here); aligning them needs a download, so it waits for the user. Change both pins together.

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

The gate checks the context extractor, the evidence packager, their synthetic
tests, and the runner itself. It runs Ruff lint and formatting
checks, strict mypy, and the standard-library unittest suite. Missing target
files fail the gate. It does not modify files, build a ROM, contact a service,
or require local game data. Existing `qa`, `text_catalog`, and `docs.romdata`
imports are explicit untyped boundaries; this change does not expand checks to
all legacy tools.

To check one tool while working on it:

```sh
work/.venv/bin/python -m mypy --config-file work/pyproject.toml work/tools/translation_package.py work/tools/test_translation_package.py
work/.venv/bin/python -m ruff check --config work/tools/ruff-translation.toml work/tools/translation_package.py work/tools/test_translation_package.py
work/.venv/bin/python -m ruff format --check --config work/tools/ruff-translation.toml work/tools/translation_package.py work/tools/test_translation_package.py
```

Only format files you own. Do not run a repository-wide auto-fix. Generated
indexes, packages, evaluation results, Python installations, and caches belong
under ignored `work/build/`; installed dependencies belong in ignored
`work/.venv/`. Neither the environment nor the lockfile distributes game data.

The [translation workflow](../translate/text_catalog/README.md#script-context-and-independent-review-packages)
documents script extraction and review packages. The blind-evaluation tools
(`translation_eval.py`, `translation_trial.py`, `work/translate/evaluation/`) were removed on 2026-10-09;
git history keeps them, and their local runs stay under ignored `work/build/`.
The [annotation report workflow](../translate/text_catalog/README.md#readable-annotation-reports)
shows contextual reviews beside automatic evidence, with explicit draft/reviewed
provenance and stale-source separation. Rebuild the completed local meaning review
with `python3 work/build/meaning-review-20261008/stage6/build_report.py` and open
`work/build/meaning-review-20261008/review.html`. Its 30 cases include 22 applied
corrections, six retains and two evidence holds; human benchmark ratings remain
zero. Catalogue rendering has its own synthetic gate:
`python3 -m unittest work/tools/test_text_catalog.py -v`.
The focused examples in `work/build/translation_context/examples/` and the
independent audit in `work/build/translation_context/INDEPENDENT_AUDIT.md` show
the Gold, Archie and Griseous Orb cases. The audit checks static ROM evidence;
it does not claim emulator validation or complete path coverage.

Version sources: [uv 0.12.23](https://pypi.org/project/uv/0.12.23/),
[Python 3.14.8](https://www.python.org/downloads/release/python-3148/),
[Ruff 0.16.10](https://pypi.org/project/ruff/0.16.10/), and
[mypy 2.4.0](https://pypi.org/project/mypy/2.4.0/).
