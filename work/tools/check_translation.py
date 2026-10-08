#!/usr/bin/env python3
"""Run the focused translation-tool gate without downloads or ROM access."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "work/tools"
MODULES = ("translation_context", "translation_package", "translation_eval")


def main() -> int:
    files = [TOOLS / f"{name}.py" for name in MODULES]
    files.extend(TOOLS / f"test_{name}.py" for name in MODULES)
    files.append(Path(__file__).resolve())
    missing = [str(path.relative_to(ROOT)) for path in files if not path.is_file()]
    if missing:
        print("Missing required check targets: " + ", ".join(missing), file=sys.stderr)
        return 2
    paths = [str(path.relative_to(ROOT)) for path in files]
    config = "work/pyproject.toml"
    ruff_config = "work/tools/ruff-translation.toml"
    commands = [
        ["ruff", "check", "--config", ruff_config, *paths],
        ["ruff", "format", "--check", "--config", ruff_config, *paths],
        ["mypy", "--config-file", config, *paths],
        ["unittest", "discover", "-s", "work/tools", "-p", "test_translation_*.py", "-v"],
    ]
    failed = False
    for command in commands:
        print("\n> " + " ".join([sys.executable, "-m", *command]), flush=True)
        result = subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=False)
        failed |= result.returncode != 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
