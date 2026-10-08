#!/usr/bin/env python3
"""rereview_report - review page for the full re-review, built from git history and the register.

Every commit whose subject starts with "Re-review RVxxx" is diffed against its parent; each string whose
English changed is listed with its Chinese, old and new English and the reviewer's ` | RVxxx: category:
reason` note. A second and third tab list the open register questions for the user and the open
hack-findings, with the current Chinese/English of their lines. Verdicts are kept in the browser and
exported as rereview-verdicts.json for the coordinator to apply. Local HTML, no network.

    python3 work/tools/rereview_report.py                       # -> work/build/rereview/review.html
    python3 work/tools/rereview_report.py --batch RV001 --text  # plain text for one batch

The page contains game text: it stays under work/build/ and is never published.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "work" / "build" / "rereview" / "review.html"
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


REGISTER = ROOT / "work" / "translate" / "decisions" / "decisions.jsonl"
BANKS = ROOT / "work" / "translate" / "banks"
USER_SUBTYPES = ("rereview", "question", "fidelity-review", "translation-quality", "evidence-gap", "context-note",
                 "verify-in-game", None)


def line(ref: str, cache: dict) -> dict:
    """Current zh/en of a bank line, for showing question context."""
    m = re.match(r"([^#]+)#(\d+)$", ref)
    if not m:
        return {}
    bank, i = m.group(1), int(m.group(2))
    if bank not in cache:
        f = BANKS / (bank + ".json")
        cache[bank] = {e["id"]: e for e in json.loads(f.read_text(encoding="utf-8"))["strings"]} if f.exists() else {}
    e = cache[bank].get(i)
    return {"ref": ref, "zh": flat(e.get("zh")), "en": flat(e.get("en"))} if e else {"ref": ref}


def questions() -> list[dict]:
    cache: dict = {}
    out = []
    for raw in REGISTER.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        r = json.loads(raw)
        if r.get("type") != "question" or r.get("status") != "open":
            continue
        kind = "finding" if r.get("subtype") == "hack-finding" else "question"
        refs = [x for x in (r.get("refs") or []) if isinstance(x, str)]
        out.append({"id": r["id"], "kind": kind, "subtype": r.get("subtype") or "", "title": r.get("title") or "",
                    "text": r.get("en") or "", "rationale": r.get("rationale") or "", "source": r.get("source") or "",
                    "created": r.get("created") or "", "lines": [line(x, cache) for x in refs[:8]],
                    "more": max(0, len(refs) - 8)})
    return out


def render(rows: list[dict]) -> str:
    data = json.dumps({"changes": rows, "questions": questions()}, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("@DATA@", data)


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Translation re-review</title><style>
:root{--bg:#fbfbfa;--card:#fff;--fg:#1d1d1f;--mut:#6b6b70;--line:#e3e3e0;--old:#fdeceb;--new:#e8f6ec;--acc:#2f5bd3;
--ok:#1f7a3d;--bad:#b3261e;--warn:#9a6700;--chip:#f0f0ee}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#151517;--card:#1e1e21;--fg:#ececee;--mut:#9a9aa2;
--line:#33333a;--old:#3b2323;--new:#1d3324;--acc:#8fb0ff;--ok:#6fd08f;--bad:#ff8a80;--warn:#e3b341;--chip:#2a2a2f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,sans-serif}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 16px}
h1{font-size:17px;margin:0 0 6px}nav{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px}
nav button{border:1px solid var(--line);background:var(--card);color:var(--fg);padding:5px 12px;border-radius:999px;cursor:pointer;font:inherit}
nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
.bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
select,input,textarea{font:inherit;color:var(--fg);background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 6px}
input[type=search]{min-width:200px;flex:1}.mut{color:var(--mut)}main{padding:12px 16px;max-width:1200px;margin:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:0 0 10px}
.top{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap}.ref{font:12px ui-monospace,Menlo,monospace}
.chip{background:var(--chip);border-radius:999px;padding:1px 8px;font-size:12px}
.zh{font-size:15px;margin:6px 0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
@media (max-width:700px){.grid{grid-template-columns:1fr}}
.old,.new{border-radius:6px;padding:6px 8px}.old{background:var(--old)}.new{background:var(--new)}
.lab{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut)}
.why{margin-top:6px;color:var(--mut)}.acts{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;align-items:center}
.acts button{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:6px;padding:3px 10px;cursor:pointer;font:inherit}
.acts button.ok.on{background:var(--ok);color:#fff;border-color:var(--ok)}.acts button.bad.on{background:var(--bad);color:#fff;border-color:var(--bad)}
.acts button.mid.on{background:var(--warn);color:#fff;border-color:var(--warn)}
textarea{width:100%;min-height:34px;margin-top:6px}.lines{margin-top:6px;border-top:1px dashed var(--line);padding-top:6px}
.lines div{margin:3px 0}.pager{display:flex;gap:8px;align-items:center;justify-content:center;margin:12px}
.btn{border:1px solid var(--acc);color:var(--acc);background:transparent;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}
.text{white-space:pre-wrap}
</style></head><body>
<header><h1>Translation re-review</h1>
<nav id="tabs"></nav>
<div class="bar" id="filters"></div>
<div class="bar" style="margin-top:6px"><span id="count" class="mut"></span><span style="flex:1"></span>
<span id="prog" class="mut"></span><button class="btn" id="exp">Export my verdicts</button></div></header>
<main id="list"></main><div class="pager" id="pager"></div>
<script>
const D=@DATA@;const KEY='rereview-verdicts-v1';let V={};try{V=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
const save=()=>{try{localStorage.setItem(KEY,JSON.stringify(V))}catch(e){}prog()};
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const TABS=[['changes','Changes ('+D.changes.length+')'],['question','Questions for you ('+D.questions.filter(q=>q.kind=='question').length+')'],['finding','Hack findings ('+D.questions.filter(q=>q.kind=='finding').length+')']];
let tab='changes',page=0;const PER=50;
const uniq=a=>[...new Set(a)].sort();
function filters(){const f=document.getElementById('filters');let h='<input type="search" id="q" placeholder="Search Chinese, English, ref, id...">';
 if(tab=='changes'){h+=sel('fb','all batches',uniq(D.changes.map(r=>r.batch)))+sel('fc','all categories',uniq(D.changes.flatMap(r=>r.category.split(', '))))+sel('fo','any origin',uniq(D.changes.map(r=>r.origin||'')).filter(Boolean));}
 else{h+=sel('fs','all subtypes',uniq(D.questions.filter(q=>q.kind==tab).map(q=>q.subtype)))+sel('fsrc','any source',['re-review (RVxxx)','earlier']);}
 h+=sel('fv','any verdict',['not reviewed yet','reviewed']);f.innerHTML=h;f.querySelectorAll('input,select').forEach(e=>e.addEventListener('input',()=>{page=0;draw()}))}
const sel=(id,all,xs)=>'<select id="'+id+'"><option value="">'+all+'</option>'+xs.map(x=>'<option>'+esc(x)+'</option>').join('')+'</select>';
const val=id=>{const e=document.getElementById(id);return e?e.value:''};
function items(){const q=val('q').toLowerCase(),fv=val('fv');let xs;
 if(tab=='changes'){const fb=val('fb'),fc=val('fc'),fo=val('fo');xs=D.changes.filter(r=>(!fb||r.batch==fb)&&(!fc||r.category.split(', ').includes(fc))&&(!fo||r.origin==fo));xs=xs.map(r=>({...r,key:'c:'+r.batch+':'+r.ref}));
  if(q)xs=xs.filter(r=>(r.ref+r.zh+r.old+r.new+r.reason).toLowerCase().includes(q));}
 else{const fs=val('fs'),fsrc=val('fsrc');xs=D.questions.filter(x=>x.kind==tab&&(!fs||x.subtype==fs)&&(!fsrc||(fsrc.startsWith('re-review')==x.source.startsWith('agent:RV'))));
  xs=xs.map(x=>({...x,key:'q:'+x.id}));if(q)xs=xs.filter(x=>(x.id+x.title+x.text+JSON.stringify(x.lines)).toLowerCase().includes(q));}
 if(fv)xs=xs.filter(x=>fv=='reviewed'?!!(V[x.key]&&V[x.key].v):!(V[x.key]&&V[x.key].v));return xs}
function acts(key,opts){const v=V[key]||{};return '<div class="acts">'+opts.map(([k,l,c])=>'<button class="'+c+(v.v==k?' on':'')+'" data-k="'+key+'" data-v="'+k+'">'+l+'</button>').join('')+
 '<textarea data-n="'+key+'" placeholder="Note or the English you want (optional)">'+esc(v.n||'')+'</textarea></div>'}
function card(x){if(tab=='changes')return '<div class="card"><div class="top"><span class="ref">'+esc(x.ref)+'</span><span class="chip">'+esc(x.batch)+'</span><span class="chip">'+esc(x.category)+'</span><span class="mut">was '+esc(x.origin||'')+'</span></div>'+
 '<div class="zh" lang="zh">'+esc(x.zh)+'</div><div class="grid"><div class="old"><div class="lab">before</div>'+esc(x.old)+'</div><div class="new"><div class="lab">after</div>'+esc(x.new)+'</div></div>'+
 (x.reason?'<div class="why">'+esc(x.reason)+'</div>':'')+acts(x.key,[['ok','Keep the change','ok'],['revert','Revert','bad'],['other','Different English','mid']])+'</div>';
 const ls=x.lines.map(l=>'<div><span class="ref">'+esc(l.ref)+'</span> <span lang="zh">'+esc(l.zh||'')+'</span><br><span class="mut">EN:</span> '+esc(l.en||'')+'</div>').join('')+(x.more?'<div class="mut">+'+x.more+' more refs</div>':'');
 const opts=tab=='finding'?[['approve','Approve the proposed fix','ok'],['reject','Keep as the Chinese says','bad'],['other','Other (note)','mid']]:[['answered','Answered (note)','ok'],['defer','Later','mid']];
 return '<div class="card"><div class="top"><span class="ref">'+esc(x.id)+'</span><span class="chip">'+esc(x.subtype||'question')+'</span><span class="mut">'+esc(x.source)+' · '+esc(x.created)+'</span></div>'+
 (x.title?'<div><b>'+esc(x.title)+'</b></div>':'')+'<div class="text">'+esc(x.text)+'</div>'+(ls?'<div class="lines">'+ls+'</div>':'')+acts(x.key,opts)+'</div>'}
function draw(){const xs=items();const n=Math.max(1,Math.ceil(xs.length/PER));page=Math.min(page,n-1);
 document.getElementById('count').textContent=xs.length+' shown';document.getElementById('list').innerHTML=xs.slice(page*PER,page*PER+PER).map(card).join('')||'<p class="mut">Nothing matches.</p>';
 document.getElementById('pager').innerHTML=n>1?'<button class="btn" id="pv">Previous</button><span class="mut">page '+(page+1)+' of '+n+'</span><button class="btn" id="nx">Next</button>':'';
 const pv=document.getElementById('pv'),nx=document.getElementById('nx');if(pv)pv.onclick=()=>{if(page>0){page--;draw();scrollTo(0,0)}};if(nx)nx.onclick=()=>{if(page<n-1){page++;draw();scrollTo(0,0)}};prog()}
function prog(){const t=Object.values(V).filter(v=>v.v).length;document.getElementById('prog').textContent=t+' verdicts saved in this browser'}
document.getElementById('list').addEventListener('click',e=>{const b=e.target.closest('button[data-k]');if(!b)return;const k=b.dataset.k;V[k]=V[k]||{};V[k].v=V[k].v==b.dataset.v?'':b.dataset.v;save();draw()});
document.getElementById('list').addEventListener('change',e=>{const t=e.target.closest('textarea[data-n]');if(!t)return;const k=t.dataset.n;V[k]=V[k]||{};V[k].n=t.value;save()});
document.getElementById('exp').onclick=()=>{const out=Object.entries(V).filter(([k,v])=>v.v||v.n).map(([k,v])=>{const[t,...r]=k.split(':');return t=='c'?{type:'change',batch:r[0],ref:r.slice(1).join(':'),verdict:v.v||'',note:v.n||''}:{type:'question',id:r.join(':'),verdict:v.v||'',note:v.n||''}});
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));a.download='rereview-verdicts.json';a.click()};
document.getElementById('tabs').innerHTML=TABS.map(([k,l])=>'<button data-t="'+k+'"'+(k==tab?' class="on"':'')+'>'+l+'</button>').join('');
document.getElementById('tabs').onclick=e=>{const b=e.target.closest('button');if(!b)return;tab=b.dataset.t;page=0;document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x==b));filters();draw()};
filters();draw();
</script></body></html>"""


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
