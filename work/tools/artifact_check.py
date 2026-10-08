#!/usr/bin/env python3
"""Verify an existing English ROM against a fresh workspace export; never build a ROM."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import sys

import build
import msgtool
import ws


def hashes(path):
    digests = {name: hashlib.new(name) for name in ("sha1", "sha256")}
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            for digest in digests.values():
                digest.update(chunk)
    return {"path": str(path), "size": path.stat().st_size,
            **{name: digest.hexdigest() for name, digest in digests.items()}}


def tree_hash(path):
    digest = hashlib.sha256()
    files = sorted(path.rglob("*.json"))
    for file in files:
        digest.update(file.relative_to(path).as_posix().encode() + b"\0")
        digest.update(bytes.fromhex(hashes(file)["sha256"]))
    return {"path": str(path), "files": len(files), "sha256": digest.hexdigest()}


def check(a, export_fn=None, verify_fn=None):
    report = {"schema_version": 1, "status": "incomplete", "inputs": {}, "checks": {}}
    export_fn = export_fn or ws.export
    verify_fn = verify_fn or build.verify_rom
    try:
        if sys.flags.optimize:
            report["reason"] = "optimized Python disables verifier assertions; run without -O"
            return report
        for name in ("rom", "base", "build_report"):
            path = getattr(a, name)
            if not path.is_file():
                report["reason"] = f"missing {name}: {path}"
                return report
            report["inputs"][name] = hashes(path)
        for name in ("ws", "extract"):
            path = getattr(a, name)
            if not path.is_dir():
                report["reason"] = f"missing {name}: {path}"
                return report
            report["inputs"][name] = tree_hash(path)
            if not report["inputs"][name]["files"]:
                report.update(status="failed", reason=f"empty {name}: no JSON inputs")
                return report
        prior = json.loads(a.build_report.read_text(encoding="utf-8"))
        report["status"] = "failed"
        if prior.get("rom", {}).get("sha1") != report["inputs"]["rom"]["sha1"]:
            report["reason"] = "ROM identity differs from build report; verification metadata is stale"
            return report
        if prior.get("base", {}).get("sha1") != report["inputs"]["base"]["sha1"]:
            report["reason"] = "base ROM identity differs from build report"
            return report
        for key in ("graphics", "hardcoded", "glyphs", "statuses"):
            if key not in prior:
                report.update(status="incomplete", reason=f"build report missing {key} verification metadata")
                return report
        report["checks"]["identity"] = "passed"
        report["verification_inputs"] = {
            str(path.relative_to(build.WORK)): hashes(path)
            for path in (Path(__file__), build.TOOLS / "build.py", build.TOOLS / "ws.py",
                         build.TOOLS / "gfx.py", build.TOOLS / "hardcoded.py", build.TOOLS / "fixes.py",
                         build.TOOLS / "asmpatch.py", build.TOOLS / "msgtool.py",
                         *sorted((build.WORK / "patches").glob("*/fix.toml")),
                         *sorted((build.WORK / "patches").glob("*/*.asm")),
                         *sorted((build.WORK / "patches" / "include").glob("*")),
                         build.WORK / "patches" / "overlays.toml",
                         build.TOOLS / "qa_config.json", build.TOOLS / "charmap_en.tsv",
                         build.TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv",
                         build.WORK / "graphics" / "layout_checks.json",
                         # text-speed: its checking module and native sources (fix.toml and text-speed.asm are
                         # in the globs above);
                         # text_speed_patch.verify() checks the other fixes' regions against its contract.
                         build.TOOLS / "text_speed_patch.py",
                         *(build.text_speed_patch.ASSETS / name for name in
                           ("native.c", "labels.h", "payload.json")))}
        counts, problems = export_fn(a.ws, a.extract, a.output / "export",
                                     statuses=tuple(prior["statuses"]), lenient=False)
        report["export"] = {"counts": dict(counts), "problems": problems}
        if problems or not counts.get("strings"):
            report["reason"] = "fresh export has problems or contains zero strings"
            return report
        # Require every expected archive and at least one bank in it.
        for narc in build.NARCS:
            banks = list((a.output / "export" / narc).glob("[0-9][0-9][0-9][0-9].json"))
            if not banks:
                report["reason"] = f"fresh export contains zero banks for {narc}"
                return report
        report["checks"]["export"] = "passed"
        cm = msgtool.Charmap.load(build.CHARMAPS)
        base = msgtool.load_rom(a.base)
        font = msgtool.get_file(base, msgtool.FONT_NARC_PATH)
        fonts = sorted({row["font"] for row in prior["glyphs"]})
        # the glyph codes the build restored (None: the enabled font fix's codes)
        glyph_codes = tuple(sorted({int(row["code"], 16) for row in prior["glyphs"] if "code" in row})) or None
        if not fonts or not prior["graphics"] or not prior["hardcoded"]:
            report.update(status="incomplete", reason="empty verification metadata for glyphs, graphics or hardcoded patches")
            return report
        report["verification"] = verify_fn(a.rom, a.output / "export", font, fonts, cm,
                                            prior["graphics"], prior["hardcoded"], glyph_codes)
        # This is also required for legacy/missing metadata: inspect the ROM
        # before accepting the absence of a feature report as an opt-out.
        speed = build.verify_text_speed(msgtool.load_rom(a.rom), prior.get("text_speed"))
        report["verification"]["text_speed"] = speed
        if speed["status"] == "passed":
            report["checks"]["text_speed_reproduction"] = build.text_speed_patch.verify_reproducible_payload()
        report["checks"]["artifact"] = "passed"
        # Detect edits while verification was running.
        for name in ("rom", "base", "build_report"):
            if hashes(getattr(a, name)) != report["inputs"][name]:
                raise ValueError(f"{name} changed during verification")
        for name in ("ws", "extract"):
            if tree_hash(getattr(a, name)) != report["inputs"][name]:
                raise ValueError(f"{name} changed during verification")
        for name, fingerprint in report["verification_inputs"].items():
            if hashes(Path(fingerprint["path"])) != fingerprint:
                raise ValueError(f"verification input changed during verification: {name}")
        report["status"] = "passed"
    except ModuleNotFoundError as error:
        report.update(status="incomplete", reason=f"missing dependency: {error}")
    except (Exception, SystemExit) as error:
        report.update(status="failed", reason=f"{type(error).__name__}: {error}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, default=build.OUT_ROM)
    parser.add_argument("--base", type=Path, default=build.ROM_US)
    parser.add_argument("--build-report", type=Path, default=build.BUILD / "build_report.json")
    parser.add_argument("--ws", type=Path, default=ws.DEFAULT_WS)
    parser.add_argument("--extract", type=Path, default=ws.DEFAULT_EXTRACT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", type=Path, help="Additional report target inside work/build")
    a = parser.parse_args(argv)
    root = build.BUILD.resolve()
    parent = (a.output or root / "artifact-checks").resolve()
    if not parent.is_relative_to(root) or parent == root:
        parser.error("--output must be inside ignored work/build")
    if a.json:
        a.json = a.json.resolve()
        if not a.json.is_relative_to(root) or a.json == root:
            parser.error("--json must be inside ignored work/build")
    parent.mkdir(parents=True, exist_ok=True)
    a.output = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=parent))
    report = check(a)
    report["output"] = str(a.output)
    target = a.output / "report.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    if a.json:
        a.json.parent.mkdir(parents=True, exist_ok=True)
        temporary = a.json.with_suffix(a.json.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(a.json)
    print(f"artifact: {report['status']}; report {target}")
    if report.get("reason"):
        print(report["reason"])
    return 0 if report["status"] == "passed" else 2 if report["status"] == "incomplete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
