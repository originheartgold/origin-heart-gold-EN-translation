#!/usr/bin/env python3
"""scene - readable scene transcripts and per-bank translator packets.

Built on the script-context index from translation_context.py (work/build/translation_context/index.json).
A scene is one script entry (root): every message it can show, in script order, with its speaker,
the player-gender / menu-choice / flag branch that leads to it, and the map and NPC it is bound to.

    python3 work/tools/scene.py build                     # derive the compact scene cache (once per index)
    python3 work/tools/scene.py show a027/0060#126        # the scene(s) around one line
    python3 work/tools/scene.py show a027/0060#126 --no-en --window 0   # whole scene, Chinese only
    python3 work/tools/scene.py packet a027/0060          # translator/reviewer packet for a whole bank
    python3 work/tools/scene.py packet a027/0060 --no-en --out work/build/scene/0060.md

Order is static script order (program counter), not proven play order; branch labels say which path a
line is on. A line with no script path is shown in bank order and says so. Outputs contain game text:
write files under work/build/ only. Standard library only; runs with the system python3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work"
INDEX = WORK / "build" / "translation_context" / "index.json"
CACHE = WORK / "build" / "scene" / "scenes.json"
BANKS = WORK / "translate" / "banks"
REGISTER = WORK / "translate" / "decisions" / "decisions.jsonl"
sys.path.insert(0, str(Path(__file__).resolve().parent))

COND = {0: "<", 1: "==", 2: ">", 3: "<=", 4: ">=", 5: "!="}
NEG = {"<": ">=", "==": "!=", ">": "<=", "<=": ">", ">=": "<", "!=": "=="}
GENDER = {0: "male", 1: "female"}
MENU_OPS = ("YesNo", "Menu", "GetMenuChoice", "TouchscreenMenu", "MultiChoice", "ListMenu")
LAYOUT_RE = re.compile(r"\{(NEWLINE|SCROLL|CLEAR)\}")
VAR_RE = re.compile(r"\{VAR:([0-9A-F]{4}):(\d+)(?:,\d+)?\}")
SPEAKER_RE = re.compile(r"(?:^|\{(?:SCROLL|CLEAR|NEWLINE)\})\s*([^\s『{}]{1,12}?)『")
NAME_SUBTYPES = ("character", "place", "organisation", "item", "nickname", "trainer-class", "badge", "species",
                 "move", "location", "pokemon", "event")
CN_ROM = WORK / "rom" / "origin_v4.0.3_cn.nds"
TRAINER_BANK = "a027/0718"  # one line per entry of the ROM's trainer message table (a/0/5/7)
TRMSG = {0: "intro", 1: "defeated", 2: "after battle", 3: "double intro (1st)", 4: "double defeated (1st)",
         5: "double after (1st)", 6: "double, player has 1 Pokémon (1st)", 7: "double intro (2nd)",
         8: "double defeated (2nd)", 9: "double after (2nd)", 10: "double, player has 1 Pokémon (2nd)",
         15: "in battle (turning point)", 16: "in battle (remark)", 17: "rematch intro",
         18: "rematch double (1st)", 19: "rematch double (2nd)", 20: "in battle (remark 2)"}
# description banks numbered in step with a name bank: label each line with what it describes
PAIRED = {"a027/0738": ("a027/0739", "move"), "a027/0218": ("a027/0219", "item"),
          "a027/0712": ("a027/0711", "ability"), "a027/0791": ("a027/0232", "Pokédex entry"),
          "a027/0792": ("a027/0232", "Pokédex entry"), "a027/0798": ("a027/0232", "Pokédex entry")}
BUFFER_LABEL = {"player_name": "player", "rival_name": "rival"}


# ------------------------------------------------------------------ build

def _producer(trace: list, pc: int, var: int) -> str | None:
    """Opcode that last wrote `var` before `pc` on this traced path (GetPlayerGender, a menu op...)."""
    best = None
    for t in trace:
        if t.get("pc", 0) >= pc:
            continue
        op, args = t.get("opcode", ""), t.get("args") or []
        if args and var in args and (op.startswith("Get") or any(m in op for m in MENU_OPS)):
            best = op
    return best


def _label(branch: dict, trace: list) -> str | None:
    cmp_ = branch.get("comparison") or {}
    src = cmp_.get("source") or {}
    op, args = src.get("opcode"), src.get("args") or []
    sym = COND.get(branch.get("condition_code"))
    if sym is None or branch.get("taken") is None:
        return None
    if not branch["taken"]:
        sym = NEG[sym]
    if op == "CheckFlag" and args:
        # CheckFlag + GoToIf(==) jumps when the flag is set
        return "flag %d %s" % (args[0], "set" if sym == "==" else "unset")
    if op == "CheckTrainerFlag" and args:
        return "trainer %d %s" % (args[0], "beaten" if sym == "==" else "not beaten")
    if op == "CompareVarToValue" and len(args) >= 2:
        var, val = args[0], args[1]
        prod = _producer(trace, src.get("pc", 0), var)
        if prod == "GetPlayerGender" and sym in ("==", "!=") and val in GENDER:
            g = GENDER[val] if sym == "==" else GENDER[1 - val]
            return "player is " + g
        if prod and any(m in prod for m in MENU_OPS):
            return "menu choice %s %d" % (sym, val)
        name = "result" if var == 0x800C else "var 0x%04X" % var
        if prod:
            name += " (%s)" % prod
        return "%s %s %d" % (name, sym, val)
    if op == "CompareVarToVar" and len(args) >= 2:
        return "var 0x%04X %s var 0x%04X" % (args[0], sym, args[1])
    return None


def play_order(msgs: dict[str, dict]) -> list[dict]:
    """Linearise a scene by its previous-message links (depth first, branches in script order);
    fall back to script position for lines without links."""
    succ: dict[str, list[str]] = {k: [] for k in msgs}
    has_prev = set()
    for k, m in msgs.items():
        for p in m["prev"]:
            if p in msgs and p != k:
                succ[p].append(k)
                has_prev.add(k)
    for v in succ.values():
        v.sort(key=lambda k: msgs[k]["pc"])
    starts = sorted((k for k in msgs if k not in has_prev), key=lambda k: msgs[k]["pc"])
    starts += sorted((k for k in msgs if k in has_prev), key=lambda k: msgs[k]["pc"])  # cycles
    order, done = [], set()
    for s0 in starts:
        stack = [s0]
        while stack:
            k = stack.pop()
            if k in done:
                continue
            done.add(k)
            order.append(msgs[k])
            stack.extend(reversed([x for x in succ[k] if x not in done]))
    return order


def build(index_path: Path = INDEX, out: Path = CACHE) -> dict:
    raw = index_path.read_bytes()
    idx = json.loads(raw)
    roots: dict[str, dict] = {}
    for rid, r in idx["roots"].items():
        sprites = sorted({b["event"].get("sprite") for b in r.get("event_bindings") or []
                          if isinstance(b.get("event"), dict) and b["event"].get("sprite") is not None})
        roots[rid] = {"bank": r.get("message_bank"), "file": r.get("script_file"), "entry": r.get("entry"),
                      "kind": r.get("kind"), "sprites": sprites, "maps": [], "msgs": {}}
    for ref, rr in idx["refs"].items():
        for o in rr.get("occurrences", []):
            rid = (o.get("root") or {}).get("id")
            if rid not in roots:
                continue
            R = roots[rid]
            for m in o.get("map_context") or []:
                nm = m.get("map_name_en")
                if nm and nm not in R["maps"]:
                    R["maps"].append(nm)
            key = ref
            trace = o.get("instruction_trace") or []
            labels = [x for x in (_label(b, trace) for b in o.get("branches") or []) if x]
            op = o.get("message_opcode")
            if op == "GenderMsgBox":
                idx_ = (o.get("message_operand") or {}).get("index")
                if idx_ in GENDER:
                    labels.append("player is " + GENDER[idx_])
            if op == "MenuItemAdd":
                labels.append("menu option")
            bufs = {str(k): BUFFER_LABEL.get(v.get("kind"), v.get("kind"))
                    for k, v in (o.get("buffers") or {}).items() if v.get("kind")}
            M = R["msgs"].setdefault(key, {"ref": ref, "pc": o.get("pc", 0), "op": op, "paths": [], "bufs": {},
                                           "callers": [], "prev": []})
            for pm in o.get("previous_messages") or []:
                pk = pm.get("ref")
                if pk not in M["prev"]:
                    M["prev"].append(pk)
            path = sorted(set(labels))
            if path not in M["paths"] and len(M["paths"]) < 16:
                M["paths"].append(path)
            M["bufs"].update(bufs)
            for c in o.get("call_path") or []:
                s = "%s@%s" % (c.get("script_file"), c.get("pc"))
                if s not in M["callers"] and len(M["callers"]) < 3:
                    M["callers"].append(s)
    ref2roots: dict[str, list[str]] = {}
    for rid, R in roots.items():
        R["msgs"] = play_order(R["msgs"])
        bufs: dict[str, str] = {}
        for m in R["msgs"]:
            bufs.update(m.pop("bufs"))
        R["bufs"] = bufs
        for m in R["msgs"]:
            ref2roots.setdefault(m["ref"], [])
            if rid not in ref2roots[m["ref"]]:
                ref2roots[m["ref"]].append(rid)
    roots = {k: v for k, v in roots.items() if v["msgs"]}
    trainers = trainer_table()
    if trainers is None and out.exists():
        try:
            trainers = json.loads(out.read_text(encoding="utf-8")).get("trainers")
        except (OSError, ValueError):
            trainers = None
    if trainers is None:
        print("scene: ndspy or the Chinese ROM unavailable; trainer lines get no trainer context "
              "(rebuild with work/.venv/bin/python)", file=sys.stderr)
    cache = {"index_sha256": hashlib.sha256(raw).hexdigest(), "index_mtime": index_path.stat().st_mtime,
             "roots": roots, "ref2roots": ref2roots, "trainers": trainers}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, out)
    return cache


def trainer_table(rom_path: Path = CN_ROM) -> list[dict] | None:
    """[{line, trainer, type, class}] from the untouched Chinese ROM; needs ndspy (work/.venv)."""
    try:
        import struct

        import ndspy.narc
        import ndspy.rom
    except ImportError:
        return None
    if not rom_path.exists():
        return None
    rom = ndspy.rom.NintendoDSRom.fromFile(str(rom_path))
    tbl = ndspy.narc.NARC(rom.getFileByName("a/0/5/7")).files[0]
    trdata = ndspy.narc.NARC(rom.getFileByName("a/0/5/5")).files
    out = []
    for i in range(len(tbl) // 4):
        tid, ty = struct.unpack_from("<HH", tbl, i * 4)
        cls = trdata[tid][1] if tid < len(trdata) and len(trdata[tid]) > 1 else None
        out.append({"line": i, "trainer": tid, "type": ty, "class": cls})
    return out


def load_cache(index_path: Path = INDEX, path: Path = CACHE) -> dict:
    if not path.exists():
        if not index_path.exists():
            sys.exit("no script-context index: run work/.venv/bin/python work/tools/translation_context.py build")
        print("scene: building cache from %s ..." % index_path, file=sys.stderr)
        return build(index_path, path)
    cache = json.loads(path.read_text(encoding="utf-8"))
    if index_path.exists() and index_path.stat().st_mtime > cache.get("index_mtime", 0) + 1:
        print("scene: index changed, rebuilding cache ...", file=sys.stderr)
        return build(index_path, path)
    return cache


# ------------------------------------------------------------------ text

_banks: dict[str, dict[int, dict]] = {}


def bank(key: str) -> dict[int, dict]:
    if key not in _banks:
        p = BANKS / (key + ".json")
        _banks[key] = {e["id"]: e for e in json.loads(p.read_text(encoding="utf-8"))["strings"]} if p.exists() else {}
    return _banks[key]


def entry(ref: str) -> dict:
    b, i = ref.split("#")
    return bank(b).get(int(i), {})


def clean(s: str | None, bufs: dict | None = None) -> str:
    if not s:
        return ""
    s = LAYOUT_RE.sub(" ", s)

    def var(m: re.Match) -> str:
        lab = (bufs or {}).get(m.group(2))
        return "⟨%s⟩" % lab if lab else m.group(0)

    s = VAR_RE.sub(var, s)
    return re.sub(r"\s{2,}", " ", s).strip()


def speakers(zh: str) -> list[str]:
    out = []
    for n in SPEAKER_RE.findall(zh or ""):
        if n not in out:
            out.append(n)
    return out


# ------------------------------------------------------------------ render

def _path_text(paths: list[list[str]], common: set[str]) -> str:
    """Conditions that hold on every path to the line, minus those the whole scene shares."""
    if not paths:
        return ""
    always = set(paths[0]).intersection(*map(set, paths[1:]))
    extra = sorted(always - common)
    if extra:
        return ", ".join(extra)
    return "(several paths)" if len({tuple(p) for p in paths}) > 1 else ""


def render_root(cache: dict, rid: str, target: str | None, window: int, show_en: bool,
                seen: set[str] | None = None) -> list[str]:
    R = cache["roots"][rid]
    msgs = R["msgs"]
    sets = [set(m["paths"][0]).intersection(*map(set, m["paths"][1:])) if m["paths"] else set() for m in msgs]
    common = set.intersection(*sets) if sets else set()
    lo, hi = 0, len(msgs)
    if target and window:
        pos = [i for i, m in enumerate(msgs) if m["ref"] == target]
        if pos:
            lo, hi = max(0, pos[0] - window), min(len(msgs), pos[-1] + window + 1)
    head = "### scene %s  (script file %s, entry %s; %s)" % (
        rid, R["file"], R["entry"], ", ".join(R["maps"]) or "map unknown")
    lines = [head]
    if R["sprites"]:
        lines.append("bound to NPC sprite(s): %s" % ", ".join(map(str, R["sprites"][:6])))
    if common:
        lines.append("whole scene requires: %s" % ", ".join(sorted(common)))
    if lo:
        lines.append("  … %d earlier line(s)" % lo)
    last, last_cond = None, None
    bufs = R.get("bufs", {})
    for m in msgs[lo:hi]:
        if m["ref"] == last:
            continue
        last = m["ref"]
        e = entry(m["ref"])
        mark = "▶" if m["ref"] == target else " "
        cond = _path_text(m["paths"], common)
        if cond != last_cond:
            lines.append("  -- path: %s" % (cond or "(main path)"))
            last_cond = cond
        tag = m["ref"].split("/")[1]
        lines.append("%s %s%s" % (mark, tag, "  (%s)" % m["op"] if m["op"] not in ("NPCMsg",) else ""))
        lines.append("    zh: " + clean(e.get("zh"), bufs))
        if show_en:
            lines.append("    en: " + clean(e.get("en"), bufs))
        if seen is not None:
            seen.add(m["ref"])
    if hi < len(msgs):
        lines.append("  … %d later line(s)" % (len(msgs) - hi))
    return lines


def trainer_label(t: dict) -> str:
    cls = bank("a027/0720").get(t["class"] or -1, {})
    nm = bank("a027/0719").get(t["trainer"], {})
    return "trainer %d: %s %s (%s %s)" % (t["trainer"], clean(cls.get("en")) or "?", clean(nm.get("en")) or "?",
                                          clean(cls.get("zh")), clean(nm.get("zh")))


def render_trainer(cache: dict, tid: int, target: str | None, show_en: bool, seen: set[str] | None = None) -> list[str]:
    rows = [t for t in cache.get("trainers") or [] if t["trainer"] == tid]
    if not rows:
        return []
    lines = ["### " + trainer_label(rows[0]) + "  (lines chosen by the trainer table, not a script)"]
    for t in sorted(rows, key=lambda t: (t["type"], t["line"])):
        ref = "%s#%d" % (TRAINER_BANK, t["line"])
        e = entry(ref)
        lines.append("%s 0718#%d  [%s]" % ("▶" if ref == target else " ", t["line"], TRMSG.get(t["type"], "type %d" % t["type"])))
        lines.append("    zh: " + clean(e.get("zh")))
        if show_en:
            lines.append("    en: " + clean(e.get("en")))
        if seen is not None:
            seen.add(ref)
    return lines


def paired(key: str, i: int) -> str:
    if key not in PAIRED:
        return ""
    nb, kind = PAIRED[key]
    n = bank(nb).get(i, {})
    return "  [%s: %s / %s]" % (kind, clean(n.get("en")) or "?", clean(n.get("zh")) or "?")


def bank_order(ref: str, window: int, show_en: bool) -> list[str]:
    b, i = ref.split("#")
    i = int(i)
    lines = ["### %s: no script path found; neighbouring ids in bank order (not proven play order)" % ref]
    for j in range(i - window, i + window + 1):
        e = bank(b).get(j)
        if not e:
            continue
        lines.append("%s %s#%d%s" % ("▶" if j == i else " ", b.split("/")[1], j, paired(b, j)))
        lines.append("    zh: " + clean(e.get("zh")))
        if show_en:
            lines.append("    en: " + clean(e.get("en")))
    return lines


def show(cache: dict, ref: str, window: int, show_en: bool, max_scenes: int) -> str:
    rids = cache["ref2roots"].get(ref, [])
    if ref.startswith(TRAINER_BANK + "#") and cache.get("trainers"):
        i = int(ref.split("#")[1])
        if i < len(cache["trainers"]):
            return "\n".join(render_trainer(cache, cache["trainers"][i]["trainer"], ref, show_en))
    if not rids:
        return "\n".join(bank_order(ref, window or 6, show_en))
    # smallest scenes first: they are the most specific context
    rids = sorted(rids, key=lambda r: len(cache["roots"][r]["msgs"]))
    out = []
    for rid in rids[:max_scenes]:
        out += render_root(cache, rid, ref, window, show_en) + [""]
    if len(rids) > max_scenes:
        out.append("(%d more scene(s) reach this line: %s)" % (len(rids) - max_scenes, ", ".join(rids[max_scenes:])))
    return "\n".join(out)


# ------------------------------------------------------------------ packet

def _register() -> list[dict]:
    recs = [json.loads(x) for x in REGISTER.read_text(encoding="utf-8").splitlines() if x.strip()]
    return [r for r in recs if r.get("status") not in ("superseded",)]


def _in_scope(r: dict, key: str) -> bool:
    sc = r.get("scope")
    if isinstance(sc, list):
        return key in sc
    return isinstance(sc, str) and key in sc


def packet(cache: dict, key: str, show_en: bool) -> str:
    strings = bank(key)
    if not strings:
        sys.exit("no bank %s" % key)
    bnum = int(key.split("/")[1])
    rids = [rid for rid, R in cache["roots"].items()
            if R["bank"] == bnum and any(m["ref"].startswith(key + "#") for m in R["msgs"])]
    rids.sort(key=lambda r: (cache["roots"][r]["file"], cache["roots"][r]["entry"]))
    out = ["# Packet %s" % key, "",
           "Scenes are static script order with branch labels; '▶' is not used here. Every string of the bank "
           "appears at least once: in a scene, or in the 'no script path' list at the end.", ""]
    seen: set[str] = set()
    for rid in rids:
        out += render_root(cache, rid, None, 0, show_en, seen) + [""]
    if key == TRAINER_BANK and cache.get("trainers"):
        for tid in dict.fromkeys(t["trainer"] for t in cache["trainers"]):
            out += render_trainer(cache, tid, None, show_en, seen) + [""]
    rest = [i for i in sorted(strings) if "%s#%d" % (key, i) not in seen]
    if rest:
        out.append("### strings with no script path (bank order; menus, signs, std scripts or unused)")
        for i in rest:
            e = strings[i]
            out.append("  %s#%d%s" % (key.split("/")[1], i, paired(key, i)))
            out.append("    zh: " + clean(e.get("zh")))
            if show_en:
                out.append("    en: " + clean(e.get("en")))
        out.append("")
    # context records
    allzh = "\n".join(e.get("zh") or "" for e in strings.values())
    spk = []
    for e in strings.values():
        for n in speakers(e.get("zh")):
            if n not in spk:
                spk.append(n)
    recs = _register()
    voice = [r for r in recs if r.get("type") == "voice" and r.get("zh") and
             any(r["zh"] == n or r["zh"] in n for n in spk)]
    terms = [r for r in recs if r.get("type") == "term" and r.get("zh") and len(r["zh"]) > 1 and r["zh"] in allzh
             and r.get("subtype") not in ("ui-term", "speaker-label")
             and (r.get("scope") in (None, "global") or _in_scope(r, key))]
    local = [r for r in recs if r.get("type") not in ("term", "voice", "question") and
             (_in_scope(r, key) or any(str(x).startswith(key + "#") for x in r.get("refs") or []))]
    qs = [r for r in recs if r.get("type") == "question" and r.get("status") == "open" and
          any(str(x).startswith(key + "#") for x in r.get("refs") or [])]
    out.append("## Speakers in this bank: " + (", ".join(spk) or "(none labelled)"))
    if voice:
        out.append("## Voice records (precedents, D-2081: choose tone per line)")
        for r in voice:
            out.append("- %s %s → %s: %s" % (r["id"], r["zh"], r.get("title") or "", (r.get("en") or "")[:400]))
    if terms:
        out.append("## Names and terms used (register)")
        for r in terms[:120]:
            out.append("- %s %s → %s%s" % (r["id"], r["zh"], r.get("en"),
                                           "" if r.get("subtype") in NAME_SUBTYPES or r.get("status") == "accepted" else "  [precedent, not a rule]"))
    try:
        import qa  # glossary: official names
        g, _ = qa.load_glossary()
        hits = []
        for cat, m in g.items():
            for zh, vs in m.items():
                if zh in allzh and (len(zh) > 2 or (len(zh) == 2 and cat in ("species", "items", "locations"))):
                    hits.append("%s → %s (%s)" % (zh, vs[0], cat))
        if hits:
            out.append("## Glossary names used")
            out += ["- " + h for h in sorted(set(hits))[:200]]
    except Exception as exc:  # pragma: no cover - glossary is optional context
        out.append("(glossary unavailable: %s)" % exc)
    if local:
        out.append("## Decisions for this bank")
        for r in local:
            out.append("- %s [%s/%s %s] %s" % (r["id"], r.get("type"), r.get("subtype"), r.get("status"),
                                               (r.get("title") or r.get("en") or "")[:300]))
    if qs:
        out.append("## Open questions on this bank")
        for r in qs:
            out.append("- %s %s: %s" % (r["id"], ",".join(x for x in r.get("refs") or [] if str(x).startswith(key)),
                                        (r.get("title") or r.get("en") or "")[:300]))
    return "\n".join(out) + "\n"


def _check_out(p: Path) -> None:
    if not p.resolve().is_relative_to((WORK / "build").resolve()):
        sys.exit("scene output contains game text; write it under work/build/")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=INDEX)
    ap.add_argument("--cache", type=Path, default=CACHE)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="derive the scene cache from the context index")
    s = sub.add_parser("show", help="scene(s) around one line")
    s.add_argument("ref")
    s.add_argument("--window", type=int, default=12, help="lines before/after (0 = whole scene)")
    s.add_argument("--scenes", type=int, default=3, help="max scenes to print")
    s.add_argument("--no-en", action="store_true", help="hide current English (independent translation)")
    p = sub.add_parser("packet", help="translator/reviewer packet for a bank")
    p.add_argument("bank", help="e.g. a027/0060")
    p.add_argument("--no-en", action="store_true")
    p.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "build":
        c = build(a.index, a.cache)
        print("scene cache: %d scenes, %d lines -> %s" % (len(c["roots"]), len(c["ref2roots"]), a.cache))
        return 0
    cache = load_cache(a.index, a.cache)
    if a.cmd == "show":
        text = show(cache, a.ref, a.window, not a.no_en, a.scenes)
    else:
        text = packet(cache, a.bank, not a.no_en)
    if getattr(a, "out", None):
        _check_out(a.out)
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
        print("wrote %s (%d lines)" % (a.out, text.count("\n")))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
