#!/usr/bin/env python3
"""Offline, human-scored translation comparisons. No model calls or bank writes.

All CLI artifacts must live under work/build. Independent inputs contain only
source text and identifiers; dataset.json, baseline.jsonl and answer keys are
coordinator-only. Scores measure reviewed samples, never unreviewed quality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

JsonObject = dict[str, Any]


class IndependentInput(TypedDict):
    ref: str
    zh: str
    source_sha256: str
    dataset_id: str
    context_state: str
    context_package: JsonObject | None


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 1
TAG = re.compile(r"\{[^{}]*\}")
LAYOUT = {"{NEWLINE}", "{SCROLL}", "{CLEAR}"}
SPLITS = ("development", "regression", "heldout")
DIMENSIONS = ("meaning", "omission", "addition", "tone", "terms", "fluency")
RUBRIC = {
    "scale": {
        "0": "Critical failure",
        "1": "Major problems",
        "2": "Mixed; material issues",
        "3": "Minor issues only",
        "4": "No issue found",
        "null": "Not assessed",
    },
    "meaning": "Preserves referents, polarity, conditions, quantities and author intent.",
    "omission": "Retains meaningful source details; approved exceptions need citations.",
    "addition": "Does not invent facts, certainty, motives or stronger content.",
    "tone": "Preserves register and strength, including threats, insults and adult content.",
    "terms": "Uses context-appropriate senses and approved names; verified canon only.",
    "fluency": "Natural, clear English in the actual scene and UI constraints.",
    "instruction": "Human assessment required. Higher is better for every dimension. "
    "Use null when not assessed; cite evidence and decisions in notes.",
}


def digest(value: Any) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read(path: str | Path) -> JsonObject:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object: " + str(path))
    return value


def lines(path: str | Path) -> list[JsonObject]:
    values = [
        json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    if any(not isinstance(v, dict) for v in values):
        raise ValueError("Expected JSON objects in JSONL: " + str(path))
    return values


def write(path: str | Path, data: Any, jsonl: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Never silently replace an existing experimental artifact.
    with path.open("x", encoding="utf-8") as f:
        if jsonl:
            for row in data:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        else:
            f.write(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def output_path(value: str | Path) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to((ROOT / "work/build").resolve()):
        raise ValueError("Evaluation artifacts must be inside ignored work/build/")
    return path


def plain(text: str) -> str:
    return unicodedata.normalize("NFKC", TAG.sub("", text))


def source_group(text: str) -> str:
    # Layout changes must not move duplicate source content between splits.
    return digest(re.sub(r"\s+", "", plain(text)))


def verify_artifact(data: JsonObject, field: str) -> None:
    if not isinstance(data, dict):
        raise ValueError("Expected artifact object")
    payload = {k: v for k, v in data.items() if k != field}
    if data.get(field) != digest(payload):
        raise ValueError("Artifact fingerprint mismatch: " + field)


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def independent_context(
    root: Path, context_dir: Path | None, entries: list[JsonObject]
) -> dict[str, JsonObject]:
    """Accept only independently prepared packages; hashes detect accidental edits.

    This is an integrity check, not an authenticity/signature guarantee. Glossary
    English is intentional; current-line English and review annotations are not.
    """
    if context_dir is None:
        return {}
    if not context_dir.is_dir():
        raise ValueError("Context directory does not exist")
    expected = {e["ref"]: e for e in entries}
    heldout = {e["source_group"] for e in entries if e["split"] == "heldout"}
    allowed = {
        "schema_version",
        "mode",
        "ref",
        "source",
        "linguistics",
        "context",
        "related_occurrences",
        "decisions",
        "layout",
        "provenance",
        "warnings",
        "package_sha256",
    }
    result: dict[str, JsonObject] = {}
    checked_files: dict[Path, str] = {}

    def check_dependency(path: Path, fingerprint: object) -> None:
        path = path.resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError("Missing or external context dependency: " + str(path))
        if path not in checked_files:
            checked_files[path] = file_digest(path)
        if checked_files[path] != fingerprint:
            raise ValueError("Stale context dependency: " + str(path))

    for path in sorted(context_dir.glob("*.json")):
        package = read(path)
        ref = package.get("ref")
        if not isinstance(ref, str) or ref not in expected:
            continue
        if ref in result:
            raise ValueError("Duplicate context package: " + ref)
        if (
            package.get("mode") != "independent"
            or package.get("schema_version") != 1
            or set(package) != allowed
        ):
            raise ValueError("Only allowlisted independent context packages accepted: " + ref)
        payload = {k: v for k, v in package.items() if k != "package_sha256"}
        # translation_package uses insertion-order compact JSON for its hash.
        actual = digest(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        if package.get("package_sha256") != actual:
            raise ValueError("Context package fingerprint mismatch: " + ref)
        source = package.get("source")
        if (
            not isinstance(source, dict)
            or source.get("zh") != expected[ref]["zh"]
            or source.get("sha256") != expected[ref]["source_sha256"]
        ):
            raise ValueError("Stale context source: " + ref)
        provenance = package.get("provenance")
        if not isinstance(provenance, dict) or not isinstance(provenance.get("input_hashes"), dict):
            raise ValueError("Context input fingerprints required: " + ref)
        for relative, fingerprint in provenance["input_hashes"].items():
            check_dependency(root / relative, fingerprint)
        check_dependency(
            root / "work/tools/translation_package.py", provenance.get("package_tool_sha256")
        )
        script_source = provenance.get("script_source")
        if script_source is not None:
            if not isinstance(script_source, dict) or set(script_source) != {
                "rom",
                "bank_maps",
                "script_cmds",
                "romdata",
                "extractor",
            }:
                raise ValueError("Incomplete script context dependencies: " + ref)
            for record in script_source.values():
                if not isinstance(record, dict) or not isinstance(record.get("path"), str):
                    raise ValueError("Malformed script context dependency: " + ref)
                check_dependency(Path(record["path"]), record.get("sha256"))

        # Inspect nested envelopes, including previous-text windows, for leakage.
        def inspect(value: Any, ref: str = ref) -> None:
            if isinstance(value, dict):
                if any(
                    k in value
                    for k in ("translation", "annotation", "english_sha256", "current_en")
                ):
                    raise ValueError("Review-only content in independent context: " + ref)
                if "zh" in value and "en" in value and "ref" in value:
                    raise ValueError("Existing occurrence English in independent context: " + ref)
                zh = value.get("zh")
                if (
                    isinstance(zh, str)
                    and expected[ref]["split"] != "heldout"
                    and source_group(zh) in heldout
                ):
                    raise ValueError("Held-out source leaked through tuning context: " + ref)
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        inspect(package)
        result[ref] = package
    return result


def inventory(root: Path) -> dict[str, JsonObject]:
    result = {}
    base = Path(root) / "work/translate/banks"
    for path in sorted(base.glob("*/*.json")):
        for row in read(path).get("strings", []):
            zh, en = row.get("zh"), row.get("en")
            if not isinstance(zh, str) or not isinstance(en, str):
                continue
            ref = path.relative_to(base).with_suffix("").as_posix() + "#" + str(row["id"])
            if ref in result:
                raise ValueError("Duplicate bank ID: " + ref)
            result[ref] = dict(
                ref=ref,
                zh=zh,
                en=en,
                source_sha256=digest(zh),
                english_sha256=digest(en),
                origin=row.get("origin", "unknown"),
            )
    return result


def stratum(row: JsonObject) -> str:
    text = plain(row["zh"])
    kind = "dialogue" if len(text) > 40 else "short"
    if re.search(r"杀|死|血|操|妈的|混蛋|裸|强奸|恐怖", text):
        kind = "sensitive"
    elif re.search(r"\d|[０-９]|{VAR:", row["zh"]):
        kind = "numbers-or-variables"
    return kind + "/" + str(row["origin"])


def sample(
    root: Path,
    out: Path,
    size: int = 120,
    seed: str = "origin-eval-v1",
    regression_refs: list[str] | None = None,
    context_dir: Path | None = None,
) -> JsonObject:
    if size < 3:
        raise ValueError("Sample size must be at least 3 (one per split).")
    records = inventory(root)
    regression_refs = regression_refs or []
    if len(regression_refs) != len(set(regression_refs)) or any(
        r not in records for r in regression_refs
    ):
        raise ValueError("Regression refs must be unique existing bank refs")
    regression_groups = {source_group(records[r]["zh"]) for r in regression_refs}
    if len(regression_groups) != len(regression_refs):
        raise ValueError("Regression refs must have distinct source content")
    # Whole banks stay together. Cross-bank repeated source is excluded rather
    # than connecting most story banks through ubiquitous greetings and prompts.
    group_banks: dict[str, set[str]] = defaultdict(set)
    for record in records.values():
        group_banks[source_group(record["zh"])].add(record["ref"].split("#")[0])
    regression_banks = {ref.split("#")[0] for ref in regression_refs}
    for group in regression_groups:
        regression_banks.update(group_banks[group])
    buckets: dict[str, dict[str, list[JsonObject]]] = defaultdict(lambda: defaultdict(list))
    excluded: Counter[str] = Counter()
    for row in records.values():
        zh = row["zh"]
        if "[zh redacted: song lyrics;" in zh:
            excluded["redacted_lyrics"] += 1
            continue
        if not re.search(r"[\u3400-\u9fff]", plain(zh)):
            excluded["no_han_source"] += 1
            continue
        group = source_group(zh)
        bank = row["ref"].split("#")[0]
        if len(group_banks[group]) > 1 and group not in regression_groups:
            excluded["cross_bank_duplicate_source"] += 1
            continue
        roll = int(digest(seed + "/split/" + bank)[:8], 16) % 10
        split = "development" if roll < 6 else "regression" if roll < 8 else "heldout"
        if bank in regression_banks:
            split = "regression"
        row = dict(row, source_group=group, split=split, stratum=stratum(row))
        buckets[split][row["stratum"]].append(row)
    # Within each split, round-robin strata intentionally over-samples rare risks.
    # This is a diagnostic sample, not an unbiased population estimate.
    quotas = {
        "development": size - 2 * max(1, size // 5),
        "regression": max(1, size // 5),
        "heldout": max(1, size // 5),
    }
    chosen = []
    for split in SPLITS:
        groups = buckets[split]
        for values in groups.values():
            values.sort(key=lambda r: digest(seed + "/pick/" + r["ref"]))
        used: set[str] = set()
        selected = (
            [
                dict(
                    records[ref],
                    source_group=source_group(records[ref]["zh"]),
                    split="regression",
                    stratum=stratum(records[ref]),
                )
                for ref in regression_refs
            ]
            if split == "regression"
            else []
        )
        used.update(r["source_group"] for r in selected)
        if len(selected) > quotas[split]:
            raise ValueError("Explicit regression refs exceed regression quota; increase --size")
        if any(
            "[zh redacted: song lyrics;" in r["zh"]
            or not re.search(r"[\u3400-\u9fff]", plain(r["zh"]))
            for r in selected
        ):
            raise ValueError("Regression refs must have eligible non-redacted Chinese sources")
        while len(selected) < quotas[split]:
            progress = False
            for key in sorted(groups):
                while groups[key] and groups[key][0]["source_group"] in used:
                    groups[key].pop(0)
                if groups[key] and len(selected) < quotas[split]:
                    row = groups[key].pop(0)
                    used.add(row["source_group"])
                    selected.append(row)
                    progress = True
            if not progress:
                break
        chosen.extend(selected)
    if any(not any(r["split"] == split for r in chosen) for split in SPLITS):
        raise ValueError("Not enough distinct eligible source groups to populate all splits.")
    entries = [{k: v for k, v in r.items() if k != "en"} for r in chosen]
    packages = independent_context(root, context_dir, entries)
    dependencies: dict[str, str] = {}
    for package in packages.values():
        provenance = package["provenance"]
        dependencies.update(provenance["input_hashes"])
        dependencies["work/tools/translation_package.py"] = provenance["package_tool_sha256"]
        for record in (provenance.get("script_source") or {}).values():
            dependencies[str(Path(record["path"]).resolve().relative_to(root.resolve()))] = record[
                "sha256"
            ]
    data: JsonObject = dict(
        schema_version=SCHEMA,
        status="prepared_not_evaluated",
        human_reviewed=0,
        seed=seed,
        requested_size=size,
        entries=entries,
        explicit_regression_refs=regression_refs,
        context_fingerprints={ref: p["package_sha256"] for ref, p in packages.items()},
        context_dependencies=dependencies,
        excluded=dict(excluded),
        split_counts=dict(Counter(r["split"] for r in entries)),
        sampling="Whole-bank split; cross-bank exact source duplicates excluded; deterministic round-robin strata; not population-weighted.",
        heldout_policy="Do not tune against heldout or expose its sources through development "
        "context packages. Bank and exact-source disjointness are enforced; scenes can "
        "span banks and near-paraphrases can recur, so contextual leakage still requires coordinator review.",
    )
    data["dataset_id"] = digest(data)
    out = Path(out)
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    write(out / "dataset.json", data)
    write(
        out / "baseline.jsonl",
        [
            dict(
                ref=r["ref"],
                en=r["en"],
                source_sha256=r["source_sha256"],
                english_sha256=r["english_sha256"],
            )
            for r in chosen
        ],
        True,
    )
    # Deliberate whitelist: no EN, notes, origins, bank metadata or previous decisions.
    for split in SPLITS:
        inputs: list[IndependentInput] = [
            IndependentInput(
                ref=r["ref"],
                zh=r["zh"],
                source_sha256=r["source_sha256"],
                dataset_id=data["dataset_id"],
                context_state="provided" if r["ref"] in packages else "not_provided_source_only",
                context_package=packages.get(r["ref"]),
            )
            for r in chosen
            if r["split"] == split
        ]
        write(out / (split + "-inputs.jsonl"), inputs, True)
    write(out / "rubric.json", RUBRIC)
    return data


def fresh(root: Path, dataset: JsonObject) -> None:
    verify_artifact(dataset, "dataset_id")
    entries = dataset.get("entries")
    if dataset.get("schema_version") != SCHEMA or not isinstance(entries, list) or not entries:
        raise ValueError("Invalid evaluation dataset schema")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(k), str)
            for k in ("ref", "zh", "source_sha256", "english_sha256", "source_group")
        ):
            raise ValueError("Invalid dataset entry")
        if (
            entry["ref"] in seen
            or entry.get("split") not in SPLITS
            or digest(entry["zh"]) != entry["source_sha256"]
            or source_group(entry["zh"]) != entry["source_group"]
        ):
            raise ValueError("Invalid dataset identity, split or source fingerprint")
        seen.add(entry["ref"])
    for relative, fingerprint in dataset.get("context_dependencies", {}).items():
        path = (root / relative).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or not path.is_file()
            or file_digest(path) != fingerprint
        ):
            raise ValueError("Stale dataset context: " + relative)
    current = inventory(root)
    errors = []
    for entry in dataset["entries"]:
        row = current.get(entry["ref"])
        if row is None:
            errors.append(entry["ref"] + ": missing")
        elif any(row[k] != entry[k] for k in ("source_sha256", "english_sha256")):
            errors.append(entry["ref"] + ": source or baseline changed; resample")
    if errors:
        raise ValueError("Stale dataset: " + "; ".join(errors))


def protected_tags(text: str) -> Counter[str]:
    if re.search(r"[{}]", TAG.sub("", text)):
        raise ValueError("Malformed brace/control tag")
    return Counter(t for t in TAG.findall(text) if t not in LAYOUT)


def risk_flags(zh: str, candidate: str, baseline: str) -> list[str]:
    flags = []
    if plain(candidate).strip() != plain(baseline).strip():
        flags.append("candidate_disagrees_with_baseline")
    if re.search(r"[\u3400-\u9fff]", plain(candidate)):
        flags.append("han_characters_in_english")
    if Counter(re.findall(r"\d+", plain(zh))) != Counter(re.findall(r"\d+", plain(candidate))):
        flags.append("digit_difference_check_spelled_numbers_and_units")
    if re.search(r"杀|死|血|操|妈的|混蛋|裸|强奸|恐怖", zh):
        flags.append("source_sensitive_content_check_tone_and_meaning")
    if re.search(r"不|没|无|别|禁止", zh):
        flags.append("source_negation_check_scope")
    if re.search(r"\b(?:always|never|only|all|must|kill|fuck)\b", candidate, re.I):
        flags.append("candidate_absolute_or_strong_word_check_source")
    if len(plain(candidate)) > max(80, 8 * len(plain(zh))):
        flags.append("long_candidate_check_additions")
    return flags


def import_candidates(
    root: Path, directory: Path, input_path: Path, name: str, provenance_path: Path
) -> JsonObject:
    if name == "baseline" or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Candidate name must be a safe label other than baseline.")
    directory = Path(directory)
    dataset = read(directory / "dataset.json")
    fresh(root, dataset)
    expected = {e["ref"]: e for e in dataset["entries"]}
    baseline = candidate_set(directory, dataset, "baseline")
    provenance = read(provenance_path)
    for field in ("provider", "model", "prompt_sha256", "generated_at", "input_sha256"):
        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
            raise ValueError("Missing provenance field: " + field)
    for field in ("prompt_sha256", "input_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", provenance[field]):
            raise ValueError(field + " must be a SHA-256 hex digest")
    try:
        generated_at = datetime.fromisoformat(provenance["generated_at"].replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("generated_at must be an ISO-8601 timestamp") from error
    if generated_at.tzinfo is None:
        raise ValueError("generated_at must include its timezone")
    seen = set()
    imported = []
    for row in lines(input_path):
        ref = row.get("ref")
        if not isinstance(ref, str) or ref not in expected or ref in seen:
            raise ValueError("Unknown or duplicate candidate ref: " + str(ref))
        seen.add(ref)
        if row.get("dataset_id") != dataset["dataset_id"]:
            raise ValueError(ref + ": dataset_id mismatch")
        if row.get("source_sha256") != expected[ref]["source_sha256"]:
            raise ValueError(ref + ": source fingerprint mismatch")
        en = row.get("en")
        if not isinstance(en, str) or not en.strip():
            raise ValueError(ref + ": nonempty en required")
        if protected_tags(en) != protected_tags(expected[ref]["zh"]):
            raise ValueError(ref + ": protected control tags differ (layout tags may change)")
        imported.append(
            dict(
                ref=ref,
                en=en,
                source_sha256=row["source_sha256"],
                candidate_sha256=digest(en),
                flags=risk_flags(expected[ref]["zh"], en, baseline[ref]),
            )
        )
    if not imported:
        raise ValueError("No candidates supplied")
    target = directory / "candidates" / (name + ".json")
    artifact = dict(
        schema_version=SCHEMA,
        dataset_id=dataset["dataset_id"],
        name=name,
        provenance=provenance,
        external_file_sha256=hashlib.sha256(Path(input_path).read_bytes()).hexdigest(),
        entries=imported,
        warning="Heuristics are review prompts, never semantic verdicts.",
        provenance_status="Externally declared; provider execution and supplied prompt/input hashes are not independently verified.",
    )
    artifact["artifact_sha256"] = digest(artifact)
    write(target, artifact)
    return artifact


def candidate_set(directory: Path, dataset: JsonObject, name: str) -> dict[str, str]:
    if name == "baseline":
        entries = lines(directory / "baseline.jsonl")
        expected = {e["ref"]: e for e in dataset["entries"]}
        if len(entries) != len(expected) or any(
            e["ref"] not in expected or digest(e["en"]) != expected[e["ref"]]["english_sha256"]
            for e in entries
        ):
            raise ValueError("Baseline snapshot does not match dataset")
    else:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ValueError("Invalid candidate name")
        data = read(directory / "candidates" / (name + ".json"))
        verify_artifact(data, "artifact_sha256")
        if data["dataset_id"] != dataset["dataset_id"]:
            raise ValueError("Candidate dataset mismatch")
        entries = data["entries"]
        if any(digest(e["en"]) != e["candidate_sha256"] for e in entries):
            raise ValueError("Candidate artifact fingerprint mismatch")
    result = {e["ref"]: e["en"] for e in entries}
    if len(result) != len(entries):
        raise ValueError("Duplicate candidate/baseline refs")
    return result


def blind(
    root: Path,
    directory: Path,
    out: Path,
    left: str,
    right: str,
    split: str = "heldout",
    seed: str = "blind-v1",
) -> JsonObject:
    if split not in SPLITS:
        raise ValueError("Unknown split")
    if left == right:
        raise ValueError("Choose two different candidate sets")
    directory, out = Path(directory), Path(out)
    dataset = read(directory / "dataset.json")
    fresh(root, dataset)
    candidates = {name: candidate_set(directory, dataset, name) for name in (left, right)}
    reviews, keys, omitted = [], [], []
    for row in dataset["entries"]:
        if row["split"] != split:
            continue
        ref = row["ref"]
        if any(ref not in c for c in candidates.values()):
            omitted.append(ref)
            continue
        order = [left, right]
        if int(digest(seed + ref)[:8], 16) % 2:
            order.reverse()
        item = dict(
            ref=ref,
            zh=row["zh"],
            source_sha256=row["source_sha256"],
            A=candidates[order[0]][ref],
            B=candidates[order[1]][ref],
        )
        item["pair_sha256"] = digest(item)
        item["review_id"] = digest(dataset["dataset_id"] + seed + item["pair_sha256"])[:24]
        reviews.append(item)
        keys.append(dict(review_id=item["review_id"], A=order[0], B=order[1]))
    if not reviews:
        raise ValueError("No paired candidates in requested split")
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    write(out / "review.jsonl", reviews, True)
    write(out / "answer-key.jsonl", keys, True)
    write(
        out / "score-template.jsonl",
        [
            dict(
                review_id=r["review_id"],
                ref=r["ref"],
                pair_sha256=r["pair_sha256"],
                reviewer="",
                winner="unsure",
                scores={label: dict.fromkeys(DIMENSIONS) for label in ("A", "B")},
                notes="",
            )
            for r in reviews
        ],
        True,
    )
    manifest = dict(
        schema_version=SCHEMA,
        dataset_id=dataset["dataset_id"],
        split=split,
        seed=seed,
        candidate_fingerprints={name: digest(values) for name, values in candidates.items()},
        count=len(reviews),
        omitted_unpaired_refs=omitted,
        review_sha256=digest(reviews),
        key_sha256=digest(keys),
        instruction="Give reviewers review.jsonl, rubric and approved source-only context. "
        "Keep answer-key.jsonl and candidate provenance private until scores are locked.",
    )
    manifest["artifact_sha256"] = digest(manifest)
    write(out / "manifest.json", manifest)
    write(out / "rubric.json", RUBRIC)
    return manifest


def validate_review(
    root: Path, directory: Path, review_dir: Path
) -> tuple[JsonObject, dict[str, JsonObject], dict[str, JsonObject]]:
    dataset = read(Path(directory) / "dataset.json")
    fresh(root, dataset)
    review_dir = Path(review_dir)
    manifest = read(review_dir / "manifest.json")
    verify_artifact(manifest, "artifact_sha256")
    for name, fingerprint in manifest["candidate_fingerprints"].items():
        if digest(candidate_set(Path(directory), dataset, name)) != fingerprint:
            raise ValueError("Candidate changed since blind review was prepared")
    reviews = lines(review_dir / "review.jsonl")
    keys = lines(review_dir / "answer-key.jsonl")
    if (
        manifest["dataset_id"] != dataset["dataset_id"]
        or digest(reviews) != manifest["review_sha256"]
        or digest(keys) != manifest["key_sha256"]
    ):
        raise ValueError("Review package changed or belongs to another dataset")
    return manifest, {r["review_id"]: r for r in reviews}, {r["review_id"]: r for r in keys}


def validate_scores(rows: list[JsonObject], reviews: dict[str, JsonObject]) -> None:
    seen: set[str] = set()
    if not rows:
        raise ValueError("No human assessments supplied")
    for row in rows:
        rid = row.get("review_id")
        if not isinstance(rid, str) or rid not in reviews or rid in seen:
            raise ValueError("Unknown or duplicate review_id: " + str(rid))
        seen.add(rid)
        if any(row.get(k) != reviews[rid][k] for k in ("ref", "pair_sha256")):
            raise ValueError("Score refers to changed pair: " + rid)
        if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
            raise ValueError("Named human reviewer required")
        if row.get("winner") not in ("A", "B", "tie", "unsure"):
            raise ValueError("winner must be A, B, tie or unsure")
        if not isinstance(row.get("notes"), str) or not row["notes"].strip():
            raise ValueError("Human evidence/notes required")
        if not isinstance(row.get("scores"), dict) or set(row["scores"]) != {"A", "B"}:
            raise ValueError("Both A and B score sets required")
        for values in row["scores"].values():
            if not isinstance(values, dict) or set(values) != set(DIMENSIONS):
                raise ValueError("All six rubric dimensions required; use null for unassessed")
            if any(
                v is not None and (type(v) is not int or not 0 <= v <= 4) for v in values.values()
            ):
                raise ValueError("Scores must be integers 0–4 or null")
        if all(v is None for values in row["scores"].values() for v in values.values()):
            raise ValueError("At least one human rubric score required")


def validate_human_scores(rows: list[JsonObject], reviews: dict[str, JsonObject]) -> None:
    """Legacy rows may omit kind; explicitly non-human rows never become human."""
    if any(row.get("reviewer_kind", "human") != "human" for row in rows):
        raise ValueError("Human assessments required; non-human reviewer_kind is not allowed")
    validate_scores(rows, reviews)


def score(root: Path, directory: Path, review_dir: Path, input_path: Path, out: Path) -> JsonObject:
    manifest, reviews, _ = validate_review(root, directory, review_dir)
    rows = lines(input_path)
    validate_human_scores(rows, reviews)
    data = dict(
        dataset_id=manifest["dataset_id"], review_sha256=manifest["review_sha256"], entries=rows
    )
    data["artifact_sha256"] = digest(data)
    write(out, data)
    return data


def report(
    root: Path, directory: Path, review_dir: Path, scores_path: Path | None = None
) -> JsonObject:
    manifest, reviews, keys = validate_review(root, directory, review_dir)
    output = dict(
        dataset_id=manifest["dataset_id"],
        split=manifest["split"],
        paired=len(reviews),
        unpaired=len(manifest["omitted_unpaired_refs"]),
        human_reviewed=0,
        status="prepared_not_evaluated",
        warning="No model quality benchmark has been run by this tool. "
        "Heuristic disagreement is not an error verdict. Human scores are descriptive for this "
        "stratified sample, not population estimates or independent ground truth.",
    )
    if scores_path is None:
        return output
    data = read(scores_path)
    verify_artifact(data, "artifact_sha256")
    if (
        data["dataset_id"] != manifest["dataset_id"]
        or data["review_sha256"] != manifest["review_sha256"]
    ):
        raise ValueError("Scores belong to another review package")
    if data.get("status") == "provisional_blind_llm_review" or data.get("llm_reviewed", 0):
        raise ValueError("Model review artifacts cannot be reported as human assessments")
    validate_human_scores(data["entries"], reviews)
    values: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    wins: Counter[str] = Counter()
    for row in data["entries"]:
        rid = row["review_id"]
        if rid not in reviews or row["pair_sha256"] != reviews[rid]["pair_sha256"]:
            raise ValueError("Scores refer to a different pair")
        key = keys[rid]
        winner = row["winner"]
        wins[key[winner] if winner in ("A", "B") else winner] += 1
        for label in ("A", "B"):
            for dimension, value in row["scores"][label].items():
                if value is not None:
                    values[key[label]][dimension].append(value)
    output.update(
        status="human_assessments_reported",
        human_reviewed=len(data["entries"]),
        preferences=dict(wins),
        scores={
            name: {dim: dict(n=len(v), mean=sum(v) / len(v)) for dim, v in dims.items()}
            for name, dims in values.items()
        },
    )
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("sample")
    p.add_argument("--out", required=True)
    p.add_argument("--size", type=int, default=120)
    p.add_argument("--seed", default="origin-eval-v1")
    p.add_argument(
        "--regression-refs", type=Path, help="JSON list of explicitly approved stable refs"
    )
    p.add_argument("--context-dir", type=Path)
    p = commands.add_parser("import-candidates")
    p.add_argument("--dataset", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--provenance", required=True)
    p = commands.add_parser("blind")
    p.add_argument("--dataset", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--left", default="baseline")
    p.add_argument("--right", required=True)
    p.add_argument("--split", choices=SPLITS, default="heldout")
    p.add_argument("--seed", default="blind-v1")
    p = commands.add_parser("score")
    p.add_argument("--dataset", required=True)
    p.add_argument("--review", required=True)
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p = commands.add_parser("report")
    p.add_argument("--dataset", required=True)
    p.add_argument("--review", required=True)
    p.add_argument("--scores")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if hasattr(args, "dataset"):
            args.dataset = output_path(args.dataset)
        if hasattr(args, "out"):
            args.out = output_path(args.out)
        if args.command == "sample":
            regression_refs = (
                json.loads(args.regression_refs.read_text()) if args.regression_refs else None
            )
            if regression_refs is not None and (
                not isinstance(regression_refs, list)
                or any(not isinstance(v, str) for v in regression_refs)
            ):
                raise ValueError("--regression-refs must contain a JSON list of strings")
            result = sample(ROOT, args.out, args.size, args.seed, regression_refs, args.context_dir)
        elif args.command == "import-candidates":
            result = import_candidates(ROOT, args.dataset, args.input, args.name, args.provenance)
        elif args.command == "blind":
            result = blind(
                ROOT, args.dataset, args.out, args.left, args.right, args.split, args.seed
            )
        elif args.command == "score":
            result = score(ROOT, args.dataset, args.review, args.input, args.out)
        else:
            result = report(ROOT, args.dataset, args.review, args.scores)
            write(args.out, result)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in ("entries", "provenance")},
                ensure_ascii=False,
                indent=2,
            )
        )
    except (ValueError, KeyError, TypeError, FileExistsError, FileNotFoundError) as error:
        parser.exit(2, str(error) + "\n")


if __name__ == "__main__":
    main()
