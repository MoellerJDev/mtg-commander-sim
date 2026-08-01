from __future__ import annotations

import json
import unittest

from scripts.update_architecture_audit import (
    CARD_BASELINE,
    ROOT,
    _check_outputs,
    build_report,
)


def _json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class ArchitectureAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_report()

    def test_generated_outputs_are_current(self):
        self.assertEqual(_check_outputs(self.report), [])

    def test_report_reconciles_measured_architecture_and_tests(self):
        architecture = self.report["architecture"]
        production = architecture["production"]
        engine = architecture["engine"]
        tests = self.report["tests"]

        engine_lines = len(
            (ROOT / "mtg_commander_sim" / "engine.py")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        self.assertEqual(engine["physical_lines"], engine_lines)
        self.assertEqual(
            production["oversized_module_count"],
            len(production["oversized_modules"]),
        )
        self.assertEqual(
            production["oversized_function_and_method_count"],
            len(production["oversized_functions_and_methods"]),
        )
        self.assertEqual(
            architecture["direct_game_state_write_heuristic"]["count"],
            len(architecture["direct_game_state_write_heuristic"]["locations"]),
        )
        self.assertTrue(tests["python"]["reconciles"])
        self.assertEqual(
            tests["python"]["discovered_total"],
            tests["python"]["conventional_ast_cases"]
            + tests["python"]["generated_rule_conformance_cases"],
        )

    def test_report_tracks_pinned_compiler_semantics_and_document_drift(self):
        compiler = self.report["compiler"]
        oracle = _json("coverage/oracle-coverage.json")
        rules = _json("rules/manifest.json")
        semantics = self.report["semantic_packs_and_overrides"]
        documents = self.report["documentation"]
        baseline = json.loads(CARD_BASELINE.read_text(encoding="utf-8"))

        self.assertEqual(compiler["compiler_version"], oracle["compiler_version"])
        self.assertEqual(
            self.report["rules"]["comprehensive_rules"]["source_sha256"],
            rules["source_sha256"],
        )
        self.assertEqual(
            semantics["program_entries"],
            semantics["unique_program_keys"] + semantics["duplicate_key_count"],
        )
        self.assertEqual(
            semantics["configured_card_specific_operations_not_observed"], []
        )
        self.assertEqual(
            documents["required_count"],
            documents["present_count"] + documents["missing_count"],
        )
        self.assertEqual(
            documents["metadata_complete_count"], documents["present_count"]
        )
        self.assertEqual(documents["required_count"], documents["present_count"])
        self.assertEqual(0, documents["missing_count"])
        self.assertTrue(documents["policy"]["metadata_enforced"])
        self.assertTrue(documents["policy"]["internal_links_enforced"])
        self.assertTrue(documents["policy"]["stale_claims_enforced"])
        self.assertTrue(documents["policy"]["adr_system_enforced"])
        self.assertTrue(
            self.report["architecture"]["printed_name_literals"][
                "no_unreviewed_growth"
            ]
        )
        self.assertEqual(
            self.report["architecture"]["printed_name_literals"][
                "baseline_entry_count"
            ],
            len(baseline["exact_printed_name_literals"]),
        )
        self.assertLessEqual(
            self.report["architecture"]["printed_name_literals"]["entry_count"],
            len(baseline["exact_printed_name_literals"]),
        )
        self.assertIsNotNone(self.report["architecture"]["debt_trend"])


if __name__ == "__main__":
    unittest.main()
