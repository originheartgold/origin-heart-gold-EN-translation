#!/usr/bin/env python3
"""check - one entry point for the patch toolchain's checks.

    python3 work/tools/check.py [--fast]       registry + asm lint, FIXES.md current, ruff, the synthetic assembly
                                               (when armips is found), unit tests (armips hidden); no ROM
    python3 work/tools/check.py --full         also: asmpatch.py check, the disassembly snapshots, the USA
                                               claims, the unit tests with armips (GOLDEN), a full build
                                               compared with work/patches/expected.toml
    python3 work/tools/check.py --staged       the fast check on the staged files (the pre-commit hook)
    python3 work/tools/check.py --staged --registry-only
                                               only the registry step (the hook, for decision-register commits)
    python3 work/tools/check.py --full --repro also: the native payload recompiled with the pinned clang, and a
                                               second build (another folder, file names, cwd, TZ, locale and
                                               hash seed) byte-identical to the first (about 30 s more)
    python3 work/tools/check.py --full --strict-release
                                               also fail when the text, ROM or xdelta hash moved; implies --repro
                                               (a release)
    python3 work/tools/check.py --full --update-expected
                                               record the full build's hashes in work/patches/expected.toml
    python3 work/tools/check.py --full --emu   also: the emulator layer on the build (emu_harness.py layer): fix
                                               scenarios, behaviour scenarios, text fit, freeze reproducers; one
                                               report (about 35-40 min; --emu-only fixes,scenarios,textfit,freeze)

Fast (the default, also the pre-commit hook and CI; about 6 s) needs no ROM, and armips only for asm-synth:
  registry   fixes.py check: fix.toml schema, regions, overlaps, `.open` lines, `.string` = en, and the asm
             lint (header, .area around every write, a guard before every area's first write, every area
             inside fix.toml's regions or appended under expect_end with a [[grow]], line length);
  fixes-md   work/patches/FIXES.md equals `fixes.py docs`;
  ruff       `ruff check` with the repo's ruff.toml, by the version pinned in work/tools/requirements-dev.txt
             (skipped with a note when ruff is not installed; --full requires it);
  asm-synth  `asmpatch.py synthetic`: every armips source assembled without the ROM, over zero-filled stand-ins
             of the binaries (work/patches/sizes.toml), guards off: syntax, .area overflows, regions, growth,
             strings; not the bytes. Needs armips v0.11.0 (--armips, $ARMIPS, PATH): skipped with a note when
             it is not found, a failure when --armips names one that is not there (CI passes --armips);
  tests      every work/tools/test_*.py, with armips hidden (the armips tests skip; tests that read the
             Chinese ROM run when it is there and skip when it is not).
Full adds (and fails when armips v0.11.0, the two ROMs or xdelta3 are missing; asm-synth then requires armips):
  asmpatch   asmpatch.py check: every enabled armips fix assembled against the Chinese ROM;
  listings   every armips fix assembled alone and disassembled (asmlisting.py, capstone pinned in
             requirements-dev.txt): each work/patches/<id>/<id>.listing must equal it (a stale snapshot fails,
             with the command that regenerates it);
  us-refs    every [[us_ref]] claim checked against the USA ROM (usref.py);
  tests      the unit tests again with armips: the per-binary GOLDEN SHA-1s of test_asmpatch.py, which do not
             depend on the translation text;
  build      build.py into --work-dir (default work/build/check), then its hashes against
             work/patches/expected.toml (see EXPECTED_HELP below): nontext_sha1 must match; the text, ROM and
             xdelta hashes are reported, and fail the step only with --strict-release. prereq warns about an
             xdelta3 other than build.XDELTA3_VERSION (--strict-release: a failure, and the build report must
             record the pinned one) and about another Python / ndspy / pillow.
--repro (and --strict-release) adds:
  repro      text_speed_patch.verify_reproducible_payload() (native.c recompiled by the pinned clang, fix.toml
             [native] compiler, vendor and major enforced: the same bytes and symbols as payload.json), then
             build.py again into <work-dir>-repro, with the base ROM linked under another name, other --out /
             --patch names, that folder as the working directory and other TZ, LC_ALL/LANG and PYTHONHASHSEED
             (REPRO_ENVS; the first build runs with the other set): the ROM, the xdelta and build_report.json
             (without its paths) must be byte-identical; a ROM difference is listed by NDS part (arm9, overlay
             N, file path). When the second build's Python does not get a non-UTF-8 encoding (the locale is not
             installed), a note says the locale axis was not tested.

--emu adds (needs py-desmume in this Python, i.e. the harness venv, and the battery saves of --emu-saves):
  emu        emu_harness.py layer (emu_layer.py) on the build's ROM, every part at the same time on one pool of
             --emu-jobs emulators (default 3; within the machine-wide cap EMU_HARNESS_MAX_EMULATORS):
             fixes      one scenario per fix: 'fixed' on the build, 'original' on a control ROM without that fix
                        (build.py --no-patch --without <fix>[,dependents] in <work-dir>-emu/controls; reused when
                        its build report and message text match this build, else rebuilt); graphics crops against
                        the approved digests (emu_fixes_crops.json), a crop not approved yet is 'pending';
             scenarios  every work/tools/scenarios/*.toml on both ROMs: CN/EN parity, expectations, baselines
                        against the committed digests (scenario_baselines.json), not approved yet = 'pending';
             textfit    the strings changed since --emu-since (default the latest tag) in their window;
             freeze     the melonDS freeze reproducers (rocket_hq, follower_viridian, follower_route22): no freeze
                        on the build, the freeze still reproduced on the untouched Chinese ROM.
             Runs in <work-dir>-emu/runs/<stamp>/<part>; the report (report.json, report.html: failures with
             their CN|EN evidence, pending approvals with the exact `emu_harness.py approve` commands, passes)
             in <work-dir>-emu/report/<stamp>/. The step fails on any failure; pending approvals are listed and
             do not fail it. --emu-only PARTS runs some parts (with the build), for speed while iterating.
             Not part of --full by default.

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
# the two environments of a --repro run: the first build runs in A, the second in B (another folder too)
REPRO_ENVS = ({"TZ": "UTC", "LC_ALL": "C", "LANG": "C", "PYTHONHASHSEED": "0"},
              {"TZ": "Asia/Kathmandu", "LC_ALL": "en_US.ISO8859-1", "LANG": "en_US.ISO8859-1",
               "PYTHONHASHSEED": "4242"})
REPORT_PATH_KEYS = (("base", "path"), ("rom", "path"), ("patch", "path"))
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


# work/tools and its two test folders without an __init__.py (discover does not descend into them); each
# runs as its own start directory, so its tests import their neighbours by plain module name.
TEST_DIRS = (TOOLS, TOOLS / "docs", TOOLS / "site")


def run_tests(env_armips):
    env = dict(os.environ, ARMIPS=env_armips, PYTHONDONTWRITEBYTECODE="1")
    summary = []
    for start in TEST_DIRS:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(start), "-p", "test_*.py"],
                           cwd=REPO, env=env, capture_output=True, text=True)
        tail = r.stderr.strip().splitlines()
        ran = next((ln for ln in reversed(tail) if ln.startswith("Ran ")), "")
        result = next((ln for ln in reversed(tail) if ln.startswith(("OK", "FAILED"))), "")
        where = start.relative_to(REPO)
        if r.returncode or not result.startswith("OK"):
            fails = [ln for ln in tail if ln.startswith(("FAIL:", "ERROR:"))]
            raise Failed(f"{where}:\n" + ("\n".join(fails[:40] + [ran, result]) or r.stderr[-4000:]))
        summary.append(f"{where}: {ran.split(' in ')[0][4:]}, {result}")
    return "; ".join(summary)


def step_synthetic(armips_arg, required):
    """asmpatch.py synthetic; without armips a SKIP, or a failure when `required` (--full, or --armips given)."""
    import asmpatch
    import fixes
    try:
        armips = asmpatch.find_armips(armips_arg)
        asmpatch.check_armips(armips)
    except asmpatch.AsmError as ex:
        if not required:
            raise Skip(f"armips {asmpatch.PINNED_VERSION} not found (--armips, $ARMIPS or PATH; "
                       f"work/notes/toolchain.md)") from None
        raise Skip(str(ex), fail=True) from None
    try:
        return asmpatch.synthetic(armips)
    except (asmpatch.AsmError, fixes.FixError) as ex:
        raise Failed(str(ex)) from None


def step_tests_fast():
    return run_tests(NO_ARMIPS) + "; armips hidden"


def full_prerequisites(armips_arg, release=False):
    """(armips, warnings): armips (pinned), both ROMs and xdelta3; raises Skip(fail=True) naming what is missing.
    An xdelta3 other than build.XDELTA3_VERSION is a warning, and missing for a release (--strict-release)."""
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
    warnings = []
    try:
        version, pinned = build.check_xdelta3()
        if not pinned:
            (missing if release else warnings).append(build.xdelta3_warning(version))
    except build.ToolchainError as ex:
        missing.append(str(ex))
    if missing:
        raise Skip(("--strict-release" if release else "--full") + " needs: " + "; ".join(missing), fail=True)
    return armips, warnings


def step_asmpatch(armips):
    r = subprocess.run([sys.executable, str(TOOLS / "asmpatch.py"), "--armips", armips, "check"],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        raise Failed((r.stdout + r.stderr).strip()[-4000:])
    return r.stdout.strip().splitlines()[-1]


class AssemblyCache:
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
    all_fixes, cn, done = cache.get(armips)
    rows, probs = usref.check_all(all_fixes, msgtool.load_rom(str(build.ROM_US)), cn, done)
    if probs:
        raise Failed("\n".join(probs + ["(python3 work/tools/usref.py lists every claim)"]))
    return f"{len(rows)} USA claims verified"


def step_tests_full(armips):
    return run_tests(armips) + "; with armips (GOLDEN)"


ROM_SECTIONS = ("arm9", "arm7", "arm9OverlayTable", "arm7OverlayTable", "iconBanner")


def rom_blobs(rom):
    """(key, label, bytes) of every part of an ndspy ROM: the sections (ROM_SECTIONS), then every file in id
    order (key "file<i>", label its path or the overlay it is). rom_hashes and rom_parts read the same list."""
    names = {}
    for which, loader in (("arm9", "loadArm9Overlays"), ("arm7", "loadArm7Overlays")):
        try:
            for ov_id, ov in getattr(rom, loader)().items():
                names[ov.fileID] = f"{which} overlay {ov_id}"
        except Exception:                                   # noqa: BLE001 - a broken table: files by number
            pass
    for name in ROM_SECTIONS:
        yield name, name, bytes(getattr(rom, name, None) or b"")
    for i, data in enumerate(rom.files):
        label = names.get(i)
        if label is None:
            try:
                label = rom.filenames.filenameOf(i)
            except Exception:                               # noqa: BLE001
                label = None
        yield f"file{i}", f"{label} (file {i})" if label else f"file {i}", bytes(data)


def rom_hashes(rom_path) -> dict:
    """text_sha1 (the message NARCs) and nontext_sha1 (every other part of the ROM: arm9, arm7, overlay
    tables, banner and every other file, by id) of a built ROM. The byte format of nontext_sha1 is what
    expected.toml records: per part "<key>:<length>:" + its SHA-1 digest."""
    import msgtool
    rom = msgtool.load_rom(str(rom_path))
    text_keys = {f"file{rom.filenames.idOf(p)}" for p in TEXT_NARCS}
    text = hashlib.sha1()
    for p in TEXT_NARCS:
        text.update(hashlib.sha1(bytes(rom.files[rom.filenames.idOf(p)])).digest())
    nontext = hashlib.sha1()
    for key, _label, data in rom_blobs(rom):
        if key not in text_keys:
            nontext.update(f"{key}:{len(data)}:".encode() + hashlib.sha1(data).digest())
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


def run_build(armips, work_dir, extra=(), env=None, cwd=REPO) -> dict:
    """build.py --work-dir work_dir; its build_report.json. env: variables set over os.environ."""
    work_dir = Path(work_dir)
    log = work_dir / "build.log"
    work_dir.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run([sys.executable, str(TOOLS / "build.py"), "--work-dir", str(work_dir),
                            "--armips", armips, *extra], cwd=cwd, env=dict(os.environ, **(env or {})),
                           stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        raise Failed(f"build.py failed (exit {r.returncode}); log: {log}\n" +
                     "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-15:]))
    return json.loads((work_dir / "build_report.json").read_text(encoding="utf-8"))


def step_build(armips, work_dir, update, strict=False, env=None, out=None):
    """The full build against expected.toml; `out` (a dict) receives its report and work dir for repro."""
    report = run_build(armips, work_dir, env=env)
    if out is not None:
        out.update(report=report, work_dir=Path(work_dir))
    log = Path(work_dir) / "build.log"
    if strict and not report.get("toolchain", {}).get("xdelta3_pinned"):
        raise Failed(f"the build report does not record the pinned xdelta3 ({report.get('toolchain')}); "
                     f"a release needs it (log: {log})")
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


def normalized_report(report: dict, work_dir) -> str:
    """build_report.json without what may differ between two builds of the same tree: the base, ROM and patch
    paths, and the work folder anywhere else (as <work>)."""
    rep = json.loads(json.dumps(report))
    for outer, inner in REPORT_PATH_KEYS:
        if isinstance(rep.get(outer), dict):
            rep[outer].pop(inner, None)
    text = json.dumps(rep, indent=1, ensure_ascii=False)
    for form in {str(Path(work_dir)), str(Path(work_dir).resolve())}:
        text = text.replace(json.dumps(form)[1:-1], "<work>")
    return text


def rom_parts(rom) -> dict:
    """{label: sha1} of an ndspy ROM (rom_blobs), plus the debug ROM and the header fields ndspy keeps."""
    out = {label: hashlib.sha1(data).hexdigest() for _key, label, data in rom_blobs(rom)}
    if getattr(rom, "debugRom", None) is not None:
        out["debugRom"] = hashlib.sha1(bytes(rom.debugRom)).hexdigest()
    header = {k: v for k, v in vars(rom).items()
              if isinstance(v, (int, str, bytes, bool)) and not k.startswith("_") and k not in out}
    out["header fields"] = hashlib.sha1(repr(sorted(header.items())).encode()).hexdigest()
    return out


def rom_part_diff(path_a, path_b) -> list:
    """The NDS parts that differ between two ROM files (romdiff: ndspy, part by part)."""
    import msgtool
    a, b = rom_parts(msgtool.load_rom(str(path_a))), rom_parts(msgtool.load_rom(str(path_b)))
    diff = [k for k in a if a[k] != b.get(k)] + [k for k in b if k not in a]
    if not diff:
        return ["no NDS part differs: the bytes outside the parts (header CRCs, padding, file layout)"]
    return diff


def same_bytes(a, b) -> bool:
    import filecmp
    return Path(a).stat().st_size == Path(b).stat().st_size and filecmp.cmp(a, b, shallow=False)


def preferred_encoding(env) -> str:
    """The preferred encoding a Python started with `env` over os.environ gets (locale.getpreferredencoding)."""
    r = subprocess.run([sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
                       env=dict(os.environ, **(env or {})), capture_output=True, text=True)
    return r.stdout.strip() or "?"


def locale_note(env) -> str:
    """'' when env gives Python a non-UTF-8 encoding (the locale axis is tested), else a note saying it is not."""
    enc = preferred_encoding(env)
    if enc.lower().replace("-", "").replace("_", "") in ("utf8", "?"):
        return (f"note: LC_ALL={(env or {}).get('LC_ALL')} gives Python {enc}, not a non-UTF-8 encoding (the locale "
                f"is not installed here?): the locale axis was not tested")
    return ""


EMU_SAVES = ("full_bag_6mons.sav", "route1_path_2mons.sav", "market.sav")   # what the emulator parts import
EMU_PARTS = ("fixes", "scenarios", "textfit", "freeze")


def emu_dir_of(work_dir) -> Path:
    return Path(work_dir).with_name(Path(work_dir).name + "-emu")


def step_emu(armips, first: dict, work_dir, saves, jobs=3, only=None, since=None, freeze_saves=None) -> str:
    """The emulator layer (emu_harness.py layer, emu_layer.py) on the full build's ROM: fix scenarios, behaviour
    scenarios, text fit, freeze reproducers; one report in <work-dir>-emu/report/<stamp>/. Fix control ROMs in
    <work-dir>-emu/controls are reused only when their build report and message text match this build (emu_fixes
    control_problems); otherwise rebuilt there."""
    if "report" not in first:
        raise Skip("no build to test (the build step failed)", fail=True)
    probe = subprocess.run([sys.executable, "-c", "import desmume.emulator, PIL"], capture_output=True, text=True)
    if probe.returncode:
        raise Skip(f"--emu needs py-desmume and pillow in {sys.executable} (the emulator harness's venv)", fail=True)
    missing = [n for n in EMU_SAVES if not (Path(saves) / n).is_file()]
    if missing:
        raise Skip(f"--emu needs the battery saves {', '.join(missing)} in {saves} (--emu-saves)", fail=True)
    emu_dir = emu_dir_of(work_dir)
    emu_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cmd = [sys.executable, str(TOOLS / "emu_harness.py"), "layer", "--rom", first["report"]["rom"]["path"],
           "--rom-report", str(Path(work_dir) / "build_report.json"), "--controls", str(emu_dir / "controls"),
           "--armips", armips, "--sav-dir", str(saves), "--jobs", str(jobs), "--out-root", str(emu_dir),
           "--stamp", stamp, "--parts", ",".join(only or EMU_PARTS)]
    if since:
        cmd += ["--since", since]
    if freeze_saves:
        cmd += ["--freeze-saves", freeze_saves]
    report_dir = emu_dir / "report" / stamp
    lines = []
    with subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
        for ln in proc.stdout:                       # the layer's progress lines (one per part), as they come
            lines.append(ln)
            print("     " + ln.rstrip(), flush=True)
    rc = proc.returncode
    (emu_dir / f"layer-{stamp}.log").write_text("".join(lines), encoding="utf-8")
    try:
        report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Failed(f"emu_harness.py layer failed (exit {rc}) without a report:\n"
                     + "".join(lines[-15:]).strip()) from None
    text = emu_summary(report, report_dir)
    if rc or not report["pass"]:
        raise Failed(text)
    return text


def emu_summary(report, report_dir, max_rows=40) -> str:
    """The compact summary of a layer report: per part counts, failures, pending approvals, the report path."""
    m = report.get("meta", {})
    lines = [f"{report['verdict']} in {round(m.get('seconds') or 0)} s"
             + (f", {report['pending_approvals']} pending approval" if report.get("pending_approvals") else "")
             + f"; report {Path(report_dir) / 'report.html'}"]
    for p in report["parts"]:
        c = p.get("counts", {})
        lines.append(f"{p['part']:9s} {'PASS' if p['pass'] else 'FAIL'}: {c.get('fail', 0)} fail, "
                     f"{c.get('pending', 0)} pending, {c.get('pass', 0)} pass ({round(p.get('seconds') or 0)} s)")
    fails = [r for r in report["rows"] if r["status"] == "fail"]
    pend = [r for r in report["rows"] if r["status"] == "pending"]
    for r in fails[:max_rows]:
        lines.append(f"FAIL {r['part']}: {r['title']}")
    if len(fails) > max_rows:
        lines.append(f"... {len(fails) - max_rows} more failures in the report")
    for r in pend:
        lines.append(f"PENDING {r['part']}: {r['title']}")
    if pend:
        lines.append(f"approve (after looking at the evidence): {(report.get('approve_commands') or [''])[-1]}")
    return "\n".join(lines)


def step_repro(armips, first: dict, work_dir, env=None) -> str:
    """The native payload from source with the pinned clang, then a second build in another folder, under other
    file names, working directory and environment: the ROM, xdelta and report must equal the first build's."""
    import text_speed_patch
    if not first:
        raise Failed("the first build did not finish (see build)")
    t0 = time.monotonic()
    try:
        payload = text_speed_patch.verify_reproducible_payload()
    except (OSError, ValueError, subprocess.CalledProcessError) as ex:
        raise Failed(f"native payload: {ex} (text_speed_patch.py --check-payload; clang pinned in "
                     f"work/patches/text-speed/fix.toml [native] compiler)") from None
    t_payload = time.monotonic() - t0
    work_dir = Path(work_dir)
    if work_dir.resolve() == first["work_dir"].resolve():
        raise Failed("the repro build needs its own folder")
    work_dir.mkdir(parents=True, exist_ok=True)
    base_link = work_dir / "usa base (renamed).nds"
    base_link.unlink(missing_ok=True)
    import build
    build.link_as(Path(first["report"]["base"]["path"]), base_link)
    second = run_build(armips, work_dir, extra=["--base", str(base_link), "--out", str(work_dir / "repro.nds"),
                                                "--patch", str(work_dir / "repro.xdelta")],
                       env=env, cwd=work_dir)
    a, b = first["report"], second
    fails = []
    if not same_bytes(a["rom"]["path"], b["rom"]["path"]):
        fails.append(f"the ROM differs ({a['rom']['sha1']} vs {b['rom']['sha1']}); NDS parts: "
                     + ", ".join(rom_part_diff(a["rom"]["path"], b["rom"]["path"])))
    if not same_bytes(a["patch"]["path"], b["patch"]["path"]):
        fails.append(f"the xdelta differs ({a['patch']['sha1']} vs {b['patch']['sha1']})")
    ra, rb = normalized_report(a, first["work_dir"]), normalized_report(b, work_dir)
    if ra != rb:
        import difflib
        d = list(difflib.unified_diff(ra.splitlines(), rb.splitlines(), "first", "repro", lineterm="", n=1))
        fails.append("build_report.json differs (paths left out):\n" + "\n".join(d[:40]))
    if fails:
        raise Failed("\n".join(fails) + f"\n(builds: {first['work_dir']}, {work_dir})")
    enc = preferred_encoding(env)
    lines = [f"payload reproduced by {payload['compiler']} ({t_payload:.1f} s); second build in {work_dir.name} "
             f"(renamed base, other names, cwd, TZ, locale {enc}, hash seed): ROM, xdelta and report identical"]
    if payload.get("compiler_warning"):
        lines.append(f"note: {payload['compiler_warning']}")
    note = locale_note(env)
    return "\n".join(lines + ([note] if note else []))


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
    ap.add_argument("--armips", help="armips executable for asm-synth and --full (default: $ARMIPS, then PATH); "
                                     "given, asm-synth fails without it")
    ap.add_argument("--work-dir", default=str(DEFAULT_WORK_DIR), help="build folder for --full "
                                                                     "(default work/build/check)")
    ap.add_argument("--update-expected", action="store_true",
                    help="with --full: record the build's hashes in work/patches/expected.toml")
    ap.add_argument("--strict-release", action="store_true",
                    help="with --full: also fail when the text, ROM or xdelta hash is not the recorded one; "
                         "implies --repro")
    ap.add_argument("--repro", action="store_true",
                    help="with --full: recompile the native payload with the pinned clang and build a second time "
                         "(another folder, names, cwd and environment); both builds must be byte-identical")
    ap.add_argument("--emu", action="store_true",
                    help="with --full: the emulator layer on the build (emu_harness.py layer: fix scenarios, "
                         "behaviour scenarios, text fit, freeze reproducers; one report; needs py-desmume)")
    ap.add_argument("--emu-only", help=f"with --emu: comma list of parts to run ({', '.join(EMU_PARTS)}; default all)")
    ap.add_argument("--emu-since", help="with --emu: text fit of the strings changed since this git ref (default: the "
                                        "latest tag, git describe --tags --abbrev=0, else v1.0.0-rc5)")
    ap.add_argument("--emu-freeze-saves", help="with --emu: folders searched for the freeze cases' saves by SHA-256 "
                                               "(default: --emu-saves and <its parent>/rocket-repro-20261008)")
    ap.add_argument("--emu-saves", default=str(WORK / "build" / "memcheck"),
                    help="folder with the battery saves the --emu scenarios import (read only; the same default "
                         "as emu_harness.py fixes --sav-dir)")
    ap.add_argument("--emu-jobs", type=int, default=3, help="emulators alive at once for --emu, all parts together "
                                                            "(at most 3)")
    a = ap.parse_args(argv)
    if a.emu_only or a.emu_since or a.emu_freeze_saves:
        a.emu = True
    if (a.update_expected or a.strict_release or a.repro or a.emu) and not a.full:
        ap.error("--update-expected, --strict-release, --repro and --emu need --full")
    emu_only = None
    if a.emu_only:
        emu_only = [p.strip() for p in a.emu_only.split(",") if p.strip()]
        bad = [p for p in emu_only if p not in EMU_PARTS]
        if bad or not emu_only:
            ap.error(f"--emu-only: unknown part(s) {', '.join(bad) or '(none)'}; parts: {', '.join(EMU_PARTS)}")
    repro = a.repro or a.strict_release
    # build.py runs with cwd=REPO (the repro build elsewhere): a relative --work-dir is relative to the repo root
    work_dir = Path(a.work_dir) if Path(a.work_dir).is_absolute() else REPO / a.work_dir
    if a.registry_only and a.full:
        ap.error("--registry-only is a fast check")
    if a.staged:
        return staged(["--registry-only"] if a.registry_only else [])
    if a.registry_only:
        return run([("registry", step_registry)])
    steps = [("registry", step_registry), ("fixes-md", step_fixes_md), ("ruff", lambda: step_ruff(a.full)),
             ("asm-synth", lambda: step_synthetic(a.armips, a.full or a.armips is not None))]
    if not a.full:
        steps.append(("tests", step_tests_fast))
        code = run(steps)
        print("fast mode: the ROM and build steps not run (python3 work/tools/check.py --full)")
        return code
    armips = {}

    def prereq():
        armips["path"], warn = full_prerequisites(a.armips, release=a.strict_release)
        import build
        warn += build.python_warnings()
        return "\n".join([f"armips {armips['path']}, both ROMs, xdelta3"] + [f"warning: {w}" for w in warn])

    def need(fn):
        def go():
            if "path" not in armips:
                raise Skip("prerequisites missing (see prereq)", fail=True)
            return fn(armips["path"])
        return go

    cache = AssemblyCache()
    first = {}
    steps += [("prereq", prereq), ("asmpatch", need(step_asmpatch)),
              ("listings", need(lambda p: step_listings(p, cache))),
              ("us-refs", need(lambda p: step_us_refs(p, cache))),
              ("tests", need(step_tests_full)),
              ("build", need(lambda p: step_build(p, work_dir, a.update_expected, a.strict_release,
                                                  env=REPRO_ENVS[0] if repro else None, out=first)))]
    if repro:
        steps.append(("repro", need(lambda p: step_repro(p, first, work_dir.with_name(work_dir.name + "-repro"),
                                                         env=REPRO_ENVS[1]))))
    if a.emu:
        steps.append(("emu", need(lambda p: step_emu(p, first, work_dir, a.emu_saves, a.emu_jobs, emu_only,
                                                     a.emu_since, a.emu_freeze_saves))))
    return run(steps)


if __name__ == "__main__":
    sys.exit(main())
