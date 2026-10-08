#!/usr/bin/env python3
"""Prepare a development-only, source-isolated dialogue trial. No bank writes.

Artifacts contain game text and must remain under ignored work/build. Only
explicit source labels and recorded static paths establish facts; physical bank
adjacency and inferred flag semantics never establish scene order.
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import translation_eval as E

REFS = [
    "0585#123",
    "0542#14",
    "0529#93",
    "0326#1",
    "0593#4",
    "0529#90",
    "0446#57",
    "0066#87",
    "0462#76",
    "0535#70",
    "0616#9",
    "0529#70",
    "0118#4",
    "0535#61",
    "0379#39",
    "0511#48",
    "0587#94",
    "0462#142",
    "0457#124",
    "0587#22",
    "0123#31",
    "0735#88",
    "0690#11",
    "0406#25",
]


def prepare(dataset_dir: Path, out: Path, notes_path: Path, packages: Path) -> dict[str, Any]:
    dataset = E.read(dataset_dir / "dataset.json")
    E.fresh(E.ROOT, dataset)
    rows = {r["ref"]: r for r in E.lines(dataset_dir / "development-inputs.jsonl")}
    verified = E.independent_context(E.ROOT, packages, dataset["entries"])
    entries = {r["ref"]: r for r in dataset["entries"]}
    notes = E.read(notes_path)
    source, enriched = [], []
    for suffix in REFS:
        ref = "a027/" + suffix
        if entries[ref]["split"] != "development":
            raise ValueError("Trial must never consume regression/heldout refs: " + ref)
        row = rows[ref]
        if (
            row["dataset_id"] != dataset["dataset_id"]
            or E.digest(row["zh"]) != entries[ref]["source_sha256"]
        ):
            raise ValueError("Stale independent input: " + ref)
        p = row["context_package"]
        if (
            verified.get(ref) != p
            or dataset["context_fingerprints"].get(ref) != p["package_sha256"]
        ):
            raise ValueError("Context fingerprint mismatch: " + ref)
        base = {k: row[k] for k in ("ref", "zh", "source_sha256", "dataset_id")}
        source.append(base)
        ctx = p["context"]
        paths = [
            {
                k: o.get(k)
                for k in (
                    "script_file",
                    "pc",
                    "entry",
                    "branches",
                    "buffers",
                    "variables",
                    "previous_text",
                    "following_text",
                    "unknowns",
                )
            }
            for o in ctx.get("script_occurrences", [])
        ]
        # Labels are syntactic evidence only, not an inferred actor identity.
        labels = re.findall(
            r"(?:^|[。！？！…]|\{(?:NEWLINE|SCROLL|CLEAR)\})([^『{}。！？…]{1,12})『", row["zh"]
        )
        labels = list(dict.fromkeys(labels))
        context = {
            "kind": "dialogue",
            "speaker": {
                "explicit_chinese_labels": labels,
                "evidence_ref": ref,
                "unlabeled_identity": "unknown; do not infer from nearby bank rows",
            },
            "maps": ctx.get("catalogue", {}).get("maps", []),
            "paths": paths,
            "path_scope": "bounded static alternatives, not runtime reachability; empty buffers are unknown, not absent",
            "path_count_total": ctx.get("occurrences_total", 0),
            "case_notes": notes["cases"].get(ref, []),
            "phrase_notes": [n for n in notes["phrases"] if n["phrase"] in row["zh"]],
            "linguistics": p["linguistics"],
            "accepted_decisions": p["decisions"]["accepted"],
            "layout": p["layout"],
            "canon": "No external canon quotation verified by this trial. Do not invent a canonical quote.",
            "package_sha256": p["package_sha256"],
        }
        enriched.append(dict(base, context=context))
    out = E.output_path(out)
    if out.exists():
        raise ValueError("Refuse to overwrite trial directory")
    out.mkdir(parents=True)
    E.write(out / "source-only.jsonl", source, jsonl=True)
    E.write(out / "context-enriched.jsonl", enriched, jsonl=True)
    manifest = {
        "schema_version": 1,
        "dataset": str(dataset_dir.relative_to(E.ROOT)),
        "dataset_id": dataset["dataset_id"],
        "split": "development",
        "refs": [r["ref"] for r in source],
        "selection": "Purposive difficult dialogue sample; not a representative quality estimate.",
        "notes_sha256": E.file_digest(notes_path),
        "inputs": {
            name: E.file_digest(out / name)
            for name in ("source-only.jsonl", "context-enriched.jsonl")
        },
        "external_arms": {
            "deepl_source_only": "pending provider access",
            "deepl_context": "pending provider access",
        },
        "approval": "Candidate generation and model review do not constitute human approval.",
    }
    E.write(out / "manifest.json", manifest)
    return manifest


def summarize_model_review(dataset: Path, review: Path, scores: Path, out: Path) -> dict[str, Any]:
    """Lock complete LLM scores separately from the human-only evaluation report."""
    manifest, reviews, keys = E.validate_review(E.ROOT, dataset, review)
    rows = E.lines(scores)
    E.validate_scores(rows, reviews)
    if len(rows) != len(reviews):
        raise ValueError("Complete trial review required; missing scores must not disappear")
    if any(r.get("reviewer_kind") != "llm" for r in rows):
        raise ValueError(
            "Explicit reviewer_kind=llm required; use translation_eval for human scores"
        )
    wins: Counter[str] = Counter()
    values: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        key = keys[row["review_id"]]
        winner = row["winner"]
        wins[key[winner] if winner in ("A", "B") else winner] += 1
        for label in ("A", "B"):
            for dimension, value in row["scores"][label].items():
                if value is not None:
                    values[key[label]][dimension].append(value)
    report = {
        "schema_version": 1,
        "dataset_id": manifest["dataset_id"],
        "review_sha256": manifest["review_sha256"],
        "scores_file_sha256": E.file_digest(scores),
        "status": "provisional_blind_llm_review",
        "human_reviewed": 0,
        "llm_reviewed": len(rows),
        "preferences": dict(wins),
        "scores": {
            name: {dim: {"n": len(v), "mean": sum(v) / len(v)} for dim, v in dims.items()}
            for name, dims in values.items()
        },
        "entries": rows,
        "warning": "Model judgments are provisional, not approved corrections or ground truth. "
        "Purposive development cases cannot estimate whole-game quality or causal context gains.",
    }
    report["artifact_sha256"] = E.digest(report)
    E.write(E.output_path(out), report)
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument(
        "--notes", type=Path, default=E.ROOT / "work/translate/evaluation/dialogue-trial-notes.json"
    )
    p.add_argument(
        "--packages", type=Path, default=E.ROOT / "work/build/translation_eval/packages-v2"
    )
    p.add_argument("--review", type=Path, help="Blind review directory for provisional LLM scores")
    p.add_argument("--scores", type=Path, help="Complete JSONL scores, each reviewer_kind=llm")
    args = p.parse_args()
    if args.review or args.scores:
        if not (args.review and args.scores):
            p.error("--review and --scores are required together")
        result = summarize_model_review(args.dataset, args.review, args.scores, args.out)
        print(json.dumps({"llm_reviewed": result["llm_reviewed"], "out": str(args.out)}))
        return
    result = prepare(args.dataset.resolve(), args.out, args.notes, args.packages)
    print(json.dumps({"cases": len(result["refs"]), "out": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
