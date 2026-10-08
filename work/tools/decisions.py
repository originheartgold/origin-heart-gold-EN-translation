#!/usr/bin/env python3
"""decisions - translation decision register for the 起源心金 (Origin HeartGold v4.0.3) English translation.

Source of truth: work/translate/decisions/decisions.jsonl (one JSON object per line, ids D-0001 ...).
Workflow notes: work/notes/decisions_workflow.md.

    python3 work/tools/decisions.py list [--type T] [--status S] [--source SRC] [--subtype ST] [--search TEXT]
    python3 work/tools/decisions.py show D-0012
    python3 work/tools/decisions.py add --type term --subtype character --zh 小赤 --en Red \\
                                         --rationale "..." --ref a027/0445#110 --source agent:B046
    python3 work/tools/decisions.py set D-0012 status=accepted confidence=high --reason "checked" [--by user] [--redact-old]
    python3 work/tools/decisions.py usages D-0012 [--all] [--json]
    python3 work/tools/decisions.py rename D-0012 --en NEW --reason "..." [--old OLD ...] [--dry-run]
    python3 work/tools/decisions.py resolve D-0301 --answer "..." [--decision-id D-0012]
    python3 work/tools/decisions.py report [--no-usage]           # DECISIONS.md + decisions.csv
    python3 work/tools/decisions.py import-csv decisions.csv [--apply]
    python3 work/tools/decisions.py import-progress [--progress PROGRESS.md] [--dry-run]
    python3 work/tools/decisions.py render-progress [--out FILE]
    python3 work/tools/decisions.py validate [--json]             # refs + supersede/related links

Global options (before the command): --register FILE, --ws DIR, --snapshots DIR.

Record fields: id, type (term|voice|style|layout|content|technical|question), subtype, title, zh, aliases,
en (rendering or rule text), rationale, alternatives, scope ("global" or [banks]), refs ("a027/0445#110"),
related, source ("agent:B034-B035" | "coordinator" | "user" | "glossary" | "migration"), status
(accepted|provisional|needs-review|superseded|open|resolved), superseded_by, confidence (high|medium|low),
answer, decision_id (questions), conflicts_with, created, origin_line/origin_section/origin_text/origin_hash
(PROGRESS.md provenance), mentions (later PROGRESS.md lines that repeat the decision), review_notes, history
([{date, field, old, new, by, reason}]).
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import re
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
DEFAULT_REGISTER = WORK / "translate" / "decisions" / "decisions.jsonl"
DEFAULT_WS = WORK / "translate" / "banks"
DEFAULT_PROGRESS = WORK / "translate" / "PROGRESS.md"
DEFAULT_SNAPSHOTS = WORK / "snapshots"
GLOSSARY_DIR = WORK / "glossary"

TYPES = ("term", "voice", "style", "layout", "content", "technical", "question")
STATUSES = ("accepted", "provisional", "needs-review", "superseded", "open", "resolved")
CONFIDENCES = ("high", "medium", "low")
LIST_FIELDS = ("aliases", "alternatives", "refs", "related", "conflicts_with", "review_notes")
FIELD_ORDER = ("id", "type", "subtype", "title", "zh", "aliases", "en", "rationale", "alternatives", "scope",
               "refs", "related", "source", "status", "superseded_by", "confidence", "answer", "decision_id",
               "conflicts_with", "created", "origin_line", "origin_section", "origin_text", "origin_hash",
               "mentions", "review_notes", "history")
SETTABLE = set(FIELD_ORDER) - {"id", "history", "created", "mentions"}
REDACTED = "[redacted]"   # history "old" value written by `set --redact-old` (e.g. removed song lyrics)
CSV_FIELDS = ("id", "type", "subtype", "status", "confidence", "zh", "aliases", "en", "rationale", "source",
              "usages", "consistent", "scope", "refs", "origin_line", "review_note")
LAYOUT_TAG_RE = re.compile(r"\{(?:NEWLINE|SCROLL|CLEAR)\}")
CJK = "㐀-䶿一-鿿豈-﫿"
CJK_RE = re.compile(f"[{CJK}]")


def today() -> str:
    return os.environ.get("DECISIONS_TODAY") or _dt.date.today().isoformat()


def default_by() -> str:
    return os.environ.get("DECISIONS_BY", "user")


# ======================================================================================
# register I/O
# ======================================================================================

def ordered(rec: dict) -> dict:
    out = {k: rec[k] for k in FIELD_ORDER if k in rec}
    out.update({k: v for k, v in rec.items() if k not in out})
    return out


def blank(rtype: str, **kw) -> dict:
    rec = {"id": None, "type": rtype, "subtype": None, "title": None, "zh": None, "aliases": [], "en": None,
           "rationale": None, "alternatives": [], "scope": "global", "refs": [], "related": [], "source": "agent",
           "status": "provisional", "superseded_by": None, "confidence": "medium", "created": today(),
           "origin_line": None, "history": []}
    rec.update(kw)
    return rec


def load_register(path: Path) -> list:
    path = Path(path)
    if not path.exists():
        return []
    recs = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{path}:{n}: bad JSON ({e})")
    return recs


def save_register(path: Path, recs: list):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    recs = sorted(recs, key=lambda r: id_num(r["id"]))
    txt = "".join(json.dumps(ordered(r), ensure_ascii=False) + "\n" for r in recs)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, path)


@contextlib.contextmanager
def locked_register(path: Path, write: bool = True):
    """Load under an exclusive lock (so concurrent `add`s never collide), save on success."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = open(path.with_name("." + path.name + ".lock"), "w")
    try:
        try:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX)
        except ImportError:  # pragma: no cover
            pass
        recs = load_register(path)
        yield recs
        if write:
            save_register(path, recs)
    finally:
        lock.close()


def id_num(rid) -> int:
    m = re.match(r"D-(\d+)$", rid or "")
    return int(m.group(1)) if m else 0


def next_id(recs: list) -> str:
    return "D-%04d" % (max([id_num(r["id"]) for r in recs] or [0]) + 1)


def by_id(recs: list, rid: str) -> dict:
    rid = norm_id(rid)
    for r in recs:
        if r["id"] == rid:
            return r
    sys.exit(f"no record {rid}")


def norm_id(rid: str) -> str:
    rid = rid.strip().upper()
    if re.fullmatch(r"\d+", rid):
        return "D-%04d" % int(rid)
    m = re.fullmatch(r"D-?(\d+)", rid)
    return "D-%04d" % int(m.group(1)) if m else rid


def record_change(rec: dict, field: str, new, by: str, reason: str | None, redact_old: bool = False):
    old = rec.get(field)
    if old == new:
        return False
    rec[field] = new
    rec.setdefault("history", []).append({"date": today(), "field": field,
                                          "old": REDACTED if redact_old and old is not None else old,
                                          "new": new, "by": by, "reason": reason})
    return True


def validate(rec: dict):
    if rec.get("type") not in TYPES:
        sys.exit(f"type must be one of {', '.join(TYPES)} (got {rec.get('type')!r})")
    if rec.get("status") not in STATUSES:
        sys.exit(f"status must be one of {', '.join(STATUSES)} (got {rec.get('status')!r})")
    if rec.get("confidence") not in CONFIDENCES + (None,):
        sys.exit(f"confidence must be one of {', '.join(CONFIDENCES)} (got {rec.get('confidence')!r})")
    sc = rec.get("scope")
    if not (sc == "global" or isinstance(sc, list)):
        sys.exit("scope must be 'global' or a list of banks like a027/0445")


def active(r: dict) -> bool:
    return r.get("status") != "superseded"


# ======================================================================================
# text helpers
# ======================================================================================

def has_cjk(s) -> bool:
    return bool(s and CJK_RE.search(s))


def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def text_hash(*parts) -> str:
    return hashlib.sha1("\x1f".join(norm_space(str(p)) for p in parts).encode("utf-8")).hexdigest()[:16]


def strip_md(s: str) -> str:
    return norm_space(s.replace("**", ""))


def norm_en(s: str | None) -> str:
    """Comparable form of an English rendering: no layout tags/quotes, lower case, ’ → '."""
    s = LAYOUT_TAG_RE.sub(" ", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", "").replace("”", "").replace("`", "").replace('"', "")
    s = norm_space(s).lower()
    s = re.sub(r"^the ", "", s)
    return s.rstrip(":").strip()


def short(s, n=60) -> str:
    s = norm_space(str(s or ""))
    return s if len(s) <= n else s[: n - 1] + "…"


def parse_ref(ref: str):
    """'a027/0445#110' | 'a027/0445#151-242' | 'a027/0445' -> (bank key, first, last|None)."""
    m = re.match(r"^([a-z0-9_]+/\d{4})(?:#(\d+)(?:-(\d+))?)?$", ref)
    if not m:
        return None
    a = int(m.group(2)) if m.group(2) else None
    b = int(m.group(3)) if m.group(3) else a
    return m.group(1), a, b


# ======================================================================================
# PROGRESS.md parser
# ======================================================================================

OPENERS = {"(": ")", "“": "”", "`": "`", "[": "]"}
ABBR = {"s.s", "lt", "prof", "mr", "ms", "mrs", "dr", "jr", "mt", "st", "co", "no", "vs", "sr", "e.g", "i.e", "etc"}
NAMES_SECTION_SOURCE = [  # (h3 prefix, source, default subtype)
    ("Characters", "agent:B009-B010", "character"),
    ("Trainer classes", "agent:B008", "trainer-class"),
    ("Locations", "agent:B011", "place"),
    ("Items / moves / abilities", "agent:B001-B020", None),
    ("Credits", "agent:B015", "credit-name"),
    ("Battle UI", "agent:B027-B031", "ui-term"),
    ("Battle", "agent:B021-B026", "ui-term"),
]


def scan_top(text: str):
    """Yield (index, char, depth) with depth = nesting inside () “” `` []."""
    stack = []
    for i, ch in enumerate(text):
        if stack and ch == stack[-1]:
            stack.pop()
            yield i, ch, len(stack) + 1
            continue
        if ch in OPENERS:
            stack.append(OPENERS[ch])
            yield i, ch, len(stack)
            continue
        yield i, ch, len(stack)


def top_split(text: str, seps=";,") -> list:
    """Split at top-level separators (also at '. ' followed by a hanzi) -> [(chunk, separator)]."""
    parts, start = [], 0
    for i, ch, d in scan_top(text):
        if d:
            continue
        if ch in seps:
            parts.append((text[start:i], ch))
            start = i + 1
        elif ch == "." and text[i + 1: i + 2] == " " and has_cjk(text[i + 2: i + 3]):
            parts.append((text[start:i], "."))
            start = i + 1
    parts.append((text[start:], ""))
    return parts


def top_find(text: str, needles) -> tuple:
    for i, ch, d in scan_top(text):
        if d:
            continue
        for nd in needles:
            if text.startswith(nd, i):
                return i, nd
    return -1, None


def split_label(text: str):
    """'Egg groups (0790 #196–211): 蛋组 ...' -> ('Egg groups (0790 #196–211)', '蛋组 ...')."""
    i, _ = top_find(text, (": ",))
    if i > 0:
        label = text[:i]
        if not has_cjk(re.sub(r"\([^)]*\)", "", label)) and "→" not in label and len(label) < 90:
            return label.strip(), text[i + 2:].strip()
    return None, text


ITEM_START = re.compile(r"^\s*(?P<pre>(?:[A-Za-z][\w’'.-]*\s+){0,6})(?P<zh>\S*[" + CJK + r"])")
PAIR_NOARROW = re.compile(r"^\s*(?P<pre>(?:[A-Za-z][\w’'.-]*\s+){0,6})(?P<zh>\S*[" + CJK + r"]\S*)\s+(?P<en>[A-Za-z₧].*)$")


def is_item_start(chunk: str, arrow_only: bool) -> bool:
    if not ITEM_START.match(chunk):
        return False
    if top_find(chunk, ("→",) if arrow_only else ("→", " = "))[0] >= 0:
        return True
    return (not arrow_only) and bool(PAIR_NOARROW.match(chunk))


def group_items(text: str, arrow_only=False, seps=";,") -> list:
    items = []
    for chunk, sep in top_split(text, seps):
        if items and not is_item_start(chunk, arrow_only):
            items[-1][0] += items[-1][1] + chunk
            items[-1][1] = sep
        else:
            items.append([chunk, sep])
    return [c.strip() for c, _ in items if c.strip()]


def split_en(right: str):
    """'Snowball (official item)' -> ('Snowball', '(official item)'); honours quotes and abbreviations."""
    r = right.strip()
    if r and r[0] in "\"“‘`":
        close = {'"': '"', "“": "”", "‘": "’", "`": "`"}[r[0]]
        j = r.find(close, 1)
        if j > 0:
            return r[1:j].strip(), r[j + 1:].strip(" ,;")
    for i, ch, d in scan_top(r):
        if ch == "(" and d == 1:
            j = r.find(")", i)
            after = r[j + 1:].lstrip() if j > 0 else ""
            if j > 0 and after[:1].isalnum() and r[j + 1:j + 2] == " ":   # 'the (League) construction ban'
                en, rest = split_en(norm_space(r[:i] + " " + r[j + 1:]))
                return en, "; ".join(x for x in (r[i:j + 1], rest) if x)
            return r[:i].strip().rstrip(",;"), r[i:].strip()
        if d:
            continue
        if ch == ";" or r.startswith(" — ", i):
            return r[:i].strip(), r[i + 1:].strip()
        if ch == "." and (i + 1 == len(r) or r[i + 1] == " "):
            w = re.search(r"([A-Za-z.]+)$", r[:i])
            w = w.group(1).lower() if w else ""
            if w in ABBR or len(w) == 1 or r[i - 1:i] == "." or r[i + 1:i + 2] == ".":
                continue
            return r[:i].strip(), r[i + 1:].strip()
    return r.strip().rstrip(",;"), ""


def unquote(s: str) -> str:
    s = s.strip()
    for a, b in (('"', '"'), ("“", "”"), ("‘", "’"), ("`", "`")):
        if len(s) >= 2 and s[0] == a and s[-1] == b:
            return s[1:-1].strip()
    return s


def clean_zh(left: str):
    """Left side of a pair -> (zh, context). Keeps '一之岛 … 七之岛', drops 'trials' in '德/智/技 trials'."""
    ctx = []
    for p in re.findall(r"\(([^()]*)\)", left):
        ctx.append(p)
    left = norm_space(re.sub(r"\([^()]*\)", " ", left))
    toks = left.split(" ")
    if any(re.search(r"[A-Za-z]", t) and not has_cjk(t) for t in toks):
        cjk_toks = [t for t in toks if has_cjk(t)]
        zh = cjk_toks[-1] if cjk_toks else left
        rest = norm_space(left.replace(zh, " ", 1))
        if rest:
            ctx.insert(0, rest)
    else:
        zh = left
    return zh.strip(), ctx


LEFT_OK = re.compile(r"^\s*(?:[A-Za-z][\w’'.-]*\s+){0,6}[`“\"]?\S*[" + CJK + r"]")


def parse_pairs(text: str, arrow_only=False, label=None, with_failed=False, seps=";,"):
    """-> list of {zh, aliases, en, rationale, item} or [] if the bullet is not a name list."""
    out, failed = [], []
    for item in group_items(text, arrow_only, seps):
        ai, arrow = top_find(item, ("→",) if arrow_only else ("→", " = "))
        if ai >= 0 and not LEFT_OK.match(re.sub(r"\([^()]*\)", " ", item[:ai])):
            ai = -1
        if ai >= 0:
            left, right = item[:ai], item[ai + len(arrow):]
            aliases = [unquote(a) for a in re.split(r"\s*/\s+|\s+/\s*", norm_space(left)) if a]
            zhs, ctxs = [], []
            for a in aliases:
                z, c = clean_zh(a)
                zhs.append(z)
                ctxs += c
            pi, _ = top_find(right, ("(",))
            right_main = right[:pi] if pi >= 0 else right
            ens = re.split(r"\s+/\s+", right_main.strip())
            if len(zhs) > 1 and len(ens) == len(zhs):
                rest = right[pi:].strip() if pi >= 0 else ""
                for k, (z, e) in enumerate(zip(zhs, ens)):
                    en, extra = split_en(e)
                    out.append({"zh": z, "aliases": [], "en": unquote(en),
                                "rationale": "; ".join(x for x in ctxs + [extra, rest] if x), "item": item, "k": k})
                continue
            en, rest = split_en(right)
            out.append({"zh": zhs[0], "aliases": zhs[1:], "en": unquote(en),
                        "rationale": "; ".join(x for x in ctxs + [rest] if x), "item": item, "k": 0})
            continue
        m = None if arrow_only else PAIR_NOARROW.match(item)
        if m and has_cjk(m.group("zh")):
            en, rest = split_en(m.group("en"))
            ctx = [norm_space(m.group("pre"))] if m.group("pre").strip() else []
            out.append({"zh": m.group("zh"), "aliases": [], "en": unquote(en),
                        "rationale": "; ".join(x for x in ctx + [rest] if x), "item": item, "k": 0})
            continue
        if out:
            out[-1]["rationale"] = "; ".join(x for x in (out[-1]["rationale"], item) if x)
        else:
            failed.append(item)
    if label:
        for p in out:
            p["rationale"] = "; ".join(x for x in (label, p["rationale"]) if x)
    if out and failed:
        out[0]["rationale"] = "; ".join(x for x in failed + [out[0]["rationale"]] if x)
    return (out, failed) if with_failed else out


def batch_source(text: str, default="agent") -> str:
    m = re.search(r"\bB(\d{3})\s*[/–-]\s*B?(\d{3})\b", text)
    if m:
        return "agent:B%s-B%s" % (m.group(1), m.group(2))
    m = re.search(r"\bB(\d{3})\b", text)
    return "agent:B%s" % m.group(1) if m else default


def extract_refs(text: str) -> list:
    refs, cur, cur_used = [], None, False
    pat = re.compile(r"(?:(?P<narc>a027|battle_string)/)?(?P<bank>(?<![\d.#])\d{4})(?![\d.,])"
                     r"|#(?P<a>\d+)(?:[–-](?P<b>\d+))?"
                     r"|(?<=\d)/#?(?P<c>\d+)(?:[–-](?P<d>\d+))?")

    def flush():
        if cur and not cur_used:
            refs.append(cur)

    for m in pat.finditer(text):
        if m.group("bank"):
            flush()
            cur, cur_used = "%s/%s" % (m.group("narc") or "a027", m.group("bank")), False
            continue
        a, b = (m.group("a"), m.group("b")) if m.group("a") else (m.group("c"), m.group("d"))
        if cur is None or a is None:
            continue
        refs.append(f"{cur}#{a}" + (f"-{b}" if b else ""))
        cur_used = True
    flush()
    seen, out = set(), []
    for r in refs:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


RULE_KEYWORDS = {
    "content": ["motto", "lyric", "song", " dub", "soften", "toned down", "censor", "copyright", "profan"],
    "layout": ["{scroll}", "{clear}", "{newline}", "wrap", "line count", " px", "layout", "one line", "width",
               "--mode", "paragraph", "chars", "multi-line", "lines", "overflow", "page"],
    "technical": ["qa_ignore", "category", "bank level", "bank-level", "workspace", "charmap", "false positive",
                  "qa.py", "seeded", "json", "`whitespace`", "font"],
    "style": ["mixed case", "caps", "capital", "quote", "apostrophe", "label", "money", "$", "→", "address",
              "names", "english", "romanis", "official"],
}
RULE_SUBTYPES = [("money", "money"), ("caps", "capitalisation"), ("mixed case", "capitalisation"),
                 ("speaker label", "speaker-labels"), ("motto", "motto"), ("lyric", "lyrics"), ("song", "lyrics"),
                 ("quote", "punctuation"), ("apostrophe", "punctuation"), ("trainer", "trainer-names"),
                 ("battle", "battle-messages"), ("wrap", "wrapping"), ("{scroll}", "wrapping"),
                 ("pokédex", "pokedex"), ("shop", "menus"), ("menu", "menus"), ("move", "moves"),
                 ("cjk", "romanisation"), ("romanis", "romanisation")]


def classify_rule(text: str):
    t = text.lower()
    scores = {k: sum(t.count(w) for w in ws) for k, ws in RULE_KEYWORDS.items()}
    scores["content"] *= 3
    if "coordinator decision" in t and scores["content"]:
        scores["content"] += 10
    best = max(("content", "layout", "technical", "style"), key=lambda k: (scores[k], k == "style"))
    rtype = best if scores[best] else "style"
    sub = next((s for k, s in RULE_SUBTYPES if k in t), "general")
    return rtype, sub


GLOSSARY_SUBTYPES = (("species", "species"), ("moves", "move"), ("items", "item"), ("abilities", "ability"),
                     ("locations", "place"), ("types", "type"), ("natures", "nature"))


def load_glossary_index():
    idx = {}
    for fname, sub in GLOSSARY_SUBTYPES:
        p = GLOSSARY_DIR / f"{fname}.json"
        if p.exists():
            try:
                for zh, v in json.loads(p.read_text(encoding="utf-8")).items():
                    idx.setdefault(zh, (sub, (v or {}).get("en")))
            except Exception:
                pass
    return idx


PLACE_WORDS = r"City|Town|Route|Cave|Island|Islands|Forest|Harbor|Tower|Museum|Mart|Gym|Base|Warehouse|Tunnel|" \
              r"Bridge|Cape|Road|Spring|Square|Shrine|Ruins|Lighthouse|Mine|Zone|Area|Center|House|Library|" \
              r"Waters|pool|Cottage|Path|Workshop|Preserve|Plateau|Mt\.|World|Frontier"
ORG_WORDS = r"Conference|Festival|Group|Club|Co\.|Bikers|Team|League|Academy|Association|Executives|Brains"
ITEM_WORDS = r"Orb|Map|Tip|Water|Spray|Coins|Set|Scroll|Suit|Pouch|Armor|Flute|Voucher|Rod|Ball|Balloon|Case|Egg"
PERSON_PREFIX = r"^(?:Prof\.|Professor|Dr\.|Granny|Mr\.|Ms\.|Lt\.|Nurse|President|Master|Big Sis|Captain|First Mate)"


ROLE_WORDS = r"Leader|Trainer|Champion|Boss|Chief|Elder|Captain|Mate|President|Director|director|Chairman|" \
             r"chairman|MC|examiner|Grunt|Officer|Manager|Executive|president|mate"


def term_subtype(zh, en, section, rationale, gidx):
    if section.startswith("Trainer classes"):
        return "trainer-class"
    if zh in gidx:
        return gidx[zh][0]
    for prefix, _, sub in NAMES_SECTION_SOURCE:
        if section.startswith(prefix) and sub:
            return sub
    t = (rationale or "").lower()
    e = en or ""
    if "badge" in t:
        return "badge"
    if re.search(r"\bmove\b", t) and "items / moves" in section.lower():
        return "move"
    if re.search(r"\babilit", t) and "items / moves" in section.lower():
        return "ability"
    if e.endswith(":"):
        return "speaker-label"
    if "nickname" in t or "pokémon (adventures)" in section.lower() or "'s pokémon" in t:
        return "nickname"
    if re.search(PERSON_PREFIX, e):
        return "character"
    if re.search(r"\b(?:%s)\b" % ROLE_WORDS, e):
        return "role"
    if re.search(r"\b(?:%s)\b" % PLACE_WORDS, e):
        return "place"
    if re.search(r"\b(?:%s)\b" % ORG_WORDS, e):
        return "organisation"
    if re.search(r"\b(?:%s)\b" % ITEM_WORDS, e) or "item" in t:
        return "item"
    if re.search(r"motto|catchphrase|greeting|tic\b", t):
        return "catchphrase"
    if re.fullmatch(r"[A-Z][a-zé’'-]+(?: [A-Z][a-zé’'-]+)?", e) and len(zh or "") <= 4 \
            and re.match(r"B\d{3}", section):
        return "character"
    if "items / moves" in section.lower():
        return "item"
    return "phrase"


def guess_confidence(text: str, zh=None, en=None, gidx=None) -> str:
    t = text.lower()
    if re.search(r"invented|placeholder|guess|unknown|\?|no context|not sure|probably|unclear|literal", t):
        return "low"
    if gidx and zh in gidx and norm_en(gidx[zh][1]) == norm_en(en):
        return "high"
    if re.search(r"official|\bus\b|\(us\)|glossary|anime|movie|adventures|frlg|as vanilla|as us|\bjp\b|journeys|"
                 r"origins|already|same as|pokéapi", t):
        return "high"
    return "medium"


def parse_progress(text: str) -> list:
    """PROGRESS.md -> bullets: {line, h2, h3, text, subs: [(line, text)]} (continuation lines merged)."""
    bullets, h2, h3, cur = [], "", "", None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if line.startswith("## "):
            h2, h3, cur = line[3:].strip(), "", None
            continue
        if line.startswith("### "):
            h3, cur = line[4:].strip(), None
            continue
        if line.startswith("# ") or line.strip().startswith("<!--") or not line.strip():
            if not line.strip():
                pass
            else:
                cur = None
            continue
        m = re.match(r"^- (.*)$", line)
        if m:
            cur = {"line": n, "h2": h2, "h3": h3, "text": m.group(1).strip(), "subs": []}
            bullets.append(cur)
            continue
        m = re.match(r"^\s+- (.*)$", line)
        if m and cur is not None:
            cur["subs"].append((n, m.group(1).strip()))
            continue
        if cur is not None and line.startswith(" "):
            cur["text"] += " " + line.strip()
    return bullets


def bullet_full_text(b) -> str:
    return b["text"] + "".join("\n  - " + t for _, t in b["subs"])


def candidates_from_progress(text: str, gidx=None) -> list:
    """All candidate records from PROGRESS.md (no ids yet). Each carries origin_* fields and origin_hash."""
    gidx = gidx if gidx is not None else load_glossary_index()
    out = []

    def origin(rec, b, section, item_text, k=0, kind="x"):
        rec["origin_line"] = b["line"]
        rec["origin_section"] = section
        rec["origin_text"] = bullet_full_text(b)
        rec["origin_hash"] = text_hash(kind, item_text, k)
        return rec

    for b in parse_progress(text):
        h2, h3 = b["h2"], b["h3"]
        section = h2 + (" > " + h3 if h3 else "")
        full = bullet_full_text(b)
        plain = strip_md(b["text"])
        refs = extract_refs(full)
        low = h2.lower()
        if low.startswith("done"):
            continue
        if low.startswith("character voice"):
            parts = re.split(r"\*\*([^*]+?):\*\*", b["text"])
            for k in range(1, len(parts) - 1, 2):
                label, body = parts[k].strip(), norm_space(parts[k + 1]).strip(" ;")
                zh, extra = None, []
                mm = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", label)
                name = label
                if mm:
                    name = mm.group(1).strip()
                    for bit in [x.strip() for x in mm.group(2).split(",")]:
                        if has_cjk(bit) and zh is None:
                            zh = bit
                        elif bit:
                            extra.append(bit)
                rec = blank("voice", subtype="character", title=name, zh=zh, en=body,
                            rationale="; ".join(extra) or None, refs=extract_refs(body), source=batch_source(full),
                            status="provisional", confidence="medium")
                out.append(origin(rec, b, section, label + "|" + body, k, "voice"))
            continue
        if low.startswith("open question"):
            t = strip_md(full)
            tl = t.lower()
            if re.search(r"branch|manifest label|routes:|partner/route", tl):
                sub = "context-note"
            elif re.search(r"soften|toned down|meme line|flag if the project", tl):
                sub = "content-softening"
            elif re.search(r"in game|in battle|emulator|check the screen", tl):
                sub = "verify-in-game"
            else:
                sub = "question"
            status = "resolved" if re.search(r"\bresolved\b", tl) else "open"
            rec = blank("question", subtype=sub, title=short(t, 90), en=t, refs=refs, source=batch_source(t),
                        status=status, confidence=None)
            if status == "resolved":
                rec["answer"] = "Resolved in PROGRESS.md (see text)."
            out.append(origin(rec, b, section, full, 0, "question"))
            continue
        if low.startswith("resolved by coordinator"):
            t = strip_md(full)
            m = re.match(r"^([" + CJK + r"][^\s(=→]*)\s*(?:\(([^)]*)\))?\s*(.*)$", t)
            if m:
                zh, rest = m.group(1), m.group(3)
                q = re.search(r"[\"“]([^\"”]+)[\"”]", rest)
                eq = re.match(r"^(?:=|→)\s*([^(.;]+)", rest)
                en = (eq.group(1).strip() if eq else q.group(1) if q else rest)
                rec = blank("term", subtype=term_subtype(zh, en, section, t, gidx), zh=zh, en=en, rationale=t,
                            refs=refs, source="coordinator", status="accepted", confidence="high")
            else:
                rtype, sub = classify_rule(t)
                if t.lower().startswith("scope"):
                    rtype, sub = "technical", "scope"
                rec = blank(rtype, subtype=sub, title=short(t, 80), en=t, refs=refs, source="coordinator",
                            status="accepted", confidence="high")
            out.append(origin(rec, b, section, full, 0, "resolution"))
            continue

        coordinator = "coordinator" in plain.lower()
        src = "coordinator" if coordinator else None
        if low.startswith("names decided"):
            src = src or next((s for p, s, _ in NAMES_SECTION_SOURCE if h3.startswith(p)), None) \
                or batch_source(h3)
            label, body = split_label(plain)
            pairs = [] if coordinator else parse_pairs(body, arrow_only=False, label=label)
            if pairs:
                for p in pairs:
                    rsn = p["rationale"] or None
                    conf = guess_confidence(p["item"], p["zh"], p["en"], gidx)
                    rec = blank("term", subtype=term_subtype(p["zh"], p["en"], h3, (rsn or "") + " " + (label or ""),
                                                             gidx),
                                zh=p["zh"], aliases=p["aliases"], en=p["en"], rationale=rsn,
                                refs=extract_refs((label or "") + " " + p["item"]), source=src, status="provisional",
                                confidence=conf)
                    out.append(origin(rec, b, section, p["item"], p["k"], "term"))
                continue
        # rule bullet (Decisions, or a names bullet that is not a list, or unknown section)
        src = src or batch_source(full)
        label, body = split_label(plain)
        pairs, failed = ([], True) if (coordinator or b["subs"]) else \
            parse_pairs(body, arrow_only=True, label=label, with_failed=True)
        if pairs and not failed and not label and not low.startswith("names decided"):
            for p in pairs:
                rec = blank("term", subtype=term_subtype(p["zh"], p["en"], section, p["rationale"], gidx),
                            zh=p["zh"], aliases=p["aliases"], en=p["en"], rationale=p["rationale"] or None,
                            refs=extract_refs(p["item"]), source=src,
                            status="accepted" if coordinator else "provisional",
                            confidence=guess_confidence(p["item"], p["zh"], p["en"], gidx))
                out.append(origin(rec, b, section, p["item"], p["k"], "term"))
            continue
        rtype, sub = classify_rule(full)
        known = low.startswith(("decisions", "names decided"))
        rec = blank(rtype, subtype=sub, title=short(plain, 80), en=strip_md(full), refs=refs, source=src,
                    status="accepted" if coordinator else ("provisional" if known else "needs-review"),
                    confidence="high" if coordinator else "medium")
        if not known:
            rec["rationale"] = f"Imported from an unrecognised PROGRESS.md section '{h2}'; check the type."
        out.append(origin(rec, b, section, full, 0, "rule"))
        # quoted phrase renderings inside the rule ("不买了 → “Nothing, thanks”") and sub-bullet pairs (motto)
        extra = []
        for m in re.finditer(r"([" + CJK + r"][^\s→(“\"]*)\s*(?:\([^)]*\)\s*)?→\s*[“\"]([^”\"]+)[”\"]", plain):
            extra.append((m.group(1), m.group(2), m.group(0), b["line"]))
        for ln, st in b["subs"]:
            for p in parse_pairs(strip_md(st), arrow_only=True, seps=""):
                extra.append((p["zh"], p["en"], p["item"], ln))
        for k, (zh, en, item, ln) in enumerate(extra):
            sub_t = "catchphrase" if (sub in ("motto",) or re.search(r"motto|好讨厌", full.lower() + zh)) \
                else term_subtype(zh, en, section, "", gidx)
            trec = blank("term", subtype=sub_t, zh=zh, en=en,
                         rationale=f"Part of rule at PROGRESS.md line {b['line']}: {short(plain, 100)}",
                         refs=extract_refs(item), source=src, status="accepted" if coordinator else "provisional",
                         confidence="high" if coordinator else "medium")
            origin(trec, b, section, item, k, "rule-term")
            trec["origin_line"] = ln
            out.append(trec)
    return out


def known_hashes(recs):
    hs = set()
    for r in recs:
        if r.get("origin_hash"):
            hs.add(r["origin_hash"])
        for m in r.get("mentions") or []:
            if m.get("hash"):
                hs.add(m["hash"])
    return hs


def find_same_term(recs, cand):
    if cand["type"] not in ("term", "voice") or not cand.get("zh"):
        return []
    keys = {cand["zh"], *cand.get("aliases", [])}
    return [r for r in recs if r["type"] == cand["type"] and active(r)
            and keys & {r.get("zh"), *(r.get("aliases") or [])}]


def import_candidates(recs: list, cands: list, by="migration") -> dict:
    """Add candidates not yet present (text hash, then zh+type). Returns stats; mutates recs."""
    stats = Counter()
    hashes = known_hashes(recs)
    new_ids = set()
    for c in cands:
        if c["origin_hash"] in hashes:
            stats["skipped_hash"] += 1
            continue
        same = find_same_term(recs, c)
        same_en = [r for r in same if norm_en(r.get("en")) == norm_en(c.get("en"))]
        if same_en:
            r = same_en[0]
            r.setdefault("mentions", []).append({"origin_line": c["origin_line"], "section": c["origin_section"],
                                                 "text": c["origin_text"], "hash": c["origin_hash"]})
            for f in ("aliases", "refs"):
                for v in c.get(f) or []:
                    if v not in r.setdefault(f, []) and v != r.get("zh"):
                        r[f].append(v)
            hashes.add(c["origin_hash"])
            stats["merged_mention"] += 1
            continue
        c["id"] = next_id(recs)
        if same:
            c["conflicts_with"] = [r["id"] for r in same]
            for r in same:
                r.setdefault("conflicts_with", [])
                if c["id"] not in r["conflicts_with"]:
                    r["conflicts_with"].append(c["id"])
                if c["source"] in ("coordinator", "user") and not str(r.get("source")).startswith(("coordinator", "user")):
                    record_change(r, "superseded_by", c["id"], by, "later coordinator/user decision on the same term")
                    record_change(r, "status", "superseded", by, f"superseded by {c['id']} ({c['source']})")
                else:
                    if r["status"] != "superseded":
                        record_change(r, "status", "needs-review", by,
                                      f"same zh rendered differently in {c['id']} (PROGRESS.md line {c['origin_line']})")
            if c["status"] not in ("accepted",):
                c["status"] = "needs-review"
                c["history"].append({"date": today(), "field": "status", "old": "provisional", "new": "needs-review",
                                     "by": by, "reason": "same zh already rendered differently in "
                                                         + ", ".join(c["conflicts_with"])})
            stats["conflict"] += 1
        recs.append(c)
        new_ids.add(c["id"])
        hashes.add(c["origin_hash"])
        stats["added"] += 1
        stats["added_" + c["type"]] += 1
    link_records(recs, new_ids, by)
    return stats


def link_records(recs: list, new_ids: set, by="migration"):
    """Resolve open questions that a coordinator/user term decision answers; relate questions to terms."""
    terms = [r for r in recs if r["type"] == "term" and r.get("zh") and len(r["zh"]) >= 2 and active(r)]
    by_en = {}
    for r in recs:
        if r["type"] == "term" and r.get("zh") and active(r) and r.get("subtype") == "character":
            by_en.setdefault(r["en"], r)
    for v in recs:
        if v["type"] == "voice" and v["id"] in new_ids and not v.get("zh"):
            names = [n.strip() for n in re.split(r"/|→|&", v.get("title") or "")]
            hits = [by_en[n] for n in names if n in by_en]
            if hits:
                v["zh"] = hits[0]["zh"]
                v["aliases"] = [h["zh"] for h in hits[1:]]
                v["related"] = [h["id"] for h in hits]
    for q in recs:
        if q["type"] != "question":
            continue
        text = (q.get("en") or "") + " " + (q.get("origin_text") or "")
        for t in terms:
            if not (q["id"] in new_ids or t["id"] in new_ids):
                continue
            keys = [t["zh"], *(a for a in t.get("aliases") or [] if len(a) >= 2)]
            if not any(k in text for k in keys):
                continue
            if t["id"] not in q.setdefault("related", []) and len(q["related"]) < 12:
                q["related"].append(t["id"])
            if q["status"] == "open" and t["source"] in ("coordinator", "user") and t["status"] == "accepted":
                record_change(q, "answer", f"{t['zh']} → {t['en']} ({t['source']} decision {t['id']})", by,
                              "answered by a coordinator decision")
                record_change(q, "decision_id", t["id"], by, None)
                record_change(q, "status", "resolved", by, f"answered by {t['id']}")


# ======================================================================================
# workspace scanning (usages, rename)
# ======================================================================================

def load_ws(ws: Path) -> dict:
    """-> {bank key: (path, bank dict)}"""
    out = {}
    for p in sorted(Path(ws).rglob("[0-9]*.json")):
        try:
            b = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out["%s/%04d" % (b["narc"], b["bank"])] = (p, b)
    return out


def term_keys(r: dict) -> list:
    keys = [k for k in [r.get("zh"), *(r.get("aliases") or [])] if k and has_cjk(k)]
    return list(dict.fromkeys(keys))


class TermIndex:
    """Longest-match scanner over all active term records' zh/aliases (a shorter term inside a longer
    registered term is 'shadowed' there and belongs to the longer decision)."""

    def __init__(self, recs: list):
        self.key_to_ids = defaultdict(list)
        for r in recs:
            if r["type"] == "term" and active(r):
                for k in term_keys(r):
                    self.key_to_ids[k].append(r["id"])
        keys = sorted(self.key_to_ids, key=len, reverse=True)
        self.rx = re.compile("|".join(map(re.escape, keys))) if keys else None
        self._cache = {}

    def matches(self, zh: str) -> list:
        if self.rx is None:
            return []
        if zh not in self._cache:
            self._cache[zh] = [m.group(0) for m in self.rx.finditer(zh)]
        return self._cache[zh]


def in_scope(r: dict, bank_key: str) -> bool:
    sc = r.get("scope") or "global"
    return sc == "global" or bank_key in sc


def en_variants(en: str) -> list:
    base = norm_en(en)
    return [base] if base else []


def en_contains(en_text: str, variant: str) -> bool:
    if not variant:
        return False
    hay = norm_en(en_text)
    return re.search(r"(?<![a-z0-9é])" + re.escape(variant) + r"(?:'s|s|es)?(?![a-z0-9é])", hay) is not None


def usages_for(r: dict, wsdata: dict, index: TermIndex) -> dict:
    keys = term_keys(r)
    res = {"id": r["id"], "zh": r.get("zh"), "en": r.get("en"), "total": 0, "translated": 0, "consistent": [],
           "inconsistent": [], "untranslated": [], "shadowed": Counter(), "shadowed_refs": []}
    if not keys:
        return res
    variants = en_variants(r.get("en"))
    for bk, (_p, b) in wsdata.items():
        if not in_scope(r, bk):
            continue
        for e in b["strings"]:
            zh = e.get("zh") or ""
            if not any(k in zh for k in keys):
                continue
            ms = index.matches(zh)
            own = [m for m in ms if r["id"] in index.key_to_ids.get(m, [])]
            ref = f"{bk}#{e['id']}"
            if not own:
                for m in ms:
                    if any(k in m for k in keys):
                        res["shadowed"][m] += 1
                res["shadowed_refs"].append(ref)
                continue
            res["total"] += 1
            en = e.get("en")
            if en is None or e.get("status") == "todo":
                res["untranslated"].append(ref)
                continue
            res["translated"] += 1
            (res["consistent"] if any(en_contains(en, v) for v in variants) else res["inconsistent"]).append(
                (ref, en))
    return res


# ======================================================================================
# rename
# ======================================================================================

BREAK = r"(?:\s+|\s*\{(?:NEWLINE|SCROLL|CLEAR)\}\s*)"


def old_pattern(old: str):
    words = norm_space(old).split(" ")
    parts = []
    for w in words:
        parts.append("".join("['’]" if ch in "'’" else re.escape(ch) for ch in w))
    body = BREAK.join(parts)
    return re.compile(r"(?<![A-Za-z0-9éÉ])" + body + r"(?=(?:s|es|['’]s)?(?![A-Za-z0-9éÉ]))", re.IGNORECASE)


def case_like(matched: str, old: str, new: str) -> str:
    letters = [c for c in matched if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(letters) > 1 and not all(
            c.isupper() for c in old if c.isalpha()):
        return new.upper()
    if matched[:1].isupper() and old[:1].islower() and new[:1].islower():
        return new[:1].upper() + new[1:]
    if matched[:1].islower() and old[:1].isupper() and new[:1].isupper():
        return new[:1].lower() + new[1:]
    return new


def strip_article(s: str) -> str:
    return re.sub(r"^(?:the|The) ", "", s.strip())


def rename_text(en: str, olds: list, new: str):
    """-> (new text, n replacements, spanned_break)."""
    n, spanned = 0, False
    new_core = strip_article(unquote(new))
    for old in sorted({strip_article(unquote(o)) for o in olds if o}, key=len, reverse=True):
        rx = old_pattern(old)

        def sub(m):
            nonlocal n, spanned
            n += 1
            if LAYOUT_TAG_RE.search(m.group(0)):
                spanned = True
            return case_like(m.group(0), old, new_core)
        en = rx.sub(sub, en)
    return en, n, spanned


LAYOUT_CODES = {"line_too_wide", "too_many_lines", "line_may_overflow", "needs_vanilla_glyphs", "name_too_long",
                "wider_than_zh", "more_lines_than_zh"}


def qa_issues(bank: dict) -> list:
    try:
        sys.path.insert(0, str(TOOLS))
        import qa  # noqa
        return qa.check_bank(bank)
    except SystemExit:
        raise
    except Exception as e:  # QA must never block a rename silently
        return [{"narc": bank["narc"], "bank": bank["bank"], "id": -1, "level": "error", "code": "qa_crash",
                 "msg": repr(e)}]


def issue_key(i):
    return (i["id"], i["level"], i["code"], i["msg"])


def plan_rename(r: dict, new: str, olds: list, wsdata: dict, index: TermIndex, include_shadowed=False,
                note: str = "") -> dict:
    keys = term_keys(r)
    plan = {"changes": defaultdict(list), "not_found": [], "shadowed": [], "untranslated": []}
    for bk, (_p, b) in wsdata.items():
        if not in_scope(r, bk):
            continue
        for e in b["strings"]:
            zh = e.get("zh") or ""
            if not any(k in zh for k in keys):
                continue
            ref = f"{bk}#{e['id']}"
            own = [m for m in index.matches(zh) if r["id"] in index.key_to_ids.get(m, [])]
            if not own and not include_shadowed:
                plan["shadowed"].append(ref)
                continue
            if e.get("en") is None:
                plan["untranslated"].append(ref)
                continue
            text, n, spanned = rename_text(e["en"], olds, new)
            if n == 0:
                plan["not_found"].append((ref, e["en"]))
                continue
            plan["changes"][bk].append({"id": e["id"], "old": e["en"], "new": text, "spanned": spanned,
                                        "status": e.get("status")})
    return plan


def apply_to_bank(bank: dict, changes: list, note: str) -> dict:
    by = {c["id"]: c for c in changes}
    for e in bank["strings"]:
        c = by.get(e["id"])
        if c is None:
            continue
        if e.get("en") != c["old"]:   # changed since planning: redo on the current text
            continue
        e["en"] = c["new"]
        e["status"] = "draft"
        e["notes"] = (e.get("notes") + " | " if e.get("notes") else "") + note
    return bank


def snapshot(paths: list, snapdir: Path, label: str, ws: Path) -> Path:
    snapdir = Path(snapdir)
    snapdir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = snapdir / f"banks_{stamp}_before_{label}.tgz"
    with tarfile.open(out, "w:gz") as tf:
        for p in paths:
            rel = Path(p).resolve().relative_to(Path(ws).resolve())
            tf.add(str(p), arcname=str(Path("translate/banks") / rel))
    return out


def write_bank_atomic(path: Path, bank: dict, expect_bytes: bytes) -> bool:
    """Write only if the file still has the content we planned against (a translator may be editing)."""
    if Path(path).read_bytes() != expect_bytes:
        return False
    tmp = Path(path).with_name(Path(path).name + ".dec.tmp")
    tmp.write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return True


def do_rename(reg_path, ws, snapdir, rid, new, reason, by, olds=None, dry_run=False, include_shadowed=False,
              out=None, force=False) -> dict:
    """Rename a term decision and propagate it to the workspace. Returns a result dict."""
    out = out or sys.stdout
    recs = load_register(reg_path)
    r = by_id(recs, rid)
    if r["type"] != "term" and not force:
        sys.exit(f"{r['id']} is a {r['type']} record; rename is for terms (use `set {r['id']} en=...`).")
    if not new or not new.strip():
        sys.exit("--en must not be empty")
    olds = olds or [r["en"]]
    wsdata = load_ws(ws)
    index = TermIndex(recs)
    note = f"[{r['id']} rename {today()}: {short(olds[0], 40)} → {short(new, 40)}]"
    plan = plan_rename(r, new, olds, wsdata, index, include_shadowed, note)
    touched = sorted(plan["changes"])
    nchg = sum(len(v) for v in plan["changes"].values())
    print(f"{r['id']} {r.get('zh')}: {r['en']!r} → {new!r}   ({'dry run' if dry_run else 'apply'})", file=out)
    print(f"  {nchg} strings in {len(touched)} banks change; {len(plan['not_found'])} contain the term but not "
          f"the old English; {len(plan['shadowed'])} only inside longer terms (skipped); "
          f"{len(plan['untranslated'])} untranslated", file=out)
    related = [x for x in recs if x["id"] != r["id"] and active(x) and x["type"] == "term"
               and any(en_contains(x.get("en") or "", norm_en(o)) for o in olds)]
    result = {"id": r["id"], "changed": nchg, "banks": touched, "new_errors": [], "rewrap": [], "snapshot": None,
              "skipped_banks": [], "related": [x["id"] for x in related], "plan": plan}

    rewrap = []
    for bk in touched:
        path, bank = wsdata[bk]
        before = {issue_key(i) for i in qa_issues(bank)}
        newbank = json.loads(json.dumps(bank))
        apply_to_bank(newbank, plan["changes"][bk], note)
        after = qa_issues(newbank)
        changed_ids = {c["id"] for c in plan["changes"][bk]}
        for c in plan["changes"][bk]:
            if dry_run:
                print(f"  {bk}#{c['id']}\n    - {c['old']}\n    + {c['new']}", file=out)
            if c["spanned"]:
                rewrap.append((f"{bk}#{c['id']}", "match spanned a line break (removed); re-wrap", c["new"]))
            if bool(re.match(r"(?i)the ", olds[0])) != bool(re.match(r"(?i)the ", new)):
                rewrap.append((f"{bk}#{c['id']}", "article changed ('the'); check grammar", c["new"]))
        for i in after:
            if i["id"] in changed_ids and issue_key(i) not in before:
                ref = f"{bk}#{i['id']}"
                if i["level"] == "error":
                    result["new_errors"].append((ref, i["code"], i["msg"]))
                if i["code"] in LAYOUT_CODES or i["level"] == "error":
                    txt = next(c["new"] for c in plan["changes"][bk] if c["id"] == i["id"])
                    rewrap.append((ref, f"QA {i['level']} {i['code']}: {i['msg']}", txt))
    for ref, en in plan["not_found"]:
        rewrap.append((ref, "zh has the term but the old English was not found; check by hand", en))
    result["rewrap"] = rewrap

    if result["new_errors"]:
        print(f"  QA: {len(result['new_errors'])} NEW errors after the rename:", file=out)
        for ref, code, msg in result["new_errors"][:40]:
            print(f"    E {ref} [{code}] {msg}", file=out)
    else:
        print("  QA: no new errors", file=out)
    if related:
        print("  Related decisions whose English contains the old text (rename separately if needed): "
              + ", ".join(f"{x['id']} {x.get('zh')} → {x['en']}" for x in related[:10]), file=out)
    if dry_run:
        if rewrap:
            print(f"  {len(rewrap)} strings would need manual attention:", file=out)
            for ref, why, _ in rewrap[:40]:
                print(f"    {ref}: {why}", file=out)
        return result

    # ---- apply: snapshot, write banks, update record, QA, rewrap list
    if touched:
        result["snapshot"] = str(snapshot([wsdata[bk][0] for bk in touched], snapdir, f"{r['id']}_rename", ws))
        print(f"  snapshot: {result['snapshot']}", file=out)
    written = []
    for bk in touched:
        path = wsdata[bk][0]
        ok = False
        for _attempt in range(3):
            raw = Path(path).read_bytes()
            bank = json.loads(raw.decode("utf-8"))
            chg = []
            for c in plan["changes"][bk]:
                e = next((x for x in bank["strings"] if x["id"] == c["id"]), None)
                if e is None or e.get("en") is None:
                    continue
                t, n, sp = rename_text(e["en"], olds, new)
                if n:
                    chg.append({"id": c["id"], "old": e["en"], "new": t, "spanned": sp})
            apply_to_bank(bank, chg, note)
            if write_bank_atomic(path, bank, raw):
                ok = True
                written.append(bk)
                break
        if not ok:
            result["skipped_banks"].append(bk)
            print(f"  WARNING: {bk} kept changing while writing; skipped (re-run rename later)", file=out)
    with locked_register(reg_path) as recs2:
        r2 = by_id(recs2, r["id"])
        old_en = r2["en"]
        record_change(r2, "en", new, by, reason)
        if old_en and old_en not in (r2.get("alternatives") or []):
            record_change(r2, "alternatives", list(r2.get("alternatives") or []) + [old_en], by,
                          f"previous rendering (renamed {today()})")
    for bk in written:
        res = run_qa_file(wsdata[bk][0])
        s = res["summary"]
        print(f"  qa.py check {bk}: {s['errors']} errors, {s['warnings']} warnings", file=out)
    if rewrap:
        rw = write_rewrap_list(Path(reg_path).parent, r["id"], rewrap, ws)
        result["rewrap_file"] = str(rw)
        print(f"  {len(rewrap)} strings need manual attention: {rw}", file=out)
    return result


def run_qa_file(path):
    sys.path.insert(0, str(TOOLS))
    import qa  # noqa
    return qa.run_check(path)


def repo_path(p) -> str:
    """p relative to the repo root when it lies inside it (published files must not carry local paths)."""
    try:
        return Path(p).resolve().relative_to(WORK.parent).as_posix()
    except ValueError:
        return str(p)


def write_rewrap_list(regdir: Path, rid: str, rows: list, ws) -> Path:
    d = Path(regdir) / "rewrap"
    d.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    p = d / f"{rid}_{stamp}.tsv"
    banks = defaultdict(set)
    for ref, _w, _t in rows:
        bk, a, _b = parse_ref(ref)
        banks[bk].add(a)
    lines = [f"# Strings that need manual attention after renaming {rid} ({today()}).",
             "# Re-wrap with (per bank; check the result by eye):"]
    for bk, ids in sorted(banks.items()):
        lines.append(f"#   python3 work/tools/qa.py wrap {repo_path(Path(ws) / (bk + '.json'))} --ids "
                     f"{','.join(map(str, sorted(ids)))} --reflow --mode scroll --which max --in-place")
    lines.append("ref\treason\ten")
    for ref, why, txt in rows:
        lines.append(f"{ref}\t{why}\t{txt}")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


# ======================================================================================
# commands
# ======================================================================================

def fmt_table(rows, headers):
    w = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            w[i] = max(w[i], disp_len(str(c)))
    line = lambda cells: "  ".join(pad(str(c), w[i]) for i, c in enumerate(cells)).rstrip()
    return "\n".join([line(headers), line(["-" * x for x in w])] + [line(r) for r in rows])


def disp_len(s: str) -> int:
    return sum(2 if has_cjk(ch) or "　" <= ch <= "ヿ" or "＀" <= ch <= "￯" else 1 for ch in s)


def pad(s: str, n: int) -> str:
    return s + " " * max(0, n - disp_len(s))


def filter_recs(recs, a):
    out = []
    for r in recs:
        if a.type and r["type"] != a.type:
            continue
        if a.status and r["status"] not in a.status.split(","):
            continue
        if a.source and not str(r.get("source", "")).startswith(a.source):
            continue
        if getattr(a, "subtype", None) and r.get("subtype") != a.subtype:
            continue
        if getattr(a, "confidence", None) and r.get("confidence") != a.confidence:
            continue
        if a.search:
            hay = " ".join(str(r.get(k) or "") for k in ("zh", "en", "title", "rationale", "subtype")) + " " + \
                " ".join(r.get("aliases") or [])
            if a.search.lower() not in hay.lower():
                continue
        out.append(r)
    return out


def cmd_list(a):
    recs = filter_recs(load_register(a.register), a)
    rows = []
    for r in recs:
        label = r.get("zh") or ""
        if r.get("aliases"):
            label += " /" + "/".join(r["aliases"])
        en = r.get("en") if r["type"] in ("term",) else (r.get("title") or r.get("en"))
        if r["type"] == "voice":
            en = f"{r.get('title')}: {r.get('en')}"
        rows.append([r["id"], r["type"], r.get("subtype") or "", r["status"], (r.get("confidence") or "-")[:3],
                     short(label, 18), short(en, a.width), r.get("source") or ""])
    print(fmt_table(rows, ["id", "type", "subtype", "status", "cnf", "zh", "en / rule", "source"]))
    print(f"({len(rows)} records)")


def cmd_show(a):
    recs = load_register(a.register)
    for rid in a.ids:
        r = by_id(recs, rid)
        if a.json:
            print(json.dumps(ordered(r), ensure_ascii=False, indent=1))
            continue
        print(f"{r['id']}  [{r['type']}/{r.get('subtype')}]  {r['status']}  confidence={r.get('confidence')}  "
              f"source={r.get('source')}  created={r.get('created')}")
        for k in FIELD_ORDER:
            if k in ("id", "type", "subtype", "status", "confidence", "source", "created", "history", "mentions",
                     "origin_hash"):
                continue
            v = r.get(k)
            if v in (None, [], ""):
                continue
            if k == "origin_text":
                print(f"  {k}:\n    " + str(v).replace("\n", "\n    "))
            else:
                print(f"  {k}: {v if not isinstance(v, list) else ', '.join(map(str, v))}")
        for m in r.get("mentions") or []:
            print(f"  also in PROGRESS.md line {m.get('origin_line')} ({m.get('section')})")
        for h in r.get("history") or []:
            print(f"  history {h['date']} {h['field']}: {short(h['old'], 50)!r} → {short(h['new'], 50)!r} "
                  f"by {h['by']}" + (f" ({h['reason']})" if h.get("reason") else ""))
        print()


def split_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        out = []
        for x in v:
            out += split_list(x)
        return out
    v = v.strip()
    if v.startswith("["):
        return json.loads(v)
    return [x.strip() for x in re.split(r"\s*[,;]\s*", v) if x.strip()] if v else []


def parse_scope(v):
    if v is None or v.strip() in ("", "global"):
        return "global"
    return split_list(v)


def cmd_add(a):
    rtype = a.type
    rec = blank(rtype, subtype=a.subtype, title=a.title, zh=a.zh, aliases=split_list(a.alias), en=a.en,
                rationale=a.rationale, alternatives=split_list(a.alternative), scope=parse_scope(a.scope),
                refs=split_list(a.ref), related=[norm_id(x) for x in split_list(a.related)], source=a.source,
                status=a.status or ("open" if rtype == "question" else "provisional"),
                confidence=None if (rtype == "question" and not a.confidence) else (a.confidence or "medium"))
    if not rec["en"]:
        sys.exit("--en is required (the rendering, rule text or question)")
    if rtype == "term" and not rec["zh"]:
        sys.exit("--zh is required for a term")
    validate(rec)
    with locked_register(a.register) as recs:
        same = find_same_term(recs, rec)
        if same and not a.force:
            ex = same[0]
            msg = f"{ex['id']} already covers {rec['zh']} ({ex['type']}): {ex.get('en')!r} [{ex['status']}]"
            if norm_en(ex.get("en")) == norm_en(rec["en"]):
                print(ex["id"])
                print(f"exists: {msg}; nothing added (add refs with: set {ex['id']} refs+=...)", file=sys.stderr)
                return
            sys.exit(f"conflict: {msg}. Use `set`/`rename` to change it, or --force to add a competing record "
                     f"(it is then marked needs-review).")
        rec["id"] = next_id(recs)
        if same:
            rec["conflicts_with"] = [x["id"] for x in same]
            rec["status"] = "needs-review"
            for x in same:
                x.setdefault("conflicts_with", []).append(rec["id"])
                if x["status"] in ("accepted", "provisional"):
                    record_change(x, "status", "needs-review", a.source, f"competing rendering {rec['id']}")
        recs.append(rec)
    print(rec["id"])


def coerce(field, value, rec):
    if value == "null":
        return None
    if field == "scope":
        return parse_scope(value)
    if field in LIST_FIELDS:
        vals = split_list(value)
        return [norm_id(v) for v in vals] if field in ("related", "conflicts_with") else vals
    if field in ("superseded_by", "decision_id"):
        return norm_id(value)
    if field == "origin_line":
        return int(value)
    return value


def apply_sets(rec, assignments, by, reason, redact_old=False):
    changed = []
    for asg in assignments:
        m = re.match(r"^([a-z_]+)(\+=|-=|=)(.*)$", asg, re.S)
        if not m:
            sys.exit(f"bad assignment {asg!r}: use field=value, field+=value or field-=value")
        field, op, value = m.groups()
        if field not in SETTABLE:
            sys.exit(f"field {field!r} can't be set (settable: {', '.join(sorted(SETTABLE))})")
        if op in ("+=", "-="):
            if field not in LIST_FIELDS and field != "scope":
                sys.exit(f"{op} only works on list fields ({', '.join(LIST_FIELDS)})")
            cur = list(rec.get(field) or []) if rec.get(field) != "global" else []
            vals = coerce(field, value, rec)
            new = cur + [v for v in vals if v not in cur] if op == "+=" else [v for v in cur if v not in vals]
        else:
            new = coerce(field, value, rec)
        if field == "en" and rec["type"] == "term":
            print(f"note: `set en=` changes the record only; use `rename {rec['id']} --en ...` to update the "
                  f"translations too.", file=sys.stderr)
        if record_change(rec, field, new, by, reason, redact_old):
            changed.append(field)
    validate(rec)
    if rec["status"] == "superseded" and not rec.get("superseded_by"):
        print(f"warning: {rec['id']} is superseded but superseded_by is empty", file=sys.stderr)
    return changed


def cmd_set(a):
    with locked_register(a.register) as recs:
        r = by_id(recs, a.id)
        changed = apply_sets(r, a.assignments, a.by, a.reason, a.redact_old)
    print(f"{r['id']}: changed {', '.join(changed) if changed else 'nothing'}")


def cmd_resolve(a):
    with locked_register(a.register) as recs:
        q = by_id(recs, a.id)
        if q["type"] != "question":
            sys.exit(f"{q['id']} is not a question")
        if a.decision_id:
            by_id(recs, a.decision_id)
            record_change(q, "decision_id", norm_id(a.decision_id), a.by, a.reason)
        record_change(q, "answer", a.answer, a.by, a.reason)
        record_change(q, "status", "resolved", a.by, a.reason or "answered")
    print(f"{q['id']}: resolved")


def print_usages(res, show_all=False, out=None):
    out = out or sys.stdout
    print(f"{res['id']} {res['zh']} → {res['en']}: {res['total']} strings contain the term "
          f"({res['translated']} translated, {len(res['untranslated'])} untranslated)", file=out)
    print(f"  consistent (English contains {res['en']!r}): {len(res['consistent'])}", file=out)
    print(f"  possible inconsistencies: {len(res['inconsistent'])}", file=out)
    lim = None if show_all else 25
    for ref, en in res["inconsistent"][:lim]:
        print(f"    {ref}: {short(LAYOUT_TAG_RE.sub(' ', en), 110)}", file=out)
    if lim and len(res["inconsistent"]) > lim:
        print(f"    ... {len(res['inconsistent']) - lim} more (--all)", file=out)
    if show_all:
        for ref, en in res["consistent"]:
            print(f"    ok {ref}: {short(LAYOUT_TAG_RE.sub(' ', en), 110)}", file=out)
    if res["shadowed"]:
        print("  also inside longer registered terms (counted there): "
              + ", ".join(f"{k}×{v}" for k, v in res["shadowed"].most_common(8)), file=out)


def cmd_usages(a):
    recs = load_register(a.register)
    wsdata = load_ws(a.ws)
    index = TermIndex(recs)
    for rid in a.ids:
        r = by_id(recs, rid)
        if r["type"] != "term":
            print(f"{r['id']} is a {r['type']} record; usages works on terms", file=sys.stderr)
            continue
        res = usages_for(r, wsdata, index)
        if a.json:
            res = dict(res, shadowed=dict(res["shadowed"]))
            print(json.dumps(res, ensure_ascii=False, indent=1))
        else:
            print_usages(res, a.all)
            if len(r.get("zh") or "") == 1:
                print("  note: single-character term, expect false matches", file=sys.stderr)


def cmd_rename(a):
    do_rename(a.register, a.ws, a.snapshots, a.id, a.en, a.reason, a.by, a.old, a.dry_run, a.include_shadowed,
              force=a.force)


# ---------------------------------------------------------------------- report / csv

def md_cell(s, n=None) -> str:
    s = norm_space(LAYOUT_TAG_RE.sub(" ", str(s if s is not None else "")))
    if n:
        s = short(s, n)
    return s.replace("|", "\\|")


def compute_usages(recs, ws):
    wsdata = load_ws(ws)
    index = TermIndex(recs)
    return {r["id"]: usages_for(r, wsdata, index) for r in recs if r["type"] == "term" and active(r)}


def review_buckets(recs):
    q_open = [r for r in recs if r["type"] == "question" and r["status"] == "open" and r.get("subtype") != "context-note"]
    notes = [r for r in recs if r["type"] == "question" and r["status"] == "open" and r.get("subtype") == "context-note"]
    nr = [r for r in recs if r["status"] == "needs-review"]
    low = [r for r in recs if r.get("confidence") == "low" and r["status"] in ("provisional", "accepted")]
    prov = [r for r in recs if r["status"] == "provisional" and r.get("confidence") != "low"]
    return q_open, nr, low, prov, notes


def usage_txt(u):
    if not u:
        return ""
    if not u["total"]:
        return "0"
    return f"{len(u['consistent'])}/{u['translated']}" + (f" (+{len(u['untranslated'])} todo)" if u["untranslated"] else "")


def render_report(recs, usages, reg_path) -> str:
    L = []
    counts = Counter((r["type"], r["status"]) for r in recs)
    q_open, nr, low, prov, notes = review_buckets(recs)
    L += ["# Translation decisions", "",
          f"Generated {today()} from `{Path(reg_path).name}` ({len(recs)} records). Don't edit this file: "
          "it's regenerated. Change decisions with `python3 work/tools/decisions.py` or by editing "
          "`decisions.csv` and running `decisions.py import-csv decisions.csv` (see "
          "`work/notes/decisions_workflow.md`).", "",
          "**Usage** = translated strings whose English contains the chosen rendering / translated strings whose "
          "Chinese contains the term. A low ratio points to inconsistent translations "
          "(`decisions.py usages ID` lists them).", "",
          "| type | " + " | ".join(STATUSES) + " | total |", "|---|" + "---|" * (len(STATUSES) + 1)]
    for t in TYPES:
        row = [counts.get((t, s), 0) for s in STATUSES]
        L.append(f"| {t} | " + " | ".join(str(x or "") for x in row) + f" | {sum(row)} |")
    L += ["", "## Needs your review", "",
          f"{len(q_open)} open questions, {len(nr)} needing review (conflicts), {len(low)} low-confidence, "
          f"{len(prov)} other provisional choices by translator agents, plus {len(notes)} context notes.", ""]

    L += [f"### Open questions ({len(q_open)})", "", "| id | kind | question | refs | related |", "|---|---|---|---|---|"]
    for r in q_open:
        L.append(f"| {r['id']} | {r.get('subtype') or ''} | {md_cell(r['en'], 300)} | "
                 f"{md_cell(', '.join((r.get('refs') or [])[:4]))} | {', '.join(r.get('related') or [])} |")
    L += ["", f"### Needs review: conflicting or flagged decisions ({len(nr)})", "",
          "| id | type | zh | en | conflicts with | why | usage |", "|---|---|---|---|---|---|---|"]
    for r in nr:
        why = next((h["reason"] for h in reversed(r.get("history") or []) if h["field"] == "status"), "") or ""
        L.append(f"| {r['id']} | {r['type']}/{r.get('subtype') or ''} | {md_cell(r.get('zh'))} | "
                 f"{md_cell(r.get('en') if r['type'] == 'term' else r.get('title') or r.get('en'), 90)} | "
                 f"{', '.join(r.get('conflicts_with') or [])} | {md_cell(why, 90)} | {usage_txt(usages.get(r['id']))} |")
    L += ["", f"### Low confidence ({len(low)})", "", "Invented names, placeholders and guesses.", "",
          "| id | subtype | zh | en | rationale | usage |", "|---|---|---|---|---|---|"]
    for r in low:
        L.append(f"| {r['id']} | {r.get('subtype') or r['type']} | {md_cell(r.get('zh'))} | "
                 f"{md_cell(r.get('en') if r['type'] == 'term' else r.get('title'), 60)} | "
                 f"{md_cell(r.get('rationale'), 120)} | {usage_txt(usages.get(r['id']))} |")
    L += ["", f"### Provisional ({len(prov)})", "",
          "Agent choices that nobody has reviewed yet. Accept them in bulk by setting `status` to `accepted` in the "
          "CSV. Full details are in the sections below.", ""]
    groups = defaultdict(list)
    for r in prov:
        groups[(r["type"], r.get("subtype") or "")].append(r)
    for (t, st), rs in sorted(groups.items()):
        if t == "term":
            items = "; ".join(f"{r['id'][2:]} {r.get('zh')} → {md_cell(r.get('en'), 40)}" for r in rs)
        else:
            items = "; ".join(f"{r['id'][2:]} {md_cell(r.get('title') or r.get('en'), 50)}" for r in rs)
        L.append(f"- **{t}/{st}** ({len(rs)}): {items}")
    L += ["", f"### Context notes ({len(notes)})", "",
          "Route/branch maps and similar notes from the open-questions list. No action needed unless they look wrong.", ""]
    for r in notes:
        L.append(f"- {r['id']}: {md_cell(r['en'], 400)}")

    L += ["", "## Terms", ""]
    terms = [r for r in recs if r["type"] == "term"]
    by_sub = defaultdict(list)
    for r in terms:
        by_sub[r.get("subtype") or "other"].append(r)
    for st in sorted(by_sub, key=lambda s: (-len(by_sub[s]), s)):
        rs = by_sub[st]
        L += [f"### {st} ({len(rs)})", "", "| id | zh | en | status | conf | source | usage | rationale |",
              "|---|---|---|---|---|---|---|---|"]
        for r in rs:
            zh = r.get("zh") or ""
            if r.get("aliases"):
                zh += " (" + " / ".join(r["aliases"]) + ")"
            st_txt = r["status"] + (f" → {r['superseded_by']}" if r.get("superseded_by") else "")
            L.append(f"| {r['id']} | {md_cell(zh)} | {md_cell(r.get('en'))} | {st_txt} | {r.get('confidence') or ''} | "
                     f"{r.get('source') or ''} | {usage_txt(usages.get(r['id']))} | {md_cell(r.get('rationale'), 160)} |")
        L.append("")
    voices = [r for r in recs if r["type"] == "voice"]
    L += [f"## Character voices ({len(voices)})", "", "| id | character | zh | voice | status | source |",
          "|---|---|---|---|---|---|"]
    for r in voices:
        L.append(f"| {r['id']} | {md_cell(r.get('title'))} | {md_cell(r.get('zh'))} | {md_cell(r.get('en'))} | "
                 f"{r['status']} | {r.get('source') or ''} |")
    for t in ("style", "layout", "content", "technical"):
        rs = [r for r in recs if r["type"] == t]
        L += ["", f"## {t.capitalize()} rules ({len(rs)})", "", "| id | subtype | rule | status | source |",
              "|---|---|---|---|---|"]
        for r in rs:
            L.append(f"| {r['id']} | {r.get('subtype') or ''} | {md_cell(r.get('en'), 700)} | {r['status']} | "
                     f"{r.get('source') or ''} |")
    qs = [r for r in recs if r["type"] == "question" and r["status"] != "open"]
    L += ["", f"## Resolved questions ({len(qs)})", "", "| id | question | answer | decision |", "|---|---|---|---|"]
    for r in qs:
        L.append(f"| {r['id']} | {md_cell(r['en'], 200)} | {md_cell(r.get('answer'), 200)} | {r.get('decision_id') or ''} |")
    # same English for different zh (info)
    by_en = defaultdict(list)
    for r in terms:
        if active(r) and r.get("en"):
            by_en[norm_en(r["en"])].append(r)
    dup = {k: v for k, v in by_en.items() if len({x.get('zh') for x in v}) > 1}
    L += ["", f"## Same English for different Chinese terms ({len(dup)})", "",
          "For information: usually fine (old and new names, variants), but check that these are meant to be the same.", ""]
    for k, v in sorted(dup.items()):
        L.append(f"- **{md_cell(v[0]['en'])}**: " + ", ".join(f"{x['id']} {x.get('zh')}" for x in v))
    hist = [(h, r) for r in recs for h in r.get("history") or []]
    hist.sort(key=lambda hr: (hr[0]["date"], id_num(hr[1]["id"])), reverse=True)
    L += ["", f"## Changelog ({len(hist)} changes)", "", "| date | id | field | old | new | by | reason |",
          "|---|---|---|---|---|---|---|"]
    for h, r in hist:
        L.append(f"| {h['date']} | {r['id']} | {h['field']} | {md_cell(h['old'], 60)} | {md_cell(h['new'], 60)} | "
                 f"{h.get('by') or ''} | {md_cell(h.get('reason'), 100)} |")
    return "\n".join(L) + "\n"


def write_csv(recs, usages, path: Path):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_FIELDS)
    for r in recs:
        u = usages.get(r["id"])
        w.writerow([r["id"], r["type"], r.get("subtype") or "", r["status"], r.get("confidence") or "",
                    r.get("zh") or "", " / ".join(r.get("aliases") or []), r.get("en") or "",
                    r.get("rationale") or "", r.get("source") or "", u["total"] if u else "",
                    len(u["consistent"]) if u else "", "global" if r.get("scope", "global") == "global"
                    else ",".join(r["scope"]), ", ".join(r.get("refs") or []), r.get("origin_line") or "", ""])
    tmp = Path(path).with_name(Path(path).name + ".tmp")
    tmp.write_text(buf.getvalue(), encoding="utf-8-sig")
    os.replace(tmp, path)


def cmd_report(a):
    recs = load_register(a.register)
    usages = {} if a.no_usage else compute_usages(recs, a.ws)
    outdir = Path(a.out_dir) if a.out_dir else Path(a.register).parent
    outdir.mkdir(parents=True, exist_ok=True)
    md = outdir / "DECISIONS.md"
    tmp = md.with_name(md.name + ".tmp")
    tmp.write_text(render_report(recs, usages, a.register), encoding="utf-8")
    os.replace(tmp, md)
    write_csv(recs, usages, outdir / "decisions.csv")
    q_open, nr, low, prov, notes = review_buckets(recs)
    print(f"wrote {md} and {outdir / 'decisions.csv'} ({len(recs)} records; needs review: {len(q_open)} open "
          f"questions, {len(nr)} needs-review, {len(low)} low confidence, {len(prov)} provisional)")


def csv_plan(recs, path):
    rows = list(csv.DictReader(io.StringIO(Path(path).read_text(encoding="utf-8-sig"))))
    ids = {r["id"]: r for r in recs}
    plan = []
    for row in rows:
        rid = (row.get("id") or "").strip()
        if not rid:
            continue
        rid = norm_id(rid)
        r = ids.get(rid)
        if r is None:
            plan.append((rid, "error", "unknown id", None, None))
            continue
        for field in ("en", "status", "confidence", "subtype", "rationale"):
            if field not in row or row[field] is None:
                continue
            new = row[field].strip()
            old = (r.get(field) or "")
            if new == norm_space(str(old)) or new == str(old).strip():
                continue
            if field in ("rationale",) and norm_space(new) == norm_space(str(old)):
                continue
            if not new and field in ("en", "status"):
                continue
            op = "rename" if (field == "en" and r["type"] == "term") else "set"
            plan.append((rid, op, field, old, new))
        note = (row.get("review_note") or "").strip()
        if note:
            plan.append((rid, "note", "review_notes", None, note))
    return plan


def cmd_import_csv(a):
    recs = load_register(a.register)
    plan = csv_plan(recs, a.file)
    if not plan:
        print("no changes in the CSV")
        return
    print(f"{len(plan)} changes in {a.file}:")
    for rid, op, field, old, new in plan:
        if op == "error":
            print(f"  {rid}: ERROR {field}")
        else:
            print(f"  {rid}: {op:6s} {field}: {short(old, 50)!r} → {short(new, 50)!r}")
    if not a.apply:
        renames = [p for p in plan if p[1] == "rename"]
        for rid, _op, _f, _old, new in renames:
            print()
            do_rename(a.register, a.ws, a.snapshots, rid, new, a.reason, a.by, dry_run=True)
        print("\n(dry run; add --apply to make these changes)")
        return
    reason = a.reason or f"CSV review ({Path(a.file).name})"
    for rid, op, field, old, new in plan:
        if op == "rename":
            do_rename(a.register, a.ws, a.snapshots, rid, new, reason, a.by)
    with locked_register(a.register) as recs2:
        for rid, op, field, old, new in plan:
            if op == "error":
                continue
            r = by_id(recs2, rid)
            if op == "set":
                apply_sets(r, [f"{field}={new}"], a.by, reason)
            elif op == "note":
                r.setdefault("review_notes", []).append(f"{today()} {a.by}: {new}")
    print(f"applied {sum(1 for p in plan if p[1] != 'error')} changes")


# ---------------------------------------------------------------------- PROGRESS import / digest

def cmd_import_progress(a):
    text = Path(a.progress).read_text(encoding="utf-8")
    cands = candidates_from_progress(text)
    if a.dry_run:
        recs = load_register(a.register)
        stats = import_candidates(recs, cands)
        print(f"dry run: {len(cands)} candidates; " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
        return
    with locked_register(a.register) as recs:
        stats = import_candidates(recs, cands, by="migration")
    print(f"{len(cands)} candidates from {a.progress}; " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))


def render_digest(recs) -> str:
    L = ["# Decision digest", "",
         f"Generated {today()} from work/translate/decisions/decisions.jsonl. Don't edit this; it's regenerated. "
         "Record new decisions with `python3 work/tools/decisions.py add ...` (see work/notes/decisions_workflow.md). "
         "`(?)` = disputed (status needs-review): follow it, but flag doubts in your notes. Provisional agent choices are "
         "not marked. Superseded decisions are left out.",
         ""]
    live = [r for r in recs if active(r)]

    def mark(r):
        return "" if r["status"] in ("accepted", "resolved") else ("(?)" if r["status"] == "needs-review" else "")
    for t, title in (("style", "Style rules"), ("layout", "Layout rules"), ("content", "Content rules"),
                     ("technical", "Technical notes")):
        rs = [r for r in live if r["type"] == t]
        if not rs:
            continue
        L += [f"## {title}", ""]
        for r in rs:
            L.append(f"- [{r['id'][2:]}]{mark(r)} {norm_space(r['en'])}")
        L.append("")
    vs = [r for r in live if r["type"] == "voice"]
    if vs:
        L += ["## Character voices", ""]
        for r in vs:
            L.append(f"- **{r.get('title')}**" + (f" ({r['zh']})" if r.get("zh") else "") + f": {norm_space(r['en'])}")
        L.append("")
    L += ["## Names and terms (zh → en)", ""]
    by_sub = defaultdict(list)
    for r in live:
        if r["type"] == "term":
            by_sub[r.get("subtype") or "other"].append(r)
    for st in sorted(by_sub, key=lambda s: (-len(by_sub[s]), s)):
        items = []
        for r in by_sub[st]:
            zh = " / ".join([r["zh"], *(r.get("aliases") or [])])
            items.append(f"{zh} → {r['en']}{mark(r)}")
        L.append(f"- **{st}:** " + "; ".join(items))
    qs = [r for r in live if r["type"] == "question" and r["status"] == "open" and r.get("subtype") != "context-note"]
    L += ["", f"## Open questions ({len(qs)})", ""]
    if any(r.get("subtype") == "hack-finding" for r in qs):
        L += ["Hack findings (subtype hack-finding) describe the string as it was when the finding was logged; many were "
              "retranslated later to match the Chinese (D-1195). `HACK_FINDINGS.md` shows the current English.", ""]
    for r in qs:
        L.append(f"- [{r['id'][2:]}] {short(r['en'], 160)}")
    return "\n".join(L) + "\n"


def cmd_render_progress(a):
    txt = render_digest(load_register(a.register))
    if a.out:
        Path(a.out).write_text(txt, encoding="utf-8")
        print(f"wrote {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(txt)


# ======================================================================================

# ======================================================================================
# validate: refs point at existing strings, links point at existing records
# ======================================================================================

TEXT_REF_RE = re.compile(r"^([a-z0-9_]+)/(\d{4})(?:#(\d+)(?:-(\d+))?)?$")


def validate_register(recs: list, ws: Path) -> list:
    """-> [{id, level, field, value, msg}]. A ref whose narc folder is a workspace text narc (a027,
    battle_string) must name an existing bank and existing ids; other refs (overlay offsets, script
    offsets, files) are not text refs and are skipped. Also checks superseded_by / related /
    conflicts_with / decision_id point at existing records and that 'superseded' and superseded_by agree."""
    ws = Path(ws)
    ids = {r["id"]: r for r in recs}
    banks = {}

    def bank_ids(key):
        if key not in banks:
            p = ws / (key + ".json")
            banks[key] = ({e["id"] for e in json.loads(p.read_text(encoding="utf-8"))["strings"]}
                          if p.exists() else None)
        return banks[key]

    out = []

    def err(r, field, value, msg, level="error"):
        out.append({"id": r["id"], "level": level, "field": field, "value": value, "msg": msg})

    for r in recs:
        for ref in r.get("refs") or []:
            m = TEXT_REF_RE.match(ref or "")
            if not m or not (ws / m.group(1)).is_dir():
                continue
            key = "%s/%s" % (m.group(1), m.group(2))
            have = bank_ids(key)
            if have is None:
                err(r, "refs", ref, "bank %s does not exist" % key)
                continue
            if m.group(3) is None:
                continue
            if len(m.group(3)) == 4 and m.group(3).startswith("0"):
                err(r, "refs", ref, "zero-padded id looks like a bank pair from the PROGRESS migration "
                                    "(%s#%s = banks %s and %s/%s?)" % (key, m.group(3), key, m.group(1), m.group(3)))
                continue
            a = int(m.group(3))
            b = int(m.group(4)) if m.group(4) else a
            if b < a:
                err(r, "refs", ref, "reversed id range")
                continue
            missing = [i for i in (a, b) if i not in have]
            if missing:
                err(r, "refs", ref, "id %s not in %s (max id %d)" % (missing[0], key, max(have) if have else -1))
        sb = r.get("superseded_by")
        if sb:
            if sb == r["id"]:
                err(r, "superseded_by", sb, "supersedes itself")
            elif sb not in ids:
                err(r, "superseded_by", sb, "no record %s" % sb)
            else:
                seen, cur = {r["id"]}, ids[sb]
                while cur.get("superseded_by") and cur["id"] not in seen:
                    seen.add(cur["id"])
                    cur = ids.get(cur["superseded_by"]) or {}
                    if not cur:
                        break
                if cur and cur.get("id") in seen:
                    err(r, "superseded_by", sb, "supersede cycle")
                elif ids[sb].get("status") == "superseded":
                    err(r, "superseded_by", sb, "%s is itself superseded (chain ends at %s)" % (sb, cur.get("id")),
                        "warning")
            if r.get("status") != "superseded":
                err(r, "status", r.get("status"), "has superseded_by %s but status is %s" % (sb, r.get("status")))
        elif r.get("status") == "superseded":
            err(r, "superseded_by", None, "status superseded but superseded_by is empty")
        for f in ("related", "conflicts_with"):
            for x in r.get(f) or []:
                if x not in ids:
                    err(r, f, x, "no record %s" % x)
        if r.get("decision_id") and r["decision_id"] not in ids:
            err(r, "decision_id", r["decision_id"], "no record %s" % r["decision_id"])
    return out


def cmd_validate(a):
    recs = load_register(Path(a.register))
    issues = validate_register(recs, Path(a.ws))
    if a.json:
        print(json.dumps(issues, ensure_ascii=False, indent=1))
    else:
        for i in issues:
            print(f"{i['level'][0].upper()} {i['id']} {i['field']}: {i['value']}: {i['msg']}")
        ne = sum(1 for i in issues if i["level"] == "error")
        print(f"validate: {len(recs)} records, {ne} errors, {len(issues) - ne} warnings", file=sys.stderr)
    sys.exit(1 if any(i["level"] == "error" for i in issues) else 0)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", default=os.environ.get("DECISIONS_REGISTER", str(DEFAULT_REGISTER)))
    ap.add_argument("--ws", default=os.environ.get("DECISIONS_WS", str(DEFAULT_WS)))
    ap.add_argument("--snapshots", default=os.environ.get("DECISIONS_SNAPSHOTS", str(DEFAULT_SNAPSHOTS)))
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("list", help="compact table")
    p.add_argument("--type", choices=TYPES)
    p.add_argument("--status", help="comma-separated")
    p.add_argument("--source", help="prefix, e.g. agent or agent:B034")
    p.add_argument("--subtype")
    p.add_argument("--confidence", choices=CONFIDENCES)
    p.add_argument("--search")
    p.add_argument("--width", type=int, default=60)
    p.set_defaults(func=cmd_list)

    p = sp.add_parser("show")
    p.add_argument("ids", nargs="+")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sp.add_parser("add", help="add a decision; prints the new id")
    p.add_argument("--type", required=True, choices=TYPES)
    p.add_argument("--subtype")
    p.add_argument("--title")
    p.add_argument("--zh")
    p.add_argument("--en", required=True, help="rendering, rule text or question text")
    p.add_argument("--alias", action="append", help="other zh forms (repeat or comma-separate)")
    p.add_argument("--rationale")
    p.add_argument("--alternative", action="append", help="rejected options (repeatable)")
    p.add_argument("--scope", help="global (default) or banks: a027/0445,a027/0446")
    p.add_argument("--ref", action="append", help="example string, e.g. a027/0445#110 (repeatable)")
    p.add_argument("--related", action="append")
    p.add_argument("--source", default="agent", help="agent:B046-B047 | coordinator | user | glossary")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--confidence", choices=CONFIDENCES)
    p.add_argument("--force", action="store_true", help="add even if the zh already has a different rendering")
    p.set_defaults(func=cmd_add)

    p = sp.add_parser("set", help="change fields (recorded in history)")
    p.add_argument("id")
    p.add_argument("assignments", nargs="+", help="field=value | list+=value | list-=value | field=null")
    p.add_argument("--reason")
    p.add_argument("--by", default=default_by())
    p.add_argument("--redact-old", action="store_true",
                   help="store the old values in history as [redacted] (text that must not stay in the register, "
                        "e.g. song lyrics)")
    p.set_defaults(func=cmd_set)

    p = sp.add_parser("usages", help="where a term occurs and whether the English is consistent")
    p.add_argument("ids", nargs="+")
    p.add_argument("--all", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_usages)

    p = sp.add_parser("rename", help="change a term's English and propagate it to the workspace")
    p.add_argument("id")
    p.add_argument("--en", required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--old", action="append", help="English text to replace (default: the record's en; repeatable)")
    p.add_argument("--by", default=default_by())
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--include-shadowed", action="store_true",
                   help="also touch strings where the term only occurs inside a longer registered term")
    p.add_argument("--force", action="store_true", help="allow non-term records")
    p.set_defaults(func=cmd_rename)

    p = sp.add_parser("resolve", help="answer an open question")
    p.add_argument("id")
    p.add_argument("--answer", required=True)
    p.add_argument("--decision-id")
    p.add_argument("--reason")
    p.add_argument("--by", default=default_by())
    p.set_defaults(func=cmd_resolve)

    p = sp.add_parser("report", help="write DECISIONS.md and decisions.csv")
    p.add_argument("--no-usage", action="store_true", help="skip the workspace scan")
    p.add_argument("--out-dir")
    p.set_defaults(func=cmd_report)

    p = sp.add_parser("import-csv", help="apply edits made in decisions.csv (dry run unless --apply)")
    p.add_argument("file")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--reason")
    p.add_argument("--by", default=default_by())
    p.set_defaults(func=cmd_import_csv)

    p = sp.add_parser("import-progress", help="idempotent import of PROGRESS.md")
    p.add_argument("--progress", default=str(DEFAULT_PROGRESS))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_import_progress)

    p = sp.add_parser("render-progress", help="compact digest for translator agents")
    p.add_argument("--out")
    p.set_defaults(func=cmd_render_progress)

    p = sp.add_parser("validate", help="check refs (bank#id exist) and supersede/related links")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    a = ap.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
