#!/usr/bin/env python3
"""omission_check - flag English lines that may drop, add or soften what the Chinese says.

Mechanical signals only; every flag is a question for a reviewer, never a verdict:

  length      English much shorter/longer than usual for that much Chinese (dropped or invented content)
  clauses     far fewer English sentences than Chinese sentences
  speakers    a 名字『 speaker label in the Chinese has no 'Name:' label in the English, or counts differ
  question    the Chinese asks (？) and the English has no question mark
  names       a character/place/species/item named in the Chinese is missing from the English
  strength    the Chinese has a strong marker (death/kill, 妈的, 混蛋, 滚, 装逼…) and the English none
  exclaim     the Chinese has 3+ exclamations and the English none

    python3 work/tools/omission_check.py a027/0047 a027/0060        # banks
    python3 work/tools/omission_check.py --all --min-score 3 --top 200
    python3 work/tools/omission_check.py --all --json --out work/build/omission/all.jsonl

Score = sum of signal weights; sort descending. Lines with origin 'copy' and redacted lyrics are skipped.
Output contains game text: write files under work/build/ only. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "work"
BANKS = WORK / "translate" / "banks"
REGISTER = WORK / "translate" / "decisions" / "decisions.jsonl"
sys.path.insert(0, str(Path(__file__).resolve().parent))

TAG_RE = re.compile(r"\{[^}]*\}")
HAN_RE = re.compile(r"[㐀-鿿]")
SPEAKER_RE = re.compile(r"(?:^|\{(?:SCROLL|CLEAR|NEWLINE)\})\s*([^\s『{}]{1,12}?)『")
EN_SPEAKER_RE = re.compile(r"(?:^|\{(?:SCROLL|CLEAR|NEWLINE)\}|[.!?…]\s)\s*([^\s:{}][^:{}\n]{0,30}?|\{VAR:[^}]*\}):(?:\s|$|\{)")
ZH_SENT_RE = re.compile(r"[。！？!?；]+|……+|⋯⋯+")
EN_SENT_RE = re.compile(r"[.!?;]+(?=\s|$|[’'\"”])|\.\.\.|…")

# (zh pattern, English evidence) — zh patterns avoid the common false friends (妈妈, 婆婆妈妈, 逼 = force)
STRENGTH = [
    ("death/kill", r"弄死|杀了|杀死|宰了|去死|受死|找死|死定|死路|送你上西天|干掉|偿命|毙命|灭口",
     r"\b(die|dies|dying|dead|death|kill|killed|killing|grave|murder|end you|finish(ed)? (you|them|off)|"
     r"done for|six feet|take (you|them|him|her|it) (out|down)|rub (you|them) out|wipe(d)? out|suicide|life|lives)\b"),
    ("swear", r"(?<!妈)妈的|他妈|特么|尼玛|卧槽|我操|操你|(?<![一今明昨每生节])日你|狗日",
     r"(damn|dammit|\bhell\b|shit|fuck|goddamn|crap|bloody|bitch)"),
    ("insult", r"混蛋|王八|杂种|混账|狗东西|畜生|贱人|婊子|废物|蠢货|傻[逼瓜]|笨蛋|白痴|垃圾(?![喷桶箱堆场袋])|窝囊废|人渣|狗娘|兔崽子|臭小鬼|臭丫头",
     r"\b(bastard|asshole|son of a bitch|scum|bitch|jerk|prick|swine|animal|beast|trash|garbage|loser|idiot|"
     r"moron|fool|dumb|stupid|brat|runt|punk|worm|filth|whore|slut|useless|pathetic|dimwit|dope|imbecile|wretch)"),
    ("vulgar", r"装逼|逼逼|牛逼|笨逼|怂逼|傻逼|妈了个逼|屁|尿|屎",
     r"(shit|crap|\bass|piss|fart|bitch|fuck|poop|\bpee\b|butt|spank)"),
    ("get-lost", r"(?<![翻打圆])滚(开|出|蛋|回|一边|远|吧|！|!)|给我滚|快滚",
     r"(get lost|beat it|scram|get out|hell|piss off|get the|outta|go away|back off|buzz off|shove off|"
     r"take a hike|crawl|get away|move it|clear off)"),
]

NAME_BANKS = {"a027/0232", "a027/0739", "a027/0219", "a027/0711", "a027/0724", "a027/0033", "a027/0183",
              "a027/0738", "a027/0712"}  # names and fixed-width descriptions: length is set by the box
COMMON = {"姐姐", "妈妈", "爸爸", "哥哥", "弟弟", "妹妹", "爷爷", "奶奶", "大叔", "阿姨", "老师", "自行车", "地图",
          "太郎", "怪力", "毒针", "大树果", "地下通道"}


def name_ok(en: str, ens: list[str]) -> bool:
    """English carries the name: full form, 'Prof.'/'Professor' and 'the' folded, or its distinctive word."""
    low = en.lower().replace("professor ", "prof. ")
    for x in ens:
        x = x.lower().replace("professor ", "prof. ")
        x = re.sub(r"^the ", "", x)
        if x and x in low:
            return True
        words = [w for w in re.findall(r"[a-zé’'.]+", x) if len(w) >= 4 and w not in ("city", "town", "region", "prof.")]
        if words and any(w in low for w in words):
            return True
    return False


WEIGHTS = {"length-short": 3, "length-long": 2, "clauses": 2, "speakers": 3, "question": 1, "names": 2,
           "strength": 3, "exclaim": 1}


def visible(s: str) -> str:
    return re.sub(r"\s{2,}", " ", TAG_RE.sub(" ", s or "")).strip()


def load_names() -> list[tuple[str, list[str]]]:
    """(zh, acceptable English) for characters, places, species, items: things a line must not lose."""
    out: dict[str, list[str]] = {}
    try:
        import qa
        g, _ = qa.load_glossary()
        for cat in ("species", "items", "locations"):
            for zh, vs in g.get(cat, {}).items():
                if len(zh) >= 2 and zh not in COMMON:
                    out.setdefault(zh, []).extend(vs)
    except Exception:
        pass
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("type") == "term" and r.get("subtype") in ("character", "place", "organisation", "nickname") \
                and r.get("status") != "superseded" and r.get("zh") and r.get("en") and len(r["zh"]) >= 2:
            for zh in [x for x in [r["zh"]] + list(r.get("aliases") or []) if len(x) >= 2 and x not in COMMON]:
                out.setdefault(zh, []).extend(x.strip() for x in re.split(r"\s*/\s*", r["en"]) if x.strip())
    # longest first so 派拉斯特 is tried before 派拉斯
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


def bank_entries(key: str) -> list[dict]:
    return json.loads((BANKS / (key + ".json")).read_text(encoding="utf-8"))["strings"]


def ratio(zh: str, en: str) -> float | None:
    h = len(HAN_RE.findall(zh))
    if h < 10:
        return None
    return len(visible(en)) / h


def analyse(key: str, e: dict, names: list[tuple[str, list[str]]], med: float) -> dict | None:
    zh, en = e.get("zh") or "", e.get("en") or ""
    if not en or e.get("origin") == "copy" or zh.startswith("[zh redacted") or not HAN_RE.search(zh):
        return None
    vz, ve = visible(zh), visible(en)
    flags: list[tuple[str, str]] = []
    r = ratio(zh, en) if key not in NAME_BANKS else None
    if r is not None:
        if r < med * 0.5:
            flags.append(("length-short", "en/zh %.1f vs usual %.1f" % (r, med)))
        elif r > med * 2.1:
            flags.append(("length-long", "en/zh %.1f vs usual %.1f" % (r, med)))
    zs = len([x for x in ZH_SENT_RE.split(vz) if HAN_RE.search(x)])
    es = len([x for x in EN_SENT_RE.split(ve) if re.search(r"[A-Za-z]", x)])
    if zs >= 4 and es < zs * 0.5:
        flags.append(("clauses", "%d zh sentences, %d en" % (zs, es)))
    zsp = [m.group(1) for m in SPEAKER_RE.finditer(zh)
           if "』" not in re.split(r"\{(?:SCROLL|CLEAR)\}", zh[m.end():])[0]]
    esp = EN_SPEAKER_RE.findall(en)
    if zsp and len(esp) < len(zsp):
        flags.append(("speakers", "zh labels %s, en %d" % ("/".join(zsp), len(esp))))
    if re.search(r"[？?]", vz) and "?" not in ve:
        flags.append(("question", "zh asks, en has no '?'"))
    if len(re.findall(r"[！!]", vz)) >= 3 and "!" not in ve:
        flags.append(("exclaim", "zh has %d '！', en none" % len(re.findall(r"[！!]", vz))))
    rest = vz
    missing = []
    for zhn, ens in names:
        if zhn in rest:
            rest = rest.replace(zhn, " ")
            if not name_ok(ve, ens):
                missing.append("%s→%s" % (zhn, ens[0]))
    if missing:
        flags.append(("names", ", ".join(missing[:4])))
    for label, zp, ep in STRENGTH:
        m = re.search(zp, re.sub(r"(乱扔|扔|捡)垃圾", "", vz))
        if m and not re.search(ep, ve, re.I):
            flags.append(("strength", "%s '%s' with no matching English" % (label, m.group(0))))
    if not flags:
        return None
    score = sum(WEIGHTS[f[0]] for f in flags)
    return {"ref": "%s#%d" % (key, e["id"]), "score": score, "origin": e.get("origin"), "status": e.get("status"),
            "flags": [{"signal": a, "detail": b} for a, b in flags], "zh": vz, "en": ve}


def median_ratio(keys: list[str]) -> float:
    vals = []
    for k in keys:
        for e in bank_entries(k):
            if e.get("en") and e.get("origin") not in ("copy",):
                r = ratio(e.get("zh") or "", e["en"])
                if r is not None:
                    vals.append(r)
    return statistics.median(vals) if vals else 3.0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("banks", nargs="*", help="e.g. a027/0047")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--min-score", type=int, default=2)
    ap.add_argument("--top", type=int, default=0, help="only the N highest scores")
    ap.add_argument("--signal", action="append", help="only these signals (repeatable)")
    ap.add_argument("--origin", action="append", help="only these origins, e.g. us, tm_v3, agent")
    ap.add_argument("--json", action="store_true", help="JSON lines")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    allkeys = sorted("%s/%s" % (p.parent.name, p.stem) for p in BANKS.glob("*/*.json"))
    keys = allkeys if a.all else a.banks
    if not keys:
        ap.error("give banks or --all")
    med = median_ratio(allkeys)
    meds = {}
    for k in keys:
        vals = [ratio(e.get("zh") or "", e["en"]) for e in bank_entries(k) if e.get("en") and e.get("origin") != "copy"]
        vals = [v for v in vals if v is not None]
        if len(vals) >= 30:
            meds[k] = statistics.median(vals)
    names = load_names()
    rows = []
    for k in keys:
        for e in bank_entries(k):
            r = analyse(k, e, names, meds.get(k, med))
            if not r or r["score"] < a.min_score:
                continue
            if a.signal and not any(f["signal"] in a.signal or f["signal"].split("-")[0] in a.signal
                                    for f in r["flags"]):
                continue
            if a.origin and r["origin"] not in a.origin:
                continue
            rows.append(r)
    rows.sort(key=lambda r: (-r["score"], r["ref"]))
    if a.top:
        rows = rows[: a.top]
    if a.json:
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    else:
        lines = []
        for r in rows:
            lines.append("%s  score %d  [%s/%s]" % (r["ref"], r["score"], r["origin"], r["status"]))
            for f in r["flags"]:
                lines.append("   - %s: %s" % (f["signal"], f["detail"]))
            lines.append("   zh: " + r["zh"])
            lines.append("   en: " + r["en"])
        lines.append("%d flagged line(s) in %d bank(s); en/zh median %.2f" % (len(rows), len(keys), med))
        text = "\n".join(lines) + "\n"
    if a.out:
        if not a.out.resolve().is_relative_to((WORK / "build").resolve()):
            sys.exit("output contains game text; write it under work/build/")
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(text, encoding="utf-8")
        print("wrote %s (%d rows)" % (a.out, len(rows)))
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
