#!/usr/bin/env python3
"""qa - QA gate and auto-wrap for the 起源心金 English translation workspace.

    python3 work/tools/qa.py check <workspace dir | narc dir | bank file> [--json OUT|-]
                                   [--font-set vanilla_us|hack_v4] [--status tm,draft,reviewed]
                                   [--max-print 40] [--no-glossary]
    python3 work/tools/qa.py wrap --zh ZH --en EN [--category dialogue] [--mode auto|page|scroll]
    python3 work/tools/qa.py wrap <bank file> [--ids 3,5-9] [--in-place] [--reflow] [--mode ...]
    python3 work/tools/qa.py variants [path] [--min-len 6] [--no-punct] [--json OUT|-] [--max-print 60]

check validates every string that has an English text (en != null):
  errors   tag_mismatch  non-layout tags ({VAR:..}, {COMPRESSED}, {U+..}) differ from zh (multiset)
           tag_order     COLOR/SIZE tag sequence differs, or a leading/trailing control tag moved
                         ({VAR:FF01:100}{SCROLL}{VAR:FF01:200} counts as a page break inside one SIZE span)
           cjk           Chinese/Japanese/Korean characters left in en
           unencodable   a character has no code in charmap_en.tsv (e.g. ASCII ' or ": use ’ ‘ “ ”)
           missing_glyph character has no glyph (width 0) in the box's font
           line_too_wide a line exceeds the box width (placeholders at typical width)
           too_many_lines more lines on one box view than the box holds (2 for dialogue)
           too_many_units more stored code units (incl. terminator) than the screen's buffer holds
                         (category max_units; item descriptions: 114, D-1507)
           name_too_long name exceeds its character limit (species 10, moves/items/abilities 12, ...)
           layout_in_name a line break inside a single-line name
           empty         en is empty but zh is not
           prefix_split  a line ends with Mt./Prof./S.S./Lt./Mr./Mrs./Ms./Dr. (name on the next line), Lv./No.
                         before a number, or Pokémon before Center/League (TMs./HMs. are not prefixes)
           glossary_name (species/moves) an old name (Faint Attack), a spelling variant or a misspelling of
                         a species or move name in prose (see glossary_name below)
  warnings line_may_overflow  fits with typical placeholders, not with worst-case ones
           line_past_frame a line is wider than the category's soft_line_px (fits the window, but runs into
                         the panel frame or a picture; item descriptions 200 px, D-1512)
           needs_vanilla_glyphs fits only with the vanilla US …/“/” widths (hack font has 12 px ones)
           wider_than_zh / more_lines_than_zh   ('ui' banks with unknown box size)
           fullwidth     full-width / CJK punctuation or digits (，。！１　 etc.)
           glossary      zh contains a glossary term whose English is missing from en
           number_missing a number in zh does not appear in en
           currency      zh has 元 but en has no $
           whitespace    leading/trailing/double spaces not present in zh
           trailing_layout zh ends with a layout tag that en does not
           zh_changed    the source text changed after this translation was made
           mid_sentence_page a {SCROLL} page ends mid-sentence where the Chinese page ends a sentence
           glossary_name (items/abilities; name-bank abbreviations in prose) capitalised name spans compared
                         with the glossary, name banks 0232/0739/0219/0711 and register terms; reviewed
                         false positives: qa_config.json glossary_names.allow
variants reports zh_variant groups: identical Chinese (layout ignored) with different English in the same
  category; strings whose notes say context/branch and battle owner variants (The wild/The foe’s) are skipped.
Per-string suppression: "qa_ignore": ["glossary", "number_missing", "glossary:术语", ...].
Exit status: 1 if any error, else 0.  Box/categories: work/tools/qa_config.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import textmetrics as tm  # noqa: E402
import zh_redact  # noqa: E402

EXTRACT_DIR = WORK / "extract" / "v4"   # source of redacted zh (zh_redact.py), filled in memory only

GLOSSARY_DIR = WORK / "glossary"
FW_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
ORDERED_CMDS_HI = (0xFF,)          # COLOR / SIZE / FF02: order matters
ANCHOR_CMDS_HI = (0x02, 0xFF)      # YESNO/PAUSE/WAIT/CURSOR/ALIGN/COLOR/SIZE: position at start/end matters


# --------------------------------------------------------------------------------------
# category resolution
# --------------------------------------------------------------------------------------

def bank_category(bank: dict, cfg: dict) -> str:
    if bank.get("category"):
        return bank["category"]
    key = "%s/%04d" % (bank["narc"], bank["bank"])
    if key in cfg["banks"]:
        return cfg["banks"][key]
    if any("{SCROLL}" in e["zh"] or "{CLEAR}" in e["zh"] for e in bank["strings"]):
        return "dialogue"
    return "ui"


def string_categories(bank: dict, cfg: dict) -> dict:
    """qa_config.json "string_categories": {"<narc>/<NNNN>": {"<ids>": category}} -> {id: category}.
    ids use the --ids syntax ("10-29,31"); later keys override earlier ones. A string's own "category"
    field still wins (see check_bank)."""
    spec = cfg.get("string_categories", {}).get("%s/%04d" % (bank["narc"], bank["bank"]), {})
    out = {}
    for ids, cat in spec.items():
        for i in _parse_ids(ids):
            out[i] = cat
    return out


# --------------------------------------------------------------------------------------
# glossary
# --------------------------------------------------------------------------------------

def _norm_en(s: str) -> str:
    s = s.lower().replace("é", "e").replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9]", "", s)


@lru_cache(maxsize=None)
def load_glossary(gdir: str = str(GLOSSARY_DIR)):
    """-> {category: {zh: [acceptable English variants]}} incl. README abbreviations."""
    gdir = Path(gdir)
    abbrev = {}
    try:
        sys.path.insert(0, str(gdir))
        import manual_overrides as mo  # type: ignore
        abbrev = {k: re.sub(r"\s*\(.*\)$", "", v) for k, v in getattr(mo, "ABBREV", {}).items()}
    except Exception:
        pass
    out = {}
    for p in sorted(gdir.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        cat = p.stem
        m = {}
        for zh, v in d.items():
            en = v.get("en") if isinstance(v, dict) else v
            if not en:
                continue
            vs = [en]
            base = re.sub(r"\s*\(.*\)$", "", en)
            if base != en:
                vs.append(base)
            for x in list(vs):
                if x in abbrev:
                    vs.append(abbrev[x])
            m[zh] = vs
        out[cat] = m
    return out, abbrev


@lru_cache(maxsize=None)
def glossary_matcher(cats: tuple, min_len: int, skip: tuple):
    g, _ = load_glossary()
    terms = {}
    for c in cats:
        for zh, vs in g.get(c, {}).items():
            if len(zh) < min_len or zh in skip or re.search(r"[（(]", zh):
                continue
            terms.setdefault(zh, [])
            for v in vs:
                if v not in terms[zh]:
                    terms[zh].append(v)
    if not terms:
        return None, {}
    rx = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)))
    return rx, terms


# --------------------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------------------

def _cmd_hi(tag: str) -> int | None:
    if tag.startswith("VAR:"):
        return tm.var_cmd(tag) >> 8
    return None


def _printable_tokens(text):
    return [(k, v) for k, v in tm.tokenize(text) if k != "layout"]


# A 200 % shout split over pages repeats its SIZE tags: "{end size}{SCROLL}{start size}" counts as a page
# break inside one SIZE span, so it must not change the tag multiset or order (heap_audit.md, Misty scene).
SIZE_PAGE_SPLIT = re.compile(r"\{VAR:FF01:100\}\{SCROLL\}\{VAR:FF01:(\d+)\}")


def _merge_size_pages(text: str) -> str:
    return SIZE_PAGE_SPLIT.sub(lambda m: "{SCROLL}" if m.group(1) != "100" else m.group(0), text or "")


def check_tags(zh: str, en: str, add):
    zh, en = _merge_size_pages(zh), _merge_size_pages(en)
    zt, et = tm.non_layout_tags(zh), tm.non_layout_tags(en)
    zc, ec = Counter(zt), Counter(et)
    if zc != ec:
        missing = list((zc - ec).elements())
        extra = list((ec - zc).elements())
        add("error", "tag_mismatch", "missing %s; extra %s" % (
            " ".join("{%s}" % t for t in missing) or "-", " ".join("{%s}" % t for t in extra) or "-"))
        return
    zo = [t for t in zt if _cmd_hi(t) in ORDERED_CMDS_HI]
    eo = [t for t in et if _cmd_hi(t) in ORDERED_CMDS_HI]
    if zo != eo:
        add("error", "tag_order", "COLOR/SIZE sequence differs: zh %s / en %s" % (zo, eo))
    zp, ep = _printable_tokens(zh), _printable_tokens(en)
    if zp and ep:
        for pos, name in ((0, "first"), (-1, "last")):
            zk, zv = zp[pos]
            if zk == "tag" and zv == "COMPRESSED" or (zk == "var" and _cmd_hi(zv) in ANCHOR_CMDS_HI):
                if ep[pos] != (zk, zv):
                    add("error", "tag_order", "{%s} must stay %s" % (zv, name))
    zl, el = tm.tokenize(zh), tm.tokenize(en)
    if zl and zl[-1][0] == "layout" and (not el or el[-1] != zl[-1]):
        add("warning", "trailing_layout", "zh ends with {%s}" % zl[-1][1])


def check_chars(en: str, font: int, fset: dict, cm_en, add):
    vis = tm.visible_text(en)
    cj = sorted(set(tm.CJK_RE.findall(vis)))
    if cj:
        add("error", "cjk", "CJK left: " + "".join(cj[:20]))
    fw = sorted(set(tm.FULLWIDTH_RE.findall(vis)))
    if fw:
        add("warning", "fullwidth", "full-width/CJK punctuation: " + " ".join(fw))
    import msgtool as m
    try:
        m.encode_text(en, cm_en)
    except ValueError as ex:
        msg = str(ex)
        hint = ""
        if "'" in vis or '"' in vis:
            hint = " (use ’ ‘ “ ” — qa.py wrap normalizes ASCII quotes)"
        add("error", "unencodable", msg + hint)
    miss = sorted(ch for ch in set(vis) if ch in cm_en.enc and not tm.CJK_RE.match(ch)
                  and tm.char_width(ch, font, fset) is None)
    if miss:
        add("error", "missing_glyph", "no glyph in font %d: %s" % (font, " ".join(miss)))


def check_layout(zh, en, cat: dict, catname: str, narc: str, cfg: dict, fset: dict, fset_hack: dict | None,
                 bank_ctx: dict, add):
    font = cat.get("font", 1)
    sev = cat.get("severity", "error")
    soft = "warning"
    spacing = cat.get("char_spacing", 0)

    def measure(text, which, widths):
        """measure_lines plus the screen's extra pixels per character (char_spacing, e.g. Pokédex category)."""
        out = tm.measure_lines(text, font, cfg, narc, which, widths)
        if spacing:
            for ln in out:
                ln["px"] += spacing * len(tm.visible_text(ln["text"]))
        return out

    lines = measure(en, "typ", fset)
    if "line_px" in cat:
        lim = cat["line_px"]
        lines_max = measure(en, "max", fset)
        lines_hack = measure(en, "typ", fset_hack) if fset_hack else None
        # the source proves the real box: if a zh line is wider than the nominal box, the box is wider
        zlim = max(ln["px"] for ln in measure(zh, "typ", fset_hack or fset))
        for i, ln in enumerate(lines):
            if ln["px"] > lim and ln["px"] <= zlim:
                add(soft, "line_too_wide", "line %d is %d px > %d, but zh has a %d px line (larger box?): %s"
                    % (i + 1, ln["px"], lim, zlim, ln["text"]))
            elif ln["px"] > lim:
                add(sev, "line_too_wide", "line %d is %d px > %d: %s" % (i + 1, ln["px"], lim, ln["text"]))
            elif lines_max[i]["px"] > lim:
                add(soft, "line_may_overflow", "line %d is %d px with worst-case placeholders > %d: %s"
                    % (i + 1, lines_max[i]["px"], lim, ln["text"]))
            elif lines_hack and lines_hack[i]["px"] > lim:
                add(soft, "needs_vanilla_glyphs", "line %d is %d px with the hack's 12 px …/“/” glyphs: %s"
                    % (i + 1, lines_hack[i]["px"], ln["text"]))
            if ln["px"] <= lim and ln["px"] > cat.get("soft_line_px", lim):
                add(soft, "line_past_frame", "line %d is %d px > %d (%s): %s"
                    % (i + 1, ln["px"], cat["soft_line_px"], cat.get("soft_desc", "soft limit"), ln["text"]))
    if cat.get("relative_to_zh"):
        zmax = bank_ctx.get("zh_max_px")
        zlines = tm.measure_lines(zh, font, cfg, narc, "typ", fset)
        if zmax:
            for i, ln in enumerate(lines):
                if ln["px"] > zmax:
                    add(soft, "wider_than_zh", "line %d is %d px; widest Chinese line in this bank is %d px: %s"
                        % (i + 1, ln["px"], zmax, ln["text"]))
        if len(lines) > len(zlines):
            add(soft, "more_lines_than_zh", "%d lines vs %d in zh" % (len(lines), len(zlines)))
    if "lines" in cat:
        maxl = cat["lines"]
        if maxl == 1:
            if tm.layout_tags(en) and not tm.layout_tags(zh):
                add(sev, "layout_in_name", "line break in a single-line %s string" % catname)
        else:
            n, nz = tm.page_lines(en), tm.page_lines(zh)
            if n > maxl:
                if nz >= n:
                    add(soft, "too_many_lines", "%d lines in one box view (zh also has %d)" % (n, nz))
                else:
                    add(sev, "too_many_lines", "%d lines in one box view > %d" % (n, max(maxl, nz)))
    if "max_chars" in cat:
        vis = tm.visible_text(en)
        if len(vis) > cat["max_chars"]:
            add(sev, "name_too_long", "%d chars > %d: %s" % (len(vis), cat["max_chars"], vis))
    if "max_units" in cat:
        import msgtool as m
        try:
            n = len(m.encode_text(en, _cm_en()))
        except ValueError:
            n = None                                 # check_chars already reports it
        if n is not None and n > cat["max_units"]:
            add(sev, "too_many_units", "%d stored code units (incl. terminator) > %d: the screen shows nothing"
                % (n, cat["max_units"]))


def _spacing_text(text: str) -> str:
    """Keep rendered placeholders as occupied text, but discard nonprinting controls."""
    out = []
    for kind, value in tm.tokenize(text):
        if kind == "layout":
            out.append("\n")
        elif kind == "text":
            out.append(value)
        elif kind == "var":
            if tm.var_cmd(value) >> 8 not in (0x02, 0xFF):
                out.append("□")
        elif value != "COMPRESSED":
            # Encoded glyphs (U+XXXX), and conservatively unknown tags, occupy text.
            out.append("□")
    return "".join(out)


def _has_currency_amount(text: str) -> bool:
    out = []
    for kind, value in tm.tokenize(text):
        if kind == "text":
            out.append(value)
        elif kind == "layout":
            out.append("\n")
        elif kind == "var":
            cmd = tm.var_cmd(value)
            if 0x0132 <= cmd <= 0x013B:
                out.append("#")  # Numeric STRVAR_1, not a name or layout control.
            elif cmd >> 8 not in (0x02, 0xFF):
                out.append("□")
        elif value != "COMPRESSED":
            out.append("□")
    # 元气 is a word (including the Revive item names), not the currency unit 元.
    return bool(re.search(r"[0-9０-９#]\s*元(?!气)", "".join(out)))


def check_misc(zh, en, add):
    if tm.visible_text(zh).strip() and not en.strip():
        add("error", "empty", "en is empty")
        return
    zv, ev = tm.visible_text(zh), tm.visible_text(en)
    # Removing tags concatenates unrelated runs (e.g. TM14{NEWLINE}5500).
    # Match within literal text tokens; never interpret digits in VAR payloads.
    znums = [n for kind, value in tm.tokenize(zh) if kind == "text"
             for n in re.findall(r"\d+", value.translate(FW_DIGITS))]
    enums = [n for kind, value in tm.tokenize(en) if kind == "text"
             for n in re.findall(r"\d+", value.translate(FW_DIGITS))]
    ec = Counter(enums)
    for n in znums:
        if ec[n] > 0:
            ec[n] -= 1
        else:
            add("warning", "number_missing", "number %s from zh not found in en" % n)
    if _has_currency_amount(zh) and "$" not in ev:
        add("warning", "currency", "zh has 元; en has no $")
    for s in _spacing_text(en).split("\n"):
        if (s != s.strip() and s.strip()) or "  " in s:
            zsegs = _spacing_text(zh).split("\n")
            if not any(z != z.strip() or "  " in z for z in zsegs):
                add("warning", "whitespace", "leading/trailing/double space in %r" % s)
                break


def _route_template_matches(zh: str, en: str) -> bool:
    """Resolve the glossary's literal Route N template only for explicit numbers."""
    source = _spacing_text(zh).translate(FW_DIGITS)
    routes = re.findall(r"(?<![0-9□.,])([0-9]+)号道路", source)
    if not routes or len(routes) != source.count("号道路"):
        return False  # A variable or unresolved identifier cannot prove equivalence.
    needed = Counter(int(n) for n in routes)
    # A visible dynamic suffix or decimal continuation makes this a different or
    # unknown identifier. Zero-width colour/size controls are already removed.
    found = Counter(int(n) for n in re.findall(
        r"\bRoute\s+([0-9]+)(?![\w□]|[.,][0-9□])", _spacing_text(en), re.I))
    return all(found[n] >= count for n, count in needed.items())


def _count_noun_plural_matches(variant: str, en: str) -> bool:
    # These two glossary count nouns have common prose plurals; names remain atomic.
    match = re.search(r"\b(Berry|Candy)$", variant)
    if not match:
        return False
    plural = variant[:match.start()] + {"Berry": "Berries", "Candy": "Candies"}[match.group()]
    words = re.split(r"\s+", plural)
    pattern = r"\b" + r"\s+".join(re.escape(word) for word in words) + r"\b"
    return bool(re.search(pattern, _spacing_text(en), re.I))


def check_glossary(zh, en, catname, cfg, add):
    gcfg = cfg.get("glossary", {})
    g, _ = load_glossary()
    if catname in g and zh in g[catname]:          # a name bank entry: must be one of the variants
        vs = g[catname][zh]
        if tm.visible_text(en) not in vs and _norm_en(tm.visible_text(en)) not in {_norm_en(v) for v in vs}:
            add("warning", "glossary", "glossary %s says %s for %s" % (catname, " / ".join(vs), zh))
        return
    if "max_chars" in cfg["categories"].get(catname, {}):   # names are atomic: no substring matching
        return
    rx, terms = glossary_matcher(tuple(gcfg.get("prose_categories", [])), gcfg.get("min_term_len", 2),
                                 tuple(gcfg.get("skip_terms", [])))
    if rx is None:
        return
    ne = _norm_en(tm.visible_text(en))
    seen = set()
    for mt in rx.finditer(tm.visible_text(zh)):
        t = mt.group(0)
        if t in seen:
            continue
        seen.add(t)
        if t == "号道路" and "Route N" in terms[t]:
            matched = _route_template_matches(zh, en)
        else:
            matched = any((_norm_en(v) and _norm_en(v) in ne) or _count_noun_plural_matches(v, en)
                          for v in terms[t])
        if not matched:
            add("warning", "glossary", "%s → %s not found" % (t, " / ".join(terms[t][:3])), key="glossary:" + t)


def check_name_buffer(sid: int, en: str, spec: dict, cm_en, add):
    """Names the build stores {COMPRESSED} (qa_config "compressed_banks", trainer names 0719, D-1326).
    The battle copies each name into u16[max_units]; a name that doesn't fit is dropped (garbage name).
    Compressed: every code must be < 0x1FF (9 bits) and the packed name must fit (<= 10 characters).
    raw_ids (Frontier Brains, printed without the formatter): plain, <= raw_max_chars."""
    import msgtool as m
    if "{" in en:
        add("error", "name_tag", "tags are not allowed in a name the game stores compressed: %s" % en)
        return
    try:
        units = m.encode_text(en, cm_en)
    except ValueError:
        return                                   # check_chars already reports it
    if sid in spec["raw_ids"]:
        if len(tm.visible_text(en)) > spec["raw_max_chars"]:
            add("error", "name_too_long", "%d chars > %d: %s (printed uncompressed on the Frontier VS screen)"
                % (len(tm.visible_text(en)), spec["raw_max_chars"], en))
        return
    wide = sorted({"%s U+%04X" % (cm_en.canonical(c) or "?", c) for c in units[:-1] if c >= 0x1FF})
    if wide:
        add("error", "not_compressible", "code(s) >= 0x1FF cannot be stored compressed: %s" % ", ".join(wide))
        return
    try:
        m.stored_name_text(en, cm_en, compress=True, max_units=spec["max_units"])
    except ValueError as ex:
        add("error", "name_buffer", str(ex))


# --------------------------------------------------------------------------------------
# line/page-break lints (prefix_split, mid_sentence_page)
# --------------------------------------------------------------------------------------

BREAK_SPLIT_RE = re.compile(r"\{(?:NEWLINE|SCROLL|CLEAR)\}|\n")
# honorifics/abbreviations that must stay on the line of the word or number after them.
# The lookbehind keeps "TMs." / "HMs." / "items." out.
PREFIX_TITLE_RE = re.compile(r"(?<![A-Za-z0-9.’'])(Mt|Prof|S\.S|Lt|Mr|Mrs|Ms|Dr)\.$")
PREFIX_NUM_RE = re.compile(r"(?<![A-Za-z0-9.’'])(Lv|No)\.$")
PKMN_END_RE = re.compile(r"(?<![A-Za-z])Pok[ée]mon$", re.I)
PKMN_NEXT_RE = re.compile(r"(Centers?|League)(?![A-Za-z])", re.I)


def check_prefix_split(en, add):
    """A line ends with Mt./Prof./S.S./Lt./Mr./Mrs./Ms./Dr. (the name follows on the next line), with
    Lv./No. before a number, or with 'Pokémon' before 'Center'/'League'."""
    segs = BREAK_SPLIT_RE.split(en)
    for i in range(len(segs) - 1):
        s, nxt = segs[i].rstrip(), segs[i + 1].lstrip()
        if not tm.visible_text(nxt).strip() and not nxt.startswith("{VAR"):
            continue
        m = PREFIX_TITLE_RE.search(s)
        if m:
            add("error", "prefix_split", "line %d ends with ‘%s.’; keep it with ‘%s’" % (i + 1, m.group(1), nxt[:20]))
            continue
        m = PREFIX_NUM_RE.search(s)
        if m and re.match(r"\d|\{VAR:", nxt):
            add("error", "prefix_split", "line %d ends with ‘%s.’; keep it with its number" % (i + 1, m.group(1)))
            continue
        if PKMN_END_RE.search(s) and PKMN_NEXT_RE.match(nxt):
            add("error", "prefix_split", "‘Pokémon %s’ split over lines %d-%d" % (PKMN_NEXT_RE.match(nxt).group(1),
                                                                             i + 1, i + 2))


ZH_SENTENCE_END = set("。！？…」』”）!?.~～♪—：:")
EN_SENTENCE_END = set(".!?…”’)~♪:-—")


def _page_tail(page: str) -> str:
    """Page text without trailing control tags; a trailing name placeholder counts as a word ('X')."""
    s = page.rstrip()
    while True:
        m = re.search(r"\{([^{}]*)\}\s*$", s)
        if not m:
            return s
        t = m.group(1)
        if t.startswith("VAR:") and (tm.var_cmd(t) >> 8) not in (0x02, 0xFF):
            return s[:m.start()] + "X"
        s = s[:m.start()].rstrip()


def _is_heading_page(page: str) -> bool:
    """A one-line title page (signposts: 'Trainer Tips', 'Indigo Plateau')."""
    if re.search(r"\{(?:NEWLINE|CLEAR)\}|\n", page):
        return False
    w = re.sub(r"\{[^}]*\}", " ", page).split()
    return 0 < len(w) <= 5 and all(x[0].isupper() or x in ("of", "the", "and", "to", "&") for x in w)


def check_mid_sentence_page(zh, en, add):
    """A {SCROLL} page break inside an English sentence where the Chinese breaks at a sentence end.
    Same page count: page i of en doesn't end a sentence but zh page i does.
    Different page count: en page ends with no punctuation at all (mid-clause) and no zh page
    breaks mid-sentence (continuation pages that end at a comma are normal and not reported)."""
    if "{SCROLL}" not in en:
        return
    zp, ep = zh.split("{SCROLL}"), en.split("{SCROLL}")
    zmid = [(_page_tail(z)[-1:] not in ZH_SENTENCE_END) for z in zp[:-1]]
    for i in range(len(ep) - 1):
        t = _page_tail(ep[i])
        if not t or t[-1] in EN_SENTENCE_END or _is_heading_page(ep[i]):
            continue
        if len(zp) == len(ep):
            if zmid[i]:
                continue
        elif any(zmid) or t[-1] in ",;":
            continue
        add("warning", "mid_sentence_page", "page %d ends mid-sentence (‘…%s’) before {SCROLL}"
            % (i + 1, tm.visible_text(t)[-30:]))


# --------------------------------------------------------------------------------------
# glossary_name: English species/move/item/ability names that are not the known names
# --------------------------------------------------------------------------------------

NAME_BANKS = {"a027/0232": "species", "a027/0739": "moves", "a027/0219": "items", "a027/0711": "abilities",
              "a027/0724": "types", "a027/0033": "natures", "a027/0183": "locations"}
NAME_CATS = ("species", "moves", "items", "abilities")
REGISTER = WORK / "translate" / "decisions" / "decisions.jsonl"
BANKS_DIR = WORK / "translate" / "banks"
_NAME_WORD = r"[A-Z][A-Za-zé’'♀♂\-.]*[A-Za-z0-9é♀♂.]|[A-Z]"
NAME_RUN_RE = re.compile(r"(?:%s)(?: (?:%s|\d+))*" % (_NAME_WORD, _NAME_WORD))


def _lev(a: str, b: str, mx: int) -> int:
    if abs(len(a) - len(b)) > mx:
        return mx + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _deletes(w: str, d: int) -> set:
    out = {w}
    for _ in range(d):
        out |= {x[:i] + x[i + 1:] for x in out for i in range(len(x))}
    return out


@lru_cache(maxsize=None)
def _dictionary_words() -> frozenset:
    for p in ("/usr/share/dict/words", "/usr/dict/words"):
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                return frozenset(w.strip().lower() for w in f)
        except OSError:
            continue
    return frozenset()


@lru_cache(maxsize=None)
def known_names(banks_dir: str = str(BANKS_DIR), register: str = str(REGISTER)) -> dict:
    """canon: {official name: category} from the glossary and the name banks ('abbreviated from X' notes);
    abbr: {abbreviated/Gen 4 form: full name} (glossary ABBREV, name-bank abbreviations);
    other: other known capitalised names (register terms, types, natures, locations, general terms,
    qa_config glossary_names.allow)."""
    g, abbrev = load_glossary()
    cfg = tm.load_config().get("glossary_names", {})
    canon, abbr, other = {}, {}, set()
    for cat, m in g.items():
        for vs in m.values():
            if cat in NAME_CATS:
                canon.setdefault(vs[0], cat)
                for v in vs[1:]:
                    if v != vs[0] and v in abbrev.values():
                        abbr.setdefault(v, vs[0])
                    else:
                        canon.setdefault(v, cat)
            else:
                other.update(vs)
    for key, cat in NAME_BANKS.items():
        p = Path(banks_dir) / (key + ".json")
        if not p.exists():
            continue
        for e in json.loads(p.read_text(encoding="utf-8"))["strings"]:
            en = tm.visible_text(e.get("en") or "").strip()
            if not en:
                continue
            if cat not in NAME_CATS:
                other.add(en)
                continue
            m = re.search(r"abbreviated from ([^;,]+?)(?:[;,]|$)", e.get("notes") or "")
            if m and m.group(1).strip() != en:
                canon.setdefault(m.group(1).strip(), cat)
                abbr.setdefault(en, m.group(1).strip())
            elif en not in abbr:
                canon.setdefault(en, cat)
    try:
        for line in Path(register).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("type") == "term" and r.get("status") != "superseded" and r.get("en"):
                other.add(r["en"].strip())
                other.update(a.strip() for a in re.split(r" / ", r["en"]) if a.strip())
    except OSError:
        pass
    other.update(cfg.get("allow", {}).keys())
    old = dict(cfg.get("old_names", {}))
    bynorm = {}
    for k, cat in canon.items():
        bynorm.setdefault(_norm_en(k), []).append(k)
    idx = {}
    for k, cat in canon.items():
        nk = _norm_en(k)
        if len(nk) < 5:
            continue
        for d in _deletes(nk, 1):
            idx.setdefault(d, set()).add(k)
    return {"canon": canon, "abbr": abbr, "other": other, "old": old, "bynorm": bynorm, "idx": idx}


def _name_forms(s: str):
    """s, then s without closing punctuation / a possessive / a plural ending."""
    yield s
    t = s.rstrip(".…’!?,")
    if t != s:
        yield t
    for suf in ("’s", "'s", "’"):
        if t.endswith(suf):
            t = t[: -len(suf)]
            yield t
            break
    if t.endswith("ies"):
        yield t[:-3] + "y"
    if t.endswith("es"):
        yield t[:-2]
    if t.endswith("s"):
        yield t[:-1]


def _is_english_word(w: str) -> bool:
    words = _dictionary_words()
    lw = w.lower()
    if lw in words:
        return True
    for suf, rep in (("s", ""), ("es", ""), ("ies", "y"), ("ed", ""), ("ed", "e"), ("d", ""), ("ly", ""),
                     ("ily", "y"), ("ing", ""), ("ing", "e"), ("er", ""), ("ers", "")):
        if lw.endswith(suf) and lw[: -len(suf)] + rep in words:
            return True
    return False


def _fuzzy_name(s: str, kn: dict):
    """A canonical name one edit away from s: single words that are not English words, or multi-word
    names with the same word count where the other words are identical (Faint Attack -> Feint Attack)."""
    ns = _norm_en(s)
    if len(ns) < 6 or "-" in s or re.search(r"[^A-Za-zé♀♂ ]", s):
        return None
    words = s.split(" ")
    if len(words) == 1 and _is_english_word(s):
        return None
    for d in _deletes(ns, 1):
        for k in sorted(kn["idx"].get(d, ())):
            kw = k.split(" ")
            if len(kw) != len(words) or _lev(ns, _norm_en(k), 1) > 1:
                continue
            if len(words) > 1:
                diff = [(a, b) for a, b in zip(words, kw) if a != b]
                if len(diff) != 1 or diff[0][0][:1].lower() != diff[0][1][:1].lower():
                    continue
            return k
    return None


def check_glossary_names(zh, en, add, kn=None):
    """Tokenise capitalised word runs and compare every 1-4 word span with the known names.
    Untouched copies (en == zh: foreign-language data) are skipped."""
    if en == zh:
        return
    kn = kn or known_names()
    g = load_glossary()[0].get("species", {})
    canon, abbr, other, old = kn["canon"], kn["abbr"], kn["other"], kn["old"]
    allow = set(tm.load_config().get("glossary_names", {}).get("allow", {}))
    v = BREAK_SPLIT_RE.sub(" ", en)
    v = re.sub(r"\{[^}]*\}", " | ", v)
    seen = set()
    for m in NAME_RUN_RE.finditer(v):
        ws = m.group(0).split(" ")
        covered = [False] * len(ws)
        for n in range(min(4, len(ws)), 0, -1):
            for i in range(len(ws) - n + 1):
                if any(covered[i:i + n]):
                    continue
                raw = " ".join(ws[i:i + n]).replace("'", "’")
                hit = None
                forms = list(_name_forms(raw))
                if any(f in canon or f in other or f in allow for f in forms):
                    covered[i:i + n] = [True] * n
                    continue
                if any(f.isupper() and _norm_en(f) in kn["bynorm"] for f in forms):
                    covered[i:i + n] = [True] * n           # ALL-CAPS menu style
                    continue
                if any(re.sub(r"[-.…]", "", f) + g in canon for f in forms if re.search(r"\w[-.…]+\w", f)
                       for g in ("", "♀", "♂")):
                    covered[i:i + n] = [True] * n           # syllable stutter: Ivy-saur, Squir...tle
                    continue
                for f in forms:
                    if f in old:
                        hit = ("old", f, old[f])
                    elif f in abbr:
                        hit = ("abbr", f, abbr[f])
                    elif _norm_en(f) in kn["bynorm"] and len(_norm_en(f)) >= 4:
                        want = kn["bynorm"][_norm_en(f)]
                        base = f.rstrip(".…’!?,")
                        if base + "♀" in canon or base + "♂" in canon:   # bare Nidoran: decide from the zh
                            want = [w for w in (base + "♀", base + "♂")
                                    if any(z in zh for z, vs in g.items() if w in vs)]
                            if len(want) != 1:
                                hit = ("skip", f, None)          # the zh doesn't say which: leave it
                                break
                        hit = ("variant", f, want[0])
                    if hit:
                        break
                if not hit and n <= 3:
                    for f in forms:
                        k = _fuzzy_name(f, kn)
                        if k:
                            hit = ("fuzzy", f, k)
                            break
                if not hit:
                    continue
                covered[i:i + n] = [True] * n
                kind, found, want = hit
                if kind == "skip":
                    continue
                if (found, want) in seen:
                    continue
                seen.add((found, want))
                cat = canon.get(want, "name")
                lvl = "error" if cat in ("species", "moves") and kind != "abbr" else "warning"
                what = {"old": "old name", "abbr": "abbreviated name-bank form in prose",
                        "variant": "spelling differs from", "fuzzy": "unknown name, close to"}[kind]
                add(lvl, "glossary_name", "%s: ‘%s’ → ‘%s’ (%s)" % (what, found, want, cat),
                    key="glossary_name:" + found)


def bank_context(bank: dict, cat: dict, cfg: dict, fset: dict) -> dict:
    ctx = {}
    if cat.get("relative_to_zh"):
        font = cat.get("font", 1)
        mx = 0
        for e in bank["strings"]:
            for ln in tm.measure_lines(e["zh"], font, cfg, bank["narc"], "typ", fset):
                mx = max(mx, ln["px"])
        ctx["zh_max_px"] = mx
    return ctx


def check_bank(bank: dict, cfg: dict | None = None, fset_name: str | None = None, statuses=None,
               glossary=True) -> list:
    import msgtool as m
    cfg = cfg or tm.load_config()
    fset = tm.font_set(fset_name)
    full = tm.load_widths()
    fset_hack = full["font_sets"].get("hack_v4") if fset.get("name") != "hack_v4" else None
    cm_en = _cm_en()
    catname = bank_category(bank, cfg)
    cat_default = cfg["categories"][catname]
    ctx = bank_context(bank, cat_default, cfg, fset)
    cspec = tm.compressed_spec(bank["narc"], bank["bank"], cfg)
    scat = string_categories(bank, cfg)
    issues = []
    for e in bank["strings"]:
        en = e.get("en")
        if en is None:
            continue
        if statuses and e.get("status") not in statuses:
            continue
        zh = e["zh"]
        cname = e.get("category") or scat.get(e["id"]) or catname
        cat = cfg["categories"][cname]
        ignore = set(e.get("qa_ignore", []))

        def add(level, code, msg, key=None, _e=e, _ign=ignore):
            if code in _ign or (key and key in _ign):
                return
            issues.append({"narc": bank["narc"], "bank": bank["bank"], "id": _e["id"], "level": level,
                           "code": code, "msg": msg, "category": cname})

        check_misc(zh, en, add)
        check_tags(zh, en, add)
        check_chars(en, cat.get("font", 1), fset, cm_en, add)
        check_layout(zh, en, cat, cname, bank["narc"], cfg, fset, fset_hack,
                     ctx if cname == catname else bank_context(bank, cat, cfg, fset), add)
        check_prefix_split(en, add)
        if "line_px" in cat:
            check_mid_sentence_page(zh, en, add)
        if glossary:
            check_glossary(zh, en, cname, cfg, add)
            if "max_chars" not in cat:
                check_glossary_names(zh, en, add)
        if cspec is not None:
            check_name_buffer(e["id"], en, cspec, cm_en, add)
        if e.get("zh_changed"):
            add("warning", "zh_changed", "source changed; was %r" % e.get("zh_old"))
    return issues


@lru_cache(maxsize=None)
def _cm_en():
    import msgtool as m
    return m.Charmap.load([str(tm.CHARMAP_EN)])


def iter_bank_files(path: Path):
    path = Path(path)
    if path.is_file():
        yield path
    else:
        yield from sorted(path.rglob("[0-9]*.json"))


def run_check(path, fset_name=None, statuses=None, glossary=True):
    issues, nbanks, nchecked = [], 0, 0
    for p in iter_bank_files(path):
        b, _ = zh_redact.hydrate(json.loads(p.read_text(encoding="utf-8")), EXTRACT_DIR)
        nbanks += 1
        nchecked += sum(1 for e in b["strings"] if e.get("en") is not None
                        and (not statuses or e.get("status") in statuses))
        issues += check_bank(b, None, fset_name, statuses, glossary)
    lv = Counter(i["level"] for i in issues)
    summary = {"banks": nbanks, "strings_checked": nchecked, "errors": lv.get("error", 0),
               "warnings": lv.get("warning", 0),
               "by_code": dict(Counter("%s:%s" % (i["level"], i["code"]) for i in issues).most_common()),
               "font_set": tm.font_set(fset_name)["name"]}
    return {"summary": summary, "issues": issues}


def cmd_check(a):
    statuses = tuple(s for s in a.status.split(",") if s) if a.status else None
    res = run_check(a.path, a.font_set, statuses, not a.no_glossary)
    if a.json:
        txt = json.dumps(res, ensure_ascii=False, indent=1)
        if a.json == "-":
            print(txt)
        else:
            Path(a.json).write_text(txt, encoding="utf-8")
    s = res["summary"]
    out = sys.stderr if a.json == "-" else sys.stdout
    print(f"checked {s['strings_checked']} strings in {s['banks']} banks (font set {s['font_set']}): "
          f"{s['errors']} errors, {s['warnings']} warnings", file=out)
    for k, v in s["by_code"].items():
        print(f"  {k:32s} {v}", file=out)
    shown = 0
    for i in sorted(res["issues"], key=lambda i: (i["level"] != "error", i["narc"], i["bank"], i["id"])):
        if shown >= a.max_print:
            print(f"  ... ({len(res['issues']) - shown} more; use --json)", file=out)
            break
        print(f"  {i['level'][0].upper()} {i['narc']}/{i['bank']:04d}#{i['id']} [{i['code']}] {i['msg']}", file=out)
        shown += 1
    sys.exit(1 if s["errors"] else 0)


# --------------------------------------------------------------------------------------
# zh_variant: identical Chinese with different English across the workspace
# --------------------------------------------------------------------------------------

VARIANT_SKIP_NOTES = re.compile(r"context|branch", re.I)


def _norm_zh_key(zh: str) -> str:
    return re.sub(r"\s+", "", BREAK_SPLIT_RE.sub("", zh))


def _norm_en_layout(en: str) -> str:
    return re.sub(r"\s+", " ", BREAK_SPLIT_RE.sub(" ", en)).strip()


def _punct_key(en: str) -> str:
    return re.sub(r"[^0-9a-zé♀♂{}:]+", "", en.lower())


OWNER_PREFIX_RE = re.compile(r"^(?:But )?(?:the |The )?(?:wild |foe’s |opposing )", re.I)


def variant_groups(path, min_len: int = 6, cfg=None) -> list:
    """Group strings by normalised zh (layout tags and whitespace removed, other tags kept) and category;
    report groups with more than one English (layout differences ignored). Skipped: en == zh copies, empty
    en, strings whose notes mention 'context' or 'branch', and battle-message owner variants that differ
    only by 'The wild ' / 'The foe’s ' (deliberate differences)."""
    cfg = cfg or tm.load_config()
    groups = {}
    for p in iter_bank_files(path):
        b = json.loads(Path(p).read_text(encoding="utf-8"))
        bc = bank_category(b, cfg)
        for e in b["strings"]:
            en = e.get("en")
            if not en or not en.strip() or en == e["zh"]:
                continue
            if VARIANT_SKIP_NOTES.search(e.get("notes") or ""):
                continue
            zk = _norm_zh_key(e["zh"])
            if len(tm.visible_text(zk)) < min_len:
                continue
            cat = e.get("category") or bc
            groups.setdefault((zk, cat), []).append(
                {"ref": "%s/%04d#%d" % (b["narc"], b["bank"], e["id"]), "en": _norm_en_layout(en),
                 "status": e.get("status"), "origin": e.get("origin")})
    out = []
    for (zk, cat), mem in groups.items():
        variants = Counter(m["en"] for m in mem)
        if len(variants) < 2 or len({OWNER_PREFIX_RE.sub("", v) for v in variants}) < 2:
            continue
        out.append({"zh": zk, "category": cat, "size": len(mem), "n_variants": len(variants),
                    "punct_only": len({_punct_key(v) for v in variants}) == 1,
                    "variants": [{"en": v, "count": n, "refs": [m["ref"] for m in mem if m["en"] == v]}
                                 for v, n in variants.most_common()]})
    out.sort(key=lambda g: (-g["size"], -g["n_variants"], g["zh"]))
    return out


def cmd_variants(a):
    groups = variant_groups(a.path, a.min_len)
    if a.no_punct:
        groups = [g for g in groups if not g["punct_only"]]
    if a.json:
        txt = json.dumps(groups, ensure_ascii=False, indent=1)
        if a.json == "-":
            print(txt)
            return
        Path(a.json).write_text(txt, encoding="utf-8")
    np_ = sum(1 for g in groups if g["punct_only"])
    print(f"zh_variant: {len(groups)} identical-Chinese groups with more than one English "
          f"({len(groups) - np_} beyond punctuation, {np_} punctuation/case only)")
    for g in groups[: a.max_print]:
        print(f"\n[{g['size']} strings, {g['n_variants']} variants{', punctuation only' if g['punct_only'] else ''}]"
              f" ({g['category']}) {g['zh'][:80]}")
        for v in g["variants"]:
            refs = ", ".join(v["refs"][:6]) + (" …" if len(v["refs"]) > 6 else "")
            print(f"  W zh_variant {v['count']:3d}× {v['en'][:110]}\n        {refs}")
    if len(groups) > a.max_print:
        print(f"\n... ({len(groups) - a.max_print} more groups; use --json)")


# --------------------------------------------------------------------------------------
# normalisation + wrap
# --------------------------------------------------------------------------------------

def normalize_punct(text: str) -> str:
    """ASCII quotes/dashes -> the glyphs the DS font has (’ ‘ “ ” -), outside {tags}."""
    parts = re.split(r"(\{[^{}]*\})", text)
    out = []
    dq_open = True
    prev = ""
    for part in parts:
        if part.startswith("{") and part.endswith("}"):
            out.append(part)
            if part not in ("{NEWLINE}", "{SCROLL}", "{CLEAR}"):
                prev = "}"          # a placeholder counts as a word: {VAR}'s -> ’s
            else:
                prev = " "
            continue
        buf = []
        for ch in part:
            if ch == "'":
                buf.append("‘" if (not prev or prev.isspace() or prev in "(“") else "’")
            elif ch == '"':
                buf.append("“" if dq_open else "”")
                dq_open = not dq_open
            elif ch in "—–":
                buf.append("-")
            elif ch == " ":
                buf.append(" ")
            else:
                buf.append(ch)
            prev = buf[-1]
        out.append("".join(buf))
    return "".join(out)


def _trailing_layout(tokens):
    tail = []
    for k, v in reversed(tokens):
        if k == "layout":
            tail.append(v)
        else:
            break
    return list(reversed(tail))


def _zh_breaks(zh: str):
    toks = tm.tokenize(zh)
    n_tail = len(_trailing_layout(toks))
    body = toks[:len(toks) - n_tail] if n_tail else toks
    return [v for k, v in body if k == "layout" and v in ("SCROLL", "CLEAR")], _trailing_layout(toks)


def _split_paragraphs(en: str, zh_breaks, reflow: bool):
    """-> list of paragraphs (each a list of forced-line strings) and explicit boundary types (None = auto)."""
    en = en.replace("\r\n", "\n")
    toks = tm.tokenize(en.replace("\n\n", "\x00"))
    # strip trailing layout; zh's trailing tags are re-added by wrap()
    while toks and toks[-1][0] == "layout":
        toks.pop()
    explicit = [v for k, v in toks if k == "layout" and v in ("SCROLL", "CLEAR")]
    keep_explicit = (not reflow) or len(explicit) == len(zh_breaks)
    paras, bounds = [[""]], []
    for k, v in toks:
        if k == "layout":
            if v == "NEWLINE":
                if reflow:
                    paras[-1][-1] += " "
                else:
                    paras[-1].append("")
            elif keep_explicit:
                paras.append([""])
                bounds.append(v)
            else:
                paras[-1][-1] += " "
        elif k == "text":
            chunks = v.split("\x00")
            for ci, c in enumerate(chunks):
                if ci:
                    paras.append([""])
                    bounds.append(None)
                paras[-1][-1] += c
        else:
            paras[-1][-1] += "{" + v + "}"
    return paras, bounds


def _word_px(word, font, cfg, narc, fset, which):
    return tm.measure_lines(word, font, cfg, narc, which, fset)[0]["px"] if word else 0


def fill_lines(text: str, line_px: int, font=1, cfg=None, narc=None, fset=None, which="typ"):
    """Greedy word wrap of one forced line (no layout tags) into lines <= line_px."""
    cfg = cfg or tm.load_config()
    fset = fset or tm.font_set()
    words = [w for w in re.split(r" +", text.strip())]
    sp = tm.char_width(" ", font, fset) or 4
    lines, cur, cur_px = [], "", 0
    for w in words:
        if w == "":
            continue
        wp = _word_px(w, font, cfg, narc, fset, which)
        if not cur:
            cur, cur_px = w, wp
        elif cur_px + sp + wp <= line_px:
            cur, cur_px = cur + " " + w, cur_px + sp + wp
        else:
            lines.append(cur)
            cur, cur_px = w, wp
    if cur or not lines:
        lines.append(cur)
    return lines


def wrap(en: str, zh: str, category: str = "dialogue", mode: str = "auto", reflow: bool = False,
         narc: str | None = None, cfg=None, fset=None, which="typ", normalize=True) -> str:
    """Re-flow English prose into box lines/pages following the zh tag structure.

    Input conventions: a blank line (\\n\\n) or an explicit {SCROLL}/{CLEAR} separates paragraphs;
    paragraph k is followed by the k-th {SCROLL}/{CLEAR} of the zh when the counts match, else
    by the default page break. A single \\n or {NEWLINE} forces a line break (reflow: treated as space).
    Overflowing lines continue with {NEWLINE} while the box has room, then with the continuation
    break (mode page -> {SCROLL} = new box; scroll -> {CLEAR} = scroll one line; auto -> follow zh).
    zh's trailing layout tags are appended."""
    cfg = cfg or tm.load_config()
    fset = fset or tm.font_set()
    cat = cfg["categories"][category]
    if normalize:
        en = normalize_punct(en)
    if "line_px" not in cat:
        return en
    lim, maxl, font = cat["line_px"], cat.get("lines", 2), cat.get("font", 1)
    if "soft_line_px" in cat and lim > cat["soft_line_px"]:
        # prefer the soft limit (clear of the frame); keep the window width if the soft one needs more breaks
        plain = {k: v for k, v in cat.items() if k != "soft_line_px"}
        cats = dict(cfg["categories"], _hard=plain, _soft=dict(plain, line_px=cat["soft_line_px"]))
        c2 = dict(cfg, categories=cats)
        hard, soft = (wrap(en, zh, k, mode, reflow, narc, c2, fset, which, normalize=False)
                      for k in ("_hard", "_soft"))
        n_breaks = lambda t: len(re.findall(r"\{(?:SCROLL|CLEAR)\}", t))
        return soft if n_breaks(soft) == n_breaks(hard) and tm.page_lines(soft) <= maxl else hard
    zb, ztail = _zh_breaks(zh)
    if mode == "auto":
        cont = "CLEAR" if ("CLEAR" in zb and "SCROLL" not in zb) else "SCROLL"
    else:
        cont = {"page": "SCROLL", "scroll": "CLEAR"}[mode]
    paras, bounds = _split_paragraphs(en, zb, reflow)
    if len(bounds) == len(zb):
        bounds = [b or z for b, z in zip(bounds, zb)]
    else:
        bounds = [b or cont for b in bounds]
    out, y = [], 0
    for pi, para in enumerate(paras):
        if pi:
            b = bounds[pi - 1]
            out.append("{%s}" % b)
            if b == "SCROLL":
                y = 0
        lines = []
        for forced in para:
            lines += fill_lines(forced, lim, font, cfg, narc, fset, which)
        for li, ln in enumerate(lines):
            if li:
                if y < maxl - 1:
                    out.append("{NEWLINE}")
                    y += 1
                else:
                    out.append("{%s}" % cont)
                    if cont == "SCROLL":
                        y = 0
            out.append(ln)
    out += ["{%s}" % t for t in ztail]
    return "".join(out)


def _parse_ids(s):
    ids = set()
    for part in s.split(","):
        if "-" in part:
            a, b = part.split("-")
            ids.update(range(int(a), int(b) + 1))
        elif part:
            ids.add(int(part))
    return ids


def cmd_wrap(a):
    cfg = tm.load_config()
    fset = tm.font_set(a.font_set)
    if a.bank:
        p = Path(a.bank)
        b = json.loads(p.read_text(encoding="utf-8"))
        hyd, _ = zh_redact.hydrate(b, EXTRACT_DIR)          # real zh for layout; never written back
        src_zh = {e["id"]: e["zh"] for e in hyd["strings"]}
        catname = bank_category(hyd, cfg)
        scat = string_categories(hyd, cfg)
        ids = _parse_ids(a.ids) if a.ids else None
        n = 0
        for e in b["strings"]:
            if e.get("en") is None or (ids is not None and e["id"] not in ids):
                continue
            if re.search(r"\{(?:NEWLINE|SCROLL|CLEAR)\}", e["en"]) and not a.reflow:
                continue            # already laid out; use --reflow to redo it
            c = a.category or e.get("category") or scat.get(e["id"]) or catname
            new = wrap(e["en"], src_zh[e["id"]], c, a.mode, a.reflow, b["narc"], cfg, fset, a.which)
            if new != e["en"]:
                n += 1
                if not a.in_place:
                    print(f"#{e['id']}: {new}")
                e["en"] = new
        if a.in_place:
            import ws
            ws.save_json(p, b)
        print(f"wrapped {n} strings" + (" (written)" if a.in_place else ""), file=sys.stderr)
    else:
        if a.en is None or a.zh is None:
            sys.exit("wrap needs --zh and --en, or a bank file")
        print(wrap(a.en.replace("\\n", "\n"), a.zh, a.category or "dialogue", a.mode, a.reflow, a.narc,
                   cfg, fset, a.which))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("path")
    c.add_argument("--json")
    c.add_argument("--font-set")
    c.add_argument("--status", default="")
    c.add_argument("--max-print", type=int, default=40)
    c.add_argument("--no-glossary", action="store_true")
    v = sub.add_parser("variants", help="zh_variant report: identical Chinese, different English")
    v.add_argument("path", nargs="?", default=str(BANKS_DIR))
    v.add_argument("--min-len", type=int, default=6, help="minimum visible zh characters (default 6)")
    v.add_argument("--json")
    v.add_argument("--max-print", type=int, default=60)
    v.add_argument("--no-punct", action="store_true", help="hide groups that differ only in punctuation/case")
    w = sub.add_parser("wrap")
    w.add_argument("bank", nargs="?")
    w.add_argument("--zh")
    w.add_argument("--en")
    w.add_argument("--category")
    w.add_argument("--mode", default="auto", choices=("auto", "page", "scroll"))
    w.add_argument("--reflow", action="store_true")
    w.add_argument("--ids")
    w.add_argument("--in-place", action="store_true")
    w.add_argument("--narc")
    w.add_argument("--font-set")
    w.add_argument("--which", default="typ", choices=("typ", "max"))
    a = ap.parse_args(argv)
    {"check": cmd_check, "wrap": cmd_wrap, "variants": cmd_variants}[a.cmd](a)


if __name__ == "__main__":
    main()
