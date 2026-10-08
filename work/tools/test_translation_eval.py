"""Synthetic evaluation fixtures only; no game text, downloads or model calls."""

import importlib.util
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any

SPEC = importlib.util.spec_from_file_location(
    "translation_eval", Path(__file__).with_name("translation_eval.py")
)
assert SPEC is not None and SPEC.loader is not None
ev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ev)


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bank = self.root / "work/translate/banks/synthetic/0001.json"
        self.bank.parent.mkdir(parents=True)
        self.rows = [
            dict(
                id=i,
                zh=f"测试句子{i}不可以。{{VAR:0103:0}}",
                en=f"SYNTHETIC SECRET {i} {{VAR:0103:0}}",
                origin="agent",
            )
            for i in range(100)
        ]
        self.rows += [
            dict(id=100, zh=self.rows[0]["zh"], en="SECOND SECRET", origin="us"),
            dict(id=101, zh="[zh redacted: song lyrics; sha256:" + "0" * 64 + "]", en="hum"),
        ]
        self.bank.write_text(json.dumps(dict(strings=self.rows)))
        for index in range(2, 32):
            other = self.bank.with_name(f"{index:04}.json")
            other.write_text(
                json.dumps(
                    dict(
                        strings=[
                            dict(
                                id=i,
                                zh=f"第{index}组测试句子{i}不可以。{{VAR:0103:0}}",
                                en=f"SYNTHETIC SECRET {index}/{i} {{VAR:0103:0}}",
                                origin="agent",
                            )
                            for i in range(10)
                        ]
                    )
                )
            )
        self.out = self.root / "dataset"

    def prepare(self) -> dict[str, Any]:
        result: dict[str, Any] = ev.sample(self.root, self.out, 30, "test")
        return result

    def candidates(
        self, data: dict[str, Any], mutation: Callable[[list[dict[str, Any]]], None] | None = None
    ) -> dict[str, Any]:
        rows = [
            dict(
                ref=r["ref"],
                dataset_id=data["dataset_id"],
                source_sha256=r["source_sha256"],
                en="A synthetic translation. {VAR:0103:0}",
            )
            for r in data["entries"]
        ]
        if mutation:
            mutation(rows)
        path = self.root / "external.jsonl"
        ev.write(path, rows, True)
        provenance = self.root / "provenance.json"
        ev.write(
            provenance,
            dict(
                provider="synthetic",
                model="test-only",
                generated_at="2026-01-01T00:00:00Z",
                prompt_sha256="1" * 64,
                input_sha256="2" * 64,
            ),
        )
        result: dict[str, Any] = ev.import_candidates(
            self.root, self.out, path, "alternative", provenance
        )
        return result

    def test_deterministic_stratified_disjoint_and_no_existing_english_leak(self) -> None:
        data = self.prepare()
        second = ev.sample(self.root, self.root / "second", 30, "test")
        self.assertEqual(data, second)
        self.assertEqual(sum(data["split_counts"].values()), 30)
        hashes = [r["source_group"] for r in data["entries"]]
        self.assertEqual(len(hashes), len(set(hashes)))
        for split in ev.SPLITS:
            text = (self.out / (split + "-inputs.jsonl")).read_text()
            self.assertNotIn("SECRET", text)
            for row in ev.lines(self.out / (split + "-inputs.jsonl")):
                self.assertNotIn("en", row)
                self.assertNotIn("origin", row)
        self.assertEqual(data["excluded"]["redacted_lyrics"], 1)

    def test_stale_english_or_source_rejected(self) -> None:
        data = self.prepare()
        bank, chosen = data["entries"][0]["ref"].split("#")
        path = self.root / "work/translate/banks" / (bank + ".json")
        current = ev.read(path)
        current["strings"][int(chosen)]["en"] = "changed"
        path.write_text(json.dumps(current))
        with self.assertRaisesRegex(ValueError, "Stale dataset"):
            ev.fresh(self.root, data)

    def test_missing_protected_tag_rejects_whole_import(self) -> None:
        data = self.prepare()
        with self.assertRaisesRegex(ValueError, "protected control tags"):
            self.candidates(data, lambda rows: rows[0].update(en="Missing variable"))
        self.assertFalse((self.out / "candidates/alternative.json").exists())

    def test_duplicate_refs_rejected(self) -> None:
        data = self.prepare()
        with self.assertRaisesRegex(ValueError, "duplicate candidate ref"):
            self.candidates(data, lambda rows: rows.append(rows[0]))

    def test_source_fingerprint_rejected(self) -> None:
        data = self.prepare()
        with self.assertRaisesRegex(ValueError, "source fingerprint"):
            self.candidates(data, lambda rows: rows[0].update(source_sha256="0" * 64))

    def test_flags_are_warnings_and_layout_is_allowed(self) -> None:
        data = self.prepare()
        imported = self.candidates(
            data, lambda rows: rows[0].update(en="Never!{NEWLINE}{VAR:0103:0}")
        )
        self.assertIn(
            "candidate_absolute_or_strong_word_check_source", imported["entries"][0]["flags"]
        )
        self.assertIn("never semantic verdicts", imported["warning"])

    def test_blinding_scores_and_honest_unscored_report(self) -> None:
        data = self.prepare()
        self.candidates(data)
        review = self.root / "blind"
        ev.blind(self.root, self.out, review, "baseline", "alternative")
        unscored = ev.report(self.root, self.out, review)
        self.assertEqual(unscored["status"], "prepared_not_evaluated")
        self.assertEqual(unscored["human_reviewed"], 0)
        for row in ev.lines(review / "review.jsonl"):
            self.assertEqual(
                set(row), {"ref", "zh", "source_sha256", "A", "B", "pair_sha256", "review_id"}
            )
        scores = ev.lines(review / "score-template.jsonl")
        for row in scores:
            row.update(reviewer="Synthetic reviewer", notes="Synthetic evidence.", winner="tie")
            row["scores"]["A"]["meaning"] = 3
            row["scores"]["B"]["meaning"] = 4
        inp = self.root / "human.jsonl"
        ev.write(inp, scores, True)
        out = self.root / "scores.json"
        ev.score(self.root, self.out, review, inp, out)
        result = ev.report(self.root, self.out, review, out)
        self.assertEqual(result["human_reviewed"], len(scores))
        self.assertEqual(result["preferences"]["tie"], len(scores))

    def test_explicit_model_scores_cannot_become_human_assessments(self) -> None:
        data = self.prepare()
        self.candidates(data)
        review = self.root / "blind"
        ev.blind(self.root, self.out, review, "baseline", "alternative")
        rows = ev.lines(review / "score-template.jsonl")
        for row in rows:
            row.update(reviewer="Model", reviewer_kind="llm", notes="Evidence", winner="tie")
            row["scores"]["A"]["meaning"] = 3
        inp = self.root / "model.jsonl"
        ev.write(inp, rows, True)
        with self.assertRaisesRegex(ValueError, "Human assessments required"):
            ev.score(self.root, self.out, review, inp, self.root / "bad.json")
        manifest = ev.read(review / "manifest.json")
        artifact = dict(
            dataset_id=manifest["dataset_id"],
            review_sha256=manifest["review_sha256"],
            entries=rows,
            status="provisional_blind_llm_review",
            llm_reviewed=len(rows),
        )
        artifact["artifact_sha256"] = ev.digest(artifact)
        out = self.root / "model.json"
        ev.write(out, artifact)
        with self.assertRaisesRegex(ValueError, "Model review artifacts"):
            ev.report(self.root, self.out, review, out)

    def test_review_tampering_and_empty_score_template_rejected(self) -> None:
        data = self.prepare()
        self.candidates(data)
        review = self.root / "blind"
        ev.blind(self.root, self.out, review, "baseline", "alternative")
        with self.assertRaisesRegex(ValueError, "human reviewer"):
            ev.score(
                self.root, self.out, review, review / "score-template.jsonl", self.root / "bad.json"
            )
        with (review / "review.jsonl").open("a") as f:
            f.write(json.dumps(ev.lines(review / "review.jsonl")[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "Review package changed"):
            ev.report(self.root, self.out, review)

    def test_output_guard_and_no_overwrite(self) -> None:
        with self.assertRaises(ValueError):
            ev.output_path("/tmp/untracked-eval")
        self.prepare()
        with self.assertRaises(FileExistsError):
            ev.sample(self.root, self.out, 30, "test")

    def test_whole_banks_and_explicit_regressions_are_disjoint(self) -> None:
        data = ev.sample(self.root, self.out, 30, "test", ["synthetic/0001#1"])
        splits: dict[str, set[str]] = {}
        for row in data["entries"]:
            splits.setdefault(row["ref"].split("#")[0], set()).add(row["split"])
        self.assertTrue(all(len(values) == 1 for values in splits.values()))
        self.assertEqual(splits["synthetic/0001"], {"regression"})
        self.assertIn("synthetic/0001#1", [r["ref"] for r in data["entries"]])

    def context_fixture(self, entry: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        folder = self.root / "context"
        folder.mkdir(exist_ok=True)
        tool = self.root / "work/tools/translation_package.py"
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_text("synthetic package tool")
        package = dict(
            schema_version=1,
            mode="independent",
            ref=entry["ref"],
            source=dict(zh=entry["zh"], sha256=entry["source_sha256"], language="zh"),
            linguistics={},
            context={},
            related_occurrences={},
            decisions={},
            layout={},
            provenance=dict(
                input_hashes={}, package_tool_sha256=ev.file_digest(tool), script_source=None
            ),
            warnings=[],
        )
        return folder, package

    def save_package(self, folder: Path, package: dict[str, Any]) -> None:
        package.pop("package_sha256", None)
        package["package_sha256"] = ev.digest(
            json.dumps(package, ensure_ascii=False, separators=(",", ":"))
        )
        (folder / "source.json").write_text(json.dumps(package, ensure_ascii=False))

    def test_context_allowlist_fingerprints_and_heldout_leakage(self) -> None:
        data = self.prepare()
        entry = next(r for r in data["entries"] if r["split"] == "development")
        folder, package = self.context_fixture(entry)
        self.save_package(folder, package)
        included = ev.independent_context(self.root, folder, data["entries"])
        self.assertEqual(list(included), [entry["ref"]])
        package["mode"] = "review"
        self.save_package(folder, package)
        with self.assertRaisesRegex(ValueError, "allowlisted independent"):
            ev.independent_context(self.root, folder, data["entries"])
        package["mode"] = "independent"
        held = next(r for r in data["entries"] if r["split"] == "heldout")
        package["context"] = {"previous": {"zh": held["zh"]}}
        self.save_package(folder, package)
        with self.assertRaisesRegex(ValueError, "Held-out source leaked"):
            ev.independent_context(self.root, folder, data["entries"])
        package["context"] = {}
        self.save_package(folder, package)
        package["source"]["zh"] = "tampered"
        (folder / "source.json").write_text(json.dumps(package))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            ev.independent_context(self.root, folder, data["entries"])

    def test_candidate_and_score_tampering_rejected(self) -> None:
        data = self.prepare()
        self.candidates(data)
        review = self.root / "blind"
        ev.blind(self.root, self.out, review, "baseline", "alternative")
        rows = ev.lines(review / "score-template.jsonl")[:1]
        rows[0].update(reviewer="Human", notes="Synthetic evidence.")
        rows[0]["scores"]["A"]["meaning"] = 4
        inp, out = self.root / "human.jsonl", self.root / "scores.json"
        ev.write(inp, rows, True)
        scores = ev.score(self.root, self.out, review, inp, out)
        scores["entries"][0]["scores"]["A"]["meaning"] = 0
        out.write_text(json.dumps(scores))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            ev.report(self.root, self.out, review, out)
        path = self.out / "candidates/alternative.json"
        artifact = ev.read(path)
        artifact["entries"][0]["en"] = "Edited after review"
        path.write_text(json.dumps(artifact))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            ev.report(self.root, self.out, review)

    def test_json_boundary_rejects_nonobject_rows(self) -> None:
        path = self.root / "invalid.jsonl"
        path.write_text("[]\n")
        with self.assertRaisesRegex(ValueError, "JSON objects"):
            ev.lines(path)


if __name__ == "__main__":
    unittest.main()
