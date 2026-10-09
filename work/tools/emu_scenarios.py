#!/usr/bin/env python3
"""emu_scenarios - data-driven emulator scenarios: one TOML file per check in work/tools/scenarios/, one runner.

A new behaviour check is a scenario file, not a Python module. A file says where the game starts (battery
save, teleport, flags, vars, clock, bag, party edits), what to do (the harness op language, emu_harness.OP_HELP,
plus a few table steps), what to record (observations: decoded party slots, RAM, flags, vars, position, clock,
bag, screen-crop digests, message pages, execution-hook captures, WildLog rows, Pokedex panels) and what the
records must be (expectations, per ROM language or on both). Every run (scenario x case x ROM) is its own child
process (one emulator per process; the machine-wide emulator cap applies). The runner writes one JSON result
per scenario and a summary, and exits 1 on a failed expectation, 2 on a schema error.

    <venv>/bin/python work/tools/emu_harness.py scenarios [--only id,...] [--lang cn|en|both] [--jobs 3]
        [--out DIR] [--rom-cn R] [--rom-en R] [--sav-dir D]        ('suite' is an alias)
    python3 work/tools/emu_scenarios.py validate [FILE ...]     schema check only (no emulator)

Format: see work/notes/emu_harness.md ('Scenario files') and the files in work/tools/scenarios/.

Parity is the default verdict (D-1002: the Chinese hack is the behaviour reference): every scenario runs on both
ROMs and every observation must be equal on cn and en, unless the scenario's [parity] table declares it as
differing (`differ`, optionally with per-ROM checks) or restricts the comparison to named fields (`fields`). A
scenario needs no hand-written expectations; those it has are judged in addition. The game's RNGs are pinned
(start.rng, default DEFAULT_RNG_SEED; start.rng_repin re-pins at declared code addresses), so runs repeat and
the two ROMs take the same random path.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import time
import tomllib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SCENARIO_DIR = TOOLS / "scenarios"
LANGS = ("cn", "en")
SETUP = "__setup__"


class ScenarioError(ValueError):
    """A scenario file that does not follow the format; the message names the file and the place."""


# ----------------------------------------------------------------------------- schema

TOP_KEYS = {"id", "description", "refs", "default", "timeout", "start", "setup", "hook", "steps", "expect",
            "case", "params", "parity"}
START_KEYS = {"save", "map", "x", "y", "height", "direction", "flags", "clear_flags", "vars", "clock",
              "pockets", "party", "rng", "rng_repin"}
CASE_START_WITH_SETUP = {"clock", "rng"}      # what a case may change when it starts from the [setup] savestate
CASE_KEYS = {"id", "description", "params", "start", "steps", "expect"}
HOOK_KEYS = {"name", "addr", "read", "sig", "max"}
EXPECT_OPS = ("equals", "in", "min", "max", "set", "all", "len", "contains", "approved", "baseline")
EXPECT_KEYS = {"obs", "lang", "note", *EXPECT_OPS}
OBSERVE_KINDS = ("party", "ram", "flag", "var", "position", "location", "clock", "bag", "crop", "message", "text_fit")
OBSERVE_KEYS = {"observe", "size", "fields", "screen_name", *OBSERVE_KINDS}
TABLE_OPS = {"encounters": {"op", "observe", "count", "walk", "span", "tiles", "max_steps", "shots"},
             "dexcapture": {"op", "observe", "first", "last"}}
PARTY_FIELDS = {"slot", "species", "item", "form", "moves", "pp", "ability"}
PARITY_KEYS = {"differ", "fields"}
DIFFER_KEYS = {"why", *LANGS}
REPIN_KEYS = {"addr", "sig", "note"}
REG_NAMES = {f"r{i}" for i in range(13)} | {"sp", "lr", "pc"}
HOOK_READ = re.compile(r"^(?:(u8|u16|u32)@)?(r\d{1,2}|sp|lr|pc)(?:\+(0x[0-9a-fA-F]+|\d+))?$")
DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")
PARAM = re.compile(r"\$\{(\w+)\}")


def _err(where, msg):
    raise ScenarioError(f"{where}: {msg}")


def _keys(where, table, allowed):
    if not isinstance(table, dict):
        _err(where, f"must be a table, got {type(table).__name__}")
    extra = sorted(set(table) - allowed)
    if extra:
        _err(where, f"unknown key(s) {', '.join(extra)} (allowed: {', '.join(sorted(allowed))})")


def _type(where, value, types, what):
    if isinstance(value, bool) and bool not in (types if isinstance(types, tuple) else (types,)):
        _err(where, f"must be {what}, got {value!r}")
    if not isinstance(value, types):
        _err(where, f"must be {what}, got {value!r}")


def _int_list(where, value):
    _type(where, value, list, "a list of integers")
    for v in value:
        _type(where, v, int, "a list of integers")


def substitute(obj, params):
    """${name} in strings -> params[name]. A string that is exactly '${name}' takes the parameter's own type,
    so `equals = "${form}"` compares with the integer. Unknown names raise KeyError."""
    if isinstance(obj, str):
        m = PARAM.fullmatch(obj)
        if m:
            return params[m.group(1)]
        return PARAM.sub(lambda m: str(params[m.group(1)]), obj)
    if isinstance(obj, list):
        return [substitute(x, params) for x in obj]
    if isinstance(obj, dict):
        return {k: substitute(v, params) for k, v in obj.items()}
    return obj


def check_start(where, start):
    _keys(where, start, START_KEYS)
    if "save" in start:
        _type(f"{where}.save", start["save"], str, "a battery save file name (in the saves folder)")
    tele = [k for k in ("map", "x", "y") if k in start]
    if tele and len(tele) != 3:
        _err(where, "a teleport needs all of map, x, y")
    for k in ("map", "x", "y", "height"):
        if k in start:
            _type(f"{where}.{k}", start[k], int, "an integer")
    if "direction" in start and start["direction"] not in DIRECTIONS:
        _err(f"{where}.direction", f"one of {', '.join(DIRECTIONS)}")
    for k in ("flags", "clear_flags"):
        if k in start:
            _int_list(f"{where}.{k}", start[k])
    if "vars" in start:
        _type(f"{where}.vars", start["vars"], dict, "a table {var id = value}")
        for k, v in start["vars"].items():
            try:
                int(k, 0)
            except ValueError:
                _err(f"{where}.vars", f"key {k!r} is not a var id (e.g. 16565 or 0x40B5)")
            _type(f"{where}.vars.{k}", v, int, "an integer")
    if "clock" in start:
        try:
            datetime.datetime.fromisoformat(start["clock"])
        except (TypeError, ValueError):
            _err(f"{where}.clock", f"not an ISO date-time: {start['clock']!r}")
    if "pockets" in start:
        import emu_harness as E
        _type(f"{where}.pockets", start["pockets"], dict, "a table {pocket = [[item, qty], ...]}")
        for name, items in start["pockets"].items():
            if name not in E.POCKETS:
                _err(f"{where}.pockets", f"unknown pocket {name!r} (one of {', '.join(E.POCKETS)})")
            _type(f"{where}.pockets.{name}", items, list, "a list of [item, qty]")
            for it in items:
                if not (isinstance(it, list) and len(it) == 2 and all(isinstance(v, int) for v in it)):
                    _err(f"{where}.pockets.{name}", f"entry {it!r} is not [item, qty]")
    if "rng" in start and not (start["rng"] is False or (isinstance(start["rng"], int) and
                                                       not isinstance(start["rng"], bool) and
                                                       0 <= start["rng"] <= 0xFFFFFFFF)):
        _err(f"{where}.rng", "a 32-bit seed (e.g. 0x5EED0001) or false (keep the game's own seed)")
    if "rng_repin" in start:
        if start.get("rng", True) is False:
            _err(f"{where}.rng_repin", "needs the RNG pinned (rng is false)")
        _type(f"{where}.rng_repin", start["rng_repin"], list, "a list of { addr, sig } tables")
        for i, rp in enumerate(start["rng_repin"]):
            w = f"{where}.rng_repin[{i}]"
            _keys(w, rp, REPIN_KEYS)
            _type(f"{w}.addr", rp.get("addr"), int, "an ARM9 code address (Thumb: even)")
            if "sig" in rp and not (isinstance(rp["sig"], str) and re.fullmatch(r"([0-9a-f]{2})+", rp["sig"])):
                _err(f"{w}.sig", "hex code bytes, e.g. 'd8f594fd'")
    for i, edit in enumerate(start.get("party", [])):
        w = f"{where}.party[{i}]"
        _keys(w, edit, PARTY_FIELDS)
        if "slot" not in edit or not isinstance(edit["slot"], int) or not 0 <= edit["slot"] < 6:
            _err(w, "needs slot = 0..5")


def check_step(where, step):
    """A step is an op string (emu_harness.parse_op), an observation table or a table op."""
    import emu_harness as E
    if isinstance(step, str):
        try:
            E.parse_op(step)
        except ValueError as e:
            _err(where, str(e))
        return
    if not isinstance(step, dict):
        _err(where, f"a step is an op string or a table, got {step!r}")
    if "op" in step:
        if step["op"] not in TABLE_OPS:
            _err(where, f"unknown table op {step['op']!r} (one of {', '.join(TABLE_OPS)})")
        _keys(where, step, TABLE_OPS[step["op"]])
        if step["op"] == "encounters":
            _type(f"{where}.count", step.get("count"), int, "an integer (wild Pokemon to log)")
            if "walk" in step and (not isinstance(step["walk"], list) or
                                   any(d not in DIRECTIONS for d in step["walk"])):
                _err(f"{where}.walk", f"a list of directions ({', '.join(DIRECTIONS)})")
            if "tiles" in step and (not isinstance(step["tiles"], list) or len(step["tiles"]) < 2 or any(
                    not (isinstance(t, list) and len(t) == 2) for t in step["tiles"])):
                _err(f"{where}.tiles", "a list of at least two [x, y] tiles")
        else:
            for k in ("first", "last"):
                _type(f"{where}.{k}", step.get(k), int, "a Pokedex number")
        if "observe" in step:
            _type(f"{where}.observe", step["observe"], str, "an observation name")
        return
    if "observe" not in step:
        _err(where, "a table step needs 'observe' (an observation) or 'op' (a table op)")
    _keys(where, step, OBSERVE_KEYS)
    _type(f"{where}.observe", step["observe"], str, "an observation name")
    kinds = [k for k in OBSERVE_KINDS if k in step]
    if len(kinds) != 1:
        _err(where, f"name exactly one observation kind ({', '.join(OBSERVE_KINDS)}), got {kinds or 'none'}")
    kind, v = kinds[0], step[kinds[0]]
    if kind == "party" and not (v == "@gen" or (isinstance(v, int) and 0 <= v < 6)):
        _err(f"{where}.party", "a party slot 0..5 or '@gen'")
    if kind in ("ram", "flag", "var"):
        _type(f"{where}.{kind}", v, int, "an integer address / id")
    if kind == "ram" and step.get("size", 4) not in (1, 2, 4):
        _err(f"{where}.size", "1, 2 or 4")
    if kind == "crop" and not (isinstance(v, list) and len(v) == 4 and all(isinstance(c, int) for c in v)
                               and v[0] < v[2] <= 256 and v[1] < v[3] <= 384):
        _err(f"{where}.crop", "a box [x0, y0, x1, y1] inside the 256x384 two-screen image")
    if kind in ("message", "text_fit") and not (isinstance(v, str) and re.fullmatch(r"\d+#\d+", v)):
        _err(f"{where}.{kind}", "'bank#id' of a027, e.g. '457#123'")
    if kind in ("position", "location", "clock", "bag") and v is not True:
        _err(f"{where}.{kind}", "must be true")


def check_expect(where, exp):
    _keys(where, exp, EXPECT_KEYS)
    _type(f"{where}.obs", exp.get("obs"), str, "an observation path (e.g. 'after_candy.species')")
    ops = [k for k in EXPECT_OPS if k in exp]
    if len(ops) != 1:
        _err(where, f"name exactly one check ({', '.join(EXPECT_OPS)}), got {ops or 'none'}")
    if exp.get("lang", "both") not in ("both", *LANGS):
        _err(f"{where}.lang", "both, cn or en")
    op, want = ops[0], exp[ops[0]]
    if op in ("in", "set", "approved") and not isinstance(want, list):
        _err(f"{where}.{op}", "must be a list")
    if op in ("min", "max", "len") and (isinstance(want, bool) or not isinstance(want, (int, float))):
        _err(f"{where}.{op}", "must be a number")
    if op == "baseline" and want is not True:
        _err(f"{where}.baseline", "must be true")


def check_hook(where, hook):
    _keys(where, hook, HOOK_KEYS)
    _type(f"{where}.name", hook.get("name"), str, "a name (the observation it fills)")
    _type(f"{where}.addr", hook.get("addr"), int, "an ARM9 address (e.g. 0x0203A7D6)")
    if not HOOK_READ.match(hook.get("read", "")):
        _err(f"{where}.read", "a register (r0..r12, sp, lr, pc), optionally read through as u8@r2 / u32@sp+8")
    if "sig" in hook and not re.fullmatch(r"([0-9a-f]{2})+", hook["sig"]):
        _err(f"{where}.sig", "hex code bytes, e.g. '10bd'")


def rng_seed(start):
    """The seed a run pins (start.rng, default emu_harness.DEFAULT_RNG_SEED), or None for rng = false."""
    import emu_harness as E
    rng = start.get("rng", E.DEFAULT_RNG_SEED)
    return None if rng is False else rng


def check_repin_addresses(where, start, hooks):
    """A re-pin hook must not sit on an address another hook uses: DeSmuME keeps one callback per address."""
    import emu_harness as E
    taken = {h.get("addr") for h in hooks} | set(E.RNG_SEED_SITES) | {
        E.WILD_FINALIZE, E.WILD_FINALIZE_SETFORM, E.WILD_FINALIZE_AFTER_SET, E.WILD_FINALIZE_RESTORE,
        E.WILD_FINALIZE_END, E.RTC_SYNC_DONE}
    addrs = [rp["addr"] for rp in start.get("rng_repin", [])]
    for a in addrs:
        if a in taken:
            _err(where, f"{a:#x} is already hooked (a [[hook]], the RNG seed sites or the wild-encounter log)")
    if len(set(addrs)) != len(addrs):
        _err(where, "duplicate address")


def _plain_path(where, path):
    if not isinstance(path, str) or not path or "*" in path or any(not p for p in path.split(".")):
        _err(where, f"{path!r} is not an observation name or a dotted path without '*'")


def check_parity(where, p):
    """[parity]: differ = {obs-or-path = 'why' | {why, cn = {check}, en = {check}}}, fields = {obs = [paths]}.
    Returns {differ: {path: why}, fields: {obs: [paths]}, expect: [the per-ROM checks as expectations]}."""
    _keys(where, p, PARITY_KEYS)
    differ, expect = {}, []
    if "differ" in p:
        _type(f"{where}.differ", p["differ"], dict, "a table {observation = 'why it differs'}")
        for path, spec in p["differ"].items():
            w = f"{where}.differ.{path}"
            _plain_path(w, path)
            if isinstance(spec, str):
                differ[path] = spec
                continue
            _keys(w, spec, DIFFER_KEYS)
            _type(f"{w}.why", spec.get("why"), str, "the reason the ROMs differ")
            differ[path] = spec["why"]
            for lang in LANGS:
                if lang not in spec:
                    continue
                chk = spec[lang]
                _keys(f"{w}.{lang}", chk, set(EXPECT_OPS) | {"path", "note"})
                if "path" in chk:
                    _plain_path(f"{w}.{lang}.path", chk["path"])
                exp = {"obs": path + (f".{chk['path']}" if "path" in chk else ""), "lang": lang,
                       **{k: v for k, v in chk.items() if k in EXPECT_OPS},
                       "note": chk.get("note", f"declared difference: {spec['why']}")}
                check_expect(f"{w}.{lang}", exp)
                expect.append(exp)
    fields = {}
    if "fields" in p:
        _type(f"{where}.fields", p["fields"], dict, "a table {observation = ['field.path', ...]}")
        for obs, paths in p["fields"].items():
            w = f"{where}.fields.{obs}"
            if "." in obs:
                _err(w, "the key is an observation name; the dotted paths go in the list")
            if not (isinstance(paths, list) and paths and all(isinstance(x, str) and x for x in paths)):
                _err(w, "a non-empty list of field paths (dotted, '*' maps over a list)")
            if obs in differ or any(d.startswith(obs + ".") for d in differ):
                _err(w, "an observation is either compared by fields or declared in differ, not both")
            fields[obs] = paths
    return {"differ": differ, "fields": fields, "expect": expect}


def load(path):
    """Load and validate one scenario file; returns the scenario dict with `cases` expanded (each case: id,
    start, steps, expect with the params substituted). Raises ScenarioError naming the file and the place."""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ScenarioError(f"{path.name}: not valid TOML: {e}") from None
    w = path.name
    _keys(w, raw, TOP_KEYS)
    if raw.get("id") != path.stem:
        _err(w, f"id must equal the file name ({path.stem!r}), got {raw.get('id')!r}")
    _type(f"{w}.description", raw.get("description"), str, "a one-line description")
    if "refs" in raw and not (isinstance(raw["refs"], list) and all(isinstance(r, str) for r in raw["refs"])):
        _err(f"{w}.refs", "a list of decision / fix ids (strings)")
    if "default" in raw:
        _type(f"{w}.default", raw["default"], bool, "true or false")
    if "timeout" in raw:
        _type(f"{w}.timeout", raw["timeout"], int, "seconds")
    for i, hook in enumerate(raw.get("hook", [])):
        check_hook(f"{w}.hook[{i}]", hook)
    names = [h["name"] for h in raw.get("hook", [])]
    if len(set(names)) != len(names):
        _err(f"{w}.hook", "hook names must be unique")
    parity_spec = check_parity(f"{w}.parity", raw.get("parity", {}))
    setup = raw.get("setup")
    if setup is not None:
        _keys(f"{w}.setup", setup, {"steps"})
    raw_cases = raw.get("case") or [{"id": "main"}]
    _type(f"{w}.case", raw_cases, list, "a list of tables")
    cases, seen = [], set()
    for i, c in enumerate(raw_cases):
        cw = f"{w}.case[{i}]"
        _keys(cw, c, CASE_KEYS)
        _type(f"{cw}.id", c.get("id"), str, "a case id")
        if c["id"] in seen or c["id"] == SETUP:
            _err(f"{cw}.id", f"duplicate or reserved id {c['id']!r}")
        seen.add(c["id"])
        cw = f"{w}.case[{c['id']}]"
        params = {**raw.get("params", {}), **c.get("params", {})}
        try:
            start = substitute({**raw.get("start", {}), **c.get("start", {})}, params)
            steps = substitute(c.get("steps", raw.get("steps", [])), params)
            expect = substitute(raw.get("expect", []) + c.get("expect", []) + parity_spec["expect"], params)
        except KeyError as e:
            _err(cw, f"unknown parameter ${{{e.args[0]}}}")
        if setup is not None and set(c.get("start", {})) - CASE_START_WITH_SETUP:
            _err(f"{cw}.start", "with [setup] the cases start from its savestate: only clock and rng may change")
        check_start(f"{cw}.start", start)
        check_repin_addresses(f"{cw}.start.rng_repin", start, raw.get("hook", []))
        _type(f"{cw}.steps", steps, list, "a list of steps")
        for j, s in enumerate(steps):
            check_step(f"{cw}.steps[{j}]", s)
        for j, e in enumerate(expect):
            check_expect(f"{cw}.expect[{j}]", e)
        cases.append({"id": c["id"], "description": c.get("description", ""), "params": params,
                      "start": start, "steps": steps, "expect": expect, "rng": rng_seed(start)})
    if setup is not None:
        for j, s in enumerate(setup.get("steps", [])):
            check_step(f"{w}.setup.steps[{j}]", s)
        check_start(f"{w}.start", raw.get("start", {}))
    return {"id": raw["id"], "file": str(path), "description": raw["description"], "refs": raw.get("refs", []),
            "default": raw.get("default", True), "timeout": raw.get("timeout", 900),
            "start": raw.get("start", {}), "setup": setup, "hooks": raw.get("hook", []),
            "parity": {"differ": parity_spec["differ"], "fields": parity_spec["fields"]}, "cases": cases}


def discover(folder=SCENARIO_DIR):
    return sorted(Path(folder).glob("*.toml"))


def load_all(folder=SCENARIO_DIR, only=None):
    """All scenario files (or the ids in `only`); every schema error of every file is collected first."""
    files = discover(folder)
    if only:
        known = {p.stem: p for p in files}
        missing = [i for i in only if i not in known]
        if missing:
            raise ScenarioError(f"unknown scenario id(s) {', '.join(missing)} (known: {', '.join(known)})")
        files = [known[i] for i in only]
    out, errors = [], []
    for p in files:
        try:
            out.append(load(p))
        except ScenarioError as e:
            errors.append(str(e))
    if errors:
        raise ScenarioError("\n".join(errors))
    return out if only else [s for s in out if s["default"]]


# ----------------------------------------------------------------------------- judging (pure)

_MISSING = object()


def get_path(obs, path):
    """'a.b.0.c' into nested dicts/lists; '*' maps over a list. Returns _MISSING when absent."""
    cur = [obs]
    many = False
    for part in path.split("."):
        nxt = []
        for c in cur:
            if part == "*":
                if not isinstance(c, list):
                    return _MISSING
                nxt.extend(c)
                many = True
            elif isinstance(c, dict) and part in c:
                nxt.append(c[part])
            elif isinstance(c, list) and part.lstrip("-").isdigit() and -len(c) <= int(part) < len(c):
                nxt.append(c[int(part)])
            else:
                return _MISSING
        cur = nxt
    return cur if many else cur[0]


def _norm(v):
    return json.loads(json.dumps(v))     # tuples -> lists, int keys -> str: compare as the JSON reads


def check_value(op, want, got):
    """(passed, note) for one expectation operator."""
    got, want = _norm(got), _norm(want)
    if op == "equals":
        return got == want, ""
    if op == "in":
        return got in want, ""
    if op in ("min", "max"):
        n = len(got) if isinstance(got, (list, dict, str)) else got
        if isinstance(n, bool) or not isinstance(n, (int, float)):
            return False, f"not a number: {got!r}"
        return (n >= want if op == "min" else n <= want), ""
    if op == "set":
        if not isinstance(got, list):
            return False, "not a list"
        return sorted(set(map(json.dumps, got))) == sorted(set(map(json.dumps, want))), ""
    if op == "all":
        if not isinstance(got, list) or not got:
            return False, "not a non-empty list"
        return all(g == want for g in got), ""
    if op == "len":
        return isinstance(got, (list, dict, str)) and len(got) == want, ""
    if op == "contains":
        return isinstance(got, (list, dict, str)) and want in got, ""
    if op == "approved":
        return got in want, "" if got in want else "digest not approved"
    raise ValueError(f"unknown check {op!r}")


def baseline_file(base_dir, scenario, case, lang, obs):
    safe = re.sub(r"[^\w.-]", "_", obs)
    return Path(base_dir) / scenario / f"{case}__{lang}__{safe}.json"


def judge(expect, observations, lang, scenario="", case="", base_dir=None):
    """Judge the expectations that apply to `lang` against one run's observations. Returns rows
    {obs, check, want, got, pass[, note]}. A 'baseline' check compares with the stored value of an earlier
    approved run (base_dir/<scenario>/<case>__<lang>__<obs>.json); a missing baseline is created and passes."""
    rows = []
    for e in expect:
        if e.get("lang", "both") not in ("both", lang):
            continue
        op = next(k for k in EXPECT_OPS if k in e)
        got = get_path(observations, e["obs"])
        row = {"obs": e["obs"], "check": op, "want": e[op]}
        if got is _MISSING:
            row.update(got=None, **{"pass": False}, note="observation missing")
        elif op == "baseline":
            bf = baseline_file(base_dir, scenario, case, lang, e["obs"])
            row["want"] = str(bf)
            if bf.exists():
                ok = _norm(got) == json.loads(bf.read_text())["value"]
                row.update(got="(same as baseline)" if ok else got, **{"pass": ok},
                           note="" if ok else "differs from the approved baseline")
            else:
                bf.parent.mkdir(parents=True, exist_ok=True)
                bf.write_text(json.dumps({"value": _norm(got), "created": datetime.datetime.now().isoformat(
                    timespec="seconds")}, indent=1))
                row.update(got="(stored)", **{"pass": True}, note="baseline created")
        else:
            ok, note = check_value(op, e[op], got)
            row.update(got=got, **{"pass": ok})
            if note:
                row["note"] = note
        if e.get("note"):
            row["why"] = e["note"]
        rows.append(row)
    return rows


def run_verdict(result, rows):
    """'error' / 'timeout' (the child failed), 'fail' (an expectation failed), 'pass', or 'observed' (no
    expectation applies to this ROM; the observations are still recorded)."""
    if result.get("verdict") in ("error", "timeout"):
        return result["verdict"]
    if not rows:
        return "observed"
    return "pass" if all(r["pass"] for r in rows) else "fail"


EQUAL, DECLARED, MISMATCH, UNAVAILABLE = "equal", "differs-declared", "MISMATCH", "unavailable"
_SHORT = 2000           # JSON characters above which a mismatch row keeps only the leaf differences


def leaf_diff(a, b, path="", limit=20):
    """[{path, cn, en}] for the leaves where a (cn) and b (en) differ; a list of another length or a value of
    another type is one leaf."""
    out = []

    def walk(x, y, p):
        if len(out) >= limit:
            return
        if isinstance(x, dict) and isinstance(y, dict):
            for k in sorted(set(x) | set(y), key=str):
                walk(x.get(k, "(missing)"), y.get(k, "(missing)"), f"{p}.{k}" if p else str(k))
        elif isinstance(x, list) and isinstance(y, list) and len(x) == len(y):
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, f"{p}.{i}" if p else str(i))
        elif x != y:
            out.append({"path": p, "cn": x, "en": y})
    walk(_norm(a), _norm(b), path)
    return out


def _drop_path(obj, path):
    """A copy of obj without the dotted path (dict keys / list indexes); obj itself is not changed."""
    obj = _norm(obj)
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.lstrip("-").isdigit() and -len(cur) <= int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return obj
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    elif isinstance(cur, list) and parts[-1].lstrip("-").isdigit() and -len(cur) <= int(parts[-1]) < len(cur):
        cur[int(parts[-1])] = "(not compared)"
    return obj


def _mismatch_row(case, obs, a, b, **extra):
    row = {"case": case, "obs": obs, "status": MISMATCH, **extra}
    a, b = (None if v is _MISSING else _norm(v) for v in (a, b))
    if len(json.dumps(a, ensure_ascii=False)) + len(json.dumps(b, ensure_ascii=False)) <= _SHORT:
        row.update(cn=a, en=b)
    row["diff"] = leaf_diff(a, b)
    return row


def compare_observation(case, obs, a, b, differ, fields):
    """Parity rows for one observation of one case: a = cn value, b = en value (_MISSING when absent)."""
    if obs in differ:
        return [{"case": case, "obs": obs, "status": DECLARED, "why": differ[obs],
                 "equal_anyway": _norm(None if a is _MISSING else a) == _norm(None if b is _MISSING else b)}]
    if obs in fields:
        bad = []
        for f in fields[obs]:
            u = _MISSING if a is _MISSING else get_path(a, f)
            v = _MISSING if b is _MISSING else get_path(b, f)
            if (u is _MISSING) != (v is _MISSING) or (u is not _MISSING and _norm(u) != _norm(v)):
                bad.append({"path": f, "cn": None if u is _MISSING else u, "en": None if v is _MISSING else v})
        if bad:
            return [{"case": case, "obs": obs, "status": MISMATCH, "fields": fields[obs], "diff": bad}]
        return [{"case": case, "obs": obs, "status": EQUAL, "fields": fields[obs]}]
    rows = []
    subs = sorted(d for d in differ if d.startswith(obs + "."))
    for d in subs:
        rest = d[len(obs) + 1:]
        u = _MISSING if a is _MISSING else get_path(a, rest)
        v = _MISSING if b is _MISSING else get_path(b, rest)
        rows.append({"case": case, "obs": d, "status": DECLARED, "why": differ[d],
                     "equal_anyway": _norm(None if u is _MISSING else u) == _norm(None if v is _MISSING else v)})
        a = a if a is _MISSING else _drop_path(a, rest)
        b = b if b is _MISSING else _drop_path(b, rest)
    if a is _MISSING or b is _MISSING or _norm(a) != _norm(b):
        rows.insert(0, _mismatch_row(case, obs, a, b, **({"not_compared": subs} if subs else {})))
    else:
        rows.insert(0, {"case": case, "obs": obs, "status": EQUAL, **({"not_compared": subs} if subs else {})})
    return rows


def parity(scn, runs, langs=LANGS):
    """The Chinese-vs-English verdict (D-1002). Per case and observation one row: 'equal', 'differs-declared'
    (listed in [parity] differ; its per-ROM checks are judged with the expectations), 'MISMATCH' (with both
    values or the differing leaves) or 'unavailable' (a run of the case failed; its verdict says why).
    Not judged when only one ROM ran."""
    p = scn.get("parity", {})
    differ, fields = p.get("differ", {}), p.get("fields", {})
    if set(langs) != set(LANGS):
        return {"judged": False, "note": "one ROM only: parity needs both", "rows": [], "counts": {}}
    rows = []
    for case in scn["cases"]:
        by = {r["lang"]: r for r in runs if r["case"] == case["id"]}
        if any(by.get(lang, {}).get("observations") is None for lang in LANGS):
            rows.append({"case": case["id"], "obs": "*", "status": UNAVAILABLE,
                         "note": "a run of this case has no observations (see its verdict)"})
            continue
        cn, en = by["cn"]["observations"], by["en"]["observations"]
        names = sorted(set(cn) | set(en) | {d.split(".")[0] for d in differ if d.split(".")[0] in cn or
                                            d.split(".")[0] in en})
        for obs in names:
            rows += compare_observation(case["id"], obs, cn.get(obs, _MISSING), en.get(obs, _MISSING), differ,
                                        fields)
    counts = {k: sum(r["status"] == k for r in rows) for k in (EQUAL, DECLARED, MISMATCH, UNAVAILABLE)}
    stale = sorted({r["obs"] for r in rows if r["status"] == DECLARED and r.get("equal_anyway")} -
                   {r["obs"] for r in rows if r["status"] == DECLARED and not r.get("equal_anyway")})
    out = {"judged": True, "counts": counts, "rows": sorted(rows, key=lambda r: r["status"] != MISMATCH),
           "declared": differ, "fields": fields}
    if stale:
        out["declared_but_equal"] = stale      # a declaration that may no longer be needed
    return out


def scenario_verdict(runs, par):
    if any(r["verdict"] not in ("pass", "observed") for r in runs):
        return "fail"
    return "fail" if par.get("counts", {}).get(MISMATCH) else "pass"


def _short(v, n=160):
    t = json.dumps(v, ensure_ascii=False)
    return t if len(t) <= n else t[:n] + "..."


# ----------------------------------------------------------------------------- child: one run in one emulator

def _hook_reader(spec):
    m = HOOK_READ.match(spec)
    width, reg, off = m.group(1), m.group(2), int(m.group(3) or "0", 0)

    def read(h):
        v = getattr(h.reg, reg) + off
        return {"u8": h.u8, "u16": h.u16, "u32": h.u32}[width](v) if width else v
    return read


def _crop_digest(img, box):
    return hashlib.sha256(img.convert("RGB").crop(tuple(box)).tobytes()).hexdigest()


def observe(h, step, tag):
    import emu_harness as E
    from PIL import Image
    name = step["observe"]
    if "party" in step:
        slot = h.generated_slot if step["party"] == "@gen" else step["party"]
        party = h.party()
        mon = dict(party[slot]) if slot < len(party) else None
        if mon is not None:
            mon["slot"] = slot
            if step.get("fields"):
                mon = {k: mon.get(k) for k in step["fields"]}
        return mon
    if "ram" in step:
        return {1: h.u8, 2: h.u16, 4: h.u32}[step.get("size", 4)](step["ram"])
    if "flag" in step:
        return int(h.get_flag(step["flag"]))
    if "var" in step:
        return h.get_var(step["var"])
    if "position" in step:
        return list(h.position())
    if "location" in step:
        return h.location()
    if "clock" in step:
        return h.clock()
    if "bag" in step:
        return {str(k): v for k, v in sorted(E.bag_items(h).items())}
    if "crop" in step:
        img = Image.open(h.screenshot(f"{step.get('screen_name', name)}_{tag}"))
        img.convert("RGB").crop(tuple(step["crop"])).save(h.out / f"{name}_{tag}_crop.png")
        return _crop_digest(img, step["crop"])
    if "message" in step:
        bank, msg = (int(v) for v in step["message"].split("#"))
        pages = h.show_message(bank, msg, name=f"{name}_{tag}")
        return {"pages": len(pages), "digests": [_crop_digest(Image.open(p), (8, 150, 232, 186)) for p in pages]}
    if "text_fit" in step:      # the field message window, judged by emu_textfit (EN: read back; CN: pixels)
        import emu_textfit
        return emu_textfit.observe(h, step["text_fit"], tag if tag in LANGS else "en")
    raise ValueError(f"no observation kind in {step}")


def table_op(h, step, tag):
    import emu_harness as E
    if step["op"] == "encounters":
        log = E.WildLog(h)
        n = E.pace_for_encounters(h, log, step["count"], walk=tuple(step.get("walk", ("LEFT", "RIGHT"))),
                                  span=step.get("span", 3), tiles=[tuple(t) for t in step.get("tiles", [])],
                                  max_steps=step.get("max_steps", 3000), shots=step.get("shots", 0), tag=tag)
        for addr in (E.WILD_FINALIZE, E.WILD_FINALIZE_SETFORM, E.WILD_FINALIZE_AFTER_SET, E.WILD_FINALIZE_RESTORE,
                     E.WILD_FINALIZE_END):
            h.on_exec(addr, None)
        return {"steps": n, "rows": log.rows, "summary": E.wild_summary(log.rows)}
    if step["op"] == "dexcapture":
        import emu_dex
        from PIL import Image
        emu_dex.open_dex_list(h)
        shots = Path(h.out) / f"dex_{tag}"
        done, errors = emu_dex.capture_entries(h, step["first"], step["last"], shots)
        return {"captured": done, "errors": errors,
                "digests": {p.stem: hashlib.sha256(Image.open(p).convert("RGB").tobytes()).hexdigest()
                            for p in sorted(shots.glob("*.png"))}}
    raise ValueError(f"unknown table op {step['op']!r}")


def run_steps(h, steps, tag, obs, shots):
    import emu_harness as E
    for step in steps:
        if isinstance(step, str):
            E.exec_op(h, *E.parse_op(step), tag=tag, shots=shots)
        elif "op" in step:
            obs[step.get("observe", step["op"])] = table_op(h, step, tag)
        else:
            obs[step["observe"]] = observe(h, step, tag)


def _save_edit(start):
    def edit(sf):
        for f in start.get("clear_flags", []):
            sf.set_flag(f, False)
        for name, items in start.get("pockets", {}).items():
            sf.set_pocket(name, [tuple(it) for it in items])
        for e in start.get("party", []):
            sf.edit_party_mon(e["slot"], **{k: v for k, v in e.items() if k != "slot"})
    return edit


def execute(scn, case_id, lang, rom, sav_dir, out, state_in=None, state_out=None, gen_slot=None):
    """Run one case (or the shared setup, case_id SETUP) on one ROM in this process. Returns the result dict:
    {case, lang, observations, screenshots, seconds, gen_slot, rng}. From a setup savestate, gen_slot is the
    party slot the setup's gen: op filled (what '@gen' means in the cases).

    RNG (start.rng, unless false): from a battery save the boot routine's seed is replaced by the pinned seed
    (power-on and Continue), and both RNGs are written again once the run stands in the field; from a setup
    savestate they are written when the case starts. Each start.rng_repin address re-pins the LCRNG every time
    the ARM9 executes it (the n-th time: emu_harness.repin_value(seed, n)). `rng` records what was done."""
    import emu_harness as E
    t0 = time.time()
    case = next(c for c in scn["cases"] if c["id"] == case_id) if case_id != SETUP else \
        {"id": SETUP, "start": scn["start"], "steps": scn["setup"]["steps"], "rng": rng_seed(scn["start"])}
    start = case["start"]
    seed = case["rng"]
    rng = {"seed": None if seed is None else hex(seed), "seeding": [], "start_state": None, "repins": 0,
           "repin_skipped": 0}
    clock = datetime.datetime.fromisoformat(start["clock"]) if "clock" in start else None
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    captured = {hk["name"]: [] for hk in scn["hooks"]} if case_id != SETUP else {}

    def repin(h, addr, sig):
        if sig and h.read(addr, len(sig) // 2).hex() != sig:
            rng["repin_skipped"] += 1           # another overlay at this address
            return
        rng["repins"] += 1
        h.w32(E.LCRNG_STATE, E.repin_value(seed, rng["repins"]))

    def install(h, boot):
        for hk in (scn["hooks"] if case_id != SETUP else []):
            read, rows, cap = _hook_reader(hk["read"]), captured[hk["name"]], hk.get("max", 1000)
            h.on_exec(hk["addr"], lambda h, read=read, rows=rows, cap=cap: len(rows) < cap and rows.append(read(h)))
        if seed is not None:
            if boot:
                E.pin_rng_seeding(h, seed, rng["seeding"])
            for rp in start.get("rng_repin", []):
                sig = rp.get("sig")
                h.on_exec(rp["addr"], lambda h, a=rp["addr"], s=sig: repin(h, a, s))

    def pin_now(h):
        if seed is not None:
            if state_in is None and not rng["seeding"]:
                raise RuntimeError("RNG pin: the boot routine's seeding was never seen (RNG_SEED_SITES)")
            rng["start_state"] = hex(E.write_rng(h, seed))

    def check_sigs(h):
        for hk in scn["hooks"]:
            if "sig" in hk and h.read(hk["addr"], len(hk["sig"]) // 2).hex() != hk["sig"]:
                raise RuntimeError(f"hook {hk['name']}: code at {hk['addr']:#x} is "
                                   f"{h.read(hk['addr'], len(hk['sig']) // 2).hex()}, expected {hk['sig']}")

    obs, shots, slot = {}, [], [gen_slot]
    if state_in:
        with E.Harness(rom, None, savestate=state_in, out=out, verbose=False) as h:
            if clock:
                h.set_clock(clock)
            if gen_slot is not None:
                h.generated_slot = gen_slot
            check_sigs(h)
            install(h, boot=False)
            pin_now(h)
            run_steps(h, case["steps"], lang, obs, shots)
    else:
        sav = Path(sav_dir) / start.get("save", "full_bag_6mons.sav")
        vars_ = {int(k, 0): v for k, v in start.get("vars", {}).items()}
        with E.start_at(start.get("map"), start.get("x"), start.get("y"), rom=rom, sav=sav,
                        flags=start.get("flags", []), vars=vars_, clock=clock, out=out, verbose=False,
                        hooks=lambda h: install(h, boot=True), edit=_save_edit(start),
                        height=start.get("height", 0), direction=start.get("direction", "DOWN")) as h:
            check_sigs(h)
            pin_now(h)
            run_steps(h, case["steps"], lang, obs, shots)
            slot[0] = getattr(h, "generated_slot", None)
            if state_out:
                h.save_state(state_out)
    obs.update(captured)
    return {"case": case_id, "lang": lang, "observations": obs, "screenshots": shots,
            "seconds": round(time.time() - t0, 1), "gen_slot": slot[0], "rng": rng}


def cmd_child(a):
    scn = load(a.file)
    absolute = [str(Path(p).resolve()) if p else None for p in (a.rom, a.sav_dir, a.out, a.state_in, a.state_out)]
    res = execute(scn, a.case, a.lang, *absolute[:3], *absolute[3:], a.gen_slot)    # the emulator runs elsewhere
    print("RESULT " + json.dumps(res), flush=True)
    return 0


def add_child_arguments(p):
    p.add_argument("--file", required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--lang", choices=LANGS, required=True)
    p.add_argument("--rom", required=True)
    p.add_argument("--sav-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--state-in")
    p.add_argument("--state-out")
    p.add_argument("--gen-slot", type=int)


# ----------------------------------------------------------------------------- parent: fan out, judge, report

def add_arguments(p):
    import emu_harness as E
    p.add_argument("--only", help="comma list of scenario ids (also runs files marked default = false)")
    p.add_argument("--lang", choices=("cn", "en", "both"), default="both")
    p.add_argument("--jobs", type=int, default=3, help="runs in parallel (each opens one emulator; live emulators "
                   "are capped machine-wide by EMU_HARNESS_MAX_EMULATORS, default 6)")
    p.add_argument("--out", help="new folder for this run (default work/build/harness/scenarios/run-<time>)")
    p.add_argument("--rom-cn", default=str(E.DEF_ROM_CN))
    p.add_argument("--rom-en", default=str(E.DEF_ROM_EN))
    p.add_argument("--sav-dir", default=str(E.DEF_SAVES), help="battery saves the scenarios' start.save names")
    p.add_argument("--baselines", default=str(E.DEF_OUT / "baselines" / "scenarios"),
                   help="approved values of 'baseline' expectations (outside git); delete a file to re-approve")
    p.add_argument("--dir", default=str(SCENARIO_DIR), help=argparse.SUPPRESS)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(a):
    """Load and validate every scenario, run each (scenario, case, ROM) in a child process, judge, report."""
    import concurrent.futures as cf

    import emu_harness as E
    only = [s for s in (a.only or "").split(",") if s]
    try:
        scns = load_all(a.dir, only or None)
    except ScenarioError as e:
        print(f"scenario schema error(s):\n{e}", file=sys.stderr)
        return 2
    langs = list(LANGS) if a.lang == "both" else [a.lang]
    roms = {"cn": a.rom_cn, "en": a.rom_en}
    for lang in langs:
        if not Path(roms[lang]).exists():
            print(f"ROM not found: {roms[lang]}", file=sys.stderr)
            return 2
    out = (Path(a.out) if a.out else E.DEF_OUT / "scenarios" / time.strftime("run-%Y%m%d-%H%M%S")).resolve()
    if (out / "summary.json").exists():
        print(f"{out} already holds a run; choose a new --out", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results = {s["id"]: [] for s in scns}

    def child(scn, case_id, lang, state_in=None, state_out=None, gen_slot=None):
        d = out / scn["id"] / lang / case_id
        args = ["scenario-run", "--file", scn["file"], "--case", case_id, "--lang", lang, "--rom", roms[lang],
                "--sav-dir", a.sav_dir, "--out", d]
        if state_in:
            args += ["--state-in", state_in]
        if state_out:
            args += ["--state-out", state_out]
        if gen_slot is not None:
            args += ["--gen-slot", gen_slot]
        try:
            r = E.run_child(args, timeout=scn["timeout"])
        except Exception as e:      # a crash or a timeout is the run's verdict, with the message
            r = {"case": case_id, "lang": lang, "observations": None, **E.child_error(e)}
        return scn, case_id, lang, r

    with cf.ThreadPoolExecutor(max(1, a.jobs)) as ex:
        pending = set()
        for scn in scns:
            for lang in langs:
                if scn["setup"] is not None:
                    st = out / scn["id"] / lang / "setup.dst"
                    pending.add(ex.submit(child, scn, SETUP, lang, None, str(st)))
                else:
                    pending |= {ex.submit(child, scn, c["id"], lang) for c in scn["cases"]}
        while pending:
            done, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            for f in done:
                scn, case_id, lang, r = f.result()
                if case_id == SETUP:
                    if r.get("observations") is None:      # setup failed: every case of this ROM fails with it
                        for c in scn["cases"]:
                            results[scn["id"]].append({**r, "case": c["id"], "expectations": [],
                                                       "error": "setup: " + r.get("error", "")})
                        print(json.dumps({"scenario": scn["id"], "case": SETUP, "rom": lang,
                                          "verdict": r.get("verdict")}), flush=True)
                    else:
                        st = str(out / scn["id"] / lang / "setup.dst")
                        pending |= {ex.submit(child, scn, c["id"], lang, st, None, r.get("gen_slot"))
                                    for c in scn["cases"]}
                    continue
                case = next(c for c in scn["cases"] if c["id"] == case_id)
                rows = [] if r.get("observations") is None else judge(
                    case["expect"], r["observations"], lang, scn["id"], case_id, a.baselines)
                r["expectations"] = rows
                r["verdict"] = run_verdict(r, rows)
                results[scn["id"]].append(r)
                print(json.dumps({"scenario": scn["id"], "case": case_id, "rom": lang, "verdict": r["verdict"],
                                  "seconds": r.get("seconds")}), flush=True)

    rom_ids = {lang: {"path": str(roms[lang]), "sha256": _sha256(roms[lang])} for lang in langs}
    summary = summarise(scns, results, langs, rom_ids, out, round(time.time() - t0, 1))
    print_summary(summary)
    return 0 if summary["pass"] else 1


def summarise(scns, results, langs, rom_ids, out, seconds):
    """Write <scenario>.json per scenario and summary.json; return the summary. The summary lists the parity
    mismatches first, then the failed expectations, then the runs that errored, then one row per scenario."""
    summary = {"pass": True, "mismatches": [], "failed_expectations": [], "errors": [], "roms": rom_ids,
               "langs": langs, "out": str(out), "seconds": seconds, "scenarios": []}
    for scn in scns:
        order = [c["id"] for c in scn["cases"]]
        runs = sorted(results[scn["id"]], key=lambda r: (order.index(r["case"]), r["lang"]))
        par = parity(scn, runs, langs)
        verdict = scenario_verdict(runs, par)
        doc = {"scenario": scn["id"], "description": scn["description"], "refs": scn["refs"], "file": scn["file"],
               "verdict": verdict, "roms": rom_ids, "parity": par, "runs": runs}
        (Path(out) / f"{scn['id']}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        summary["mismatches"] += [{"scenario": scn["id"], **r} for r in par["rows"] if r["status"] == MISMATCH]
        for r in runs:
            summary["failed_expectations"] += [
                {"scenario": scn["id"], "case": r["case"], "lang": r["lang"], **e}
                for e in r.get("expectations", []) if not e["pass"]]
            if r["verdict"] in ("error", "timeout"):
                summary["errors"].append({"scenario": scn["id"], "case": r["case"], "lang": r["lang"],
                                          "verdict": r["verdict"], "error": r.get("error", "")})
        summary["scenarios"].append({"scenario": scn["id"], "verdict": verdict, "refs": scn["refs"],
                                     "parity": par.get("counts") or par.get("note"),
                                     "declared_but_equal": par.get("declared_but_equal", []),
                                     "runs": {f"{r['case']}/{r['lang']}": r["verdict"] for r in runs}})
    summary["pass"] = all(s["verdict"] == "pass" for s in summary["scenarios"])
    (Path(out) / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))
    return summary


def print_summary(summary):
    for m in summary["mismatches"]:
        detail = (f"cn={_short(m['cn'])} en={_short(m['en'])}" if "cn" in m else
                  "; ".join(f"{d['path']}: cn={_short(d['cn'], 60)} en={_short(d['en'], 60)}" for d in m["diff"][:5]))
        print(f"MISMATCH {m['scenario']}/{m['case']} {m['obs']}: {detail}")
    for e in summary["failed_expectations"]:
        print(f"FAILED   {e['scenario']}/{e['case']}/{e['lang']} {e['obs']} {e['check']} {_short(e['want'], 60)}: "
              f"got {_short(e['got'], 80)}" + (f" ({e['note']})" if e.get("note") else ""))
    for e in summary["errors"]:
        print(f"{e['verdict'].upper():8} {e['scenario']}/{e['case']}/{e['lang']}: {_short(e['error'], 200)}")
    for s in summary["scenarios"]:
        par = s["parity"]
        par = (f"parity {par.get(EQUAL, 0)} equal, {par.get(DECLARED, 0)} declared, {par.get(MISMATCH, 0)} "
               f"mismatch" + (f", {par[UNAVAILABLE]} unavailable" if par.get(UNAVAILABLE) else "")
               if isinstance(par, dict) else f"parity: {par}")
        bad = [k for k, v in s["runs"].items() if v not in ("pass", "observed")]
        print(f"{s['verdict'].upper():5} {s['scenario']}  {par}" + (f"  failed runs: {', '.join(bad)}" if bad else "")
              + (f"  declared but equal: {', '.join(s['declared_but_equal'])}" if s["declared_but_equal"] else ""))
    print(json.dumps({"pass": summary["pass"], "mismatches": len(summary["mismatches"]),
                      "failed_expectations": len(summary["failed_expectations"]), "seconds": summary["seconds"],
                      "summary": str(Path(summary["out"]) / "summary.json")}))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="schema-check scenario files (default: all in work/tools/scenarios)")
    v.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    files = a.files or discover()
    bad = 0
    for f in files:
        try:
            scn = load(f)
            print(f"ok    {Path(f).name}: {len(scn['cases'])} case(s)")
        except ScenarioError as e:
            bad += 1
            print(f"ERROR {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.path.insert(0, str(TOOLS))
    sys.exit(main())
