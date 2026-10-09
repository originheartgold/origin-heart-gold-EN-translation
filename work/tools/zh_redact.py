"""zh_redact - keep third-party song lyrics out of the published workspace.

A few Chinese source strings are song lyrics (anime theme songs, C-pop lines). The published bank
files must not reproduce them, but the build only uses our English for a string whose workspace zh
equals the dump (work/extract/v4). So such an entry stores a marker instead of the Chinese:

    "zh": "[zh redacted: song lyrics; sha256:<sha256 of the original zh, UTF-8>]"

and the tools treat the marker as equal to the dump text whose hash matches:
    ws.py init/export/import  -> matches()   (no zh_changed flag; English is exported)
    qa.py check/wrap          -> hydrate()   (fills the real zh in memory from the local dump)
Nothing ever writes the hydrated text back. Redact a string with `ws.py redact NARC BANK ID...`.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

MARK_RE = re.compile(r"^\[zh redacted: song lyrics; sha256:([0-9a-f]{64})\]$")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def marker(text: str) -> str:
    return f"[zh redacted: song lyrics; sha256:{digest(text)}]"


def is_marker(zh) -> bool:
    return isinstance(zh, str) and MARK_RE.match(zh) is not None


def matches(ws_zh, source_zh) -> bool:
    """True if the workspace zh is the source text, or a redaction marker of exactly that text."""
    if ws_zh == source_zh:
        return True
    m = MARK_RE.match(ws_zh) if isinstance(ws_zh, str) else None
    return bool(m) and isinstance(source_zh, str) and m.group(1) == digest(source_zh)


@lru_cache(maxsize=64)
def _source_texts(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    return {s["id"]: s.get("text") for s in json.loads(p.read_text(encoding="utf-8")).get("strings", [])}


def hydrate(bank: dict, extract) -> tuple[dict, int]:
    """Return (copy of bank with markers replaced by the matching dump text, number replaced).
    The input is not modified; markers without a matching dump string are left as they are."""
    if not any(is_marker(e.get("zh")) for e in bank.get("strings", [])):
        return bank, 0
    src = _source_texts(str(Path(extract) / bank["narc"] / f"{bank['bank']:04d}.json"))
    out = dict(bank)
    out["strings"] = []
    n = 0
    for e in bank["strings"]:
        text = src.get(e["id"])
        if is_marker(e.get("zh")) and matches(e["zh"], text):
            e = dict(e, zh=text)
            n += 1
        out["strings"].append(e)
    return out, n
