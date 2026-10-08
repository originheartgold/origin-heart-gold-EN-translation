#!/usr/bin/env python3
"""Build a local, versioned evidence package for one translation. Never calls an API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

import qa
import text_catalog as catalog

Mode = Literal["review", "independent"]
Successors = dict[str, list[dict[str, Any]]]
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INDEX = ROOT / "work/build/translation_context/index.json"


class SourceText(TypedDict):
    zh: str
    sha256: str
    language: str


class CurrentTranslation(TypedDict):
    en: str | None
    sha256: str
    status: str | None
    origin: str | None
    notes: str | None


class ReviewPackage(TypedDict):
    schema_version: int
    mode: Mode
    ref: str
    source: SourceText
    linguistics: dict[str, Any]
    context: dict[str, Any]
    related_occurrences: dict[str, Any]
    decisions: dict[str, list[dict[str, Any]]]
    layout: dict[str, Any]
    provenance: dict[str, Any]
    warnings: list[str]
    translation: NotRequired[CurrentTranslation]
    annotation: NotRequired[dict[str, Any] | None]
    package_sha256: NotRequired[str]


@dataclass(frozen=True)
class PackageOptions:
    mode: Mode = "review"
    related_limit: int = 20
    occurrence_limit: int = 12

    def __post_init__(self) -> None:
        if self.mode not in ("review", "independent"):
            raise ValueError("mode must be review or independent")
        if not 0 <= self.related_limit <= 100:
            raise ValueError("related_limit must be between 0 and 100")
        if not 1 <= self.occurrence_limit <= 1000:
            raise ValueError("occurrence_limit must be between 1 and 1000")


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_output(path: Path, root: Path) -> None:
    if not path.resolve().is_relative_to((root / "work/build").resolve()):
        raise ValueError("translation packages contain game text; write them under work/build/")


def ref_matches(pattern: str, ref: str) -> bool:
    """Exact refs, whole-bank refs, and explicit numeric ranges; never substrings."""
    if pattern == ref or pattern == ref.split("#")[0]:
        return True
    match = re.fullmatch(r"([^#]+)#(\d+)[–-](\d+)", pattern)
    if not match or "#" not in ref:
        return False
    bank, number = ref.split("#", 1)
    return bank == match[1] and number.isdecimal() and int(match[2]) <= int(number) <= int(match[3])


def in_scope(scope: object, ref: str) -> bool:
    if scope == "global":
        return True
    values = [scope] if isinstance(scope, str) else scope
    return isinstance(values, list) and any(
        isinstance(s, str) and ref_matches(s, ref) for s in values
    )


def live_entry(db: sqlite3.Connection, root: Path, ref: str) -> dict[str, Any]:
    row = db.execute(
        "SELECT e.payload,e.file_path,f.sha256 FROM entries e JOIN files f ON f.path=e.file_path WHERE ref=?",
        (ref,),
    ).fetchone()
    if row is None:
        raise ValueError("unknown text reference: " + ref)
    path = root / row["file_path"]
    if not path.exists() or file_hash(path) != row["sha256"]:
        raise ValueError("catalogue is stale; rebuild before packaging: " + row["file_path"])
    payload: object = json.loads(row["payload"])
    if not isinstance(payload, dict) or not isinstance(payload.get("zh"), str):
        raise ValueError("invalid catalogue entry payload: " + ref)
    return payload


def decisions_for(root: Path, ref: str, zh: str, mode: Mode) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"accepted": [], "unresolved": []}
    path = root / "work/translate/decisions/decisions.jsonl"
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        refs = row.get("refs", [])
        direct = any(ref_matches(r, ref) for r in refs)
        term_match = row.get("type") == "term" and any(
            t and t in zh for t in [row.get("zh")] + row.get("aliases", [])
        )
        general_rule = row.get("scope", "global") == "global" and row.get("type") in (
            "style",
            "content",
        )
        if row.get("status") == "superseded" or not in_scope(row.get("scope", "global"), ref):
            continue
        if not (direct or term_match or general_rule):
            continue
        # Target-specific decisions, old answers and proposals would reveal an existing translation.
        if mode == "independent" and (direct or row.get("status") != "accepted"):
            continue
        fields = (
            "id",
            "type",
            "subtype",
            "zh",
            "en",
            "status",
            "scope",
            "refs",
            "rationale",
            "answer",
            "decision_id",
        )
        compact = {key: row[key] for key in fields if key in row}
        destination = (
            "accepted"
            if row.get("status") == "accepted"
            or (row.get("status") == "resolved" and row.get("type") == "question")
            else "unresolved"
        )
        result[destination].append(compact)
    return result


def load_context(path: Path | None, root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if path is None or not path.exists():
        return None, [
            "No script index supplied; no dialogue sequence or speaker is inferred from storage order."
        ]
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or not isinstance(data.get("refs"), dict)
    ):
        raise ValueError("unsupported context index schema")
    # Index producer owns this manifest. Only relative workspace paths are accepted.
    source = data.get("source", {})
    if "rom" in source:
        from translation_context import load_index

        return dict(load_index(path, verify_sources=True)), []
    for relative, expected in source.get("input_hashes", {}).items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("unsafe context source path")
        current = root / rel
        if not current.exists() or file_hash(current) != expected:
            raise ValueError("script context is stale: " + relative)
    if not source.get("input_hashes"):
        raise ValueError("context index lacks input fingerprints")
    return data, []


def layout_for(
    db: sqlite3.Connection, root: Path, ref: str, entry: dict[str, Any]
) -> dict[str, Any]:
    config = root / "work/tools/qa_config.json"
    if not config.exists():
        return {"state": "unknown"}
    cfg = json.loads(config.read_text())
    row = db.execute(
        "SELECT f.content FROM files f JOIN entries e ON e.file_path=f.path WHERE e.ref=?", (ref,)
    ).fetchone()
    bank = json.loads(row[0])
    if "bank" not in bank or "narc" not in bank:
        return {"state": "unknown", "reason": "hardcoded label; consult its registered constraints"}
    category = (
        entry.get("category")
        or qa.string_categories(bank, cfg).get(entry["id"])
        or qa.bank_category(bank, cfg)
    )
    return {
        "category": category,
        "constraints": cfg["categories"][category],
        "evidence": "work/tools/qa_config.json",
        "state": "configured",
        "qa_ignore": entry.get("qa_ignore", []),
    }


def contextual_text(db: sqlite3.Connection, root: Path, ref: str, mode: Mode) -> dict[str, Any]:
    if db.execute("SELECT 1 FROM entries WHERE ref=?", (ref,)).fetchone() is None:
        return {"ref": ref, "state": "missing-from-catalogue"}
    source = live_entry(db, root, ref)
    if catalog.REDACTED.fullmatch(source["zh"]):
        return {"ref": ref, "state": "redacted"}
    text = {"ref": ref, "zh": source["zh"], "source_sha256": catalog.digest(source["zh"])}
    if mode == "review":
        text["en"] = source.get("en")
    return text


def following_occurrences(index: dict[str, Any], target_ref: str) -> Successors:
    return build_successor_index(index, {target_ref}).get(target_ref, {})


def build_successor_index(
    index: dict[str, Any], target_refs: set[str] | None = None
) -> dict[str, Successors]:
    """Reverse explicit predecessor evidence; retain alternatives, not a fabricated linear scene."""
    result: dict[str, Successors] = {}
    for ref, context in index.get("refs", {}).items():
        for occurrence in context.get("occurrences", []):
            for previous in occurrence.get("previous_messages", []):
                if not isinstance(previous, dict) or not isinstance(previous.get("ref"), str):
                    continue
                target_ref = previous["ref"]
                if target_refs is not None and target_ref not in target_refs:
                    continue
                key = catalog.packed(
                    [occurrence.get("root"), previous.get("script_file"), previous.get("pc")]
                )
                item = {
                    "ref": ref,
                    "script_file": occurrence.get("script_file"),
                    "pc": occurrence.get("pc"),
                    "branches": occurrence.get("branches", []),
                    "relation": "possible static successor; world-state feasibility unproven",
                }
                bucket = result.setdefault(target_ref, {}).setdefault(key, [])
                if item not in bucket:
                    bucket.append(item)
    return result


def diverse_occurrences(occurrences: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Show distinct entry roots and message sites before repeating branch variants."""
    grouped: dict[str, deque[dict[str, Any]]] = {}
    for occurrence in occurrences:
        key = catalog.packed(
            [occurrence.get("root"), occurrence.get("script_file"), occurrence.get("pc")]
        )
        grouped.setdefault(key, deque()).append(occurrence)
    queues = deque(grouped.values())
    result: list[dict[str, Any]] = []
    while queues and len(result) < limit:
        group = queues.popleft()
        result.append(group.popleft())
        if group:
            queues.append(group)
    return result


def make_package(
    db: sqlite3.Connection,
    root: Path,
    ref: str,
    options: PackageOptions,
    context_index: dict[str, Any] | None = None,
    *,
    successors: Successors | None = None,
) -> ReviewPackage:
    entry = live_entry(db, root, ref)
    detail = catalog.inspect(db, ref)
    if options.mode == "review":
        fresh = next(
            (
                annotation
                for annotation in catalog.load_annotations(
                    root / "work/translate/text_catalog/annotations.jsonl"
                )
                if annotation["ref"] == ref
            ),
            None,
        )
        cached = detail["annotation"]
        if cached is not None:
            cached = {key: value for key, value in cached.items() if key != "state"}
        if fresh != cached:
            raise ValueError("annotation changed since catalogue build; rebuild the catalogue")
    if detail["analysis_state"] == "redacted":
        raise ValueError("redacted lyrics cannot enter a translation package")
    zh = entry["zh"]
    warnings = [
        "Automatic pronunciation and dictionary segmentation do not establish the intended meaning."
    ]
    occurrences = (context_index or {}).get("refs", {}).get(ref, {}).get("occurrences", [])
    if not isinstance(occurrences, list) or any(not isinstance(o, dict) for o in occurrences):
        raise ValueError("invalid script occurrences")
    if not occurrences:
        warnings.append(
            "No resolved script occurrence: this does not establish that the line is unused."
        )
    if len(occurrences) > options.occurrence_limit:
        warnings.append(
            "Script alternatives are truncated in this package; inspect the complete index before deciding meaning."
        )
    warnings.append(
        "Script paths are bounded static evidence; runtime reachability and speaker identity require confirmation."
    )
    # Enrich only explicit previous-message references from the extractor, preserving each alternative.
    script_context = []
    if successors is None:
        successors = following_occurrences(context_index or {}, ref)
    for occurrence in diverse_occurrences(occurrences, options.occurrence_limit):
        item = dict(occurrence)
        previous = []
        for message in occurrence.get("previous_messages", []):
            previous_ref = message if isinstance(message, str) else message.get("ref")
            if not previous_ref:
                continue
            previous.append(contextual_text(db, root, previous_ref, options.mode))
        item["previous_text"] = previous
        key = catalog.packed(
            [occurrence.get("root"), occurrence.get("script_file"), occurrence.get("pc")]
        )
        following = successors.get(key, [])
        item["following_total"] = len(following)
        item["following_text"] = [
            {**next_message, **contextual_text(db, root, next_message["ref"], options.mode)}
            for next_message in following[: options.occurrence_limit]
        ]
        if len(following) > options.occurrence_limit:
            warnings.append(
                "Following-message alternatives are truncated; inspect the complete index."
            )
        script_context.append(item)
    related_rows = db.execute(
        "SELECT ref FROM entries WHERE source_id=(SELECT source_id FROM entries WHERE ref=?) AND ref!=? ORDER BY ref",
        (ref, ref),
    ).fetchall()
    related = []
    for row in related_rows[: options.related_limit]:
        other = live_entry(db, root, row["ref"])
        match: dict[str, Any] = {
            "ref": row["ref"],
            "relationship": "exact source equality; context may differ",
        }
        if options.mode == "review":
            match["en"] = other.get("en")
        related.append(match)
    words = []
    # Load project terms fresh, not from a possibly older glossary snapshot in SQLite.
    lexicon = catalog.Lexicon()
    catalog.load_terms(root, lexicon)
    for word in detail["words"]:
        copy = {key: value for key, value in word.items() if key != "project_terms"}
        terms = []
        for term in lexicon.terms.get(word["text"], []):
            payload = term["payload"]
            if not in_scope(term["scope"], ref):
                continue
            direct = any(ref_matches(r, ref) for r in payload.get("refs", []))
            if options.mode == "independent" and (
                direct or payload.get("status", "accepted") != "accepted"
            ):
                continue
            terms.append(
                {
                    "zh": term["zh"],
                    "en": term["en"],
                    "provenance": term["provenance"],
                    "status": payload.get("status", "project-glossary"),
                }
            )
        copy["project_terms"] = terms
        words.append(copy)
    paths = [
        root / "work/translate/decisions/decisions.jsonl",
        root / "work/tools/qa_config.json",
        root / "work/translate/STYLE.md",
        root / "work/translate/text_catalog/annotations.jsonl",
        root / "work/translate/bank_maps.json",
        root / "work/translate/manifest_playorder.json",
        root / "work/tools/text_catalog.py",
        root / "work/tools/qa.py",
    ]
    paths.extend(sorted((root / "work/glossary").glob("*.json")))
    fingerprints = {str(p.relative_to(root)): file_hash(p) for p in paths if p.exists()}
    bank_ref, entry_id = ref.split("#", 1)
    maps = catalog.read_json(root / "work/translate/bank_maps.json", {})
    manifest = catalog.read_json(root / "work/translate/manifest_playorder.json", {})
    batches = []
    for batch in manifest.get("batches", []):
        for part in batch.get("parts", []):
            if (
                part["bank"] == bank_ref
                and entry_id.isdecimal()
                and part["ids"][0] <= int(entry_id) <= part["ids"][1]
            ):
                batches.append(
                    {"batch": batch["batch"], "label": batch["label"], "ids": part["ids"]}
                )
    catalogue_context = {
        "maps": maps.get(bank_ref.removeprefix("a027/"), [])
        if bank_ref.startswith("a027/")
        else [],
        "batches": batches,
    }
    script_roots = {}
    for occurrence in script_context:
        root_id = occurrence.get("root", {}).get("id")
        if root_id is None or root_id in script_roots:
            continue
        full_root = (context_index or {}).get("roots", {}).get(root_id)
        if not isinstance(full_root, dict):
            continue
        bindings = full_root.get("event_bindings", [])
        script_roots[root_id] = {
            **full_root,
            "event_bindings": bindings[: options.occurrence_limit],
            "event_bindings_total": len(bindings),
            "event_bindings_shown": min(len(bindings), options.occurrence_limit),
        }
        if len(bindings) > options.occurrence_limit:
            warnings.append(
                "Event bindings are truncated in this package; inspect the complete script root in the index."
            )
    output: ReviewPackage = {
        "schema_version": 1,
        "mode": options.mode,
        "ref": ref,
        "source": {"zh": zh, "sha256": catalog.digest(zh), "language": detail["language"]},
        "linguistics": {
            "pinyin": detail["pinyin"],
            "pinyin_method": detail["pinyin_method"],
            "words": words,
            "characters": detail["characters"],
            "dictionary_sources": {
                row["id"]: json.loads(row["metadata"])
                for row in db.execute("SELECT id,metadata FROM dictionary_sources ORDER BY id")
            },
        },
        "context": {
            "catalogue": catalogue_context,
            "script_occurrences": script_context,
            "script_roots": script_roots,
            "analysis_stats": (context_index or {}).get("stats", {}),
            "occurrences_total": len(occurrences),
            "occurrences_shown": len(script_context),
            "speaker": {
                "state": "unknown",
                "note": "NPC identity or a trainer battle does not by itself prove the speaker.",
            },
        },
        "related_occurrences": {"total": len(related_rows), "shown": related},
        "decisions": decisions_for(root, ref, zh, options.mode),
        "layout": layout_for(db, root, ref, entry),
        "provenance": {
            "input_hashes": fingerprints,
            "script_source": (context_index or {}).get("source"),
            "package_tool_sha256": file_hash(Path(__file__)),
        },
        "warnings": warnings,
    }
    if options.mode == "review":
        output["translation"] = {
            "en": entry.get("en"),
            "sha256": catalog.digest(catalog.packed(entry.get("en"))),
            "status": entry.get("status"),
            "origin": entry.get("origin"),
            "notes": entry.get("notes"),
        }
        output["annotation"] = detail["annotation"]
    else:
        output["warnings"].append(
            "Independent mode excludes existing English, translation notes, annotations and target-specific decisions."
        )
    # The fingerprint covers the complete payload rather than only the Chinese line.
    output["package_sha256"] = catalog.digest(catalog.packed(output))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref")
    parser.add_argument("--db", type=Path, default=catalog.DEFAULT_DB)
    parser.add_argument("--context-index", type=Path, default=DEFAULT_INDEX)
    parser.add_argument("--mode", choices=["review", "independent"], default="review")
    parser.add_argument("--related-limit", type=int, default=20)
    parser.add_argument("--occurrence-limit", type=int, default=12)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    check_output(args.out, ROOT)
    context, warnings = load_context(args.context_index, ROOT)
    with catalog.connect(args.db) as db:
        output = make_package(
            db,
            ROOT,
            args.ref,
            PackageOptions(args.mode, args.related_limit, args.occurrence_limit),
            context,
        )
    output["warnings"].extend(warnings)
    output.pop("package_sha256")
    output["package_sha256"] = catalog.digest(catalog.packed(output))
    atomic_json(args.out, output)
    print(
        json.dumps(
            {
                "ref": args.ref,
                "mode": args.mode,
                "out": str(args.out),
                "script_occurrences": len(output["context"]["script_occurrences"]),
                "package_sha256": output["package_sha256"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        raise SystemExit(str(error)) from None
