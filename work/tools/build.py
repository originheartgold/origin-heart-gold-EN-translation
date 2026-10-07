#!/usr/bin/env python3
"""build - build the English WIP ROM of 起源心金 (Origin HeartGold v4.0.3) and its xdelta patch.

Pipeline
  0. fixes    fixes.py: load work/patches/<fix-id>/fix.toml (every change to the Chinese ROM besides the
              message text; overview work/patches/FIXES.md), validate it and select the enabled fixes
              (--only / --without; a selected fix whose `requires` is not selected stops the build);
              work/patches/overlays.toml is checked against the ROM's overlay table in stage 2
  1. export   ws.export(): workspace (statuses tm,draft,reviewed by default) -> work/build/export/<narc>/;
              banks in qa_config.json "compressed_banks" (trainer names a027/0719) are written
              {COMPRESSED} like US 0729, so 8-10 character names fit the battle's u16[8] (D-1326)
  2. insert   msgtool: rebuild a/0/2/7 and battle/string/battle_string.narc from the export into a copy
              of work/rom/origin_v4.0.3_cn.nds (charmaps: charmap_en.tsv + Xzonn zh table, so the
              remaining Chinese strings still encode)
  3. glyphs   fix font-glyphs: restore … “ ” (codes 0x01AF, 0x01B4, 0x01B5) in font NARC a/0/1/6 files
              0/1/2/4 from the USA ROM's font (glyph bitmap + width-table byte); the hack drew them 12/13 px wide
  3a. regen   gfx.regenerate(): run every `gfx.py make-*` generator from the two ROMs into work/graphics
              (generated/*.bin, weather_en/*.png, dex_type_list_en.png, naming_labels_en.png). These
              files hold Nintendo / hack art, so they are git-ignored; the generators are deterministic,
              so a fresh clone builds the same ROM and patch
  3b. graphics  gfx.apply_patches(): the gfx-* fixes' [[graphics]] entries - restore English graphics from the USA
              ROM (type/contest icons, Pokedex type badges, summary labels, YES/NO buttons, Pokegear,
              bag, Pokeathlon SWITCH), hg-engine FAIRY icons and weather letters, PNG-built sheets
              (naming keyboard, weather banners), generated members (Pokedex header/buttons,
              battle info-panel labels, trainer card, link-capture bar, optional bilingual title) and
              USA tile data inside code
              (battle HP-box status icons, overlay 14) - see
              work/notes/graphics_inventory.md
  3c. hardcoded  hardcoded.apply(): fix outfit-chooser-strings ([[string]]) - English for Chinese strings that
              live outside the message NARCs (overlay 58 outfit chooser); written in place when they fit,
              otherwise appended to the overlay and repointed; refuses anything that does not fit. Then the
              selected code/data fixes (namelen, naming-keyboard, msgload, pcbox-name-width, ivev-panel):
              asmpatch.apply() assembles each fix's armips source (work/patches/<fix>/<fix>.asm) over the
              decompressed arm9/overlay images and refuses any change outside the regions its fix.toml
              declares (--code-engine armips, the default; armips v0.11.0 from --armips, $ARMIPS or PATH, see
              work/notes/toolchain.md). --code-engine python applies the frozen halfword patches of
              legacy_code_patches.toml instead (kept to prove both give the same ROM) - see
              work/notes/hardcoded_text.md
  4. write    work/build/origin_hg_v4.0.3_en_wip.nds
  5. verify   re-open with ndspy; message NARCs parse and round-trip (container rebuild byte-identical,
              every bank decodes and re-encodes identically, the exported text is what the ROM holds);
              every compressed-bank name fits its buffer and decompresses to the English;
              glyphs/widths equal the US ones; every patched graphics member is what the stage wrote;
              every hardcoded string/pointer/overlay size is what stage 3c wrote
  6. patch    xdelta3 -e -9 -S lzma -s BASE TARGET work/build/Origin_HeartGold_v4.0.3_EN_wip.xdelta,
              then re-apply it to BASE and compare SHA-1 with TARGET

Usage
  python3 work/tools/build.py [--status tm,draft,reviewed] [--no-patch] [--lenient]
                              [--only FIX,...] [--without FIX,...]
                              [--glyph-fonts 0,1,2,4] [--no-graphics] [--no-regen-graphics]
                              [--no-hardcoded] [--keep-export]
                              [--code-engine armips|python] [--armips PATH]
  --only/--without take fix ids (python3 work/tools/fixes.py list). --no-glyphs, --no-graphics and
  --no-hardcoded leave out every fix of kind font / graphics / strings+code+data; `requires` still holds,
  so e.g. --no-hardcoded alone is refused (gfx-naming-tabs requires naming-keyboard).
Nothing is uploaded anywhere; all outputs stay in work/build/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import asmpatch  # noqa: E402
import fixes as fixreg  # noqa: E402
import gfx  # noqa: E402
import hardcoded  # noqa: E402
import msgtool as m  # noqa: E402
import textmetrics as tm  # noqa: E402
import ws  # noqa: E402

ROM_CN = WORK / "rom" / "origin_v4.0.3_cn.nds"
ROM_US = WORK / "rom" / "Pokemon - HeartGold Version (USA).nds"
BUILD = WORK / "build"
OUT_ROM = BUILD / "origin_hg_v4.0.3_en_wip.nds"
OUT_PATCH = BUILD / "Origin_HeartGold_v4.0.3_EN_wip.xdelta"
CHARMAPS = [str(TOOLS / "charmap_en.tsv"), str(TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv")]
NARCS = {"a027": m.MSG_NARC_PATH, "battle_string": "battle/string/battle_string.narc"}
US_SHA1 = "4fcded0e2713dc03929845de631d0932ea2b5a37"


def log(msg):
    print(f"[build {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------------------
# glyphs
# --------------------------------------------------------------------------------------

def _font_hdr(data: bytes):
    hs, wo, cnt, mw, mh, tw, th = struct.unpack_from("<IIIBBBB", data, 0)
    return hs, wo, cnt, 16 * tw * th


def glyph_spec(fixes=None):
    """(fonts, codes) of the font fixes (default: every enabled fix), or ((), ()) when none is selected."""
    if fixes is None:
        fixes = [f for f in fixreg.load_all() if f.get("enabled")]
    spec = fixreg.font_spec(fixes)
    if spec is None:
        return (), ()
    narc, fonts, codes = spec
    assert narc == m.FONT_NARC_PATH, f"font fix targets {narc}, the build restores {m.FONT_NARC_PATH}"
    return fonts, codes


def restore_glyphs(font_narc: bytes, us_font_narc: bytes, fonts=None, codes=None):
    """Copy glyph bitmaps + widths for `codes` from the US font files into the hack's font files.
    fonts/codes default to the enabled font fix (font-glyphs: … “ ” in fonts 0/1/2/4)."""
    if fonts is None or codes is None:
        f, c = glyph_spec()
        fonts = f if fonts is None else fonts
        codes = c if codes is None else codes
    narc = m.Narc.parse(font_narc)
    us = m.Narc.parse(us_font_narc)
    files = list(narc.files)
    changes = []
    for fi in fonts:
        d = bytearray(files[fi])
        u = bytes(us.files[fi])
        hs, wo, cnt, gsz = _font_hdr(d)
        uhs, uwo, ucnt, ugsz = _font_hdr(u)
        assert gsz == ugsz, f"font {fi}: glyph size differs ({gsz} vs {ugsz})"
        for c in codes:
            assert c <= cnt and c <= ucnt, f"font {fi}: code {c:04X} outside width table"
            g_old, w_old = bytes(d[hs + (c - 1) * gsz: hs + c * gsz]), d[wo + c - 1]
            g_new, w_new = u[uhs + (c - 1) * gsz: uhs + c * gsz], u[uwo + c - 1]
            d[hs + (c - 1) * gsz: hs + c * gsz] = g_new
            d[wo + c - 1] = w_new
            changes.append((fi, c, w_old, w_new, g_old != g_new))
        files[fi] = bytes(d)
    out = m.Narc(files, narc.btnf, narc.pad_byte, narc.pad_last, narc.bom_ver, narc.size_quirks)
    return out.build(), changes


# --------------------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------------------

def verify_name_bank(data: bytes, spec: dict) -> str:
    """A fixed-buffer name bank (trainer names 0719, D-1326): every stored string fits u16[max_units]
    (EnemyTrainerSet_Init copies it with CopyStringToU16Array(.., 8)); raw_ids are plain text; every
    other English name is {COMPRESSED} and decompresses (the game's 9-bit scheme, as in
    String_Cat_HandleTrainerName, hack arm9 0x0202703C) to exactly its plain encoding."""
    _, strings, _ = m.decrypt_bank(data)
    n_comp = n_plain = 0
    for sid, units in enumerate(strings):
        size = units.index(m.CODE_END) if m.CODE_END in units else len(units)
        assert size + 1 <= spec["max_units"], f"name #{sid}: {size + 1} units > {spec['max_units']}"
        if units and units[0] == m.CODE_COMPRESSED:
            assert sid not in spec["raw_ids"], f"name #{sid} must stay uncompressed (printed raw)"
            codes, _ = m.decompress_units(units)
            assert m.compress_codes(codes) == units[:size + 1], f"name #{sid}: compression round trip differs"
            assert all(c < 0x1FF for c in codes)
            n_comp += 1
        else:
            n_plain += 1
    return f"ok ({n_comp} compressed, {n_plain} plain, all fit u16[{spec['max_units']}])"


def verify_rom(out_rom: Path, export_dir: Path, us_font_narc: bytes, fonts, cm, gfx_report=(), hc_report=None,
               glyph_codes=None):
    import ndspy.rom
    rom = ndspy.rom.NintendoDSRom.fromFile(str(out_rom))
    res = {"title": rom.name.decode("ascii", "replace"), "code": bytes(rom.idCode).decode("ascii", "replace"),
           "files": len(rom.files)}
    for narc_key, path in NARCS.items():
        raw = m.get_file(rom, path)
        narc = m.Narc.parse(raw)
        assert narc.build() == raw, f"{path}: NARC container rebuild not byte-identical"
        mism = 0
        n_str = 0
        for bi, data in enumerate(narc.files):
            obj = m.bank_to_json(bi, data, cm)
            assert m.json_to_bank(obj, cm) == data, f"{path} bank {bi}: re-encode differs"
            exp = json.loads((export_dir / narc_key / f"{bi:04d}.json").read_text(encoding="utf-8"))
            want = {s["id"]: s["text"] for s in exp["strings"]}
            for s in obj.get("strings", []):
                n_str += 1
                if "raw_hex" in s:
                    continue
                if s["text"] != want.get(s["id"]):
                    # the decoder canonicalises; compare encoded units instead of text
                    if m.encode_text(s["text"], cm) != m.encode_text(want.get(s["id"], ""), cm):
                        mism += 1
        assert mism == 0, f"{path}: {mism} strings differ from the export"
        res[path] = {"banks": len(narc.files), "strings": n_str, "roundtrip": "ok", "matches_export": True}
        for bi, data in enumerate(narc.files):
            spec = tm.compressed_spec(narc_key, bi)
            if spec is not None:
                res[f"{narc_key}/{bi:04d}"] = verify_name_bank(data, spec)
    if glyph_codes is None:
        glyph_codes = glyph_spec()[1]
    font = m.Narc.parse(m.get_file(rom, m.FONT_NARC_PATH))
    us = m.Narc.parse(us_font_narc)
    for fi in fonts:
        d, u = font.files[fi], us.files[fi]
        hs, wo, _, gsz = _font_hdr(d)
        uhs, uwo, _, _ = _font_hdr(u)
        for c in glyph_codes:
            assert d[hs + (c - 1) * gsz: hs + c * gsz] == u[uhs + (c - 1) * gsz: uhs + c * gsz]
            assert d[wo + c - 1] == u[uwo + c - 1]
    res["glyphs"] = "ok"
    narcs = {}
    n_code = gfx.verify_code_rows(gfx.CodeView(rom), gfx_report)
    for r in gfx_report:
        if "code" in r:
            continue
        if r["narc"] not in narcs:
            narcs[r["narc"]] = m.Narc.parse(m.get_file(rom, r["narc"]))
        got = hashlib.sha1(narcs[r["narc"]].files[r["member"]]).hexdigest()[:12]
        assert got == r["sha1"], f"graphics {r['narc']} #{r['member']}: {got} != {r['sha1']}"
    res["graphics"] = f"ok ({len(gfx_report) - n_code} members, {n_code} code ranges)"
    if gfx_report:
        res["graphics_layouts"] = gfx.check_layouts(lambda p: m.get_file(rom, p), gfx.CodeView(rom))
    if hc_report is not None:
        res["hardcoded"] = hardcoded.verify(rom, hc_report, cm)
    return res


# --------------------------------------------------------------------------------------

def build_paths(work_dir, out=None, patch=None):
    """All generated state belongs to the selected work directory."""
    directory = Path(work_dir)
    return {"work": directory, "export": directory / "export",
            "report": directory / "build_report.json",
            "rom": Path(out) if out is not None else directory / OUT_ROM.name,
            "patch": Path(patch) if patch is not None else directory / OUT_PATCH.name}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", default="tm,draft,reviewed")
    ap.add_argument("--ws", default=str(ws.DEFAULT_WS))
    ap.add_argument("--extract", default=str(ws.DEFAULT_EXTRACT))
    ap.add_argument("--rom", default=str(ROM_CN))
    ap.add_argument("--base", default=str(ROM_US), help="USA HeartGold dump: font source and patch base")
    ap.add_argument("--work-dir", default=str(BUILD), help="Directory for export, build report and patch verification scratch files")
    ap.add_argument("--out", help="ROM output (default: selected work directory / standard ROM filename)")
    ap.add_argument("--patch", help="Patch output (default: selected work directory / standard patch filename)")
    ap.add_argument("--only", help="build with exactly these fixes (comma-separated ids, see fixes.py list); "
                                   "a disabled fix named here is applied too")
    ap.add_argument("--without", help="leave out these fixes (comma-separated ids)")
    ap.add_argument("--glyph-fonts", default=None, help="font files for the font fix (default: from the fix, 0,1,2,4)")
    ap.add_argument("--no-glyphs", action="store_true", help="leave out every font fix")
    ap.add_argument("--no-graphics", action="store_true", help="leave out every graphics fix")
    ap.add_argument("--no-regen-graphics", action="store_true",
                    help="use the generated graphics already in work/graphics instead of rebuilding them")
    ap.add_argument("--no-hardcoded", action="store_true",
                    help="leave out every strings, code and data fix (hardcoded stage)")
    ap.add_argument("--code-engine", choices=("armips", "python"), default="armips",
                    help="how the code/data fixes are applied: their armips sources (default), or the legacy "
                         "Python halfword patches (legacy_code_patches.toml; for the equivalence check)")
    ap.add_argument("--armips", help=f"armips executable (default: ${asmpatch.ENV_VAR}, then PATH); must be "
                                     f"{asmpatch.PINNED_VERSION}")
    ap.add_argument("--no-patch", action="store_true")
    ap.add_argument("--no-verify", action="store_true")
    ap.add_argument("--lenient", action="store_true", help="unencodable en falls back to zh instead of failing")
    ap.add_argument("--keep-export", action="store_true")
    a = ap.parse_args(argv)

    paths = build_paths(a.work_dir, a.out, a.patch)
    out_rom, patch, base = paths["rom"], paths["patch"], Path(a.base)
    paths["work"].mkdir(parents=True, exist_ok=True)
    statuses = tuple(s.strip() for s in a.status.split(",") if s.strip())
    report = {"statuses": statuses}

    # 0. fixes: everything the build changes besides the message text
    without_kinds = (("font",) if a.no_glyphs else ()) + (("graphics",) if a.no_graphics else ()) + \
        (("strings", "code", "data") if a.no_hardcoded else ())
    try:
        active = fixreg.active_fixes(a.only, a.without, without_kinds)
    except fixreg.FixError as ex:
        sys.exit(str(ex))
    kinds = {f["kind"] for f in active}
    fonts, glyph_codes = glyph_spec(active)
    if a.glyph_fonts is not None and fonts:
        fonts = tuple(int(x) for x in a.glyph_fonts.split(","))
    report["fixes"] = {"only": a.only, "without": a.without, "without_kinds": list(without_kinds),
                       "applied": [f["id"] for f in active]}
    log(f"fixes: {len(active)} selected: {', '.join(f['id'] for f in active)}")

    # 1. export
    export_dir = paths["export"]
    if export_dir.exists():
        shutil.rmtree(export_dir)
    log(f"export workspace ({','.join(statuses)}) -> {export_dir}")
    counts, problems = ws.export(Path(a.ws), Path(a.extract), export_dir, statuses, a.lenient)
    unenc = [p for p in problems if p[3].startswith("unencodable")]
    for p in problems[:20]:
        print("  %s/%04d #%d: %s" % p, file=sys.stderr)
    if unenc and not a.lenient:
        sys.exit(f"{len(unenc)} unencodable strings; fix them (qa.py check) or pass --lenient")
    report["export"] = dict(counts, problems=len(problems))
    log(f"export: {dict(counts)}; problems {len(problems)}")
    bsha = sha1(base)
    report["base"] = {"path": str(base), "sha1": bsha, "is_no_intro_usa": bsha == US_SHA1}
    if bsha != US_SHA1:
        log(f"WARNING: base sha1 {bsha} is not the No-Intro USA dump {US_SHA1}")

    # 2. insert
    cm = m.Charmap.load(CHARMAPS)
    log(f"load {a.rom}")
    rom = m.load_rom(a.rom)
    try:
        fixreg.check_overlay_bases(rom)
    except fixreg.FixError as ex:
        sys.exit(str(ex))
    report["code_engine"] = a.code_engine
    armips = None
    if a.code_engine == "armips" and fixreg.code_entries_fixes(active):
        try:
            armips = asmpatch.find_armips(a.armips)
            version = asmpatch.check_armips(armips)
        except asmpatch.AsmError as ex:
            sys.exit(str(ex))
        log(f"armips {version}: {armips}")
    for narc_key, path in NARCS.items():
        tmpl = m.Narc.parse(m.get_file(rom, path))
        narc = m.build_msg_narc(tmpl, export_dir / narc_key, cm)
        m.set_file(rom, path, narc.build())
        log(f"inserted {narc_key} -> {path} ({len(narc.files)} banks)")

    # 3. glyphs
    us_rom = m.load_rom(base)
    us_font = m.get_file(us_rom, m.FONT_NARC_PATH)
    del us_rom
    if fonts:
        new_font, changes = restore_glyphs(m.get_file(rom, m.FONT_NARC_PATH), us_font, fonts, glyph_codes)
        m.set_file(rom, m.FONT_NARC_PATH, new_font)
        report["glyphs"] = [{"font": f, "code": "%04X" % c, "width": [wo, wn], "bitmap_changed": ch}
                            for f, c, wo, wn, ch in changes]
        log("glyphs restored: " + ", ".join(f"f{f}:{c:04X} {wo}->{wn}px" for f, c, wo, wn, _ in changes))

    # 3a. regenerate the git-ignored generated graphics from the ROMs
    if "graphics" in kinds and not a.no_regen_graphics:
        written = gfx.regenerate(a.rom, base, log=log)
        report["graphics_regenerated"] = {str(p.relative_to(gfx.GRAPHICS)): sha1(p) for p in written}
        log(f"graphics regenerated: {len(written)} files in {gfx.GRAPHICS}")

    # 3b. graphics
    gfx_report = []
    if "graphics" in kinds:
        us_rom = m.load_rom(base)
        gfx_report = gfx.apply_patches(lambda p: m.get_file(rom, p), lambda p, b: m.set_file(rom, p, b),
                                       lambda p: m.get_file(us_rom, p), manifest=gfx.load_manifest(fixes=active),
                                       code=gfx.CodeView(rom), us_code=gfx.CodeView(us_rom), check_layout=True)
        del us_rom
        report["graphics"] = gfx_report
        log(f"graphics: {sum('code' not in r for r in gfx_report)} NARC members and "
            f"{sum('code' in r for r in gfx_report)} code ranges patched by "
            f"{len({r.get('fix') for r in gfx_report})} graphics fixes")

    # 3c. hardcoded strings (outside the message NARCs)
    hc_report = None
    if kinds & {"strings", "code", "data"}:
        try:
            if a.code_engine == "python":
                hc_report = hardcoded.apply(rom, cm, cfg=hardcoded.load(fixes=active),
                                            code_patches=hardcoded.load_code_patches(fixes=active))
            else:
                hc_report = hardcoded.apply(rom, cm, cfg=hardcoded.load(fixes=active), code_patches=[])
                if armips is not None:
                    asm_report = asmpatch.apply(rom, active, armips)
                    hc_report["code_patches"] = asm_report["code_patches"]
                    hc_report["files"].update(asm_report["files"])
                    hc_report["armips"] = asm_report["armips"]
        except (hardcoded.HardcodedError, asmpatch.AsmError) as ex:
            sys.exit(str(ex))
        hc_report["code_engine"] = a.code_engine
        report["hardcoded"] = hc_report
        log(f"hardcoded: {len(hc_report['strings'])} strings written "
            f"({sum(r['mode'] == 'relocated' for r in hc_report['strings'])} relocated), "
            f"{hc_report['todo']} untranslated, {len(hc_report['code_patches'])} code/data regions "
            f"({a.code_engine})")

    # 4. write
    log(f"write {out_rom}")
    rom.saveToFile(str(out_rom))
    del rom
    report["rom"] = {"path": str(out_rom), "size": out_rom.stat().st_size, "sha1": sha1(out_rom)}
    log(f"ROM {out_rom.stat().st_size:,} bytes sha1 {report['rom']['sha1']}")

    # 5. verify
    if not a.no_verify:
        log("verify: ndspy parse, NARC round-trip, text == export, glyphs, graphics, hardcoded")
        report["verify"] = verify_rom(out_rom, export_dir, us_font, fonts, cm, gfx_report, hc_report,
                                      glyph_codes)
        log(f"verify ok: {report['verify']}")

    # 6. patch
    if not a.no_patch:
        if patch.exists():
            patch.unlink()
        log(f"xdelta3 -e -9 -S lzma -s BASE TARGET {patch}")
        subprocess.run(["xdelta3", "-e", "-9", "-S", "lzma", "-s", str(base), str(out_rom), str(patch)], check=True)
        with tempfile.TemporaryDirectory(dir=paths["work"]) as td:
            back = Path(td) / "reapplied.nds"
            subprocess.run(["xdelta3", "-d", "-s", str(base), str(patch), str(back)], check=True)
            ok = sha1(back) == report["rom"]["sha1"]
        report["patch"] = {"path": str(patch), "size": patch.stat().st_size, "sha1": sha1(patch),
                           "reapply_sha1_match": ok}
        log(f"patch {patch.stat().st_size:,} bytes; re-apply sha1 match: {ok}")
        if not ok:
            sys.exit("patch re-application produced a different file")

    if not a.keep_export:
        shutil.rmtree(export_dir, ignore_errors=True)
    paths["report"].write_text(json.dumps(report, indent=1, ensure_ascii=False))
    log(f"done; report {paths['report']}")


if __name__ == "__main__":
    main()
