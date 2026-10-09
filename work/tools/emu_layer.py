#!/usr/bin/env python3
"""emu_layer - the whole emulator layer in one run, one report, one approve step (suite v2 step 5).

    <venv>/bin/python work/tools/emu_harness.py layer --rom EN.nds [--rom-report build_report.json]
        [--parts fixes,scenarios,textfit,freeze] [--jobs 3] [--since REF] [--out-root DIR]
    <venv>/bin/python work/tools/emu_harness.py approve --from <report dir | run dir>
        (--crops K[,K] | --baselines KEY[,KEY] | --all-pending) --by "<who, date>"
    python3 work/tools/check.py --full --emu [--emu-only PARTS] [--emu-since REF]    (the layer after the build)

Parts (all by default; they run at the same time and share one emulator pool: every child gets
EMU_HARNESS_MAX_EMULATORS = --jobs, so at most --jobs emulators of this run are alive, within the machine-wide
slot cap):
  fixes      emu_harness.py fixes: one scenario per fix on the build and on a control build without it, graphics
             crops against the approved digests (emu_fixes_crops.json); a crop not approved yet is 'pending'
  scenarios  emu_harness.py scenarios: every scenario file on both ROMs, CN/EN parity, expectations, baselines
             against the committed digests (scenario_baselines.json); a baseline not approved yet is 'pending'
  textfit    emu_harness.py textfit --since REF --pairs: the strings changed since REF (default: the latest tag,
             `git describe --tags --abbrev=0`, else v1.0.0-rc5) rendered in their window on the build
  freeze     emu_harness.py hang on melonDS (it emulates the ARM9 protection unit, so the hack's NULL reads
             freeze as on hardware): the reproducers not covered by `fixes` (FREEZE_CASES; `fixes` covers
             texture-bounds, reflection and msgload with DeSmuME hooks). Each case must reproduce the freeze on the
             untouched Chinese ROM and must not freeze on the build.

Output, a new folder per run: <out-root>/runs/<stamp>/<part>/ (each tool's own report, screenshots, crops) and
<out-root>/report/<stamp>/report.json + report.html (local, no external resources; the images are referenced by
relative paths into runs/, never copied). Rows: failures first, then pending approvals, then passes. Exit 1 on
any failure; pending approvals do not fail the run.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
REPO = WORK.parent
sys.path.insert(0, str(TOOLS))

PARTS = ("fixes", "scenarios", "textfit", "freeze")
STATUS_ORDER = {"fail": 0, "pending": 1, "pass": 2}
MAX_IMAGES = 6                      # per ROM column of one row in the HTML
FIXES_SAVES = ("full_bag_6mons.sav", "route1_path_2mons.sav", "market.sav")   # what `fixes` imports

# The freeze reproducers of emu_hang.py that `fixes` does not run. On melonDS the hack's NULL read is a data abort
# (the game hangs in the abort handler); `fixes` proves the same two fixes with DeSmuME execution hooks
# (texture-bounds, reflection), so these add the observed freeze itself. Deterministic: two processes abort at
# the same frame with the same registers (work/notes/melonds_backend.md). The save is found by its SHA-256.
FREEZE_CASES = {
    "rocket_hq": {"fix": "overworld-texture-frame-bounds", "refs": ["D-2043"],
                  "what": "Rocket HQ B1F, east from (13,4) to the camera ambush (player A's save)"},
    "follower_viridian": {"fix": "bulbasaur-reflection-boundary", "refs": ["D-2270"],
                          "what": "Bulbasaur following along the Viridian City pond (player B's save, teleported)"},
}
FREEZE_SAVE_DIR = "rocket-repro-20261008"     # next to the default save folder: the 2026-10-08 reproductions


class LayerError(ValueError):
    pass


class ApproveError(ValueError):
    """An approval that cannot be recorded: nothing was written."""


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _short(v, n=300):
    t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    return t if len(t) <= n else t[:n] + "..."


def _row(part, status, rid, title, detail="", images=None, approve=None, **extra):
    """One report row. images: [{label, cn: [paths], en: [paths]}] (CN | EN side by side) or
    [{label, paths: [...]}] (one column)."""
    row = {"part": part, "status": status, "id": rid, "title": title, "detail": detail}
    if images:
        row["images"] = images
    if approve:
        row["approve"] = approve
    row.update(extra)
    return row


def _existing(paths):
    return [str(p) for p in paths if p and Path(p).is_file()]


# ============================================================================ adapters: a part's run -> rows

def part_fixes(run_dir, seconds=None):
    """Rows of an `emu_harness.py fixes` run (fixes_report.json)."""
    import emu_fixes as F
    run_dir = Path(run_dir)
    src = run_dir / "fixes_report.json"
    if not src.is_file():
        return _missing_part("fixes", run_dir, seconds)
    rep = _load(src)
    obs = rep.get("observations", {})
    rows = []
    for r in rep["fixes"]:
        sc, fx = r["scenario"], r["fix"]
        status = "fail" if not r["pass"] else ("pending" if r.get("pending_approval") else "pass")
        crop = F.CROP_CHECKS.get((sc, fx))
        images, approve = None, None
        if crop:
            key, shot_key = crop

            def crop_png(label, key=key, shot_key=shot_key, sc=sc):
                shot = (obs.get(f"{sc}/{label}") or {}).get(shot_key) or {}
                p = shot.get("screenshot") if isinstance(shot, dict) else None
                return Path(p).with_name(f"{Path(p).stem}_{key}_crop.png") if p else None
            images = [{"label": f"crop {key}: Chinese ROM | build", "cn": _existing([crop_png("cn")]),
                       "en": _existing([crop_png("fixed")])},
                      {"label": f"control (build without {fx})", "paths": _existing([crop_png(f'no-{fx}')])}]
            if status == "pending":
                ev = r["fixed_rom"].get("evidence", {})
                approve = {"kind": "crop", "key": key, "digest": ev.get("digest"),
                           "chinese_digest": ev.get("chinese_rom_digest"), "fix": fx, "scenario": sc,
                           "source": str(src), "rom": rep.get("inputs", {}).get("rom"),
                           "evidence": _existing([crop_png("fixed"), crop_png("cn")])}
        fixed, control = r.get("fixed_rom", {}), r.get("control", {})
        detail = f"build: {fixed.get('state')} (expected fixed), control: {control.get('state')} (expected original)"
        if status == "fail":
            detail += "; evidence: " + _short({"build": fixed.get("evidence"), "control": control.get("evidence"),
                                                **({"pair": r["pair"]} if "pair" in r else {})}, 1200)
        rows.append(_row("fixes", status, f"{fx} ({sc})", f"fix {fx}, scenario {sc}", detail, images, approve))
    counts = _counts(rows)
    return {"part": "fixes", "pass": bool(rep.get("pass")), "counts": counts, "run_dir": str(run_dir),
            "report": str(src), "seconds": seconds if seconds is not None else rep.get("seconds"),
            "note": f"no scenario: {', '.join(sorted(rep.get('uncovered', {})))}", "rows": rows}


def _case_images(run_dir, scenario, case, lang, obs=None):
    """PNGs of one scenario run: the observation's crop when it has one, else every PNG of the run folder."""
    d = Path(run_dir) / scenario / lang / case
    if obs:
        crop = d / f"{obs.split('.')[0]}_{lang}_crop.png"
        if crop.is_file():
            return [str(crop)]
    return [str(p) for p in sorted(d.rglob("*.png"))] if d.is_dir() else []


def part_scenarios(run_dir, seconds=None):
    """Rows of an `emu_harness.py scenarios` run (summary.json and <scenario>.json)."""
    run_dir = Path(run_dir)
    src = run_dir / "summary.json"
    if not src.is_file():
        return _missing_part("scenarios", run_dir, seconds)
    s = _load(src)
    rows = []

    def pair(scn, case, obs=None):
        return [{"label": f"{scn}/{case}: Chinese ROM | English build", "cn": _case_images(run_dir, scn, case, "cn", obs),
                 "en": _case_images(run_dir, scn, case, "en", obs)}]
    for m in s.get("mismatches", []):
        diff = m.get("diff") or []
        detail = "; ".join(f"{d['path'] or '(value)'}: cn={_short(d['cn'], 80)} en={_short(d['en'], 80)}"
                           for d in diff[:8]) or f"cn={_short(m.get('cn'))} en={_short(m.get('en'))}"
        rows.append(_row("scenarios", "fail", f"{m['scenario']}/{m['case']} {m['obs']}",
                         f"parity MISMATCH: {m['scenario']}/{m['case']} {m['obs']}", detail,
                         pair(m["scenario"], m["case"], m["obs"])))
    for e in s.get("failed_expectations", []):
        rows.append(_row("scenarios", "fail", f"{e['scenario']}/{e['case']}/{e['lang']} {e['obs']}",
                         f"expectation failed: {e['scenario']}/{e['case']} on {e['lang']}: {e['obs']} {e['check']}",
                         f"want {_short(e.get('want'), 200)}, got {_short(e.get('got'), 200)}"
                         + (f" ({e['note']})" if e.get("note") else ""), pair(e["scenario"], e["case"], e["obs"])))
    for e in s.get("errors", []):
        rows.append(_row("scenarios", "fail", f"{e['scenario']}/{e['case']}/{e['lang']}",
                         f"run {e['verdict']}: {e['scenario']}/{e['case']} on {e['lang']}", _short(e.get("error"), 1500)))
    for e in s.get("pending_approval", []):
        doc = run_dir / f"{e['scenario']}.json"
        approve = {"kind": "baseline", "key": e["key"], "digest": e.get("digest"),
                   "approved_digest": e.get("approved_digest"), "scenario": e["scenario"], "case": e["case"],
                   "lang": e["lang"], "obs": e["obs"], "source": str(doc), "rom": s.get("roms", {}).get(e["lang"]),
                   "evidence": _case_images(run_dir, e["scenario"], e["case"], e["lang"], e["obs"])}
        detail = e.get("note", "")
        if e.get("diff"):
            detail += "; changed: " + "; ".join(f"{d['path']}: approved {_short(d['cn'], 60)} now {_short(d['en'], 60)}"
                                                for d in e["diff"][:8])
        rows.append(_row("scenarios", "pending", e["key"], f"baseline {e['key']} needs approval", detail,
                         pair(e["scenario"], e["case"], e["obs"]), approve))
    for sc in s.get("scenarios", []):
        if sc["verdict"] == "pass":
            par = sc.get("parity")
            par = (", ".join(f"{v} {k}" for k, v in par.items()) if isinstance(par, dict) else str(par))
            rows.append(_row("scenarios", "pass", sc["scenario"], f"scenario {sc['scenario']}",
                             f"parity: {par}; runs: " + ", ".join(f"{k} {v}" for k, v in sc["runs"].items())))
        elif not any(r["status"] == "fail" and r["id"].startswith(sc["scenario"] + "/") for r in rows):
            rows.append(_row("scenarios", "fail", sc["scenario"], f"scenario {sc['scenario']}: {sc['verdict']}",
                             _short(sc.get("runs"))))
    return {"part": "scenarios", "pass": bool(s.get("pass")), "counts": _counts(rows), "run_dir": str(run_dir),
            "report": str(src), "seconds": seconds if seconds is not None else s.get("seconds"), "rows": rows}


def part_textfit(run_dir, seconds=None):
    """Rows of an `emu_harness.py textfit` run (summary.json): one row per failing or erroring string, one row
    for all the strings that fit."""
    run_dir = Path(run_dir)
    src = run_dir / "summary.json"
    if not src.is_file():
        return _missing_part("textfit", run_dir, seconds)
    s = _load(src)
    rows = []
    for f in s.get("failures", []):
        reasons = "; ".join(f"{r['code']}" + (f" view {r['view']}" if r.get("view") else "")
                            + (f" line {r['row']}" if r.get("row") else "") + f": {r['detail']}" for r in f["reasons"])
        images = ([{"label": "Chinese ROM | English build (the same string, the same window)",
                    "paths": _existing([f.get("pair")])}] if f.get("pair") and Path(f["pair"]).is_file() else
                  [{"label": "English build", "paths": _existing([f.get("crop")])}])
        rows.append(_row("textfit", "fail", f["ref"], f"{f['ref']} [{f['window']}]", reasons, images,
                         codes=sorted({r["code"] for r in f["reasons"]})))
    for e in s.get("errors", []):
        rows.append(_row("textfit", "fail", e["ref"], f"{e['ref']} [{e['window']}]: error", _short(e.get("error"), 800)))
    c = s.get("counts", {})
    if c.get("pass"):
        rows.append(_row("textfit", "pass", "strings that fit", f"{c['pass']} strings fit",
                         f"{c.get('rendered', 0)} rendered of {c.get('strings', 0)} ({s.get('selection')})"))
    unsupported = ", ".join(f"{k} {v['count']}" for k, v in s.get("unsupported", {}).items())
    return {"part": "textfit", "pass": bool(s.get("pass")), "counts": _counts(rows), "run_dir": str(run_dir),
            "report": str(src), "seconds": seconds if seconds is not None else s.get("seconds"),
            "note": f"{s.get('selection')}: {c.get('strings', 0)} strings, {c.get('rendered', 0)} rendered, "
                    f"{c.get('pass', 0)} fit, {c.get('fail', 0)} fail, {c.get('error', 0)} errors; not rendered "
                    f"(no window for their type): {unsupported or 'none'}", "rows": rows}


def part_freeze(run_dir, seconds=None):
    """Rows of the freeze part (freeze.json, written by run_freeze)."""
    run_dir = Path(run_dir)
    src = run_dir / "freeze.json"
    if not src.is_file():
        return _missing_part("freeze", run_dir, seconds)
    rep = _load(src)
    rows = []
    for c in rep["cases"]:
        b, o = c.get("build") or {}, c.get("cn") or {}
        detail = (f"build: {_hang_line(b)} (must not freeze); untouched Chinese ROM: {_hang_line(o)} (must freeze: "
                  f"the reproducer still reproduces)")
        images = [{"label": f"{c['case']}: after the walk, Chinese ROM | build",
                   "cn": _existing([o.get("shot")]), "en": _existing([b.get("shot")])}]
        rows.append(_row("freeze", "pass" if c["pass"] else "fail", c["case"],
                         f"{c['case']} ({c['fix']}; {', '.join(c['refs'])}): {c['what']}", detail, images))
    return {"part": "freeze", "pass": bool(rep.get("pass")), "counts": _counts(rows), "run_dir": str(run_dir),
            "report": str(src), "seconds": seconds if seconds is not None else rep.get("seconds"),
            "note": "melonDS 1.1 (ARM9 protection unit): a NULL read freezes as on hardware", "rows": rows}


def _hang_line(r):
    if r.get("error"):
        return f"error: {_short(r['error'], 300)}"
    s = f"{'OK' if r.get('ok') else 'FAIL'}, hung={r.get('hung')}, goal reached={r.get('reached_goal')}"
    if r.get("fault_pc"):
        s += f", data abort at {r['fault_pc']}"
    if r.get("problems"):
        s += " - " + "; ".join(r["problems"])
    return s


def _missing_part(part, run_dir, seconds):
    log = Path(run_dir).with_suffix(".log")
    tail = ""
    if log.is_file():
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-12:])
    rows = [_row(part, "fail", part, f"{part}: no report", f"{run_dir} has no report (the tool failed; log {log})"
                 + (f":\n{tail}" if tail else ""))]
    return {"part": part, "pass": False, "counts": _counts(rows), "run_dir": str(run_dir), "seconds": seconds,
            "rows": rows}


def _counts(rows):
    return {k: sum(r["status"] == k for r in rows) for k in STATUS_ORDER}


# ============================================================================ report

def build_report(parts, meta=None):
    """The report dict: verdict, per part {pass, counts, seconds, ...}, then every row (failures, then pending
    approvals, then passes; within a status in part order). A part that failed without a failing row gets one."""
    for p in parts:
        if not p["pass"] and not any(r["status"] == "fail" for r in p["rows"]):
            p["rows"].insert(0, _row(p["part"], "fail", p["part"], f"{p['part']} failed",
                                     f"the tool reported a failure without a failing row; see {p.get('report')}"))
            p["counts"] = _counts(p["rows"])
    rows = [r for p in parts for r in p["rows"]]
    rows.sort(key=lambda r: (STATUS_ORDER[r["status"]], PARTS.index(r["part"]) if r["part"] in PARTS else 99))
    ok = all(p["pass"] for p in parts)
    pending = [r for r in rows if r["status"] == "pending"]
    return {"schema": 1, "verdict": "PASS" if ok else "FAIL", "pass": ok, "pending_approvals": len(pending),
            "meta": meta or {},
            "parts": [{k: v for k, v in p.items() if k != "rows"} for p in parts],
            "rows": rows}


def exit_code(report):
    """0 when every part passed (pending approvals do not fail the run), else 1."""
    return 0 if report["pass"] else 1


def approve_command(report_dir, rows=None, python=None):
    """The exact `approve` commands for the pending rows: one per row and one for all of them."""
    py = python or sys.executable
    base = f'{py} work/tools/emu_harness.py approve --from {report_dir}'
    cmds = []
    for r in rows or []:
        ap = r.get("approve") or {}
        flag = {"crop": "--crops", "baseline": "--baselines"}.get(ap.get("kind"))
        if flag:
            cmds.append(f'{base} {flag} {ap["key"]} --by "<who, date>"')
    if len(cmds) > 1:
        cmds.append(f'{base} --all-pending --by "<who, date>"')
    return cmds


def write_report(report, report_dir):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    pend = [r for r in report["rows"] if r["status"] == "pending"]
    report["approve_commands"] = approve_command(report_dir.resolve(), pend)
    (report_dir / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str) + "\n",
                                            encoding="utf-8")
    (report_dir / "report.html").write_text(render_html(report, report_dir), encoding="utf-8")
    return report_dir / "report.json", report_dir / "report.html"


CSS = """
:root{--bg:#fff;--fg:#1d1d1f;--mut:#666;--line:#ddd;--fail:#b3261e;--failbg:#fdecea;--pend:#8a5a00;
--pendbg:#fff4dc;--pass:#1e6b34;--passbg:#e8f5ec;--code:#f4f4f4}
@media (prefers-color-scheme: dark){:root{--bg:#161616;--fg:#eee;--mut:#aaa;--line:#333;--fail:#ff8a80;
--failbg:#3a1d1b;--pend:#ffcc66;--pendbg:#3a2f14;--pass:#7fd49a;--passbg:#16301f;--code:#222}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0 auto;
max-width:1200px;padding:16px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:18px;margin:28px 0 8px;border-bottom:1px solid var(--line)}
.mut{color:var(--mut)}table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);
padding:4px 8px;text-align:left;vertical-align:top}
.v{display:inline-block;padding:2px 10px;border-radius:4px;font-weight:600}
.fail{color:var(--fail);background:var(--failbg)}.pending{color:var(--pend);background:var(--pendbg)}
.pass{color:var(--pass);background:var(--passbg)}
.row{border:1px solid var(--line);border-radius:6px;padding:8px 12px;margin:8px 0}
.row h3{font-size:15px;margin:0 0 4px}.detail{white-space:pre-wrap;word-break:break-word}
.pair{display:flex;gap:12px;flex-wrap:wrap;margin-top:6px}.col{flex:1 1 300px;min-width:0}
.col b{display:block;font-size:12px;color:var(--mut)}
img{max-width:100%;image-rendering:pixelated;border:1px solid var(--line);margin:2px 0}
code,pre{background:var(--code);border-radius:4px;padding:1px 4px;font-size:12px}
pre{padding:8px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
"""


def render_html(report, report_dir):
    """The report as one offline HTML page: summary, failures with their evidence (CN | EN side by side),
    pending approvals with the exact commands, passes collapsed. Images are relative links into runs/."""
    report_dir = Path(report_dir)
    e = html.escape

    def rel(p):
        try:
            return os.path.relpath(Path(p).resolve(), report_dir.resolve())
        except ValueError:
            return str(p)

    def imgs(paths):
        paths = list(paths or [])
        out = "".join(f'<a href="{e(rel(p))}"><img src="{e(rel(p))}" alt="{e(Path(p).name)}" loading="lazy"></a>'
                      for p in paths[:MAX_IMAGES])
        if len(paths) > MAX_IMAGES:
            out += (f'<div class="mut">{len(paths) - MAX_IMAGES} more in '
                    f'<a href="{e(rel(Path(paths[0]).parent))}">{e(rel(Path(paths[0]).parent))}</a></div>')
        return out or '<div class="mut">(no image saved)</div>'

    def row_html(r):
        parts = [f'<div class="row"><h3><span class="v {r["status"]}">{e(r["status"].upper())}</span> '
                 f'<span class="mut">{e(r["part"])}</span> {e(r["title"])}</h3>']
        if r.get("detail"):
            parts.append(f'<div class="detail">{e(r["detail"])}</div>')
        for im in r.get("images") or []:
            if "cn" in im or "en" in im:
                parts.append(f'<div class="mut">{e(im["label"])}</div><div class="pair">'
                             f'<div class="col"><b>Chinese ROM (CN)</b>{imgs(im.get("cn"))}</div>'
                             f'<div class="col"><b>English build (EN)</b>{imgs(im.get("en"))}</div></div>')
            else:
                parts.append(f'<div class="mut">{e(im["label"])}</div><div class="pair"><div class="col">'
                             f'{imgs(im.get("paths"))}</div></div>')
        ap = r.get("approve")
        if ap:
            parts.append(f'<div class="mut">{e(ap["kind"])} <code>{e(ap["key"])}</code>: digest '
                         f'<code>{e(str(ap.get("digest")))}</code>'
                         + (f', approved now <code>{e(str(ap.get("approved_digest")))}</code>'
                            if ap.get("approved_digest") else "") + '</div>')
        parts.append("</div>")
        return "".join(parts)

    m = report.get("meta", {})
    rows = report["rows"]
    fails = [r for r in rows if r["status"] == "fail"]
    pend = [r for r in rows if r["status"] == "pending"]
    passes = [r for r in rows if r["status"] == "pass"]
    h = ["<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
         "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
         f"<title>Emulator layer report</title><style>{CSS}</style></head><body>",
         f'<h1>Emulator layer: <span class="v {"pass" if report["pass"] else "fail"}">{e(report["verdict"])}</span>'
         + (f' <span class="v pending">{len(pend)} pending approval</span>' if pend else "") + "</h1>",
         f'<div class="mut">{e(m.get("started", ""))} · {e(str(m.get("seconds", "?")))} s · ROM '
         f'<code>{e(str(m.get("rom", "")))}</code> · CN <code>{e(str(m.get("rom_cn", "")))}</code> · '
         f'jobs {e(str(m.get("jobs", "")))} · text-fit since {e(str(m.get("since", "")))}</div>',
         "<h2>Summary</h2><table><tr><th>part</th><th>result</th><th>fail</th><th>pending</th><th>pass</th>"
         "<th>time</th><th>run</th></tr>"]
    for p in report["parts"]:
        c = p.get("counts", {})
        h.append(f'<tr><td>{e(p["part"])}</td><td><span class="v {"pass" if p["pass"] else "fail"}">'
                 f'{"PASS" if p["pass"] else "FAIL"}</span></td><td>{c.get("fail", 0)}</td><td>{c.get("pending", 0)}'
                 f'</td><td>{c.get("pass", 0)}</td><td>{e(str(round(p["seconds"]) if p.get("seconds") else "?"))} s'
                 f'</td><td><a href="{e(rel(p["run_dir"]))}">{e(Path(p["run_dir"]).name)}</a>'
                 + (f'<div class="mut">{e(p["note"])}</div>' if p.get("note") else "") + "</td></tr>")
    h.append("</table>")
    h.append(f"<h2>Failures ({len(fails)})</h2>" + ("".join(row_html(r) for r in fails)
                                                     or '<p class="mut">none</p>'))
    h.append(f"<h2>Pending approvals ({len(pend)})</h2>")
    if pend:
        h.append('<p>These do not fail the run. Look at the evidence below; to approve, run (with your name and '
                 'the date):</p><pre>' + e("\n".join(report.get("approve_commands") or
                                                      approve_command(report_dir, pend))) + "</pre>")
        h.append("".join(row_html(r) for r in pend))
    else:
        h.append('<p class="mut">none</p>')
    h.append(f"<details><summary><h2 style=\"display:inline\">Passes ({len(passes)})</h2></summary>"
             + "".join(row_html(r) for r in passes) + "</details>")
    h.append("</body></html>")
    return "\n".join(h)


def print_summary(report, report_dir):
    """The console summary: verdict, per part counts, the failures and the pending approvals, the report path."""
    print(f"emulator layer: {report['verdict']} in {report['meta'].get('seconds', '?')} s"
          + (f"; {report['pending_approvals']} pending approval" if report["pending_approvals"] else ""))
    for p in report["parts"]:
        c = p.get("counts", {})
        print(f"  {p['part']:9s} {'PASS' if p['pass'] else 'FAIL'}  {c.get('fail', 0)} fail, {c.get('pending', 0)} "
              f"pending, {c.get('pass', 0)} pass  ({round(p['seconds']) if p.get('seconds') else '?'} s)"
              + (f"  {_short(p['note'], 160)}" if p.get("note") else ""))
    for r in report["rows"]:
        if r["status"] == "fail":
            print(f"  FAIL    {r['part']}: {r['title']}: {_short(r['detail'], 160)}")
    for r in report["rows"]:
        if r["status"] == "pending":
            print(f"  PENDING {r['part']}: {r['title']}")
    if report["pending_approvals"]:
        print(f"  approve after looking at the evidence: {report.get('approve_commands', [''])[-1]}")
    print(f"  report: {Path(report_dir) / 'report.html'}")


# ============================================================================ running the parts

def find_melonds():
    """The melonDS shim: $MELONDS_SHIM, this checkout's work/build/melonds, else the main checkout's (a worktree
    shares the repository's .git; the library is a git-ignored build output)."""
    import melonds
    if os.environ.get("MELONDS_SHIM") or melonds.available():
        return str(melonds.default_library())
    r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                       capture_output=True, text=True)
    if r.returncode == 0:
        lib = Path(r.stdout.strip()).parent / "work" / "build" / "melonds" / melonds.LIB_NAME
        if lib.is_file():
            return str(lib)
    return None


_SAVE_HASHES: dict = {}


def find_save(sha256, dirs):
    """The first *.sav in `dirs` (not recursive) whose SHA-256 is sha256, else None."""
    _cache = _SAVE_HASHES
    for d in dirs:
        for p in sorted(Path(d).glob("*.sav")) if Path(d).is_dir() else []:
            if p.stat().st_size > (1 << 20):
                continue
            key = (str(p), p.stat().st_mtime, p.stat().st_size)
            if key not in _cache:
                _cache[key] = _sha256(p)
            if _cache[key] == sha256:
                return p
    return None


def _hang(rom, sav, case, expect, out, env, log):
    cmd = [sys.executable, str(TOOLS / "emu_harness.py"), "hang", "--case", case, "--rom", str(Path(rom).resolve()),
           "--sav", str(Path(sav).resolve()), "--expect", expect, "--out", str(Path(out).resolve())]
    with open(log, "a", encoding="utf-8") as f:
        f.write("$ " + " ".join(cmd) + "\n")
        f.flush()
        r = subprocess.run(cmd, cwd=REPO, env=env, stdout=f, stderr=subprocess.STDOUT)
    reps = sorted(Path(out).glob("*/report.json"))
    if not reps:
        return {"error": f"hang wrote no report (exit {r.returncode}; log {log})", "ok": False}
    rep = _load(reps[-1])
    shot = reps[-1].parent / "after_walk.png"
    return {"ok": bool(rep.get("ok")) and r.returncode == 0, "hung": rep.get("hung"),
            "reached_goal": rep.get("reached_goal"), "problems": rep.get("problems"),
            "fault_pc": (rep.get("abort") or {}).get("fault_pc"), "report": str(reps[-1]),
            "shot": str(shot) if shot.is_file() else None}


def run_freeze(out, rom, rom_cn, save_dirs, jobs, env, cases=None):
    """Every FREEZE_CASES case on the build (expect pass) and on the untouched Chinese ROM (expect hang), on
    melonDS; writes out/freeze.json. A missing save or melonDS library fails the case (never a silent skip)."""
    import emu_hang
    from concurrent.futures import ThreadPoolExecutor
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    lib = find_melonds()
    env = dict(env, EMU_HARNESS_EMULATOR="melonds", **({"MELONDS_SHIM": lib} if lib else {}))
    log = out.with_suffix(".log")
    rows, jobs_ = [], []
    for case in cases or FREEZE_CASES:
        meta = FREEZE_CASES[case]
        row = {"case": case, **meta, "pass": False}
        sav = find_save(emu_hang.CASES[case]["sav_sha256"], save_dirs)
        if lib is None:
            row["build"] = row["cn"] = {"error": "the melonDS shim is not built (python3 work/tools/melonds_shim/"
                                                 "build.py, or $MELONDS_SHIM)"}
        elif sav is None:
            row["build"] = row["cn"] = {"error": f"no save with SHA-256 {emu_hang.CASES[case]['sav_sha256']} in "
                                                 f"{', '.join(map(str, save_dirs))} (--freeze-saves)"}
        else:
            row["sav"] = str(sav)
            jobs_ += [(row, "build", rom, "pass"), (row, "cn", rom_cn, "hang")]
        rows.append(row)

    def go(job):
        row, label, r, expect = job
        row[label] = _hang(r, row["sav"], row["case"], expect, out / f"{row['case']}_{label}", env, log)
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        list(ex.map(go, jobs_))
    for row in rows:
        row["pass"] = bool(row.get("build", {}).get("ok") and row.get("cn", {}).get("ok"))
    rep = {"pass": all(r["pass"] for r in rows), "seconds": round(time.time() - t0, 1), "melonds": lib,
           "rom": str(rom), "rom_cn": str(rom_cn), "cases": rows}
    (out / "freeze.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return rep


ADAPTERS = {"fixes": part_fixes, "scenarios": part_scenarios, "textfit": part_textfit, "freeze": part_freeze}


def part_command(part, a, out):
    """The emu_harness.py command line of a part (freeze runs in this process)."""
    h = [sys.executable, str(TOOLS / "emu_harness.py")]
    if part == "fixes":
        cmd = h + ["fixes", "--rom", a.rom, "--controls", a.controls, "--build-controls", "--jobs", a.jobs,
                   "--sav-dir", a.sav_dir, "--rom-cn", a.rom_cn, "--out", out]
        if a.rom_report:
            cmd += ["--rom-report", a.rom_report]
        if a.armips:
            cmd += ["--armips", a.armips]
        return cmd
    if part == "scenarios":
        return h + ["scenarios", "--rom-en", a.rom, "--rom-cn", a.rom_cn, "--sav-dir", a.sav_dir, "--jobs", a.jobs,
                    "--out", out]
    if part == "textfit":
        return h + ["textfit", "--since", a.since, "--rom-en", a.rom, "--rom-cn", a.rom_cn, "--sav",
                    str(Path(a.sav_dir) / "full_bag_6mons.sav"), "--jobs", a.jobs, "--pairs", "--out", out]
    raise ValueError(part)


def parse_parts(value):
    parts = [p.strip() for p in (value or ",".join(PARTS)).split(",") if p.strip()]
    bad = [p for p in parts if p not in PARTS]
    if bad or not parts:
        raise LayerError(f"unknown part(s) {', '.join(bad) or '(none)'}; parts: {', '.join(PARTS)}")
    return [p for p in PARTS if p in parts]


def pool_env(jobs):
    """The children's environment: this run's emulators share one pool of `jobs` slots of the machine-wide cap."""
    import emu_harness as E
    return dict(os.environ, EMU_HARNESS_MAX_EMULATORS=str(max(1, min(jobs, E.MAX_EMULATORS))))


def run(a):
    """Run the selected parts at the same time on one emulator pool, then write the report. Exit 1 on any
    failure (pending approvals do not fail)."""
    import emu_textfit
    parts = parse_parts(a.parts)
    for p in (a.rom, a.rom_cn):
        if not Path(p).is_file():
            raise LayerError(f"ROM not found: {p}")
    a.rom, a.rom_cn = str(Path(a.rom).resolve()), str(Path(a.rom_cn).resolve())
    a.since = a.since or emu_textfit.latest_release_tag()
    a.jobs = max(1, min(int(a.jobs), 3))
    root = Path(a.out_root).resolve()
    stamp = a.stamp or time.strftime("%Y%m%d-%H%M%S")
    runs, report_dir = root / "runs" / stamp, root / "report" / stamp
    if runs.exists() or report_dir.exists():
        raise LayerError(f"{runs} or {report_dir} exists; every run gets new folders")
    runs.mkdir(parents=True)
    a.controls = str(Path(a.controls).resolve()) if a.controls else str(root / "controls")
    env = pool_env(a.jobs)
    save_dirs = [Path(d) for d in (a.freeze_saves.split(",") if a.freeze_saves else
                                   [a.sav_dir, str(Path(a.sav_dir).parent / FREEZE_SAVE_DIR)])]
    t0 = time.time()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"emulator layer {stamp}: {', '.join(parts)}; {a.jobs} emulators at a time; text-fit since {a.since}; "
          f"runs in {runs}", flush=True)
    results, lock = {}, threading.Lock()

    def go(part):
        p0 = time.time()
        out = runs / part
        if part == "freeze":
            try:
                run_freeze(out, a.rom, a.rom_cn, save_dirs, a.jobs, env)
            except Exception as ex:          # noqa: BLE001 - reported as the part's failure
                (runs / "freeze.log").write_text(f"{type(ex).__name__}: {ex}\n", encoding="utf-8")
        else:
            cmd = [str(x) for x in part_command(part, a, out)]
            with open(runs / f"{part}.log", "w", encoding="utf-8") as f:
                f.write("$ " + " ".join(cmd) + "\n")
                f.flush()
                subprocess.run(cmd, cwd=REPO, env=dict(env, **({"EMU_HARNESS_EMULATOR": "desmume"})),
                               stdout=f, stderr=subprocess.STDOUT)
        res = ADAPTERS[part](out, round(time.time() - p0, 1))
        with lock:
            results[part] = res
            c = res["counts"]
            print(f"  {part} done in {time.time() - p0:.0f} s: {'PASS' if res['pass'] else 'FAIL'} ({c['fail']} "
                  f"fail, {c['pending']} pending, {c['pass']} pass)", flush=True)
    threads = [threading.Thread(target=go, args=(p,), name=f"layer-{p}") for p in parts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    meta = {"stamp": stamp, "started": started, "seconds": round(time.time() - t0, 1), "rom": a.rom,
            "rom_cn": a.rom_cn, "rom_report": a.rom_report, "jobs": a.jobs, "since": a.since, "parts": parts,
            "runs": str(runs), "sav_dir": a.sav_dir, "freeze_saves": [str(d) for d in save_dirs]}
    report = build_report([results[p] for p in parts], meta)
    write_report(report, report_dir)
    print_summary(report, report_dir)
    return exit_code(report)


def cmd_run(a):
    try:
        return run(a)
    except LayerError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2


def add_arguments(p):
    import emu_harness as E
    p.add_argument("--rom", default=str(E.DEF_ROM_EN), help="the English build to test")
    p.add_argument("--rom-report", help="its build_report.json (what each fix control must equal minus its fix)")
    p.add_argument("--rom-cn", default=str(E.DEF_ROM_CN), help="the untouched Chinese ROM")
    p.add_argument("--parts", default=",".join(PARTS), help=f"comma list of {', '.join(PARTS)} (default all)")
    p.add_argument("--jobs", type=int, default=3, help="emulators of this run alive at once, all parts together "
                                                       "(at most 3; within EMU_HARNESS_MAX_EMULATORS)")
    p.add_argument("--sav-dir", default=str(E.DEF_SAVES), help="battery saves (read only): " + ", ".join(FIXES_SAVES))
    p.add_argument("--freeze-saves", help="comma list of folders searched for the freeze cases' saves by SHA-256 "
                                          f"(default: --sav-dir and <its parent>/{FREEZE_SAVE_DIR})")
    p.add_argument("--since", help="text-fit: strings changed since this git ref (default: the latest tag)")
    p.add_argument("--controls", help="fix control ROMs (default <out-root>/controls; reused when they match)")
    p.add_argument("--armips", help="armips for the control builds")
    p.add_argument("--out-root", default=str(E.DEF_OUT / "layer"),
                   help="runs/<stamp>/ and report/<stamp>/ are created here")
    p.add_argument("--stamp", help=argparse.SUPPRESS)


# ============================================================================ approve

def _rows_from(from_dir):
    """(rows, source) of a unified report folder (report.json), a fixes run (fixes_report.json) or a scenarios run
    (summary.json)."""
    d = Path(from_dir)
    if (d / "report.json").is_file():
        return _load(d / "report.json")["rows"], d / "report.json"
    if (d / "fixes_report.json").is_file():
        return part_fixes(d)["rows"], d / "fixes_report.json"
    if (d / "summary.json").is_file() and "scenarios" in _load(d / "summary.json"):
        return part_scenarios(d)["rows"], d / "summary.json"
    raise ApproveError(f"{d} holds no report.json, fixes_report.json or scenarios summary.json")


_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def check_evidence(ap, crops, baselines, rom_hash=_sha256):
    """Why the pending row `ap` (its `approve` block) cannot be approved now ([] when it can): the digest must be
    in the report and equal what its run recorded, the evidence images must still exist, the committed state must
    be what the run judged against, and the ROM at the recorded path must still be the one that was run."""
    import emu_fixes as F
    import emu_scenarios as S
    what = f"{ap.get('kind')} {ap.get('key')}"
    digest = ap.get("digest")
    if not isinstance(digest, str) or not _HEX64.match(digest):
        return [f"{what}: evidence missing: the report has no digest for it"]
    src = Path(ap.get("source") or "")
    if not src.is_file():
        return [f"{what}: evidence missing: {src} (the run's own record) is gone"]
    probs = []
    gone = [p for p in ap.get("evidence") or [] if not Path(p).is_file()]
    if not ap.get("evidence") or gone:
        probs.append(f"{what}: evidence missing: no image to look at" if not ap.get("evidence") else
                     f"{what}: evidence missing: {', '.join(gone)}")
    if ap["kind"] == "crop":
        rep = _load(src)
        row = next((r for r in rep.get("fixes", []) if F.CROP_CHECKS.get((r["scenario"], r["fix"]), ("",))[0]
                    == ap["key"]), None)
        got = row and row.get("fixed_rom", {}).get("evidence", {}).get("digest")
        if not row or not row.get("pass") or not row.get("pending_approval"):
            probs.append(f"{what}: stale: {src} has no passing row with this crop pending")
        elif got != digest:
            probs.append(f"{what}: stale: the report says {digest[:12]}, the run recorded {str(got)[:12]}")
        if ap["key"] not in crops.get("pending", {}):
            probs.append(f"{what}: stale: not pending in emu_fixes_crops.json any more"
                         + (" (already approved)" if ap["key"] in crops.get("approved", {}) else ""))
    elif ap["kind"] == "baseline":
        doc = _load(src)
        run = next((r for r in doc.get("runs", []) if r["case"] == ap["case"] and r["lang"] == ap["lang"]), None)
        value = S.get_path(run["observations"], ap["obs"]) if run and run.get("observations") else S._MISSING
        if value is S._MISSING:
            probs.append(f"{what}: evidence missing: {src} has no {ap['obs']} for {ap['case']}/{ap['lang']}")
        elif S.value_digest(value) != digest:
            probs.append(f"{what}: stale: the report says {digest[:12]}, the run recorded "
                         f"{S.value_digest(value)[:12]}")
        now = (baselines.get("approved", {}).get(ap["key"]) or {}).get("digest")
        if now == digest:
            probs.append(f"{what}: already approved with this digest")
        elif now != ap.get("approved_digest"):
            probs.append(f"{what}: stale: the approved digest changed since the run ({str(ap.get('approved_digest'))[:12]}"
                         f" then, {str(now)[:12]} now): run again")
    else:
        probs.append(f"{what}: unknown kind")
    rom = ap.get("rom") or {}
    if not rom.get("path") or not Path(rom["path"]).is_file():
        probs.append(f"{what}: stale: the ROM of the run ({rom.get('path')}) is gone; run again")
    elif rom.get("sha256") and rom_hash(rom["path"]) != rom["sha256"]:
        probs.append(f"{what}: stale: {rom['path']} changed since the run (rebuilt?); run again")
    return probs


def approve(from_dir, crops=(), baselines=(), all_pending=False, by="", crops_path=None, baselines_path=None,
            values_dir=None, rom_hash=_sha256):
    """Record the user's approval of pending rows of a report (or run) folder: crops into emu_fixes_crops.json
    (pending -> approved), scenario baselines into scenario_baselines.json (digest, who, when, run). Refuses -
    and writes nothing - when an item is not pending there, or its evidence is missing or stale
    (check_evidence). Returns the records written: [(kind, key, digest, file)]."""
    import emu_fixes as F
    import emu_scenarios as S
    if not by.strip():
        raise ApproveError("--by: who approved and when, e.g. 'Simon, 2026-10-09'")
    rows, src = _rows_from(from_dir)
    pending = {(r["approve"]["kind"], r["approve"]["key"]): r["approve"] for r in rows
               if r["status"] == "pending" and r.get("approve")}
    wanted = list(pending) if all_pending else [("crop", k) for k in crops] + [("baseline", k) for k in baselines]
    if not wanted:
        raise ApproveError(f"nothing to approve: {src} has {len(pending)} pending item(s)"
                           + (": " + ", ".join(f"{k} {v}" for k, v in pending) if pending else ""))
    crops_path = Path(crops_path or F.CROP_DIGESTS)
    baselines_path = Path(baselines_path or S.APPROVALS)
    crop_data, base_data = F.load_crop_digests(crops_path), S.load_approvals(baselines_path)
    probs, plan = [], []
    hashes = {}

    def cached_hash(p):
        if p not in hashes:
            hashes[p] = rom_hash(p)
        return hashes[p]
    for kind, key in wanted:
        ap = pending.get((kind, key))
        if ap is None:
            probs.append(f"{kind} {key}: not pending in {src} (pending: "
                         f"{', '.join(f'{k} {v}' for k, v in pending) or 'none'})")
            continue
        p = check_evidence(ap, crop_data, base_data, cached_hash)
        probs += p
        if not p:
            plan.append(ap)
    if probs:
        raise ApproveError("nothing recorded:\n" + "\n".join(probs))
    stamp = time.strftime("%Y-%m-%d %H:%M")
    done = []
    run_name = str(Path(from_dir).resolve())
    for ap in plan:
        if ap["kind"] == "crop":
            crop_data["approved"][ap["key"]] = {
                "digest": ap["digest"], "approved_by": by,
                "images": f"{run_name} (local, git-ignored): " + ", ".join(Path(p).name for p in ap["evidence"])}
            del crop_data["pending"][ap["key"]]
            done.append(("crop", ap["key"], ap["digest"], crops_path))
        else:
            base_data["approved"][ap["key"]] = {"digest": ap["digest"], "approved_by": by, "recorded": stamp,
                                                "run": run_name, "rom_sha256": (ap.get("rom") or {}).get("sha256")}
            done.append(("baseline", ap["key"], ap["digest"], baselines_path))
            if values_dir:                  # the value itself, outside git: the changed leaves of a later run
                doc = _load(ap["source"])
                run = next(r for r in doc["runs"] if r["case"] == ap["case"] and r["lang"] == ap["lang"])
                bf = S.baseline_file(values_dir, ap["scenario"], ap["case"], ap["lang"], ap["obs"])
                bf.parent.mkdir(parents=True, exist_ok=True)
                bf.write_text(json.dumps({"value": S._norm(S.get_path(run["observations"], ap["obs"])),
                                          "digest": ap["digest"], "approved_by": by}, indent=1))
    if any(k == "crop" for k, *_ in done):
        _write_json(crops_path, crop_data)
    if any(k == "baseline" for k, *_ in done):
        base_data["_doc"] = S.APPROVALS_DOC
        base_data["approved"] = dict(sorted(base_data["approved"].items()))
        _write_json(baselines_path, {"_doc": base_data["_doc"], "approved": base_data["approved"]})
    return done


def _write_json(path, data):
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def cmd_approve(a):
    import emu_harness as E
    split = (lambda v: [x for x in (v or "").split(",") if x.strip()])
    try:
        done = approve(a.run, split(a.crops), split(a.baselines), a.all_pending, a.by,
                       values_dir=E.DEF_OUT / "baselines" / "scenarios")
    except ApproveError as ex:
        print(f"refused: {ex}", file=sys.stderr)
        return 1
    for kind, key, digest, path in done:
        try:
            shown = Path(path).resolve().relative_to(REPO)
        except ValueError:
            shown = path
        print(f"recorded {kind} {key}: approved digest {digest} by {a.by!r} in {shown}")
    print("commit the JSON change with the reason (what the user looked at)")
    return 0


def add_approve_arguments(p):
    p.add_argument("--from", dest="run", required=True,
                   help="a report folder (report.json of `layer` / check.py --emu) or a fixes or scenarios run folder")
    p.add_argument("--crops", help="comma list of pending fix crops (emu_fixes_crops.json)")
    p.add_argument("--baselines", help="comma list of pending scenario baselines, <scenario>/<case>/<lang>/<obs>")
    p.add_argument("--all-pending", action="store_true", help="every pending item of the report")
    p.add_argument("--by", required=True, help="who approved and when, e.g. 'Simon, 2026-10-09'")
