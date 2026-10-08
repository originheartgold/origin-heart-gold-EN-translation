#!/usr/bin/env python3
"""rereview_report - spot-check page for the full re-review, built from git history.

Every commit whose subject starts with "Re-review RVxxx" is diffed against its parent; each string whose
English changed is listed with its Chinese, old and new English and the reviewer's ` | RVxxx: category:
reason` note. The page is local HTML (no network), filterable by batch, category and text.

    python3 work/tools/rereview_report.py                       # -> work/build/rereview/spotcheck.html
    python3 work/tools/rereview_report.py --batch RV001 --text  # plain text for one batch

The page contains game text: it stays under work/build/ and is never published.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "build" / "rereview" / "spotcheck.html"
LAYOUT = re.compile(r"\{(NEWLINE|SCROLL|CLEAR)\}")


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout


def show(rev: str, path: str) -> dict:
    s = git("show", "%s:%s" % (rev, path))
    return {e["id"]: e for e in json.loads(s)["strings"]} if s else {}


def flat(s: str | None) -> str:
    return re.sub(r"\s{2,}", " ", LAYOUT.sub(" ", s or "")).strip()


def collect(batch: str | None) -> list[dict]:
    rows = []
    for line in git("log", "--reverse", "--format=%H %s", "--grep=^Re-review RV").splitlines():
        sha, subj = line.split(" ", 1)
        m = re.match(r"Re-review (RV\d+)", subj)
        if not m or (batch and m.group(1) != batch):
            continue
        rv = m.group(1)
        for path in git("diff", "--name-only", sha + "^", sha, "--", "work/translate/banks").split():
            old, new = show(sha + "^", path), show(sha, path)
            bank = path.split("banks/")[1][:-5]
            for i, n in sorted(new.items()):
                o = old.get(i, {})
                if o.get("en") == n.get("en"):
                    continue
                notes = n.get("notes") or ""
                tag = re.findall(r"%s: ([a-z]+): ([^|]*)" % rv, notes)
                rows.append({"batch": rv, "commit": sha[:8], "ref": "%s#%d" % (bank, i), "zh": flat(n.get("zh")),
                             "old": flat(o.get("en")), "new": flat(n.get("en")), "origin": o.get("origin"),
                             "category": ", ".join(c for c, _ in tag) or "untagged",
                             "reason": "; ".join(r.strip() for _, r in tag)})
    return rows


def render(rows: list[dict]) -> str:
    batches = sorted({r["batch"] for r in rows})
    cats = sorted({c.strip() for r in rows for c in r["category"].split(",")})
    opts = lambda xs: "".join('<option>%s</option>' % html.escape(x) for x in xs)  # noqa: E731
    trs = "".join(
        '<tr data-b="{b}" data-c="{c}"><td>{b}<br><code>{ref}</code><br><small>{o}</small></td><td lang="zh">{zh}</td>'
        '<td class="old">{old}</td><td class="new">{new}</td><td><b>{c}</b><br>{why}</td></tr>'.format(
            b=r["batch"], ref=html.escape(r["ref"]), o=html.escape(r["origin"] or ""), zh=html.escape(r["zh"]),
            old=html.escape(r["old"]), new=html.escape(r["new"]), c=html.escape(r["category"]),
            why=html.escape(r["reason"])) for r in rows)
    return """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Re-review spot check</title><style>
:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd;--old:#fdecec;--new:#e9f7ee}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--mut:#aaa;--line:#333;--old:#3a2222;--new:#1f3326}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:16px}
table{border-collapse:collapse;width:100%}td{border-top:1px solid var(--line);padding:6px;vertical-align:top}
td:nth-child(1){width:9em;white-space:nowrap}.old{background:var(--old)}.new{background:var(--new)}
small,.mut{color:var(--mut)}header{position:sticky;top:0;background:var(--bg);padding:8px 0;display:flex;gap:8px;flex-wrap:wrap}
input,select{font:inherit;padding:4px}
</style></head><body><h1>Re-review spot check</h1>
<p class="mut">@N@ changed lines in @B@ batches. Red = before, green = after. Built from git history.</p>
<header><select id="b"><option value="">all batches</option>@BO@</select>
<select id="c"><option value="">all categories</option>@CO@</select>
<input id="q" placeholder="search text" size="30"><span id="n" class="mut"></span></header>
<table><tbody id="t">@TR@</tbody></table>
<script>
const b=document.getElementById('b'),c=document.getElementById('c'),q=document.getElementById('q'),n=document.getElementById('n');
function f(){let k=0;for(const r of document.querySelectorAll('#t tr')){const ok=(!b.value||r.dataset.b==b.value)&&(!c.value||r.dataset.c.includes(c.value))&&(!q.value||r.textContent.toLowerCase().includes(q.value.toLowerCase()));r.style.display=ok?'':'none';k+=ok}n.textContent=k+' shown'}
[b,c,q].forEach(e=>e.addEventListener('input',f));f();
</script></body></html>""".replace("@N@", str(len(rows))).replace("@B@", str(len(batches))).replace(
        "@BO@", opts(batches)).replace("@CO@", opts(cats)).replace("@TR@", trs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--batch")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    rows = collect(a.batch)
    if a.text:
        for r in rows:
            print("%s %s [%s] %s\n  zh:  %s\n  old: %s\n  new: %s" % (r["batch"], r["ref"], r["category"], r["reason"],
                                                                     r["zh"], r["old"], r["new"]))
        return 0
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(render(rows), encoding="utf-8")
    print("wrote %s (%d changed lines)" % (a.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
