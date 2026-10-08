#!/usr/bin/env python3
"""findings_report - readable report of suspected bugs in the hack's Chinese (D-1195).

Sources:
  * decision records with subtype "hack-finding" in work/translate/decisions/decisions.jsonl
  * work/translate/decisions/hack_findings_import.jsonl, if present (findings not yet imported into the register;
    a ref that already has a hack-finding record in the register is skipped)

Output: work/translate/decisions/HACK_FINDINGS.md, grouped by kind (wrong Pokémon or name, speaker label,
contradiction, gender, number, typo, other). Each finding shows its ref, the Chinese excerpt, what looks wrong
and the current English (read from the banks when the string exists, else the stored value).

    python3 work/tools/findings_report.py [--register FILE] [--import FILE] [--ws DIR] [--out FILE]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

WORK = Path(__file__).resolve().parent.parent
DEFAULT_REGISTER = WORK / "translate" / "decisions" / "decisions.jsonl"
DEFAULT_IMPORT = WORK / "translate" / "decisions" / "hack_findings_import.jsonl"
DEFAULT_WS = WORK / "translate" / "banks"
DEFAULT_OUT = WORK / "translate" / "decisions" / "HACK_FINDINGS.md"

KINDS = [
    ("pokemon-or-name", "Wrong Pokémon or name"),
    ("speaker-label", "Speaker label"),
    ("contradiction", "Contradiction"),
    ("gender", "Gender"),
    ("number", "Number"),
    ("typo", "Typo (translated as the intended word)"),
    ("other", "Other"),
]
KIND_NAMES = dict(KINDS)
ALIASES = {"name": "pokemon-or-name", "pokemon": "pokemon-or-name", "label": "speaker-label", "speaker": "speaker-label"}

_RULES = [
    ("typo", re.compile(r"\btypo\b|homophone|kept-typo|dropped character|stray ", re.I)),
    ("speaker-label", re.compile(r"\blabel", re.I)),
    ("gender", re.compile(r"[他她]|\bgender\b|\bpronoun|\b(he|she|him|her)\b", re.I)),
    ("number", re.compile(r"\bnumbers?\b|\bat least \d|\b\d+ (Balls?|Pokémon|years|Badges|stages?)\b", re.I)),
    ("pokemon-or-name", re.compile(r"\bname[sd]?\b|\bPokémon\b|\bspecies\b|\bcry\b", re.I)),
    ("contradiction", re.compile(r"contradict|\bbut\b|\bwhile\b|\byet\b|elsewhere|everywhere else", re.I)),
]


def classify(rec: dict) -> str:
    """Kind of a finding: its explicit `kind` field, else a keyword guess on its text."""
    kind = (rec.get("kind") or "").strip().lower()
    kind = ALIASES.get(kind, kind)
    if kind in KIND_NAMES:
        return kind
    if rec.get("action") == "kept-typo":
        return "typo"
    text = " ".join(str(rec.get(k) or "") for k in ("what_looks_wrong", "en", "title", "rationale"))
    for name, rx in _RULES:
        if rx.search(text):
            return name
    return "other"


def read_jsonl(path: Path) -> list:
    out = []
    if not path.exists():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{n}: bad JSON ({e})") from None
    return out


def parse_ref(ref: str):
    """'a027/0445#110' or 'a027/0445#151-242' -> ('a027', '0445', 110); None if no string id."""
    m = re.match(r"^([\w]+)/(\d{4})#(\d+)", ref or "")
    return (m.group(1), m.group(2), int(m.group(3))) if m else None


class Banks:
    def __init__(self, ws: Path):
        self.ws, self.cache = ws, {}

    def string(self, ref: str):
        p = parse_ref(ref)
        if not p:
            return None
        narc, bank, sid = p
        path = self.ws / narc / f"{bank}.json"
        if path not in self.cache:
            try:
                self.cache[path] = {s["id"]: s for s in json.loads(path.read_text(encoding="utf-8"))["strings"]}
            except (OSError, ValueError, KeyError):
                self.cache[path] = {}
        return self.cache[path].get(sid)


def collect(register: Path, import_file: Path | None, banks: Banks) -> list:
    """Normalised findings: {ref, refs, kind, zh, what, en, action, source, questions}."""
    items, seen = [], set()
    for r in read_jsonl(register):
        if (r.get("subtype") or "") != "hack-finding" or r.get("status") == "superseded":
            continue
        refs = list(r.get("refs") or [])
        ref = refs[0] if refs else ""
        s = banks.string(ref)
        items.append(dict(ref=ref, refs=refs, kind=classify(r),
                          zh=r.get("zh") or (s or {}).get("zh") or "",
                          what=r.get("en") or r.get("title") or "",
                          en=(s or {}).get("en") or "", action=r.get("status") or "",
                          source=r.get("id") or "", questions=list(r.get("related") or [])))
        seen.update(refs)
    if import_file is not None:
        for r in read_jsonl(import_file):
            ref = r.get("ref") or ""
            if ref in seen:
                continue
            seen.add(ref)
            s = banks.string(ref)
            items.append(dict(ref=ref, refs=list(r.get("refs") or [ref]), kind=classify(r),
                              zh=r.get("zh_excerpt") or "", what=r.get("what_looks_wrong") or "",
                              en=(s or {}).get("en") if s and s.get("en") is not None else (r.get("current_en") or ""),
                              action=r.get("action") or "", source="import",
                              questions=list(r.get("related_question_ids") or [])))
    return items


def _sort_key(it):
    p = parse_ref(it["ref"])
    return (p[0], p[1], p[2]) if p else ("~", it["ref"], 0)


def code(s: str) -> str:
    s = (s or "").replace("\n", " ").strip()
    if not s:
        return "_(none)_"
    tick = "``" if "`" in s else "`"
    return f"{tick}{s}{tick}"


def render(items: list) -> str:
    groups = {k: [] for k, _ in KINDS}
    for it in items:
        groups[it["kind"]].append(it)
    lines = ["# Hack findings", "",
             "Suspected bugs in the hack's Chinese (D-1195). The English follows the Chinese as written, except pure "
             "character typos, which are translated as the intended word. Generated by `work/tools/findings_report.py`; "
             "do not edit by hand.", "",
             "| Kind | Findings |", "|---|---|"]
    for k, title in KINDS:
        lines.append(f"| {title} | {len(groups[k])} |")
    lines.append(f"| **Total** | **{len(items)}** |")
    for k, title in KINDS:
        if not groups[k]:
            continue
        lines += ["", f"## {title}", ""]
        for it in sorted(groups[k], key=_sort_key):
            tail = [x for x in (it["action"], it["source"] if it["source"] != "import" else "") if x]
            head = it["ref"] or "No string (data finding)"
            lines.append(f"### {head}" + (f" ({', '.join(tail)})" if tail else ""))
            lines.append("")
            lines.append(f"- **Chinese:** {code(it['zh'])}")
            lines.append(f"- **Looks wrong:** {it['what'] or '_(not stated)_'}")
            lines.append(f"- **English now:** {code(it['en'])}")
            if len(it["refs"]) > 1:
                lines.append(f"- **Also in:** {', '.join(it['refs'][1:])}")
            if it["questions"]:
                lines.append(f"- **Related:** {', '.join(it['questions'])}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o644)   # mkstemp creates 0600; keep the report readable like the other generated files
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    ap.add_argument("--import", dest="import_file", type=Path, default=DEFAULT_IMPORT)
    ap.add_argument("--ws", type=Path, default=DEFAULT_WS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args(argv)
    items = collect(a.register, a.import_file, Banks(a.ws))
    write_atomic(a.out, render(items))
    print(f"wrote {a.out} ({len(items)} findings)")


if __name__ == "__main__":
    main()
