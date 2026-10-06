#!/usr/bin/env python3
"""emu_sweeps - text sweeps on the English build: capture what the game shows, read it back with the
game's own font (emu_text.py) and compare it with the bank string (`emu_harness.py sweeps`).

Sweeps (each runs in parallel child processes, one emulator per process; CN runs give the CN|EN pairs):

  trainers   every trainer of the ROM's trainer data (site/src/data/trainers.json, ids 1-1023): load a
             field savestate, `TrainerBattle id 0 0 0`, and capture the intro message ("<Class> <Name>
             wants to battle!" and whatever intro string the battle picks). MsgLog gives the battle_string
             id, the trainer class (a027/0720) and the name (a027/0719) the game read; the expected lines are
             the bank string with those two filled in. Issues: no intro, text that differs from the
             expected lines (garble, a wrong buffer, a line cut at the window edge), ink in the window's
             last column (clipped).
  battle     scripted wild battles with generator leads whose moves trigger the common battle messages
             (weather, status, stat changes, abilities, items, effectiveness, critical hits, fainting,
             switching, Exp. and level-up). Every stable page of the battle message window is decoded and
             matched against the battle_string messages the game read just before it (buffers = any text).
             Coverage = distinct battle_string ids printed / ids in banks 0-2.
  desc       descriptions where they are shown: item descriptions in the bag (every item of
             site/src/data/items.json, Items pocket filled in RAM, cursor stepped down the list), move
             descriptions on the summary's move page and ability descriptions on the summary's info page.

Screenshots and reports: work/build/harness/sweeps/<sweep>/ (pairs of the issues: pairs/).

    .venv/bin/python work/tools/emu_harness.py sweeps --sweep trainers [--ids 1-200] [--lang en|cn|both] [--jobs 6]
"""
import datetime
import json
import shutil
import struct
import tempfile
import time
from pathlib import Path

import emu_harness as E
import emu_text as T

CLOCK = datetime.datetime(2026, 10, 9, 12)       # a Friday, noon (as the other recipes)
NARC_BATTLE = 277                                # battle/string/battle_string.narc (MsgData +4 in MsgLog rows)
NARC_A027 = 27
BANKS = Path(__file__).resolve().parent.parent / "translate" / "banks"
SITE_DATA = Path(__file__).resolve().parent.parent.parent / "site" / "src" / "data"
POLL = 4                                         # frames between looks at the message window
STABLE = 3                                       # unchanged looks before a page counts as printed


def out_root(out):
    d = Path(out).resolve() / "sweeps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def lang_of(rom):
    return "en" if "en" in Path(rom).name.lower() else "cn"


_BANK_CACHE = {}


def bank(narc, no):
    """Workspace bank strings by id (the source the build exports)."""
    key = (narc, no)
    if key not in _BANK_CACHE:
        p = BANKS / narc / f"{no:04d}.json"
        _BANK_CACHE[key] = {s["id"]: s for s in json.loads(p.read_text())["strings"]}
    return _BANK_CACHE[key]


def en_of(narc, no, i):
    s = bank(narc, no).get(i)
    return (s.get("en") if s else None) or ""


# ----------------------------------------------------------------------------- message window watcher
class PageWatch:
    """Polls the battle message window; every page that stays unchanged for STABLE looks is decoded.
    A page that extends the previous one (text still printing at the last look) replaces it."""

    def __init__(self, h, f, box=T.BOXES["battle"], keep_images=True):
        self.h, self.f, self.box = h, f, box
        self.pages, self._prev, self._same, self._last_key = [], None, 0, None
        self.keep = keep_images
        b = box
        self.crop = (b["x0"], b["y0"], b["x0"] + b["width"], b["y0"] + T.LINE_H * b["lines"])

    def poll(self):
        img = self.h.emu.screenshot()
        key = img.crop(self.crop).tobytes()
        if key == self._prev:
            self._same += 1
        else:
            self._same, self._prev = 0, key
        if self._same == STABLE and key != self._last_key:
            lines = T.read_lines(img, self.box, self.f)
            if any(l["text"] for l in lines) and not all(l["unknown"] and not l["text"].strip(T.UNKNOWN)
                                                         for l in lines if l["text"]):
                page = {"frame": self.h.frame, "lines": lines, "img": img if self.keep else None}
                if self.pages and _extends(self.pages[-1]["lines"], lines):
                    self.pages[-1] = page
                else:
                    self.pages.append(page)
            self._last_key = key
        return img


def _extends(old, new):
    """True when every line of old is a prefix of the same line of new (and new has more text)."""
    a = [l["text"] for l in old]
    b = [l["text"] for l in new]
    return a != b and all(y.startswith(x) for x, y in zip(a, b))


def page_texts(page):
    return [l["text"] for l in page["lines"]]


# ----------------------------------------------------------------------------- sweep A: trainer intros
def trainer_ids():
    return [t["id"] for t in json.loads((SITE_DATA / "trainers.json").read_text())]


def trainer_expected(intro, reads):
    """Expected pages of intro string battle_string 2#<intro> with the class (0E) and name (00) buffers
    filled from the a027 reads (0720 class, 0719 name) in reading order."""
    en = en_of("battle_string", 2, intro)
    classes = [en_of("a027", 720, i) for b, i in reads if b == 720]
    names = [en_of("a027", 719, i) for b, i in reads if b == 719]
    buffers, ci, ni = {}, 0, 0
    for tok in T.TAG.findall(en):
        if tok.startswith("{VAR:01"):
            kind, idx = tok[7:9], int(tok.rstrip("}").split(":")[2].split(",")[0])
            if kind == "0E" and ci < len(classes):
                buffers[idx], ci = classes[ci], ci + 1
            elif kind == "00" and ni < len(names):
                buffers[idx], ni = names[ni], ni + 1
            elif kind == "00":              # not from 0719: the rival's name from the save (empty in the test saves)
                buffers[idx] = ""
    return en, T.expected_lines(en, buffers)


def run_trainers_child(rom, ids, out):
    """One emulator: field savestate, then per trainer: load it, start the battle, capture the intro."""
    import emu_verify as V
    lang = lang_of(rom)
    d = out_root(out) / "trainers" / lang
    d.mkdir(parents=True, exist_ok=True)
    f = T.font(str(rom), 1) if lang == "en" else None
    rows = []
    tmp = Path(tempfile.mkdtemp(prefix="sweep_tr_"))
    try:
        with E.start_at(None, rom=rom, out=d, verbose=False, clock=CLOCK) as h:
            h.save_state(tmp / "field.ds")
            ml = V.MsgLog(h)
            for tid in ids:
                h.load_state(tmp / "field.ds")
                try:
                    row = _one_trainer(h, ml, f, tid, d, lang)
                except Exception as e:          # this trainer only; the savestate resets the emulator
                    row = {"id": tid, "status": "error", "error": repr(e)[-400:]}
                rows.append(row)
                progress(out, "trainers", lang, ids, row)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def _battle_reads(ml, since):
    return [(b, i) for narc, b, i, _ in ml.rows[since:] if narc == NARC_BATTLE and b in (0, 1, 2)]


def _one_trainer(h, ml, f, tid, d, lang, max_frames=2400):
    mark = ml.mark()
    row = {"id": tid}
    try:
        h.trainer_battle(tid)
    except RuntimeError as e:
        return {**row, "status": "no_start", "error": str(e)}
    watch = PageWatch(h, f) if f else None
    intro, intro_at, best = None, None, None
    shots = []
    for _ in range(0, max_frames, POLL):
        h.step(POLL)
        reads = _battle_reads(ml, mark)
        if intro is None and reads:
            intro, intro_at = reads[0], h.frame
        img = h.emu.screenshot()
        if intro is not None:
            if watch:
                watch.poll()
            elif shots == [] or h.frame - intro_at in (40, 80, 120):
                shots.append(img)
        if intro is not None and len(reads) > 1:         # the next message: the intro is over
            break
    a027 = [(b, i) for narc, b, i, _ in ml.rows[mark:] if narc == NARC_A027 and b in (719, 720)]
    row.update(intro=intro and list(intro), a027=a027)
    if intro is None:
        row["status"] = "no_intro"
        row["shot"] = str(h.screenshot(f"tr{tid:04d}_nointro"))
        return row
    if not watch:                                        # CN: keep the last stable-looking frame for the pairs
        p = d / f"tr{tid:04d}.png"
        (shots[-1] if shots else h.emu.screenshot()).save(p)
        row.update(status="captured", shot=str(p))
        return row
    pages = [p for p in watch.pages]
    en, exp = trainer_expected(intro[1], a027) if intro[0] == 2 else ("", [])
    shown = [t for p in pages for t in page_texts(p)]
    ok, cmp = T.compare(exp, shown)
    clipped = any(l["clipped"] for p in pages for l in p["lines"])
    unknown = sum(l["unknown"] for p in pages for l in p["lines"])
    right = max((l["right"] for p in pages for l in p["lines"]), default=0)
    p = d / f"tr{tid:04d}.png"
    (pages[-1]["img"] if pages else h.emu.screenshot()).save(p)
    row.update(status="ok" if ok and not clipped and not unknown else "issue", en=en, **cmp, right=right,
               clipped=clipped, unknown=unknown, pages=len(pages), shot=str(p))
    return row


# ----------------------------------------------------------------------------- sweep B: descriptions
# Work items: item id (bag description), MOVE + move id (summary move page), ABILITY + ability id (summary).
MOVE, ABILITY = 10000, 20000
DESC_BOXES = {
    # Bag: window 27x6 tiles at x=40 (overlay 3 template 02 05 12 1B 06); the grey panel ends at x=239, the
    # frame starts at 240 (D-1512). Decoded up to the panel's edge: a line over 200 px runs into the frame.
    "item": {"x0": 40, "y0": 144, "width": 200, "lines": 3, "font": 0, "bg": None, "bank": 218, "limit": 200,
             "hard": 215},
    # Summary, skills page, bottom screen: move description under CATEGORY/POWER/ACCURACY: 5 ruled lines
    # from x=136 to the screen edge (120 px, the US maximum).
    "move": {"x0": 136, "y0": 192 + 80, "width": 120, "lines": 5, "font": 0, "bg": None, "bank": 738, "limit": 120,
             "hard": 120},
    # Summary, skills page, top screen: ability description under 'Ability <name>' (2 lines up to the
    # divider at x=147; US maximum 136 px).
    "ability": {"x0": 8, "y0": 152, "width": 139, "lines": 2, "font": 0, "bg": None, "bank": 712, "limit": 136,
                "hard": 139},
}
POCKET_CAP = 160
BAG_KEYS_FIRST = ["DOWN", "DOWN", "RIGHT", "UP", "UP"]               # page 1 from slot 0: 2, 4, 5, 3, 1
BAG_KEYS_PAGE = ["RIGHT", "LEFT", "DOWN", "DOWN", "RIGHT", "UP", "UP"]   # next page (slot 1), 0, 2, 4, 5, 3, 1
MOVE_ROW1 = (80, 25)                                                 # summary skills page: first move (touch)


def desc_items(spec):
    items = [i["id"] for i in json.loads((SITE_DATA / "items.json").read_text())]
    moves = [MOVE + i for i, s in sorted(bank("a027", 738).items()) if s.get("en") and 0 < i]
    abil = [ABILITY + i for i, s in sorted(bank("a027", 712).items()) if s.get("en") and 0 < i]
    mixed = []                     # one summary cycle shows an ability and four moves: interleave them so
    for k in range(max(len(abil), (len(moves) + 3) // 4)):     # every child gets both kinds
        mixed += abil[k:k + 1] + moves[4 * k:4 * k + 4]
    allw = items + mixed
    if not spec or spec == "all":
        return allw
    kinds = {"items": items, "moves": moves, "abilities": abil}
    out = []
    for part in spec.split(","):
        out += kinds.get(part) or parse_ids(part, allw)
    return out


def desc_expected(kind, i):
    en = en_of("a027", DESC_BOXES[kind]["bank"], i)
    return en, T.expected_lines(en)


def judge_desc(kind, i, img, f, lang):
    box = DESC_BOXES[kind]
    en, exp = desc_expected(kind, i)
    lines = T.read_lines(img, box, f)
    shown = [l["text"] for l in lines]
    ok, cmp = T.compare(exp, shown)
    want = T.flat(exp)
    widths = [f.width(w) for w in want]
    right = max((l["right"] for l in lines), default=0)
    status = "ok" if ok else "issue"
    got = [x for x in shown if x]
    if not ok and len(got) == len(want) and widths and max(widths) <= box["hard"] and all(
            g == w or (f.width(w) > box["limit"] and w.startswith(g.rstrip(T.UNKNOWN)))
            for w, g in zip(want, got)):
        status = "past_panel"           # every line that differs is one the panel cuts (QA: line_past_frame)
    return {"kind": kind, "id": i, "status": status, "en": en, **cmp, "right": right, "expected_px": widths,
            "clipped": any(l["clipped"] for l in lines), "unknown": sum(l["unknown"] for l in lines)}


def _stable(h, region, polls=3, max_frames=240):
    prev, same = None, 0
    for _ in range(0, max_frames, POLL):
        b = h.emu.screenshot().crop(region).tobytes()
        same = same + 1 if b == prev else 0
        if same >= polls:
            return True
        prev = b
        h.step(POLL)
    return False


def _bag_batch(h, ml, f, batch, d, lang, rows):
    off, cap = E.POCKETS["items"]
    a = h.array(E.ARR_BAG) + off
    h.write(a, b"".join(struct.pack("<HH", i, 1) for i in batch) + bytes(4 * (cap - len(batch))))
    mark = ml.mark()
    h.open_bag()
    h.step(60)
    seen = set()
    region = (0, 140, 256, 192)
    keys = [None] + BAG_KEYS_FIRST + BAG_KEYS_PAGE * ((len(batch) + 5) // 6)
    for key in keys:
        if key:
            m = ml.mark()
            h.press(key, after=8)
        else:
            m = mark
        _stable(h, region)
        reads = [i for b, i in ml.read(218, since=m)]
        if not reads:
            continue
        i = reads[-1]
        if i in seen or i not in batch:
            continue
        seen.add(i)
        img = h.emu.screenshot()
        p = d / f"item{i:04d}.png"
        img.save(p)
        row = judge_desc("item", i, img, f, lang) if f else {"kind": "item", "id": i, "status": "captured"}
        row["shot"] = str(p)
        rows.append(row)
        if len(seen) == len(batch):
            break
    for i in batch:
        if i not in seen:
            rows.append({"kind": "item", "id": i, "status": "not_shown"})


def _summary_cycle(h, ml, f, slot, moves, abil, d, lang, rows):
    """Edit party slot <slot> (the hack's ability field, 4 moves), open its summary, skills page: ability
    description (top) and the four move descriptions (bottom, first move touched, DOWN for the others)."""
    fields = {"moves": moves + [0] * (4 - len(moves)), "pp": [10] * 4}
    if abil is not None:
        fields["ability"] = abil
    h.edit_party_mon(slot, **fields)
    h.touch(*E.FIELD_MENU["pokemon"], frames=12, after=150)
    h.touch(*E.PARTY_SLOTS[slot], frames=12, after=60)
    h.touch(*E.PARTY_SUMMARY, frames=12, after=150)
    m = ml.mark()
    h.press("RIGHT", after=40)
    _stable(h, (0, 0, 256, 384))
    shown_ab = [i for b, i in ml.read(712, since=m)]
    img = h.emu.screenshot()
    if abil is not None:
        p = d / f"ability{abil:04d}.png"
        img.save(p)
        if abil in shown_ab:
            row = judge_desc("ability", abil, img, f, lang) if f else {"kind": "ability", "id": abil, "status": "captured"}
        else:
            row = {"kind": "ability", "id": abil, "status": "not_shown", "shown_ability": shown_ab}
        row["shot"] = str(p)
        rows.append(row)
    for k, mv in enumerate(moves):
        m = ml.mark()
        if k == 0:
            h.touch(*MOVE_ROW1, frames=10, after=30)
        else:
            h.press("DOWN", after=20)
        _stable(h, (128, 192, 256, 384))
        got = [i for b, i in ml.read(738, since=m)]
        img = h.emu.screenshot()
        p = d / f"move{mv:04d}.png"
        img.save(p)
        if mv in got:
            row = judge_desc("move", mv, img, f, lang) if f else {"kind": "move", "id": mv, "status": "captured"}
        else:
            row = {"kind": "move", "id": mv, "status": "not_shown", "read": got}
        row["shot"] = str(p)
        rows.append(row)


def run_desc_child(rom, work, out):
    import emu_verify as V
    lang = lang_of(rom)
    d = out_root(out) / "desc" / lang
    d.mkdir(parents=True, exist_ok=True)
    f = T.font(str(rom), 0) if lang == "en" else None
    items = [w for w in work if w < MOVE]
    moves = [w - MOVE for w in work if MOVE <= w < ABILITY]
    abil = [w - ABILITY for w in work if w >= ABILITY]
    rows = ProgressList(out, "desc", lang, work)
    tmp = Path(tempfile.mkdtemp(prefix="sweep_desc_"))
    try:
        with E.start_at(None, rom=rom, out=d, verbose=False, clock=CLOCK) as h:
            h.save_state(tmp / "field.ds")
            ml = V.MsgLog(h)
            for k in range(0, len(items), POCKET_CAP):
                h.load_state(tmp / "field.ds")
                _bag_batch(h, ml, f, items[k:k + POCKET_CAP], d, lang, rows)
            n = max(len(abil), (len(moves) + 3) // 4)
            for c in range(n):
                h.load_state(tmp / "field.ds")
                a = abil[c] if c < len(abil) else None
                mv = moves[4 * c:4 * c + 4]
                try:
                    _summary_cycle(h, ml, f, 0, mv, a, d, lang, rows)
                except Exception as e:     # one bad cycle does not stop the rest
                    rows.append({"kind": "cycle", "id": c, "status": "error", "error": repr(e)[-300:],
                                 "ability": a, "moves": mv})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return rows


def summarise_desc(rows, out):
    s = {}
    for l, rs in rows.items():
        by = {}
        for r in rs:
            k = by.setdefault(r.get("kind", "?"), {"n": 0, "status": {}, "max_right": 0, "issues": []})
            k["n"] += 1
            k["status"][r.get("status")] = k["status"].get(r.get("status"), 0) + 1
            k["max_right"] = max(k["max_right"], r.get("right", 0))
            if r.get("status") not in ("ok", "captured"):
                k["issues"].append(r.get("id"))
        s[l] = by
    if "en" in rows and "cn" in rows:
        s["pairs"] = make_pairs({l: [dict(r, id=(r.get("kind"), r.get("id"))) for r in rs] for l, rs in rows.items()},
                                out_root(out) / "desc" / "pairs", lambda r: f"{r['id'][0]}{r['id'][1]:04d}",
                                crop=(0, 0, 256, 384))
    return s


# ----------------------------------------------------------------------------- sweep C: battle messages
# Moves, species, items and abilities by their game ids (Gen 4 numbering; the hack keeps it).
SUNNY, RAIN, SAND, HAIL, SWORDS, GROWL, AGILITY, SCREECH = 241, 240, 201, 258, 14, 45, 97, 103
TWAVE, WISP, TOXIC, SPORE, CONFUSE, LEECH, EMBER, TACKLE, SPLASH = 86, 261, 92, 147, 109, 73, 52, 33, 150
FROST_BREATH, SHADOW_SNEAK, PSYCHIC, PROTECT, SUBSTITUTE, LIGHT_SCREEN, REFLECT = 524, 425, 94, 182, 164, 113, 115
SMEARGLE, BLISSEY, DITTO, SHEDINJA, GASTLY, SQUIRTLE, GYARADOS, MEWTWO = 235, 242, 132, 292, 92, 7, 130, 150
LEFTOVERS, LIFE_ORB, SITRUS = 234, 270, 158
DRIZZLE, SPEED_BOOST, INTIMIDATE, DROUGHT = 2, 3, 22, 70
# name: lead (species, level, moves, item, ability, hp fraction), foe (species, level) or ("trainer", id),
# plan: per turn a move slot, 'switch' (POKeMON -> party slot 1 -> shift), 'ball' (Master Ball), 'run'.
BATTLES = {
    "weather": ((BLISSEY, 100, [SUNNY, RAIN, SAND, HAIL], 0, None, 1), (BLISSEY, 100), [0, 1, 2, 3] + [3] * 6),
    "stats": ((BLISSEY, 100, [SWORDS, GROWL, AGILITY, SCREECH], 0, None, 1), (BLISSEY, 100),
              [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 2, 3]),
    "poison": ((BLISSEY, 100, [TOXIC, TWAVE, SPLASH, PROTECT], 0, None, 1), (BLISSEY, 100), [0, 1, 2, 3, 3, 2]),
    "sleep": ((BLISSEY, 100, [SPORE, LEECH, SPLASH, SUBSTITUTE], 0, None, 1), (BLISSEY, 100), [0, 1, 2, 3, 2, 2, 2, 2]),
    "burn": ((BLISSEY, 100, [WISP, LIGHT_SCREEN, REFLECT, SPLASH], 0, None, 1), (BLISSEY, 100), [0, 1, 2, 3, 3]),
    "para": ((BLISSEY, 100, [TWAVE, SPLASH], 0, None, 1), (BLISSEY, 100), [0, 1, 1, 1, 1]),
    "confuse": ((BLISSEY, 100, [CONFUSE, TACKLE], 0, None, 1), (BLISSEY, 100), [0, 1, 1, 1, 1, 1]),
    "crit": ((BLISSEY, 100, [FROST_BREATH], 0, None, 1), (BLISSEY, 100), [0, 0, 0]),
    "noeffect": ((BLISSEY, 100, [TACKLE, SPLASH], 0, None, 1), (GASTLY, 60), [0, 1, "run"]),
    "notvery": ((BLISSEY, 100, [EMBER], 0, None, 1), (SQUIRTLE, 80), [0, 0, "run"]),
    "levelup": ((DITTO, 5, [SHADOW_SNEAK], 0, None, 1), (SHEDINJA, 50), [0]),
    "leftovers": ((BLISSEY, 100, [SPLASH], LEFTOVERS, None, 0.5), (BLISSEY, 100), [0, 0, 0]),
    "lifeorb": ((BLISSEY, 100, [TACKLE], LIFE_ORB, None, 1), (BLISSEY, 100), [0, 0]),
    "sitrus": ((BLISSEY, 100, [SPLASH], SITRUS, None, 0.55), (MEWTWO, 100), [0, 0, 0]),
    "intimidate": ((BLISSEY, 100, [SPLASH], 0, INTIMIDATE, 1), (BLISSEY, 100), [0]),
    "drizzle": ((BLISSEY, 100, [SPLASH], 0, DRIZZLE, 1), (BLISSEY, 100), [0, 0]),
    "drought": ((BLISSEY, 100, [SPLASH], 0, DROUGHT, 1), (BLISSEY, 100), [0]),
    "speedboost": ((BLISSEY, 100, [SPLASH], 0, SPEED_BOOST, 1), (BLISSEY, 100), [0, 0]),
    "foe_intimidate": ((BLISSEY, 100, [SPLASH], 0, None, 1), (GYARADOS, 60), [0, "run"]),
    "switch": ((BLISSEY, 100, [SPLASH], 0, None, 1), (BLISSEY, 100), ["switch", 0, "run"]),
    "faint": ((BLISSEY, 100, [SPLASH], 0, None, 0.01), (MEWTWO, 100), [0, 0]),
    "catch": ((BLISSEY, 100, [SPLASH], 0, None, 1), (GYARADOS, 30), ["ball"]),
    "run": ((BLISSEY, 100, [SPLASH], 0, None, 1), (BLISSEY, 50), ["run"]),
    "trainer": ((MEWTWO, 100, [PSYCHIC], 0, None, 1), ("trainer", 252), [0] * 6),
}
MASTER_BALL = 1
ICON_TAIL = __import__("re").compile("\\s{2,}\ufffd+$")   # the command prompt's two status icons at x 213-231
BATTLE_BAG = {"balls": (192, 56), "first": (64, 28), "use": (100, 173)}


def battle_items(spec):
    names = list(BATTLES)
    if not spec or spec == "all":
        return list(range(len(names)))
    return [names.index(n) if n in names else int(n) for n in spec.split(",")]


class BattleLog:
    """battle_string reads (MsgLog rows of NARC 277, banks 0-2) and the decoded message-window pages."""

    def __init__(self, h, ml, f):
        self.h, self.ml, self.watch = h, ml, PageWatch(h, f) if f else None
        self.mark = ml.mark()
        self.shots = []

    def poll(self):
        if self.watch:
            self.watch.poll()
        else:                      # CN: keep a frame whenever the window changes (for the pairs)
            img = self.h.emu.screenshot()
            key = img.crop((16, 152, 232, 184)).tobytes()
            if not self.shots or self.shots[-1][0] != key:
                self.shots.append((key, self.h.frame, img))

    def reads(self):
        """(source, bank, id, frame) of battle_string (banks 0-2) and a027 reads since the battle started."""
        out = []
        for narc, b, i, fr in self.ml.rows[self.mark:]:
            if narc == NARC_BATTLE and b in (0, 1, 2):
                out.append(("battle", b, i, fr))
            elif narc == NARC_A027:
                out.append(("a027", b, i, fr))
        return out

    def step(self, n):
        for _ in range(0, n, POLL):
            self.h.step(POLL)
            self.poll()


def b_turn(h, log, action, max_frames=4000):
    """One command at the battle menu (move slot, 'switch', 'ball' or 'run'), then B through the messages,
    polling the message window, until the command menu or the field is back."""
    import emu_guide0107 as G
    if not h.run_until(lambda h: (log.poll() or True) and h.on_screen("battle_menu"), 2000, every=POLL):
        return "no_menu"
    if action == "run":
        h.touch(*E.BATTLE_BUTTONS["run"], frames=10, after=0)
    elif action == "ball":
        h.touch(*E.BATTLE_BUTTONS["bag"], frames=10, after=120)
        h.touch(*BATTLE_BAG["balls"], frames=10, after=120)
        h.touch(*BATTLE_BAG["first"], frames=10, after=120)
        h.touch(*BATTLE_BAG["use"], frames=10, after=0)
    elif action == "switch":
        h.touch(*E.BATTLE_BUTTONS["pokemon"], frames=10, after=90)
        h.touch(*E.PARTY_SLOTS[1], frames=10, after=60)
        if G._match(h, G.PARTY_SUBMENU):
            h.touch(*G.SUBMENU_SHIFT, frames=10, after=0)
    else:
        h.touch(*E.BATTLE_BUTTONS["fight"], frames=10, after=40)
        h.touch(*E.MOVE_BUTTONS[action], frames=10, after=0)
    nxt = 2
    for i in range(0, max_frames, POLL):
        log.step(POLL)
        if h.in_field():
            log.step(60)
            return "field"
        if i > 60 and h.on_screen("battle_menu"):
            return "menu"
        if i % 60 == 0 and G._match(h, G.PARTY_LIST):      # our Pokemon fainted: send the next one
            h.touch(*E.PARTY_SLOTS[nxt], frames=10, after=60)
            if G._match(h, G.PARTY_SUBMENU):
                h.touch(*G.SUBMENU_SHIFT, frames=10, after=30)
            nxt = nxt % 5 + 1
            continue
        if i % 64 == 60:
            h.press("B", after=0)
    return "stuck"


def run_battle(h, ml, f, name, d, lang):
    import emu_guide0107 as G
    (sp, lv, moves, item, ability, hpf), foe, plan = BATTLES[name]
    G.lead(h, sp, level=lv, moves=moves + [0] * (4 - len(moves)), pp=[30] * len(moves) + [0] * (4 - len(moves)))
    fields = {}
    if item:
        fields["item"] = item
    if ability:
        fields["ability"] = ability
    if fields:
        h.edit_party_mon(0, **fields)
    if hpf < 1:
        import emu_hackbugs as B
        hp_max = B.mon(h, 0)["stats"][0] if "stats" in B.mon(h, 0) else None
        if hp_max:
            G.set_party_hp(h, 0, max(1, int(hp_max * hpf)))
    if name == "catch":
        h.bag_put_first(MASTER_BALL, 5, pocket="balls")
    log = BattleLog(h, ml, f)
    if foe[0] == "trainer":
        h.trainer_battle(foe[1])
    else:
        h.run_script(program=E.script_bytes(("LockAll",), ("WildBattle", foe[0], foe[1], 0), ("ReleaseAll",), ("End",)))
    results = []
    for action in plan:
        r = b_turn(h, log, action)
        results.append(r)
        if r != "menu":
            break
    if h.on_screen("battle_menu"):
        h.touch(*E.BATTLE_BUTTONS["run"], frames=10, after=0)
        log.step(400)
    return log, results


PROMPT_ICON_X = 211          # x of the prompt icons (YES/NO, command prompt) at the right of the battle window
STATS_WINDOW_X = 128         # the level-up stats window covers the battle window from about here


def _literal(en):
    """True when a string prints some fixed text (not only buffers)."""
    return bool(T.TAG.sub("", en or "").strip())


def _candidate_text(src, b, i):
    return en_of("battle_string", b, i) if src == "battle" else en_of("a027", b, i)


def match_pages(pages, reads):
    """Assign each decoded page to the newest message read before it (battle_string banks 0-2, and a027
    lines such as a trainer's defeat line) whose text (buffers = any text) has a page with the same lines.
    Strings that are only buffers (the level-up stats numbers) are not candidates. A page that matches
    nothing is classified: 'covered' (a line ends in unknown pixels left of the stats window and its text
    starts a candidate's line: the stats window is drawn over the box), 'prompt_icon' (the unknown pixels
    sit at the prompt icons: text runs under them), else 'unmatched'."""
    out, floor = [], 0
    for pg in pages:
        raw = page_texts(pg)
        lines = [ICON_TAIL.sub("", t) for t in raw]
        lines = [t for t in lines if t and t.strip(T.UNKNOWN)]
        # battle_string reads since a few before the last match; a027 lines (a trainer's defeat line is
        # read when the battle starts) from any time before the page
        cands = [(k, r) for k, r in enumerate(reads) if r[3] <= pg["frame"] and (k >= floor - 6 or r[0] == "a027")]
        hit, prefix = None, None
        for k, (src, b, i, fr) in reversed(cands):
            en = _candidate_text(src, b, i)
            if not _literal(en):
                continue
            for pno, ep in enumerate(T.expected_lines(en)):
                ep = [x for x in ep if x]
                if len(ep) == len(lines) and all(T.line_matches(w, g) for w, g in zip(ep, lines)):
                    hit = (k, src, b, i, pno)
                    break
                if prefix is None and lines and len(ep) >= len(lines) and all(
                        T.line_matches(w, g) or (g.endswith(T.UNKNOWN) and _prefix_match(w, g.rstrip(T.UNKNOWN)))
                        for w, g in zip(ep, lines)):
                    prefix = (src, b, i, pno)
            if hit:
                break
        row = {"frame": pg["frame"], "lines": lines, "match": hit and [hit[1], hit[2], hit[3], hit[4]],
               "clipped": any(l["clipped"] for l in pg["lines"]),
               "unknown": sum(t.count(T.UNKNOWN) for t in lines),
               "right": max((l["right"] for l in pg["lines"]), default=0),
               "near": [[src, b, i] for src, b, i, fr in reads if pg["frame"] - 600 <= fr <= pg["frame"]][-4:]}
        if not hit:                     # trainer lines (a027/0718) are read by a reader MsgLog does not hook
            tid = _trainer_line(lines)
            if tid is not None:
                hit = (floor, "a027", TRAINER_TEXT_BANK, tid, 0)
                row["match"] = ["a027", TRAINER_TEXT_BANK, tid, 0]
        if hit:
            floor = hit[0]
            row["status"] = "ok" if not row["unknown"] else "unknown_pixels"
        elif prefix:
            row["prefix_of"] = list(prefix)
            cut = [T.LINE_H and l["right"] for l in pg["lines"] if l["unknown"]]
            icon = any(T.BOXES["battle"]["x0"] + r >= PROMPT_ICON_X for r in cut) and \
                "{VAR:0200" in _candidate_text(*prefix[:3])
            row["status"] = "prompt_icon" if icon else "covered"
        else:
            row["status"] = "unmatched"
        out.append(row)
    return out


TRAINER_TEXT_BANK = 718


def _trainer_line(lines):
    """Id of the a027/0718 trainer line whose single page equals the decoded lines, else None."""
    if not lines:
        return None
    for i, st in bank("a027", TRAINER_TEXT_BANK).items():
        for ep in T.expected_lines(st.get("en") or ""):
            ep = [x for x in ep if x]
            if ep == lines:
                return i
    return None


def _prefix_match(w, g):
    """g (decoded text cut by something drawn over it) is a prefix of a text that matches the expected line
    w (\\x00 = a buffer, any text)."""
    import re
    if not g:
        return False
    toks = [".+" if c == "\x00" else re.escape(c) for c in w]
    for k in range(len(toks), 0, -1):
        pat = "".join(toks[:k])
        if re.fullmatch(pat, g) or (toks[k - 1] == ".+" and re.fullmatch(pat[:-2] + ".*", g)):
            return True
    return False


def _battle_row(h, ml, f, k, name, d, lang):
    log, results = run_battle(h, ml, f, name, d, lang)
    reads = log.reads()
    row = {"id": k, "name": name, "turns": results,
           "reads": [[b, i] for src, b, i, _ in reads if src == "battle"]}
    if log.watch:
        pages = log.watch.pages
        m = match_pages(pages, reads)
        for j, (pg, mr) in enumerate(zip(pages, m)):
            if mr["status"] != "ok":
                p = d / f"{name}_page{j:02d}.png"
                pg["img"].save(p)
                mr["shot"] = str(p)
        row["pages"] = m
        row["status"] = "ok" if all(x["status"] in ("ok", "covered") for x in m) else "issue"
    else:
        shots = []
        for j, (_, fr, img) in enumerate(log.shots):
            p = d / f"{name}_{fr}.png"
            img.save(p)
            shots.append(str(p))
        row.update(status="captured", shots=shots)
    return row


def run_battle_child(rom, work, out):
    import emu_verify as V
    lang = lang_of(rom)
    d = out_root(out) / "battle" / lang
    d.mkdir(parents=True, exist_ok=True)
    f = T.font(str(rom), 1) if lang == "en" else None
    names = list(BATTLES)
    rows = ProgressList(out, "battle", lang, work)
    tmp = Path(tempfile.mkdtemp(prefix="sweep_battle_"))
    try:
        # one emulator per process (a second DeSmuME instance crashes): a field savestate per scenario
        with E.start_at(None, rom=rom, out=d, verbose=False, clock=CLOCK) as h:
            h.save_state(tmp / "field.ds")
            ml = V.MsgLog(h)
            for k in work:
                name = names[k]
                h.load_state(tmp / "field.ds")
                try:
                    row = _battle_row(h, ml, f, k, name, d, lang)
                except Exception as e:
                    row = {"id": k, "name": name, "status": "error", "error": repr(e)[-600:]}
                rows.append(row)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return list(rows)


def summarise_battle(rows, out):
    s = {}
    total = {b: len([i for i, x in bank("battle_string", b).items() if x.get("en")]) for b in (0, 1, 2)}
    for l, rs in rows.items():
        read = {(b, i) for r in rs for b, i in r.get("reads", [])}
        printed = {tuple(p["match"][1:3]) for r in rs for p in r.get("pages", [])
                   if p.get("match") and p["match"][0] == "battle"}
        s[l] = {"battles": len(rs), "status": {r["name"]: r.get("status") for r in rs},
                "ids_read": len(read), "ids_total": sum(total.values()), "ids_total_per_bank": total}
        if l == "en":
            pst = {}
            for r in rs:
                for p in r.get("pages", []):
                    pst[p["status"]] = pst.get(p["status"], 0) + 1
            s[l].update(ids_printed_checked=len(printed), pages=sum(len(r.get("pages", [])) for r in rs),
                        page_status=pst,
                        issue_pages=[{"battle": r["name"], **{k: p[k] for k in ("status", "lines", "near", "prefix_of",
                                                                               "shot") if k in p}}
                                     for r in rs for p in r.get("pages", []) if p["status"] not in ("ok", "covered")],
                        max_right_px=max((p["right"] for r in rs for p in r.get("pages", [])), default=0),
                        printed=sorted(printed))
    return s


# ----------------------------------------------------------------------------- runner
def progress_path(out, sweep, lang, work):
    return out_root(out) / sweep / "progress" / f"{lang}_{work[0]}_{len(work)}.jsonl"


class ProgressList(list):
    """A list of rows that also appends every row to the child's progress file."""

    def __init__(self, out, sweep, lang, work):
        super().__init__()
        self.args = (out, sweep, lang, work)

    def append(self, row):
        super().append(row)
        progress(*self.args, row)


def progress(out, sweep, lang, work, row):
    """Append one finished row (a child that dies, e.g. in the emulator, still leaves its rows)."""
    p = progress_path(out, sweep, lang, work)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def chunks(seq, n):
    k = max(1, (len(seq) + n - 1) // n)
    return [seq[i:i + k] for i in range(0, len(seq), k)]


def parse_ids(spec, default):
    if not spec or spec == "all":
        return default
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b or a) + 1))
    return [i for i in out if i in set(default)]


def run_sweep(sweep, roms, out, jobs=6, ids=None):
    """Split the work into child processes (per ROM), merge the rows, write the report."""
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.time()
    work = SWEEPS[sweep]["items"](ids)
    per_rom = max(1, jobs // len(roms))
    todo = [(l, c) for l in roms for c in chunks(work, per_rom)]

    def run(job):
        l, c = job
        spec = ",".join(str(x) for x in c)
        pp = progress_path(out, sweep, l, c)
        pp.unlink(missing_ok=True)
        try:
            return l, E.run_child(["sweeps", "--sweep", sweep, "--child", spec, "--rom", roms[l], "--out", out],
                                  timeout=child_timeout(sweep, c))
        except Exception as e:          # keep what the child finished; the rest of its work is reported
            done = [json.loads(x) for x in pp.read_text().splitlines()] if pp.exists() else []
            st = "timeout" if isinstance(e, E.ChildTimeout) else "error"
            return l, done + [{"status": st, "error": str(e)[-1500:], "items": c[len(done):len(done) + 5],
                               "lost": len(c) - len(done)}]
    with ThreadPoolExecutor(len(todo)) as ex:
        res = list(ex.map(run, todo))
    rows = {l: [] for l in roms}
    for l, r in res:
        rows[l] += r
    path = out_root(out) / sweep / "report.json"
    T.save_json(path, {"summary": None, "rows": rows})          # kept even if the summary fails
    errors = {l: [r for r in rs if r.get("status") in ("error", "timeout") and "id" not in r] for l, rs in rows.items()}
    rows = {l: [r for r in rs if "id" in r] for l, rs in rows.items()}
    report = SWEEPS[sweep]["summarise"](rows, out)
    report["child_errors"] = {l: [e.get("error", "")[-600:] for e in es] for l, es in errors.items() if es}
    report["seconds"] = round(time.time() - t0, 1)
    T.save_json(path, {"summary": report, "rows": rows, "child_errors": errors})
    return report, path


def child_timeout(sweep, work):
    """Wall-clock budget of one sweep child: boot plus a generous per-item time (about 4x what items took
    on 2026-10-06: trainers ~5 s, descriptions ~3.5 s, battles ~60 s each)."""
    return 600 + SWEEPS[sweep]["per_item"] * len(work)


def summarise_trainers(rows, out):
    s = {}
    for l, rs in rows.items():
        st = {}
        for r in rs:
            st[r.get("status")] = st.get(r.get("status"), 0) + 1
        s[l] = {"trainers": len(rs), "status": st,
                "intro_ids": sorted({tuple(r["intro"]) for r in rs if r.get("intro")}),
                "issues": [r["id"] for r in rs if r.get("status") not in ("ok", "captured")]}
        if l == "en":
            s[l]["max_right_px"] = max((r.get("right", 0) for r in rs), default=0)
    if "en" in rows and "cn" in rows:
        s["pairs"] = make_pairs(rows, out_root(out) / "trainers" / "pairs", lambda r: f"tr{r['id']:04d}")
    return s


def make_pairs(rows, dest, name, crop=(0, 0, 256, 192)):
    """CN|EN pairs (top screens side by side) of every EN row that is not 'ok'."""
    from PIL import Image
    dest.mkdir(parents=True, exist_ok=True)
    cn = {r.get("id"): r for r in rows.get("cn", [])}
    made = []
    for r in rows.get("en", []):
        if r.get("status") == "ok" or "shot" not in r:
            continue
        c = cn.get(r.get("id"), {})
        pair = Image.new("RGB", (2 * (crop[2] - crop[0]), crop[3] - crop[1]), (0, 0, 0))
        if c.get("shot") and Path(c["shot"]).exists():
            pair.paste(Image.open(c["shot"]).convert("RGB").crop(crop), (0, 0))
        pair.paste(Image.open(r["shot"]).convert("RGB").crop(crop), (crop[2] - crop[0], 0))
        p = dest / f"{name(r)}.png"
        pair.save(p)
        made.append(str(p))
    return len(made)


SWEEPS = {
    "trainers": {"items": lambda ids: parse_ids(ids, trainer_ids()), "child": run_trainers_child,
                 "summarise": summarise_trainers, "per_item": 20},
    "desc": {"items": desc_items, "child": run_desc_child, "summarise": summarise_desc, "per_item": 15},
    "battle": {"items": battle_items, "child": run_battle_child, "summarise": summarise_battle, "per_item": 300},
}


# Cheap subsets for `emu_harness.py suite` (about 1 min per ROM): trainers with long class+name pairs, the
# rival (name from the save) and names starting with O; the first bag page, Poké Ball (line 2 runs into the
# bag frame: past_panel, as in the US ROM), four moves, four abilities (two hack customs); the escape and
# an entry ability. EN: every row keeps the expected status; CN: every row is captured.
SUITE_SUBSETS = {
    "trainers": "171,251,252,350,390,1002",
    "desc": "1-6,10033-10036,20001,20022,20311,20326",
    "battle": "run,drizzle",
}
SUITE_EXPECT_EN = {("desc", 4): "past_panel"}


def suite_check(rom, out):
    lang = lang_of(rom)
    details, ok = {}, True
    for sweep, ids in SUITE_SUBSETS.items():
        report, _ = run_sweep(sweep, {lang: rom}, out, jobs=1, ids=ids)
        rows = json.loads((out_root(out) / sweep / "report.json").read_text())["rows"][lang]
        bad = []
        for r in rows:
            want = "captured" if lang == "cn" else SUITE_EXPECT_EN.get((sweep, r.get("id")), "ok")
            if r.get("status") != want:
                bad.append({"id": r.get("id"), "kind": r.get("kind"), "status": r.get("status"), "want": want})
        n_expected = len(SWEEPS[sweep]["items"](ids)) if sweep != "battle" else len(ids.split(","))
        if len(rows) < n_expected or bad or report.get("child_errors"):
            ok = False
        details[sweep] = {"rows": len(rows), "expected_rows": n_expected, "bad": bad[:10],
                          "child_errors": report.get("child_errors")}
    return ok, details


def rejudge(sweep, out):
    """Judge the saved EN screenshots of a finished sweep again with the current decoder and expectations
    (no emulator): after a change to emu_text, the boxes or the bank text."""
    from PIL import Image
    path = out_root(out) / sweep / "report.json"
    rep = json.loads(path.read_text())
    rows = rep["rows"]
    rom = None
    for r in rows.get("en", []):
        if r.get("shot") and Path(r["shot"]).exists() and r.get("status") not in ("not_shown", "no_source", "error",
                                                                                     "no_intro", "no_start"):
            rom = rom or str(E.DEF_ROM_EN)
            img = Image.open(r["shot"])
            if sweep == "desc":
                new = judge_desc(r["kind"], r["id"], img, T.font(rom, 0), "en")
            elif sweep == "trainers" and r.get("intro"):
                en, exp = trainer_expected(r["intro"][1], [tuple(x) for x in r.get("a027", [])])
                lines = T.read_lines(img, T.BOXES["battle"], T.font(rom, 1))
                ok, cmp = T.compare(exp, [l["text"] for l in lines])
                unknown = sum(l["unknown"] for l in lines)
                new = {"status": "ok" if ok and not unknown else "issue", "en": en, **cmp, "unknown": unknown,
                       "right": max((l["right"] for l in lines), default=0)}
            else:
                continue
            r.update(new)
    errors = rep.get("child_errors", {})
    report = SWEEPS[sweep]["summarise"](rows, out)
    report["rejudged"] = True
    report["child_errors"] = {l: [e.get("error", "")[-600:] for e in es] for l, es in errors.items() if es}
    T.save_json(path, {"summary": report, "rows": rows, "child_errors": errors})
    return report, path


def cmd(a):
    if getattr(a, "rejudge", False):
        report, path = rejudge(a.sweep, a.out)
        print(json.dumps(report, ensure_ascii=False, default=str)[:3000])
        print(json.dumps({"report": str(path)}))
        return 0
    if a.child:
        ids = [int(x) for x in a.child.split(",") if x]
        rows = SWEEPS[a.sweep]["child"](a.rom, ids, a.out)
        print("RESULT " + json.dumps(rows, ensure_ascii=False, default=str))
        return 0
    langs = ["cn", "en"] if a.lang == "both" else [a.lang]
    roms = {l: {"cn": a.rom_cn, "en": a.rom_en}[l] for l in langs}
    report, path = run_sweep(a.sweep, roms, a.out, a.jobs, a.ids)
    print(json.dumps(report, ensure_ascii=False, default=str)[:3000])
    print(json.dumps({"report": str(path)}))
    return 0
