"""Conservative, script-aware translation context for the untouched Chinese ROM.

Run from the repository root. ``build`` writes an ignored JSON index, never text
banks or a ROM. ``show REF`` reads that index and rejects stale source hashes.

This is a bounded static analysis, not a claim that a scene is reachable in a
playthrough. Entry declarations, map/event bindings and branch alternatives are
kept separate. Unknown commands erase value/buffer/predecessor assumptions.
Only explicitly identified message operands become text references.

Decoder: docs/romdata.py and docs/script_cmds.SOURCE.txt. Operand semantics were
checked against CN handlers (command table ARM9 0x020F793C): 44/45 literal bytes,
46/47 VarGet then low byte, 132 gender-selected literal bytes, 439/440 VarGet
bank then message ID. CallStd 020402A4 creates a child context with its own bank;
RestartCurrentScript 02040338 releases the parent, not a local Return. Buffer
193 takes a party slot, not a species ID. Unsupported consumers remain unknown.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

from docs import romdata as R

VERSION = 1
ROOT = Path(R.REPO)
DEFAULT_INDEX = ROOT / "work/build/translation_context/index.json"
MAPS = ROOT / "work/translate/bank_maps.json"
REF_RE = re.compile(r"a027/\d{4}#\d+\Z")


class SourceFile(TypedDict):
    path: str
    sha256: str


class Occurrence(TypedDict):
    script_file: int
    pc: int
    entry: int
    root: dict[str, Any]
    map_context: list[dict[str, Any]]
    message_opcode: str
    message_operand: dict[str, Any]
    call_path: list[dict[str, Any]]
    branches: list[dict[str, Any]]
    buffers: dict[str, dict[str, Any]]
    variables: dict[str, dict[str, Any]]
    previous_messages: list[dict[str, Any]]
    instruction_trace: list[dict[str, Any]]
    unknowns: list[str]


class RefContext(TypedDict):
    occurrences: list[Occurrence]


class ContextIndex(TypedDict):
    schema_version: int
    source: dict[str, SourceFile]
    refs: dict[str, RefContext]
    roots: dict[str, dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    stats: dict[str, Any]


@dataclass(frozen=True)
class Instruction:
    opcode: int
    args: tuple[int, ...]
    next_pc: int
    target: int | None


@dataclass
class Script:
    entries: list[int]
    instructions: dict[int, Instruction]


@dataclass(frozen=True)
class Frame:
    kind: Literal["local", "standard"]
    file: int
    bank: int | None
    return_pc: int
    call_pc: int
    target_file: int
    target_pc: int
    script_id: int | None = None
    comparison: dict[str, Any] | None = None


@dataclass
class State:
    file: int
    bank: int | None
    pc: int
    variables: dict[int, dict[str, Any]] = field(default_factory=dict)
    buffers: dict[int, dict[str, Any]] = field(default_factory=dict)
    stack: tuple[Frame, ...] = ()
    branches: tuple[dict[str, Any], ...] = ()
    comparison: dict[str, Any] | None = None
    previous: tuple[dict[str, Any], ...] = ()
    unknowns: tuple[str, ...] = ()
    menu_bank: int | None = None
    trace: tuple[dict[str, Any], ...] = ()


# Proven slot-first buffer operations. All second arguments here use VarGet.
# A resolved party slot remains a slot; no Pokémon/name is guessed from it.
BUFFER_OPS = {
    190: "player_name",
    191: "rival_name",
    192: "friend_name",
    193: "party_species_name",
    194: "item_name",
    195: "pocket_name",
    196: "tm_hm_move_name",
    197: "move_name",
    198: "integer",
    199: "party_nickname",
    200: "trainer_class_name",
    202: "species_name",
    660: "trainer_name",
}

# Known commands that do not assign script variables, replace message buffers,
# or dispatch another script. Narrow by design; false unknowns beat false facts.
TRANSPARENT = {
    0,
    1,
    49,
    50,
    51,
    52,
    53,
    54,
    73,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    82,
    84,
    85,
    87,
    94,
    95,
    96,
    97,
    98,
    99,
    104,
}
BRANCHES = {23, 24, 25, 28, 29, 225}
KNOWN_MESSAGES = {44, 45, 46, 47, 55, 59, 66, 132, 439, 440, 751}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_files(
    rom_path: Path = Path(R.ROM_PATH), maps_path: Path = MAPS
) -> dict[str, SourceFile]:
    paths = {
        "rom": rom_path,
        "bank_maps": maps_path,
        "script_cmds": Path(R.HERE) / "script_cmds.json",
        "romdata": Path(R.__file__),
        "extractor": Path(__file__),
    }
    return {
        name: {"path": str(path.resolve()), "sha256": sha256(path)} for name, path in paths.items()
    }


def decode(data: bytes) -> Script:
    """Require a valid entry-table terminator before using romdata's decoder.

    Script-header members are a different binary format. Rejecting malformed
    tables also prevents a header's arbitrary integers becoming entrypoints.
    """
    p, entries = 0, []
    while p + 2 <= len(data):
        if struct.unpack_from("<H", data, p)[0] == 0xFD13:
            p += 2
            break
        if p + 4 > len(data):
            raise ValueError("truncated script entry table")
        entries.append(p + 4 + struct.unpack_from("<i", data, p)[0])
        p += 4
    else:
        raise ValueError("missing script entry-table terminator")
    if not entries or any(e < p or e + 2 > len(data) for e in entries):
        raise ValueError("invalid script entry offset")
    got, ins = R.disasm(data)
    if got != entries:
        raise ValueError("decoder entry-table disagreement")
    return Script(
        entries,
        {
            pc: Instruction(op, tuple(args), nxt, target)
            for pc, (op, args, nxt, target) in ins.items()
        },
    )


def resolve_script_id(
    script_id: int, local_file: int, local_bank: int | None, mapping: list[tuple[int, int, int]]
) -> tuple[int, int, int | None] | None:
    """Return file, zero-based entry, bank using the CN engine's first match."""
    if script_id in (0, 0xFFFF):
        return None
    for lower, file, bank in mapping:
        if script_id >= lower:
            return file, script_id - lower, bank
    return local_file, script_id - 1, local_bank


def operand(raw: int, state: State, *, indirect: bool = True) -> dict[str, Any]:
    if not indirect or raw < 0x4000:
        return {"raw": raw, "value": raw, "kind": "literal"}
    known = state.variables.get(raw)
    return {
        "raw": raw,
        "value": known["value"] if known else None,
        "kind": "variable",
        "variable": f"0x{raw:04X}",
        "provenance": {"source": known["source"]}
        if known
        else {"reason": "value not established on this path"},
    }


def forget(state: State, reason: str) -> State:
    return replace(
        state,
        variables={},
        buffers={},
        previous=(),
        comparison=None,
        menu_bank=None,
        unknowns=tuple(dict.fromkeys((*state.unknowns, reason)))[-8:],
    )


def instruction_evidence(state: State, ins: Instruction) -> dict[str, Any]:
    return {
        "script_file": state.file,
        "pc": state.pc,
        "opcode": R.cmds()[ins.opcode][0],
        "args": list(ins.args),
    }


def proven_condition(comparison: dict[str, Any] | None, condition: int) -> bool | None:
    """CN unsigned comparison table at ARM9 0x020F78D8; unknowns stay unknown."""
    if comparison is None or not 0 <= condition <= 5:
        return None
    left = comparison.get("left", {}).get("value")
    right = comparison.get("right", {}).get("value")
    if type(left) is not int or type(right) is not int:
        return None
    return (left < right, left == right, left > right, left <= right, left >= right, left != right)[
        condition
    ]


def messages(state: State, ins: Instruction) -> list[tuple[int | None, int | None, dict[str, Any]]]:
    """Explicit consumer table. No command-name regex or any-integer fallback."""
    op, a = ins.opcode, ins.args
    if op in (44, 45, 46, 47, 55, 59):
        v = operand(a[0], state, indirect=op in (46, 47))
        value = v["value"]
        if op in (46, 47) and value is not None:
            value &= 0xFF
        return [
            (state.bank, value, {"index": 0, **v, "message_id": value, "low_byte": op in (46, 47)})
        ]
    if op == 132:
        return [
            (
                state.bank,
                a[i],
                {"index": i, "raw": a[i], "value": a[i], "kind": "literal", "gender": gender},
            )
            for i, gender in enumerate(("male", "female"))
        ]
    if op in (439, 440):
        bank, msg = operand(a[0], state), operand(a[1], state)
        return [(bank["value"], msg["value"], {"index": 1, **msg, "external_bank": bank})]
    if op in (66, 751):
        msg = operand(a[0], state, indirect=op == 751)
        return [
            (
                state.menu_bank,
                msg["value"],
                {
                    "index": 0,
                    **msg,
                    "consumer": "menu-option",
                    "bank_source": "latest menu initialization",
                },
            )
        ]
    return []


def header_events(data: bytes) -> list[dict[str, Any]]:
    """Read map-load script header records, with strict bounds."""
    out, p = [], 0
    while p < len(data) and data[p]:
        if p + 5 > len(data):
            raise ValueError("truncated map script header")
        kind = data[p]
        value = struct.unpack_from("<I", data, p + 1)[0]
        if kind == 1:
            q = p + 5 + value
            while True:
                if q + 2 > len(data):
                    raise ValueError("truncated conditional map header")
                var = struct.unpack_from("<H", data, q)[0]
                if not var:
                    break
                if q + 6 > len(data):
                    raise ValueError("truncated conditional map header row")
                var, expected, script = struct.unpack_from("<HHH", data, q)
                out.append(
                    {
                        "script": script,
                        "type": kind,
                        "variable": var,
                        "expected": expected,
                        "offset": q,
                    }
                )
                q += 6
        else:
            out.append({"script": value, "type": kind, "offset": p})
        p += 5
    return out


def analyze(
    files: list[bytes],
    zones: list[dict[str, Any]],
    mapping: list[tuple[int, int, int]],
    events: list[bytes] | None = None,
    *,
    max_states: int = 250,
    max_call_depth: int = 8,
    max_contexts: int = 8,
    root_files: set[int] | None = None,
) -> ContextIndex:
    """Pure binary-data boundary, usable with synthetic scripts in unit tests."""
    if max_states < 1 or max_call_depth < 1 or max_contexts < 1:
        raise ValueError("analysis bounds must be positive")
    result: ContextIndex = {
        "schema_version": VERSION,
        "source": {},
        "refs": {},
        "roots": {},
        "diagnostics": [],
        "stats": {},
    }
    scripts: dict[int, Script] = {}
    diagnostics = result["diagnostics"]
    header_ids = {z["script_header_bank"] for z in zones if "script_header_bank" in z}
    for f, data in enumerate(files):
        if f in header_ids:
            continue
        try:
            scripts[f] = decode(data)
        except (ValueError, IndexError, struct.error) as exc:
            diagnostics.append({"kind": "decode-failed", "script_file": f, "reason": str(exc)})
    bindings: dict[tuple[int, int, int | None], list[dict[str, Any]]] = defaultdict(list)
    file_banks: dict[int, set[int | None]] = defaultdict(set)
    file_maps: dict[tuple[int, int | None], list[dict[str, Any]]] = defaultdict(list)
    for z in zones:
        f, bank = z["scripts_bank"], z["msg_bank"]
        file_banks[f].add(bank)
        context = {
            "zone_id": z["zone_id"],
            "scripts_bank": f,
            "msg_bank": bank,
            "map_name_en": z.get("map_name_en"),
            "map_name_zh": z.get("map_name_zh"),
        }
        file_maps[f, bank].append(context)
        if events is None:
            continue
        try:
            ev = R.parse_events(events[z["events_bank"]])
            roots = [
                {"kind": kind, "index": i, "event": item}
                for kind in ("obj", "bg", "coord")
                for i, item in enumerate(ev[kind])
            ]
            if "script_header_bank" in z:
                roots += [
                    {"kind": "map-header", "event": item}
                    for item in header_events(files[z["script_header_bank"]])
                ]
            for item in roots:
                event_target = resolve_script_id(item["event"]["script"], f, bank, mapping)
                if event_target:
                    ff, entry, mb = event_target
                    binding = {"zone_id": z["zone_id"], **item}
                    if ff in scripts and 0 <= entry < len(scripts[ff].entries):
                        bindings[ff, entry, mb].append(binding)
                    else:
                        diagnostics.append(
                            {
                                **binding,
                                "event_kind": binding["kind"],
                                "kind": "invalid-event-root",
                                "target": list(event_target),
                            }
                        )
        except (KeyError, IndexError, ValueError, struct.error) as exc:
            diagnostics.append(
                {"kind": "event-decode-failed", "zone_id": z["zone_id"], "reason": str(exc)}
            )
    for _lo, f, bank in mapping:
        file_banks[f].add(bank)
    emitted: set[str] = set()
    counts: Counter[str] = Counter()
    sites: dict[tuple[str, int, int], list[tuple[str, Occurrence]]] = defaultdict(list)
    omitted: Counter[tuple[str, int, int]] = Counter()
    visited_files: set[int] = set()
    if root_files is not None and (not root_files or not root_files.issubset(scripts)):
        raise ValueError("root-file selection must contain decoded script files")

    def emit(s: State, ins: Instruction, root: dict[str, Any], maps: list[dict[str, Any]]) -> State:
        previous = []
        for bank, msg, message_operand in messages(s, ins):
            if bank is None or msg is None:
                diagnostics.append(
                    {
                        "kind": "unresolved-message",
                        **instruction_evidence(s, ins),
                        "bank": bank,
                        "message_operand": message_operand,
                        "root": root,
                    }
                )
                continue
            ref = f"a027/{bank:04d}#{msg}"
            occurrence: Occurrence = {
                "script_file": s.file,
                "pc": s.pc,
                "entry": root["entry"],
                "root": root,
                "map_context": maps,
                "message_opcode": R.cmds()[ins.opcode][0],
                "message_operand": message_operand,
                "call_path": [frame.__dict__ for frame in s.stack],
                "branches": list(s.branches),
                "buffers": {str(k): v for k, v in sorted(s.buffers.items())},
                "variables": {f"0x{k:04X}": v for k, v in sorted(s.variables.items())},
                "previous_messages": list(s.previous),
                "instruction_trace": list(s.trace),
                "unknowns": list(s.unknowns),
            }
            if "gender" in message_operand:
                occurrence["branches"] = [
                    *occurrence["branches"],
                    {
                        "script_file": s.file,
                        "pc": s.pc,
                        "kind": "gender-message",
                        "player_gender": message_operand["gender"],
                    },
                ]
            key = json.dumps([ref, occurrence], sort_keys=True, separators=(",", ":"))
            if key not in emitted:
                site = (ref, s.file, s.pc)
                existing = sites[site]
                root_counts = Counter(row["root"]["id"] for _, row in existing)
                victims = []
                if len(existing) >= max_contexts:
                    # Prefer actual map-bound caller roots over bare standard
                    # entry templates, then diversify roots before more paths.
                    priority = (bool(root.get("event_binding_count")), bool(maps))
                    for old_key, old in existing:
                        old_priority = (
                            bool(old["root"].get("event_binding_count")),
                            bool(old["map_context"]),
                        )
                        if priority > old_priority or (
                            not root_counts[root["id"]]
                            and root_counts[old["root"]["id"]] > 1
                            and priority >= old_priority
                        ):
                            victims.append((old_key, old))
                keep = len(existing) < max_contexts or bool(victims)
                if keep:
                    if victims:
                        old_key, old = victims[0]
                        existing.remove((old_key, old))
                        result["refs"][ref]["occurrences"].remove(old)
                        emitted.discard(old_key)
                        omitted[site] += 1
                    emitted.add(key)
                    existing.append((key, occurrence))
                    result["refs"].setdefault(ref, {"occurrences": []})["occurrences"].append(
                        occurrence
                    )
                else:
                    omitted[site] += 1
            previous.append(
                {
                    "ref": ref,
                    "script_file": s.file,
                    "pc": s.pc,
                    "relation": "immediate-previous-message-on-static-path",
                    **(
                        {"player_gender": message_operand["gender"]}
                        if "gender" in message_operand
                        else {}
                    ),
                }
            )
        return s if ins.opcode in (66, 751) else replace(s, previous=tuple(previous))

    for f, script in sorted(scripts.items()):
        if root_files is not None and f not in root_files:
            continue
        for bank in sorted(file_banks.get(f, {None}), key=lambda x: -1 if x is None else x):
            for entry, start in enumerate(script.entries):
                root_id = f"{f}:{bank}:{entry + 1}"
                full_root: dict[str, Any] = {
                    "id": root_id,
                    "kind": "declared-entry",
                    "script_file": f,
                    "entry": entry + 1,
                    "entry_pc": start,
                    "message_bank": bank,
                    "event_bindings": bindings.get((f, entry, bank), []),
                    "world_state_feasibility": "unproven",
                }
                result["roots"][root_id] = full_root
                root = {k: v for k, v in full_root.items() if k != "event_bindings"}
                root["event_binding_count"] = len(full_root["event_bindings"])
                maps = file_maps.get((f, bank), [])
                todo = deque([State(f, bank, start)])
                seen: set[str] = set()
                steps = 0
                counts["roots"] += 1
                while todo and steps < max_states:
                    s = todo.popleft()
                    # Unknown-warning histories are excluded from the state key;
                    # they are explanatory, not executable state.
                    key = json.dumps(
                        [
                            s.file,
                            s.bank,
                            s.pc,
                            s.variables,
                            s.buffers,
                            [x.__dict__ for x in s.stack],
                            s.branches,
                            s.comparison,
                            s.previous,
                            s.menu_bank,
                        ],
                        sort_keys=True,
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    steps += 1
                    ins = scripts.get(s.file, Script([], {})).instructions.get(s.pc)
                    if ins is None:
                        diagnostics.append(
                            {
                                "kind": "decode-frontier",
                                "script_file": s.file,
                                "pc": s.pc,
                                "root": root,
                            }
                        )
                        continue
                    op, a = ins.opcode, ins.args
                    visited_files.add(s.file)
                    evidence = instruction_evidence(s, ins)
                    s = replace(s, trace=(*s.trace[-11:], evidence))
                    if op in KNOWN_MESSAGES:
                        s = emit(s, ins, root, maps)
                    elif op in BUFFER_OPS:
                        value = operand(a[1], s) if len(a) > 1 else None
                        s = replace(
                            s,
                            buffers={
                                **s.buffers,
                                a[0]: {
                                    "kind": BUFFER_OPS[op],
                                    "slot": a[0],
                                    "operand": value,
                                    "source": evidence,
                                    "runtime_name": "unknown",
                                },
                            },
                        )
                    elif op in (64, 65, 749, 750):
                        variables = dict(s.variables)
                        variables.pop(a[4], None)  # menu result is written later
                        s = replace(
                            s, menu_bank=189 if op in (64, 749) else s.bank, variables=variables
                        )
                    elif op in (67, 752):
                        pass  # MenuExec; result destination invalidated at init
                    elif op in (41, 42, 43, 39, 40):
                        val = operand(a[1], s, indirect=op != 41)
                        variables = dict(s.variables)
                        number = val["value"]
                        if op in (39, 40):
                            old = variables.get(a[0], {}).get("value")
                            number = (
                                None
                                if old is None or number is None
                                else (old + (number if op == 39 else -number)) & 0xFFFF
                            )
                        if number is None:
                            variables.pop(a[0], None)
                        else:
                            variables[a[0]] = {"value": number, "source": evidence, "input": val}
                        s = replace(s, variables=variables)
                    elif op in (17, 18):
                        s = replace(
                            s,
                            comparison={
                                "source": evidence,
                                "left": operand(a[0], s),
                                "right": operand(a[1], s, indirect=op == 18),
                            },
                        )
                    elif op in (32, 38):
                        s = replace(
                            s, comparison={"source": evidence, "result": "unknown flag state"}
                        )
                    elif op == 19:
                        spawn_target = resolve_script_id(a[0], s.file, s.bank, mapping)
                        diagnostics.append(
                            {
                                "kind": "concurrent-script",
                                **evidence,
                                "target": list(spawn_target) if spawn_target else None,
                                "reason": "RunScript spawns a separate context; shared state and message order unknown",
                            }
                        )
                        s = forget(
                            s,
                            "RunScript concurrency: shared state and previous-message order unknown",
                        )
                    elif op not in TRANSPARENT | BRANCHES | {2, 20, 21, 22, 26, 27}:
                        counts[f"opaque_opcode:{op}"] += 1
                        s = forget(
                            s,
                            f"Unmodeled effects of {R.cmds()[op][0]} at {s.file}:{s.pc}; values, buffers and previous message cleared",
                        )

                    if op == 2:
                        # End terminates THIS context; it is never a local Return.
                        if any(x.kind == "standard" for x in s.stack):
                            diagnostics.append(
                                {"kind": "standard-end-without-release", **evidence, "root": root}
                            )
                        continue
                    if op == 27:
                        if s.stack and s.stack[-1].kind == "local":
                            frame = s.stack[-1]
                            todo.append(
                                replace(
                                    s,
                                    file=frame.file,
                                    bank=frame.bank,
                                    pc=frame.return_pc,
                                    stack=s.stack[:-1],
                                )
                            )
                        else:
                            diagnostics.append(
                                {"kind": "return-without-local-call", **evidence, "root": root}
                            )
                        continue
                    if op == 21:
                        standard = next(
                            (
                                i
                                for i in range(len(s.stack) - 1, -1, -1)
                                if s.stack[i].kind == "standard"
                            ),
                            None,
                        )
                        if standard is not None:
                            frame = s.stack[standard]
                            after = scripts[s.file].instructions.get(ins.next_pc)
                            clean_end = after is not None and after.opcode == 2
                            resumed = (
                                s
                                if clean_end
                                else forget(
                                    s,
                                    "Standard child continues after releasing parent: shared state/order unknown",
                                )
                            )
                            todo.append(
                                replace(
                                    resumed,
                                    file=frame.file,
                                    bank=frame.bank,
                                    pc=frame.return_pc,
                                    stack=s.stack[:standard],
                                    comparison=frame.comparison,
                                )
                            )
                            if clean_end:
                                continue
                            # Child still runs. Its local stack remains, but parent
                            # is no longer a suspended call to return into.
                            s = replace(
                                forget(s, "Parent resumed concurrently"),
                                stack=s.stack[standard + 1 :],
                            )
                        else:
                            s = forget(s, "RestartCurrentScript parent context unavailable")
                    if op in (20, 26, 29):
                        target: tuple[int, int, int | None] | None
                        if op == 20:
                            resolved = resolve_script_id(a[0], s.file, s.bank, mapping)
                            if (
                                resolved
                                and resolved[0] in scripts
                                and 0 <= resolved[1] < len(scripts[resolved[0]].entries)
                            ):
                                ff, ei, bb = resolved
                                target = ff, scripts[ff].entries[ei], bb
                            else:
                                target = None
                        else:
                            target = (
                                (s.file, ins.target, s.bank) if ins.target is not None else None
                            )
                        if len(s.stack) >= max_call_depth or target is None:
                            diagnostics.append(
                                {
                                    "kind": "unresolved-call",
                                    **evidence,
                                    "root": root,
                                    "reason": "call-depth bound" if target else "invalid target",
                                }
                            )
                            # Do not pretend a call whose behavior is unknown returned.
                            if op != 29:
                                continue
                        elif op != 29:
                            ff, pc, bb = target
                            frame = Frame(
                                "standard" if op == 20 else "local",
                                s.file,
                                s.bank,
                                ins.next_pc,
                                s.pc,
                                ff,
                                pc,
                                a[0] if op == 20 else None,
                                s.comparison if op == 20 else None,
                            )
                            todo.append(
                                replace(
                                    s,
                                    file=ff,
                                    bank=bb,
                                    pc=pc,
                                    stack=(*s.stack, frame),
                                    comparison=None if op == 20 else s.comparison,
                                )
                            )
                            continue
                    if op in BRANCHES:
                        # Only established numeric comparisons are pruned.
                        # Runtime flags/world state retain both alternatives.
                        truth = proven_condition(s.comparison, a[0]) if op in (28, 29) else None
                        for taken in (False, True):
                            if truth is not None and taken != truth:
                                counts["pruned_proven_branches"] += 1
                                continue
                            branch = {
                                **evidence,
                                "taken": taken,
                                "condition_code": a[0] if op in (28, 29) else None,
                                "comparison": s.comparison if op in (28, 29) else None,
                                "proven_result": truth,
                            }
                            nxt = replace(s, branches=(*s.branches[-7:], branch))
                            if op == 29 and taken:
                                if target is not None and len(s.stack) < max_call_depth:
                                    ff, pc, bb = target
                                    frame = Frame(
                                        "local", s.file, s.bank, ins.next_pc, s.pc, ff, pc
                                    )
                                    todo.append(
                                        replace(
                                            nxt, file=ff, bank=bb, pc=pc, stack=(*s.stack, frame)
                                        )
                                    )
                            else:
                                branch_pc = ins.target if taken else ins.next_pc
                                if branch_pc is not None:
                                    todo.append(replace(nxt, pc=branch_pc))
                        continue
                    next_pc = ins.target if op == 22 else ins.next_pc
                    if next_pc is not None:
                        todo.append(replace(s, pc=next_pc))
                counts["states"] += steps
                if todo:
                    diagnostics.append(
                        {
                            "kind": "state-budget-exhausted",
                            "root": root,
                            "limit": max_states,
                            "pending_states": len(todo),
                        }
                    )
    # Inventory explicit operands even beyond bounded path walks. These are
    # deliberately NOT dialogue contexts: no invented entry, predecessor, buffer
    # state or branch history is supplied for an instruction-only discovery.
    for f, script in sorted(scripts.items()):
        if root_files is not None and f not in root_files | visited_files:
            continue
        for bank in sorted(file_banks.get(f, {None}), key=lambda x: -1 if x is None else x):
            root_id = f"{f}:{bank}:instruction-only"
            static_root: dict[str, Any] = {
                "id": root_id,
                "kind": "instruction-only",
                "script_file": f,
                "entry": 0,
                "entry_pc": None,
                "message_bank": bank,
                "event_binding_count": 0,
                "world_state_feasibility": "unproven",
            }
            for pc, ins in sorted(script.instructions.items()):
                if ins.opcode not in KNOWN_MESSAGES:
                    continue
                s = State(
                    f,
                    bank,
                    pc,
                    unknowns=(
                        "Instruction-only discovery: no bounded execution path reconstructed; no dialogue order or speaker inferred",
                    ),
                )
                candidates = messages(s, ins)
                missing = [
                    (b, m)
                    for b, m, _ in candidates
                    if b is not None and m is not None and (f"a027/{b:04d}#{m}", f, pc) not in sites
                ]
                if not missing:
                    continue
                result["roots"].setdefault(root_id, {**static_root, "event_bindings": []})
                emit(s, ins, static_root, file_maps.get((f, bank), []))
                counts["instruction_only_sites"] += len(missing)
    for (ref, f, pc), amount in sorted(omitted.items()):
        diagnostics.append(
            {
                "kind": "occurrence-contexts-truncated",
                "ref": ref,
                "script_file": f,
                "pc": pc,
                "omitted_candidates": amount,
                "retained_limit": max_contexts,
            }
        )
        for _, occurrence in sites[ref, f, pc]:
            occurrence["unknowns"].append(
                f"{amount} candidate contexts omitted at this message site (limit {max_contexts}); root diversity preferred"
            )
    # Deduplicate repeated unknowns without hiding which entry roots are involved.
    unique = {json.dumps(d, sort_keys=True): d for d in diagnostics}
    result["diagnostics"] = list(unique.values())
    result["stats"] = {
        "script_files_decoded": len(scripts),
        "root_files": sorted(root_files) if root_files is not None else None,
        "traversed_files": sorted(visited_files),
        "refs": len(result["refs"]),
        "occurrences": sum(len(v["occurrences"]) for v in result["refs"].values()),
        "diagnostics": dict(Counter(d["kind"] for d in result["diagnostics"])),
        "max_states_per_root": max_states,
        "max_call_depth": max_call_depth,
        "max_contexts_per_message_site": max_contexts,
        "omitted_context_candidates": sum(omitted.values()),
        "scope": "bounded static entry paths; world-state feasibility and runtime speaker identity unproven",
        "limitations": [
            "Absence of an occurrence does not mean unused text.",
            "Unmodeled commands clear values, buffers and predecessor messages.",
            "RunScript concurrency and unsupported text consumers are unresolved.",
            "Proven numeric comparisons are pruned; unknown world state retains alternatives.",
        ],
        **dict(counts),
    }
    return result


def validate_index(value: Any) -> ContextIndex:
    """Validate the public JSON boundary before a context package consumes it."""
    if (
        not isinstance(value, dict)
        or type(value.get("schema_version")) is not int
        or value.get("schema_version") != VERSION
    ):
        raise ValueError("unsupported translation-context schema")
    for key in ("source", "refs", "roots", "stats"):
        if not isinstance(value.get(key), dict):
            raise ValueError(f"invalid context index {key}")
    if not isinstance(value.get("diagnostics"), list):
        raise ValueError("invalid context diagnostics")
    for name, source in value["source"].items():
        if (
            not isinstance(source, dict)
            or not isinstance(source.get("path"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", "")))
        ):
            raise ValueError(f"invalid source hash: {name}")
    for ref, context in value["refs"].items():
        if (
            not isinstance(ref, str)
            or not REF_RE.fullmatch(ref)
            or not isinstance(context, dict)
            or not isinstance(context.get("occurrences"), list)
        ):
            raise ValueError(f"invalid context reference: {ref!r}")
        for row in context["occurrences"]:
            if not isinstance(row, dict):
                raise ValueError(f"invalid occurrence for {ref}")
            for key in ("script_file", "pc", "entry"):
                if type(row.get(key)) is not int or row[key] < 0:
                    raise ValueError(f"invalid {key} for {ref}")
            for key in ("root", "message_operand", "buffers", "variables"):
                if not isinstance(row.get(key), dict):
                    raise ValueError(f"invalid {key} for {ref}")
            for key in (
                "map_context",
                "call_path",
                "branches",
                "previous_messages",
                "instruction_trace",
                "unknowns",
            ):
                if not isinstance(row.get(key), list):
                    raise ValueError(f"invalid {key} for {ref}")
            if not isinstance(row.get("message_opcode"), str):
                raise ValueError(f"invalid message opcode for {ref}")
            for prev in row["previous_messages"]:
                if not isinstance(prev, dict) or not REF_RE.fullmatch(str(prev.get("ref", ""))):
                    raise ValueError(f"invalid previous message for {ref}")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("context index contains non-JSON data") from exc
    return cast(ContextIndex, value)


def load_index(path: Path = DEFAULT_INDEX, *, verify_sources: bool = True) -> ContextIndex:
    value = validate_index(json.loads(Path(path).read_text(encoding="utf-8")))
    if verify_sources:
        required = {"rom", "bank_maps", "script_cmds", "romdata", "extractor"}
        if set(value["source"]) != required:
            raise ValueError("context index has incomplete source hashes; rebuild it")
        for name, record in value["source"].items():
            source = Path(record["path"])
            if not source.is_file() or sha256(source) != record["sha256"]:
                raise ValueError(f"stale translation context: {name}; rebuild the index")
        if Path(value["source"]["extractor"]["path"]).resolve() != Path(__file__).resolve():
            raise ValueError("context index was built by another extractor path")
    return value


def get_context(index: ContextIndex, ref: str) -> RefContext:
    if not REF_RE.fullmatch(ref):
        raise ValueError("expected a027/NNNN#id")
    return index["refs"].get(ref, {"occurrences": []})


def build_index(
    rom_path: Path = Path(R.ROM_PATH),
    maps_path: Path = MAPS,
    *,
    max_states: int = 250,
    max_call_depth: int = 8,
    max_contexts: int = 8,
    root_files: set[int] | None = None,
) -> ContextIndex:
    before = source_files(Path(rom_path), Path(maps_path))
    # Force refresh: romdata's legacy cache is mtime-based, whereas this artifact
    # promises hash-based provenance for these exact ROM bytes.
    rom = R.Rom(
        str(rom_path),
        cache=str(ROOT / "work/build/translation_context/rom_cache.pkl"),
        refresh=True,
    )
    zones = json.loads(Path(maps_path).read_text(encoding="utf-8"))["_zones"]
    result = analyze(
        rom["scripts"],
        zones,
        rom.std_mapping(),
        rom["events"],
        max_states=max_states,
        max_call_depth=max_call_depth,
        max_contexts=max_contexts,
        root_files=root_files,
    )
    after = source_files(Path(rom_path), Path(maps_path))
    if before != after:
        raise ValueError("source changed during context extraction; rebuild")
    result["source"] = before
    return validate_index(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build an ignored context index from the CN ROM")
    build.add_argument("--out", type=Path, default=DEFAULT_INDEX)
    build.add_argument("--rom", type=Path, default=Path(R.ROM_PATH))
    build.add_argument("--bank-maps", type=Path, default=MAPS)
    build.add_argument("--max-states", type=int, default=250)
    build.add_argument("--max-call-depth", type=int, default=8)
    build.add_argument("--max-contexts", type=int, default=8)
    build.add_argument(
        "--root-file",
        type=int,
        action="append",
        help="explore only these declared root files; callees remain decoded (repeatable)",
    )
    show = sub.add_parser("show", help="read a ref with freshness validation")
    show.add_argument("ref")
    show.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args(argv)
    if args.command == "show":
        print(
            json.dumps(get_context(load_index(args.index), args.ref), ensure_ascii=False, indent=2)
        )
    else:
        out = args.out.resolve()
        if not out.is_relative_to((ROOT / "work/build").resolve()):
            parser.error("ROM-derived indexes must stay under ignored work/build/")
        result = build_index(
            args.rom,
            args.bank_maps,
            max_states=args.max_states,
            max_call_depth=args.max_call_depth,
            max_contexts=args.max_contexts,
            root_files=set(args.root_file) if args.root_file is not None else None,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(out.suffix + ".tmp")
        temp.write_text(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        temp.replace(out)
        print(json.dumps(result["stats"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
