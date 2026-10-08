"""Synthetic context packages: no ROMs, network, or official game text."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import text_catalog as catalog
import translation_package as package


class PackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "work/translate/banks/a027/0001.json"
        self.path.parent.mkdir(parents=True)
        self.rows = [
            {"id": 0, "zh": "银行。", "en": "SECRET EXISTING TARGET", "notes": "SECRET NOTE"},
            {"id": 1, "zh": "你好吗？", "en": "SECRET NEIGHBOR"},
            {"id": 2, "zh": "银行。", "en": "SECRET DUPLICATE"},
            {"id": 3, "zh": "[zh redacted: song lyrics; sha256:" + "0" * 64 + "]", "en": "hums"},
        ]
        self.path.write_text(json.dumps({"narc": "a027", "bank": 1, "strings": self.rows}))
        decisions = self.root / "work/translate/decisions/decisions.jsonl"
        decisions.parent.mkdir(parents=True)
        self.decisions = [
            {
                "id": "D-1",
                "type": "question",
                "status": "resolved",
                "refs": ["a027/0001#0"],
                "answer": "SECRET APPROVED ANSWER",
            },
            {
                "id": "D-2",
                "type": "term",
                "status": "accepted",
                "zh": "银行",
                "en": "bank",
                "scope": "global",
            },
            {
                "id": "D-3",
                "type": "term",
                "status": "provisional",
                "zh": "银行",
                "en": "SECRET PROPOSAL",
            },
            {
                "id": "D-4",
                "type": "term",
                "status": "accepted",
                "zh": "银行",
                "en": "SECRET OTHER SCOPE",
                "scope": ["a027/0011"],
            },
            {"id": "D-5", "type": "style", "status": "accepted", "en": "Preserve uncertainty."},
        ]
        decisions.write_text("".join(json.dumps(x) + "\n" for x in self.decisions))
        self.db_path = self.root / "catalog.sqlite3"
        catalog.build(self.root, self.db_path)

    def make(
        self, mode: package.Mode = "review", context: dict[str, Any] | None = None
    ) -> package.ReviewPackage:
        with catalog.connect(self.db_path) as db:
            return package.make_package(
                db, self.root, "a027/0001#0", package.PackageOptions(mode), context
            )

    def test_review_has_existing_translation_and_decision(self) -> None:
        result = self.make()
        self.assertEqual(result["translation"]["en"], self.rows[0]["en"])
        self.assertIn("D-1", [d["id"] for d in result["decisions"]["accepted"]])
        self.assertEqual(result["context"]["speaker"]["state"], "unknown")

    def test_changed_annotation_requires_refresh(self) -> None:
        path = self.root / "work/translate/text_catalog/annotations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ref": "a027/0001#0", "note": "new evidence"}) + "\n")
        with self.assertRaisesRegex(ValueError, "annotation changed"):
            self.make()
        self.assertNotIn("annotation", self.make("independent"))

    def test_output_stays_in_ignored_build_directory(self) -> None:
        package.check_output(self.root / "work/build/package.json", self.root)
        for path in (self.root / "work/package.json", self.root / "work/build/../package.json"):
            with self.assertRaisesRegex(ValueError, "work/build"):
                package.check_output(path, self.root)
        target = self.root / "work/build/link"
        target.parent.mkdir(parents=True)
        target.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "work/build"):
            package.check_output(target / "escaped.json", self.root)

    def test_independent_excludes_translation_and_target_decisions(self) -> None:
        result = self.make(
            "independent",
            {
                "refs": {
                    "a027/0001#0": {
                        "occurrences": [
                            {
                                "previous_messages": [{"ref": "a027/0001#1"}],
                                "branches": ["condition unresolved"],
                            }
                        ]
                    }
                }
            },
        )
        encoded = json.dumps(result)
        self.assertNotIn("SECRET", encoded)
        self.assertNotIn("translation", result)
        self.assertNotIn("annotation", result)
        self.assertEqual(
            result["context"]["script_occurrences"][0]["previous_text"][0]["zh"], "你好吗？"
        )
        self.assertIn("D-2", [d["id"] for d in result["decisions"]["accepted"]])

    def test_storage_neighbors_are_not_assumed_dialogue(self) -> None:
        result = self.make()
        self.assertEqual(result["context"]["script_occurrences"], [])
        self.assertNotIn("SECRET NEIGHBOR", json.dumps(result))
        self.assertEqual(result["related_occurrences"]["total"], 1)

    def test_occurrence_limit_does_not_spend_all_slots_on_one_root(self) -> None:
        occurrences = [{"root": {"id": "standard"}, "pc": 10, "variant": n} for n in range(20)]
        occurrences.append({"root": {"id": "map-caller"}, "pc": 10})
        selected = package.diverse_occurrences(occurrences, 3)
        self.assertEqual(
            [o["root"]["id"] for o in selected], ["standard", "map-caller", "standard"]
        )

    def test_source_and_english_changes_invalidate_catalogue(self) -> None:
        data = json.loads(self.path.read_text())
        data["strings"][0]["en"] = "a new translation"
        self.path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "stale"):
            self.make()

    def test_layout_honors_per_entry_override(self) -> None:
        cfg = self.root / "work/tools/qa_config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            json.dumps(
                {
                    "banks": {"a027/0001": "ui"},
                    "categories": {"ui": {}, "sign": {"line_px": 160}},
                    "string_categories": {"a027/0001": {"0": "sign"}},
                }
            )
        )
        self.assertEqual(self.make()["layout"]["category"], "sign")

    def test_target_scope_uses_exact_refs_and_ranges(self) -> None:
        self.assertTrue(package.in_scope("a027/0001#0", "a027/0001#0"))
        self.assertFalse(package.in_scope("a027/0001#01", "a027/0001#0"))
        self.assertFalse(package.in_scope(["a027/0011"], "a027/0001#0"))
        self.assertTrue(package.ref_matches("a027/0001#0-4", "a027/0001#2"))

    def test_redacted_lyrics_are_not_packaged(self) -> None:
        with catalog.connect(self.db_path) as db:
            with self.assertRaisesRegex(ValueError, "redacted"):
                package.make_package(db, self.root, "a027/0001#3", package.PackageOptions())

    def test_context_input_hashes_fail_closed(self) -> None:
        path = self.root / "index.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "refs": {},
                    "source": {
                        "input_hashes": {
                            str(self.path.relative_to(self.root)): package.file_hash(self.path)
                        }
                    },
                }
            )
        )
        self.assertIsNotNone(package.load_context(path, self.root)[0])
        self.path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "stale"):
            package.load_context(path, self.root)

    def test_unfingerprinted_context_is_rejected(self) -> None:
        path = self.root / "index.json"
        path.write_text(json.dumps({"schema_version": 1, "refs": {}, "source": {}}))
        with self.assertRaisesRegex(ValueError, "fingerprints"):
            package.load_context(path, self.root)

    def test_package_hash_covers_mode_and_full_context(self) -> None:
        result = self.make()
        fingerprint = result.pop("package_sha256")
        self.assertEqual(fingerprint, catalog.digest(catalog.packed(result)))
        self.assertNotEqual(fingerprint, self.make("independent")["package_sha256"])

    def test_invalid_options(self) -> None:
        with self.assertRaises(ValueError):
            package.PackageOptions(related_limit=-1)

    def test_following_context_requires_matching_script_root(self) -> None:
        context = {
            "refs": {
                "a027/0001#0": {
                    "occurrences": [{"root": {"entry": 1}, "script_file": 4, "pc": 10}]
                },
                "a027/0001#1": {
                    "occurrences": [
                        {
                            "root": {"entry": 1},
                            "script_file": 4,
                            "pc": 20,
                            "previous_messages": [
                                {"ref": "a027/0001#0", "script_file": 4, "pc": 10}
                            ],
                        },
                        {
                            "root": {"entry": 2},
                            "script_file": 4,
                            "pc": 30,
                            "previous_messages": [
                                {"ref": "a027/0001#0", "script_file": 4, "pc": 10}
                            ],
                        },
                    ]
                },
            }
        }
        result = self.make("independent", context)
        following = result["context"]["script_occurrences"][0]["following_text"]
        self.assertEqual(len(following), 1)
        self.assertEqual(following[0]["pc"], 20)
        self.assertEqual(following[0]["zh"], "你好吗？")
        self.assertNotIn("SECRET", json.dumps(result))
        successors = package.build_successor_index(context, {"a027/0001#0"})
        with catalog.connect(self.db_path) as db:
            batched = package.make_package(
                db,
                self.root,
                "a027/0001#0",
                package.PackageOptions("independent"),
                context,
                successors=successors["a027/0001#0"],
            )
        self.assertEqual(batched, result)

    def test_missing_previous_message_remains_explicit(self) -> None:
        result = self.make(
            context={
                "refs": {
                    "a027/0001#0": {
                        "occurrences": [{"previous_messages": [{"ref": "a027/0001#999"}]}]
                    }
                }
            }
        )
        self.assertEqual(
            result["context"]["script_occurrences"][0]["previous_text"][0]["state"],
            "missing-from-catalogue",
        )


if __name__ == "__main__":
    unittest.main()
