#!/usr/bin/env python3
"""check - one entry point for the patch toolchain's checks.

    python3 work/tools/check.py [--fast]       registry + asm lint, FIXES.md current, ruff, unit tests (no armips)
    python3 work/tools/check.py --full         also: asmpatch.py check, the disassembly snapshots, the USA
                                               claims, the unit tests with armips (GOLDEN), a full build
                                               compared with work/patches/expected.toml
    python3 work/tools/check.py --staged       the fast check on the staged files (the pre-commit hook)
    python3 work/tools/check.py --staged --registry-only
                                               only the registry step (the hook, for decision-register commits)
    python3 work/tools/check.py --full --strict-release
                                               also fail when the text, ROM or xdelta hash moved (a release)
    python3 work/tools/check.py --full --update-expected
                                               record the full build's hashes in work/patches/expected.toml

Fast (the default, also the pre-commit hook; about 6 s) needs neither armips nor a ROM:
  registry   fixes.py check: fix.toml schema, regions, overlaps, `.open` lines, `.string` = en, and the asm
             lint (header, .area around every write, a guard before every area's first write, every area
             inside fix.toml's regions or appended under expect_end with a [[grow]], line length);
  fixes-md   work/patches/FIXES.md equals `fixes.py docs`;
  ruff       `ruff check` with the repo's ruff.toml, by the version pinned in work/tools/requirements-dev.txt
             (skipped with a note when ruff is not installed; --full requires it);
  tests      every work/tools/test_*.py, with armips hidden (the armips tests skip; tests that read the
             Chinese ROM run when it is there and skip when it is not).
Full adds (and fails when armips v0.11.0, the two ROMs or xdelta3 are missing):
  asmpatch   asmpatch.py check: every enabled armips fix assembled against the Chinese ROM;
  listings   every armips fix assembled alone and disassembled (asmlisting.py, capstone pinned in
             requirements-dev.txt): each work/patches/<id>/<id>.listing must equal it (a stale snapshot fails,
             with the command that regenerates it);
  us-refs    every [[us_ref]] claim checked against the USA ROM (usref.py; skipped with a note without it);
  tests      the unit tests again with armips: the per-binary GOLDEN SHA-1s of test_asmpatch.py, which do not
             depend on the translation text;
  build      build.py into --work-dir (default work/build/check), then its hashes against
             work/patches/expected.toml (see EXPECTED_HELP below): nontext_sha1 must match; the text, ROM and
             xdelta hashes are reported, and fail the step only with --strict-release.

Exit status 0 only when no step failed. Each step prints PASS / FAIL / SKIP with its time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
REPO = WORK.parent
sys.path.insert(0, str(TOOLS))

EXPECTED = WORK / "patches" / "expected.toml"
REQUIREMENTS_DEV = TOOLS / "requirements-dev.txt"
DEFAULT_WORK_DIR = WORK / "build" / "check"
NO_ARMIPS = "/nonexistent/armips-hidden-by-check.py"     # $ARMIPS for the fast tests: armips is not found
TEXT_NARCS = ("a/0/2/7", "battle/string/battle_string.narc")
EXPECTED_HELP = """\
work/patches/expected.toml records four SHA-1s of the default full build (`build.py`, every enabled fix):
  nontext_sha1  every part of the ROM except the two message NARCs (arm9, arm7, overlay tables, banner and
                every other file): what the fixes, graphics and code produce. It does not depend on the
                message banks, but it does hold the English of the hardcoded strings: outfit-chooser-strings
                writes its [[string]] en into overlay 58, so changing that English moves it too;
  text_sha1     the two message NARCs (a/0/2/7, battle_string.narc): the message-bank text;
  rom_sha1, xdelta_sha1  the ROM and the release patch: they move with any text.
`check.py --full` fails when nontext_sha1 differs; the other three are reported and fail only with
--strict-release (a translation change moves them). After a change to a fix, the graphics, the code or a
hardcoded string, review the build and record the new hashes in the same commit:
  python3 work/tools/check.py --full --update-expected"""


# --------------------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------------------

class Skip(Exception):
    """A step that cannot run here; with fail=True it counts as a failure (a --full prerequisite)."""

    def __init__(self, msg, fail=False):
        super().__init__(msg)
        self.fail = fail


class Failed(Exception):
    pass


def step_registry():
    import fixes
    try:
        all_fixes = fixes.load_all()
        act = fixes.select(all_fixes)
    except fixes.FixError as ex:
        raise Failed(str(ex)) from None
    n_asm = sum(1 for f in all_fixes if fixes.asm_path(f) is not None)
    return f"{len(all_fixes)} fixes ({n_asm} armips sources linted), {len(act)} enabled"


def step_fixes_md():
    import fixes
    want = fixes.render_docs(fixes.load_all())
    path = fixes.PATCHES_DIR / "FIXES.md"
    if not path.is_file() or path.read_text(encoding="utf-8") != want:
        raise Failed(f"{path.relative_to(REPO)} is out of date: python3 work/tools/fixes.py docs "
                     f"--out work/patches/FIXES.md")
    return "current"


def pinned_ruff() -> str:
    mo = re.search(r"^ruff==(\S+)", REQUIREMENTS_DEV.read_text(encoding="utf-8"), re.M)
    if not mo:
        raise Failed(f"{REQUIREMENTS_DEV.relative_to(REPO)} does not pin ruff (ruff==X.Y.Z)")
    return mo.group(1)


def find_ruff():
    """ruff next to the running interpreter (a venv), else on PATH; None when absent."""
    exe = "ruff.exe" if os.name == "nt" else "ruff"
    sibling = Path(sys.executable).parent / exe
    if sibling.is_file():
        return str(sibling)
    return shutil.which("ruff")


def step_ruff(full):
    want = pinned_ruff()
    ruff = find_ruff()
    if ruff is None:
        raise Skip(f"ruff not installed (pip install -r work/tools/requirements-dev.txt, ruff {want})", fail=full)
    out = subprocess.run([ruff, "--version"], capture_output=True, text=True).stdout.split()
    have = out[1] if len(out) > 1 else "?"
    if have != want:
        raise Failed(f"ruff {have} at {ruff}, but work/tools/requirements-dev.txt pins {want} (other versions "
                     f"report other findings): pip install -r work/tools/requirements-dev.txt")
    # --config: explicit, so a ruff config added under work/ later cannot silently replace ruff.toml there
    # (the translation tools' stricter settings live in work/tools/ruff-translation.toml, check_translation.py)
    r = subprocess.run([ruff, "check", "--no-cache", "--quiet", "--output-format", "concise",
                        "--config", str(REPO / "ruff.toml"), "."],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        raise Failed((r.stdout + r.stderr).strip())
    return f"ruff {have}: clean"


def run_tests(env_armips):
    env = dict(os.environ, ARMIPS=env_armips, PYTHONDONTWRITEBYTECODE="1")
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(TOOLS), "-p", "test_*.py"],
                       cwd=REPO, env=env, capture_output=True, text=True)
    tail = r.stderr.strip().splitlines()
    ran = next((ln for ln in reversed(tail) if ln.startswith("Ran ")), "")
    result = next((ln for ln in reversed(tail) if ln.startswith(("OK", "FAILED"))), "")
    if r.returncode or not result.startswith("OK"):
        fails = [ln for ln in tail if ln.startswith(("FAIL:", "ERROR:"))]
        raise Failed("\n".join(fails[:40] + [ran, result]) or r.stderr[-4000:])
    return f"{ran.split(' in ')[0][4:]}, {result}"


def step_tests_fast():
    return run_tests(NO_ARMIPS) + "; armips hidden"


def full_prerequisites(armips_arg):
    """armips (pinned), both ROMs and xdelta3; raises Skip(fail=True) naming what is missing."""
    import asmpatch
    import build
    missing = []
    armips = None
    try:
        armips = asmpatch.find_armips(armips_arg)
        asmpatch.check_armips(armips)
    except asmpatch.AsmError as ex:
        missing.append(str(ex))
    for p in (build.ROM_CN, build.ROM_US):
        if not p.is_file():
            missing.append(f"{p.relative_to(REPO)} is missing (CONTRIBUTING.md: Building the ROM)")
    if not shutil.which("xdelta3"):
        missing.append("xdelta3 is not on PATH")
    if missing:
        raise Skip("--full needs: " + "; ".join(missing), fail=True)
    return armips


def step_asmpatch(armips):
    r = subprocess.run([sys.executable, str(TOOLS / "asmpatch.py"), "--armips", armips, "check"],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        raise Failed((r.stdout + r.stderr).strip()[-4000:])
    return r.stdout.strip().splitlines()[-1]


class Assembled:
    """The Chinese ROM and every armips fix assembled alone over it, shared by the listings and us-refs steps."""

    def __init__(self):
        self._v = None

    def get(self, armips):
        if self._v is None:
            import asmlisting
            import asmpatch
            import build
            import fixes
            import msgtool
            all_fixes = fixes.load_all()
            cn = msgtool.load_rom(str(build.ROM_CN))
            try:
                done = asmlisting.assemble_each(cn, asmpatch.asm_fixes(all_fixes), armips)
            except (asmpatch.AsmError, fixes.FixError) as ex:
                raise Failed(str(ex)) from None
            self._v = (all_fixes, cn, done)
        return self._v


def step_listings(armips, cache):
    import asmlisting
    import asmpatch
    try:
        asmlisting.capstone_version()
    except asmlisting.ListingError as ex:
        raise Failed(str(ex)) from None
    all_fixes, _cn, done = cache.get(armips)
    texts = asmlisting.snapshots(done, asmpatch.armips_version(armips))
    probs = asmlisting.stale(all_fixes, texts)
    if probs:
        raise Failed("\n".join(probs))
    return f"{len(texts)} snapshots current (capstone {asmlisting.capstone_version()})"


def step_us_refs(armips, cache):
    import build
    import msgtool
    import usref
    if not build.ROM_US.is_file():
        raise Skip(f"{build.ROM_US.relative_to(REPO)} is missing: the USA claims are not checked")
    all_fixes, cn, done = cache.get(armips)
    rows, probs = usref.check_all(all_fixes, msgtool.load_rom(str(build.ROM_US)), cn, done)
    if probs:
        raise Failed("\n".join(probs + ["(python3 work/tools/usref.py lists every claim)"]))
    return f"{len(rows)} USA claims verified"


def step_tests_full(armips):
    return run_tests(armips) + "; with armips (GOLDEN)"


def rom_hashes(rom_path) -> dict:
    """text_sha1 (the message NARCs) and nontext_sha1 (every other part of the ROM: arm9, arm7, overlay
    tables, banner and every other file, by id) of a built ROM."""
    import msgtool
    rom = msgtool.load_rom(str(rom_path))
    text_ids = {rom.filenames.idOf(p) for p in TEXT_NARCS}
    text = hashlib.sha1()
    for p in TEXT_NARCS:
        text.update(hashlib.sha1(bytes(rom.files[rom.filenames.idOf(p)])).digest())
    nontext = hashlib.sha1()
    for name in ("arm9", "arm7", "arm9OverlayTable", "arm7OverlayTable", "iconBanner"):
        data = bytes(getattr(rom, name) or b"")
        nontext.update(f"{name}:{len(data)}:".encode() + hashlib.sha1(data).digest())
    for i, data in enumerate(rom.files):
        if i not in text_ids:
            nontext.update(f"file{i}:{len(data)}:".encode() + hashlib.sha1(bytes(data)).digest())
    return {"text_sha1": text.hexdigest(), "nontext_sha1": nontext.hexdigest()}


def load_expected(path=EXPECTED) -> dict:
    if not Path(path).is_file():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f).get("build", {})


def write_expected(values: dict, path=EXPECTED):
    lines = ["# What `python3 work/tools/check.py --full` expects from the default full build of this branch",
             "# (python3 work/tools/build.py: every enabled fix, the workspace text). Recorded by",
             "# `check.py --full --update-expected`.",
             "#"] + [f"# {ln}" if ln else "#" for ln in EXPECTED_HELP.splitlines()] + [
             "", "[build]"]
    for k in ("nontext_sha1", "text_sha1", "rom_sha1", "xdelta_sha1"):
        lines.append(f'{k} = "{values[k]}"')
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_expected(got: dict, want: dict, strict=False) -> tuple:
    """(failures, notes) of a build's hashes against expected.toml. nontext_sha1 must match; text_sha1,
    rom_sha1 and xdelta_sha1 move with the translation text, so they are notes unless strict (a release)."""
    upd = "python3 work/tools/check.py --full --update-expected"
    if not want:
        return [f"{EXPECTED.relative_to(REPO)} is missing; record it: {upd}"], []
    fails, notes = [], []
    nontext_same = got["nontext_sha1"] == want.get("nontext_sha1")
    if not nontext_same:
        fails.append(f"the ROM outside the message banks changed (nontext_sha1 {got['nontext_sha1']}, expected "
                     f"{want.get('nontext_sha1')}): a fix, the graphics, the code or a hardcoded string's English "
                     f"builds other bytes. If that is intended, say why in the commit and record it: {upd}")
    text_changed = got["text_sha1"] != want.get("text_sha1")
    for k in ("text_sha1", "rom_sha1", "xdelta_sha1"):
        if got[k] == want.get(k):
            continue
        if k == "text_sha1":
            why = "the message-bank text changed since the hashes were recorded"
        elif text_changed:
            why = "the message-bank text changed" + ("; the bytes outside it are unchanged" if nontext_same else "")
        elif not nontext_same:
            why = "it follows from the change outside the message banks (above)"
        else:
            why = ("the message text and everything outside it are the recorded ones, so this is unexpected "
                   "(the container or the patch tool?)")
        (fails if strict else notes).append(f"{k} {got[k]}, expected {want.get(k)}: {why}. After reviewing the "
                                            f"build, record the new hashes: {upd}")
    return fails, notes


def step_build(armips, work_dir, update, strict=False):
    work_dir = Path(work_dir)
    log = work_dir / "build.log"
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run([sys.executable, str(TOOLS / "build.py"), "--work-dir", str(work_dir),
                            "--armips", armips], cwd=REPO, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise Failed(f"build.py failed (exit {r.returncode}); log: {log}\n" +
                     "\n".join(log.read_text(encoding="utf-8").splitlines()[-15:]))
    report = json.loads((work_dir / "build_report.json").read_text(encoding="utf-8"))
    got = {"rom_sha1": report["rom"]["sha1"], "xdelta_sha1": report["patch"]["sha1"],
           **rom_hashes(report["rom"]["path"])}
    if update:
        write_expected(got)
        return f"recorded in {EXPECTED.relative_to(REPO)}: ROM {got['rom_sha1']}, xdelta {got['xdelta_sha1']}"
    fails, notes = compare_expected(got, load_expected(), strict)
    if fails:
        raise Failed("\n".join(fails + [f"note: {n}" for n in notes]) + f"\n(build log: {log})")
    head = f"non-text {got['nontext_sha1'][:12]} as expected; ROM {got['rom_sha1']}, xdelta {got['xdelta_sha1']}"
    if notes:
        return "\n".join([head + " (not the recorded ones, see the notes; --strict-release fails on them)"]
                         + [f"note: {n}" for n in notes])
    return head + ": as recorded"


# --------------------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------------------

def run(steps) -> int:
    rows, failed = [], False
    t_all = time.monotonic()
    for name, fn in steps:
        t0 = time.monotonic()
        print(f"-- {name} ...", flush=True)
        try:
            detail, status = fn(), "PASS"
        except Skip as ex:
            detail, status = str(ex), "FAIL" if ex.fail else "SKIP"
        except Failed as ex:
            detail, status = str(ex), "FAIL"
        dt = time.monotonic() - t0
        failed |= status == "FAIL"
        rows.append((name, status, dt, detail))
        first, *rest = (detail or "").splitlines() or [""]
        print(f"   {status} {name} ({dt:.1f} s): {first}")
        for ln in rest:
            print(f"     {ln}")
    print(f"\n{'step':10s} {'result':6s} {'time':>7s}")
    for name, status, dt, _ in rows:
        print(f"{name:10s} {status:6s} {dt:6.1f}s")
    print(f"{'total':10s} {'FAIL' if failed else 'ok':6s} {time.monotonic() - t_all:6.1f}s")
    return 1 if failed else 0


def staged(extra=()) -> int:
    """The fast check on the index (what `git commit` records): the staged tree is exported to a temp folder
    (git checkout-index; untracked and git-ignored files such as the ROMs are not there) and checked there."""
    git = shutil.which("git")
    if git is None:
        print("git not found", file=sys.stderr)
        return 1
    top = subprocess.run([git, "rev-parse", "--show-toplevel"], cwd=REPO, capture_output=True, text=True)
    if top.returncode:
        print(top.stderr.strip(), file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="poke-check-") as td:
        subprocess.run([git, "checkout-index", "--all", f"--prefix={td}/"], cwd=top.stdout.strip(), check=True)
        print(f"staged tree exported to {td}", flush=True)
        inner = Path(td) / "work" / "tools" / "check.py"
        if not inner.is_file():
            print("work/tools/check.py is not in the staged tree; nothing to check")
            return 0
        return subprocess.run([sys.executable, str(inner), "--fast", *extra], cwd=td).returncode


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fast", action="store_true", help="no armips, no ROM (the default)")
    mode.add_argument("--full", action="store_true", help="also assemble, GOLDEN tests and a full build")
    mode.add_argument("--staged", action="store_true", help="the fast check on the staged files")
    ap.add_argument("--registry-only", action="store_true",
                    help="only the registry step (fixes.py check with the asm lint); with --fast or --staged")
    ap.add_argument("--armips", help="armips executable for --full (default: $ARMIPS, then PATH)")
    ap.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR), help="build folder for --full "
                                                                     "(default work/build/check)")
    ap.add_argument("--update-expected", action="store_true",
                    help="with --full: record the build's hashes in work/patches/expected.toml")
    ap.add_argument("--strict-release", action="store_true",
                    help="with --full: also fail when the text, ROM or xdelta hash is not the recorded one")
    a = ap.parse_args(argv)
    if (a.update_expected or a.strict_release) and not a.full:
        ap.error("--update-expected and --strict-release need --full")
    if a.registry_only and a.full:
        ap.error("--registry-only is a fast check")
    if a.staged:
        return staged(["--registry-only"] if a.registry_only else [])
    if a.registry_only:
        return run([("registry", step_registry)])
    steps = [("registry", step_registry), ("fixes-md", step_fixes_md), ("ruff", lambda: step_ruff(a.full))]
    if not a.full:
        steps.append(("tests", step_tests_fast))
        code = run(steps)
        print("fast mode: armips, ROM and build steps not run (python3 work/tools/check.py --full)")
        return code
    armips = {}

    def prereq():
        armips["path"] = full_prerequisites(a.armips)
        return f"armips {armips['path']}, both ROMs, xdelta3"

    def need(fn):
        def go():
            if "path" not in armips:
                raise Skip("prerequisites missing (see prereq)", fail=True)
            return fn(armips["path"])
        return go

    cache = Assembled()
    steps += [("prereq", prereq), ("asmpatch", need(step_asmpatch)),
              ("listings", need(lambda p: step_listings(p, cache))),
              ("us-refs", need(lambda p: step_us_refs(p, cache))),
              ("tests", need(step_tests_full)),
              ("build", need(lambda p: step_build(p, a.work_dir, a.update_expected, a.strict_release)))]
    return run(steps)


if __name__ == "__main__":
    sys.exit(main())
