"""Synthetic isolation and integrity tests; no game assets or provider calls."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import translation_eval as E
import translation_trial as T


class TrialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dataset = self.root / "dataset"
        self.dataset.mkdir()
        self.notes = self.root / "notes.json"
        E.write(self.notes, {"cases": {}, "phrases": []})
        self.ref = "a027/0001#0"
        self.package = {
            "context": {},
            "linguistics": {},
            "decisions": {"accepted": []},
            "layout": {},
            "package_sha256": "fingerprint",
        }
        self.source = {
            "ref": self.ref,
            "zh": "人『测试。",
            "source_sha256": E.digest("人『测试。"),
            "dataset_id": "dataset",
            "context_package": self.package,
        }
        E.write(self.dataset / "development-inputs.jsonl", [self.source], True)
        self.data: dict[str, Any] = {
            "dataset_id": "dataset",
            "entries": [
                {
                    "ref": self.ref,
                    "split": "development",
                    "source_sha256": self.source["source_sha256"],
                    "en": "BASELINE SECRET",
                }
            ],
            "context_fingerprints": {self.ref: "fingerprint"},
        }
        E.write(self.dataset / "dataset.json", self.data)
        for obj, name, value in [(T, "REFS", ["0001#0"]), (E, "ROOT", self.root)]:
            handle = patch.object(obj, name, value)
            handle.start()
            self.addCleanup(handle.stop)
        for name, value in [("fresh", None), ("independent_context", {self.ref: self.package})]:
            mock_handle = patch.object(E, name, return_value=value)
            mock_handle.start()
            self.addCleanup(mock_handle.stop)

    def prepare(self) -> dict[str, object]:
        return T.prepare(
            self.dataset, self.root / "work/build/trial", self.notes, self.root / "packages"
        )

    def test_source_isolation_and_refusal_to_overwrite(self) -> None:
        self.prepare()
        output = self.root / "work/build/trial"
        rows = E.lines(output / "source-only.jsonl")
        self.assertEqual(set(rows[0]), {"ref", "zh", "source_sha256", "dataset_id"})
        self.assertNotIn("BASELINE SECRET", (output / "context-enriched.jsonl").read_text())
        self.assertEqual(
            E.lines(output / "context-enriched.jsonl")[0]["context"]["speaker"][
                "explicit_chinese_labels"
            ],
            ["人"],
        )
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.prepare()

    def test_heldout_rejected_before_any_output(self) -> None:
        self.data["entries"][0]["split"] = "heldout"
        (self.dataset / "dataset.json").write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, "never consume"):
            self.prepare()
        self.assertFalse((self.root / "work/build/trial").exists())

    def test_source_edit_rejected(self) -> None:
        self.source["zh"] = "changed"
        (self.dataset / "development-inputs.jsonl").write_text(json.dumps(self.source) + "\n")
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.prepare()

    def test_context_edit_rejected_even_with_original_hash(self) -> None:
        mutated = json.loads(json.dumps(self.source))
        mutated["context_package"]["context"]["speaker"] = "invented"
        (self.dataset / "development-inputs.jsonl").write_text(json.dumps(mutated) + "\n")
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.prepare()

    def test_artifacts_outside_ignored_directory_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "ignored"):
            T.prepare(self.dataset, self.root / "unsafe", self.notes, self.root / "packages")

    def score_fixture(self) -> Path:
        rows = [
            {
                "review_id": "r1",
                "ref": self.ref,
                "pair_sha256": "pair",
                "reviewer": "isolated-model",
                "reviewer_kind": "llm",
                "winner": "A",
                "scores": {label: dict.fromkeys(E.DIMENSIONS, 3) for label in ("A", "B")},
                "notes": "Synthetic evidence.",
            }
        ]
        path = self.root / "scores.jsonl"
        E.write(path, rows, True)
        handle = patch.object(
            E,
            "validate_review",
            return_value=(
                {
                    "dataset_id": "dataset",
                    "review_sha256": "review",
                    "split": "development",
                    "omitted_unpaired_refs": [],
                },
                {"r1": {"ref": self.ref, "pair_sha256": "pair"}},
                {"r1": {"A": "one", "B": "two"}},
            ),
        )
        handle.start()
        self.addCleanup(handle.stop)
        return path

    def test_llm_scores_never_count_as_human(self) -> None:
        scores = self.score_fixture()
        result = T.summarize_model_review(
            self.dataset, self.root, scores, self.root / "work/build/report.json"
        )
        self.assertEqual(result["human_reviewed"], 0)
        self.assertEqual(result["llm_reviewed"], 1)
        self.assertEqual(result["preferences"], {"one": 1})
        with self.assertRaisesRegex(ValueError, "Model review artifacts"):
            E.report(self.root, self.dataset, self.root, self.root / "work/build/report.json")
        with self.assertRaisesRegex(ValueError, "Human assessments required"):
            E.score(self.root, self.dataset, self.root, scores, self.root / "human.json")

    def test_reviewer_type_must_be_explicit(self) -> None:
        scores = self.score_fixture()
        rows = E.lines(scores)
        rows[0].pop("reviewer_kind")
        scores.write_text(json.dumps(rows[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "reviewer_kind"):
            T.summarize_model_review(
                self.dataset, self.root, scores, self.root / "work/build/report.json"
            )

    def test_partial_review_rejected(self) -> None:
        scores = self.score_fixture()
        with patch.object(
            E,
            "validate_review",
            return_value=(
                {
                    "dataset_id": "dataset",
                    "review_sha256": "review",
                    "split": "development",
                    "omitted_unpaired_refs": [],
                },
                {"r1": {"ref": self.ref, "pair_sha256": "pair"}, "r2": {}},
                {"r1": {"A": "one", "B": "two"}},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Complete"):
                T.summarize_model_review(
                    self.dataset, self.root, scores, self.root / "work/build/report.json"
                )


if __name__ == "__main__":
    unittest.main()
