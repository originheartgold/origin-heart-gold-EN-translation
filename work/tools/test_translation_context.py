"""Semantic counterexamples for translation-context extraction; no ROM required."""

import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from typing import Any

import translation_context as T
from docs import romdata as R


def script(rows: list[Any], entries: tuple[str, ...] = ("start",)) -> bytes:
    """Assemble synthetic bytes using the existing factual command-size table."""
    names = {v[0]: (op, v[1]) for op, v in R.cmds().items()}
    pc = 4 * len(entries) + 2
    labels = {}
    for row in rows:
        if isinstance(row, str):
            labels[row] = pc
        else:
            pc += 2 + sum(names[row[0]][1])
    out = bytearray()
    for label in entries:
        out += struct.pack("<i", labels[label] - len(out) - 4)
    out += b"\x13\xfd"
    for row in rows:
        if isinstance(row, str):
            continue
        op, sizes = names[row[0]]
        end = len(out) + 2 + sum(sizes)
        out += struct.pack("<H", op)
        for size, arg in zip(sizes, row[1:], strict=True):
            if isinstance(arg, str):
                arg = labels[arg] - end
            out += arg.to_bytes(size, "little", signed=size == 4)
    return bytes(out)


def analyze(rows: list[Any], bank: int = 54, *, max_states: int = 2000) -> T.ContextIndex:
    return T.analyze(
        [script(rows)],
        [{"zone_id": 7, "scripts_bank": 0, "msg_bank": bank}],
        [],
        max_states=max_states,
    )


def rows_for(index: T.ContextIndex, ref: str) -> list[T.Occurrence]:
    return T.get_context(index, ref)["occurrences"]


class TranslationContextTests(unittest.TestCase):
    def test_variable_message_low_byte_and_unknown(self) -> None:
        result = analyze(
            [
                "start",
                ("SetVar", 0x8000, 513),
                ("NonNPCMsgVar", 0x8000),
                ("NPCMsgVar", 0x8001),
                ("End",),
            ]
        )
        row = rows_for(result, "a027/0054#1")[0]
        self.assertEqual(row["message_operand"]["value"], 513)
        self.assertEqual(row["message_operand"]["message_id"], 1)
        self.assertNotIn("a027/0054#32769", result["refs"])
        self.assertEqual(result["stats"]["diagnostics"]["unresolved-message"], 1)

    def test_external_message_operand_and_bank_do_not_leak(self) -> None:
        result = analyze(
            [
                "start",
                ("SetVar", 0x8000, 10),
                ("SetVar", 0x8001, 300),
                ("MsgBoxExtern", 0x8000, 0x8001),
                ("NPCMsg", 4),
                ("End",),
            ]
        )
        self.assertIn("a027/0010#300", result["refs"])
        self.assertIn("a027/0054#4", result["refs"])
        self.assertNotIn("a027/0054#10", result["refs"])
        self.assertNotIn("a027/0010#4", result["refs"])

    def test_gender_messages_are_alternatives_not_neighbors(self) -> None:
        result = analyze(["start", ("GenderMsgBox", 6, 7), ("NPCMsg", 8), ("End",)])
        male = rows_for(result, "a027/0054#6")[0]
        female = rows_for(result, "a027/0054#7")[0]
        self.assertEqual(male["previous_messages"], [])
        self.assertEqual(female["previous_messages"], [])
        self.assertEqual(female["branches"][-1]["player_gender"], "female")
        prev = rows_for(result, "a027/0054#8")[0]["previous_messages"]
        self.assertEqual({p["player_gender"] for p in prev}, {"male", "female"})

    def test_local_call_carries_buffer_and_returns_to_caller(self) -> None:
        result = analyze(
            [
                "start",
                ("Call", "sub"),
                ("NPCMsg", 2),
                ("End",),
                "sub",
                ("BufferPlayersName", 0),
                ("NPCMsg", 1),
                ("Return",),
            ]
        )
        inside = rows_for(result, "a027/0054#1")[0]
        after = rows_for(result, "a027/0054#2")[0]
        self.assertEqual(inside["call_path"][0]["kind"], "local")
        self.assertEqual(after["call_path"], [])
        self.assertEqual(after["buffers"]["0"]["kind"], "player_name")
        self.assertEqual(after["previous_messages"][0]["ref"], "a027/0054#1")

    def test_branch_assignments_do_not_become_a_linear_guess(self) -> None:
        result = analyze(
            [
                "start",
                ("CompareVarToValue", 0x8000, 0),
                ("GoToIf", 1, "other"),
                ("SetVar", 0x8001, 3),
                ("GoTo", "join"),
                "other",
                ("SetVar", 0x8001, 8),
                "join",
                ("NPCMsgVar", 0x8001),
                ("End",),
            ]
        )
        a = rows_for(result, "a027/0054#3")[0]
        b = rows_for(result, "a027/0054#8")[0]
        self.assertFalse(a["branches"][-1]["taken"])
        self.assertTrue(b["branches"][-1]["taken"])
        self.assertEqual(a["branches"][-1]["comparison"]["left"]["value"], None)

    def test_callstd_bank_restoration_and_release(self) -> None:
        caller = script(
            ["start", ("SetVar", 0x8000, 9), ("CallStd", 2000), ("NPCMsg", 2), ("End",)]
        )
        child = script(["start", ("NPCMsgVar", 0x8000), ("RestartCurrentScript",), ("End",)])
        result = T.analyze(
            [caller, child], [{"zone_id": 7, "scripts_bank": 0, "msg_bank": 54}], [(2000, 1, 38)]
        )
        inside = next(r for r in rows_for(result, "a027/0038#9") if r["root"]["script_file"] == 0)
        after = rows_for(result, "a027/0054#2")[0]
        self.assertEqual(inside["call_path"][0]["script_id"], 2000)
        self.assertEqual(after["previous_messages"][0]["ref"], "a027/0038#9")
        self.assertNotIn("a027/0038#2", result["refs"])

    def test_callstd_end_without_release_does_not_invent_return(self) -> None:
        caller = script(["start", ("CallStd", 2000), ("NPCMsg", 2), ("End",)])
        child = script(["start", ("NPCMsg", 1), ("End",)])
        result = T.analyze(
            [caller, child], [{"zone_id": 7, "scripts_bank": 0, "msg_bank": 54}], [(2000, 1, 38)]
        )
        self.assertEqual(rows_for(result, "a027/0054#2")[0]["root"]["kind"], "instruction-only")
        self.assertEqual(rows_for(result, "a027/0054#2")[0]["previous_messages"], [])
        self.assertIn("standard-end-without-release", result["stats"]["diagnostics"])

    def test_party_slot_is_not_a_species_id(self) -> None:
        result = analyze(
            [
                "start",
                ("BufferMonSpeciesName", 0, 25),
                ("BufferSpeciesName", 1, 25, 0x8000, 2),
                ("NPCMsg", 1),
                ("End",),
            ]
        )
        buffers = rows_for(result, "a027/0054#1")[0]["buffers"]
        self.assertEqual(buffers["0"]["kind"], "party_species_name")
        self.assertEqual(buffers["1"]["kind"], "species_name")
        self.assertEqual(buffers["1"]["source"]["args"], [1, 25, 0x8000, 2])

    def test_opaque_command_erases_stale_provenance(self) -> None:
        result = analyze(
            [
                "start",
                ("SetVar", 0x8000, 1),
                ("BufferPlayersName", 0),
                ("NPCMsg", 1),
                ("ScrCmd_061",),
                ("NPCMsg", 2),
                ("NPCMsgVar", 0x8000),
                ("End",),
            ]
        )
        row = rows_for(result, "a027/0054#2")[0]
        self.assertEqual(row["buffers"], {})
        self.assertEqual(row["variables"], {})
        self.assertEqual(row["previous_messages"], [])
        self.assertTrue(row["unknowns"])

    def test_menu_uses_its_initialization_bank_and_exact_operand(self) -> None:
        result = analyze(
            [
                "start",
                ("MenuInitStdGmm", 0, 0, 0, 0, 0x8000),
                ("MenuItemAdd", 7, 8, 9),
                ("MenuInit", 0, 0, 0, 0, 0x8000),
                ("MenuItemAdd", 10, 11, 12),
                ("NPCMsg", 13),
                ("End",),
            ]
        )
        self.assertIn("a027/0189#7", result["refs"])
        self.assertIn("a027/0054#10", result["refs"])
        self.assertNotIn("a027/0054#8", result["refs"])
        self.assertEqual(rows_for(result, "a027/0054#13")[0]["previous_messages"], [])

    def test_unknown_menu_bank_is_not_assumed_local(self) -> None:
        result = analyze(["start", ("MenuItemAdd", 7, 8, 9), ("End",)])
        self.assertEqual(result["refs"], {})
        self.assertIn("unresolved-message", result["stats"]["diagnostics"])

    def test_bounded_loop_is_explicitly_incomplete(self) -> None:
        result = analyze(
            [
                "start",
                ("SetVar", 0x8000, 0),
                "loop",
                ("AddVar", 0x8000, 1),
                ("NPCMsgVar", 0x8000),
                ("GoTo", "loop"),
            ],
            max_states=12,
        )
        self.assertIn("state-budget-exhausted", result["stats"]["diagnostics"])

    def test_shared_script_has_multiple_map_bank_bindings(self) -> None:
        data = script(["start", ("NPCMsg", 1), ("End",)])
        result = T.analyze(
            [data],
            [
                {"zone_id": 1, "scripts_bank": 0, "msg_bank": 4},
                {"zone_id": 2, "scripts_bank": 0, "msg_bank": 5},
            ],
            [],
        )
        self.assertEqual(set(result["refs"]), {"a027/0004#1", "a027/0005#1"})
        self.assertEqual(rows_for(result, "a027/0005#1")[0]["map_context"][0]["zone_id"], 2)

    def test_header_not_disassembled_as_script(self) -> None:
        with self.assertRaises(ValueError):
            T.decode(b"\x02\x01\x00\x00\x00\x00")

    def test_context_limit_prefers_map_callers_over_standard_templates(self) -> None:
        child = script(["start", ("NPCMsg", 1), ("RestartCurrentScript",), ("End",)])
        caller = script(["start", ("CallStd", 2000), ("End",)])
        result = T.analyze(
            [child, caller],
            [{"zone_id": 7, "scripts_bank": 1, "msg_bank": 54}],
            [(2000, 0, 38)],
            max_contexts=1,
        )
        rows = rows_for(result, "a027/0038#1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["root"]["script_file"], 1)
        self.assertIn("occurrence-contexts-truncated", result["stats"]["diagnostics"])

    def test_instruction_inventory_survives_path_budget_without_fake_context(self) -> None:
        result = analyze(["start", ("Noop",), ("Noop",), ("NPCMsg", 99), ("End",)], max_states=1)
        row = rows_for(result, "a027/0054#99")[0]
        self.assertEqual(row["root"]["kind"], "instruction-only")
        self.assertEqual(row["previous_messages"], [])
        self.assertEqual(row["buffers"], {})
        self.assertTrue(row["unknowns"])

    def test_focused_roots_keep_callees_without_exploring_their_other_entries(self) -> None:
        caller = script(["start", ("CallStd", 2000), ("NPCMsg", 2), ("End",)])
        child = script(
            [
                "start",
                ("NPCMsg", 1),
                ("RestartCurrentScript",),
                ("End",),
                "unused",
                ("NPCMsg", 3),
                ("End",),
            ],
            entries=("start", "unused"),
        )
        result = T.analyze(
            [caller, child],
            [{"zone_id": 7, "scripts_bank": 0, "msg_bank": 54}],
            [(2000, 1, 38)],
            root_files={0},
        )
        self.assertEqual(result["stats"]["roots"], 1)
        self.assertEqual(result["stats"]["root_files"], [0])
        self.assertEqual(rows_for(result, "a027/0038#1")[0]["root"]["script_file"], 0)
        self.assertEqual(rows_for(result, "a027/0038#3")[0]["root"]["kind"], "instruction-only")
        self.assertNotIn("1:38:2", result["roots"])

    def test_known_comparisons_never_produce_contradictory_paths(self) -> None:
        for code, expected in enumerate((True, False, False, True, False, True)):
            with self.subTest(condition=code):
                result = analyze(
                    [
                        "start",
                        ("SetVar", 0x8000, 0),
                        ("CompareVarToValue", 0x8000, 1),
                        ("GoToIf", code, "yes"),
                        ("NPCMsg", 2),
                        ("End",),
                        "yes",
                        ("NPCMsg", 1),
                        ("End",),
                    ]
                )
                chosen = rows_for(result, f"a027/0054#{1 if expected else 2}")[0]
                impossible = rows_for(result, f"a027/0054#{2 if expected else 1}")[0]
                self.assertEqual(chosen["root"]["kind"], "declared-entry")
                self.assertEqual(chosen["branches"][-1]["taken"], expected)
                self.assertEqual(impossible["root"]["kind"], "instruction-only")

    def test_callstd_comparison_is_context_local_and_parent_restored(self) -> None:
        caller = script(
            [
                "start",
                ("SetVar", 0x8000, 0),
                ("CompareVarToValue", 0x8000, 1),
                ("CallStd", 2000),
                ("GoToIf", 1, "bad"),
                ("NPCMsg", 2),
                ("End",),
                "bad",
                ("NPCMsg", 3),
                ("End",),
            ]
        )
        child = script(
            [
                "start",
                ("GoToIf", 1, "other"),
                ("NPCMsg", 4),
                ("GoTo", "end"),
                "other",
                ("NPCMsg", 5),
                "end",
                ("SetVar", 0x8000, 1),
                ("CompareVarToValue", 0x8000, 1),
                ("RestartCurrentScript",),
                ("End",),
            ]
        )
        result = T.analyze(
            [caller, child],
            [{"zone_id": 7, "scripts_bank": 0, "msg_bank": 54}],
            [(2000, 1, 38)],
            root_files={0},
        )
        self.assertTrue(
            all(r["root"]["kind"] == "declared-entry" for r in rows_for(result, "a027/0038#4"))
        )
        self.assertTrue(
            all(r["root"]["kind"] == "declared-entry" for r in rows_for(result, "a027/0038#5"))
        )
        self.assertEqual(rows_for(result, "a027/0054#3")[0]["root"]["kind"], "instruction-only")
        self.assertEqual(rows_for(result, "a027/0054#2")[0]["root"]["kind"], "declared-entry")

    def test_json_boundary_and_stale_source_rejected(self) -> None:
        result = analyze(["start", ("NPCMsg", 1), ("End",)])
        T.validate_index(result)
        malformed: Any = copy.deepcopy(result)
        malformed["refs"]["a027/0054#1"]["occurrences"][0]["pc"] = "6"
        with self.assertRaises(ValueError):
            T.validate_index(malformed)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.write_text("original")
            result["source"] = {
                name: {"path": str(source), "sha256": T.sha256(source)}
                for name in ("rom", "bank_maps", "script_cmds", "romdata", "extractor")
            }
            target = Path(temp) / "index.json"
            target.write_text(json.dumps(result))
            source.write_text("changed")
            with self.assertRaisesRegex(ValueError, "stale translation context"):
                T.load_index(target)


if __name__ == "__main__":
    unittest.main()
