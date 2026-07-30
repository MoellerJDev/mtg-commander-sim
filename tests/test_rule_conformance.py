from __future__ import annotations

import unittest
from pathlib import Path

from mtg_commander_sim.rule_conformance import (
    build_rule_conformance,
    discover_unittest_ids,
    inventory_case_errors,
    rule_conformance_coverage,
    validate_rule_conformance,
)
from mtg_commander_sim.rules_corpus import parse_comprehensive_rules

from tests.test_rules_corpus import RULES_FIXTURE


class RuleConformanceTests(unittest.TestCase):
    def setUp(self) -> None:
        parsed = parse_comprehensive_rules(
            RULES_FIXTURE,
            source_sha256="a" * 64,
        )
        self.rule_index = {
            "effective_date": parsed["effective_date"],
            "source_sha256": "a" * 64,
            "rules": parsed["rules"],
        }

    def test_build_creates_one_honest_inventory_case_per_rule(self):
        corpus = build_rule_conformance(self.rule_index)
        self.assertEqual(11, corpus["case_count"])
        self.assertEqual(
            {rule["rule_id"] for rule in self.rule_index["rules"]},
            {case["rule_id"] for case in corpus["cases"]},
        )
        self.assertTrue(
            all(case["status"] == "unreviewed" for case in corpus["cases"])
        )
        self.assertTrue(
            all(
                case["assertion_kind"] == "inventory_only"
                for case in corpus["cases"]
            )
        )
        self.assertEqual(
            [],
            validate_rule_conformance(corpus, self.rule_index),
        )

    def test_same_rule_hash_preserves_review_but_changed_rule_invalidates_it(
        self,
    ) -> None:
        first = build_rule_conformance(self.rule_index)
        reviewed = first["cases"][1]
        reviewed.update(
            {
                "classification": "behavioral",
                "status": "passing",
                "assertion_kind": "executable_engine",
                "reviewed": True,
                "implementation_components": ["CommanderEngine"],
                "executable_test_ids": [
                    "tests.test_example.ExampleTests.test_rule"
                ],
                "required_scenarios": ["positive", "negative"],
                "covered_scenarios": ["positive", "negative"],
                "blockers": [],
            }
        )
        preserved = build_rule_conformance(
            self.rule_index,
            previous=first,
        )
        self.assertEqual("passing", preserved["cases"][1]["status"])

        changed_index = {
            **self.rule_index,
            "rules": [dict(rule) for rule in self.rule_index["rules"]],
        }
        changed_index["rules"][1]["text_sha256"] = "b" * 64
        invalidated = build_rule_conformance(
            changed_index,
            previous=first,
        )
        self.assertEqual("unreviewed", invalidated["cases"][1]["status"])
        self.assertEqual(
            ["semantic_review_not_completed"],
            invalidated["cases"][1]["blockers"],
        )

    def test_passing_case_requires_real_evidence_and_scenario_coverage(self):
        corpus = build_rule_conformance(self.rule_index)
        case = corpus["cases"][1]
        case.update(
            {
                "classification": "behavioral",
                "status": "passing",
                "assertion_kind": "inventory_only",
                "reviewed": True,
                "blockers": [],
            }
        )
        errors = validate_rule_conformance(corpus, self.rule_index)
        self.assertTrue(
            any(
                "without executable semantics" in error
                for error in errors
            ),
            errors,
        )
        self.assertTrue(
            any("lacks implementation, tests, or scenarios" in error
                for error in errors),
            errors,
        )

    def test_passing_case_cannot_reference_an_unknown_test(self):
        corpus = build_rule_conformance(self.rule_index)
        case = corpus["cases"][1]
        case.update(
            {
                "classification": "behavioral",
                "status": "passing",
                "assertion_kind": "executable_engine",
                "reviewed": True,
                "implementation_components": ["CommanderEngine"],
                "executable_test_ids": ["tests.missing.Case.test_rule"],
                "required_scenarios": ["positive"],
                "covered_scenarios": ["positive"],
                "blockers": [],
            }
        )
        errors = validate_rule_conformance(
            corpus,
            self.rule_index,
            known_test_ids=set(),
        )
        self.assertTrue(
            any("unknown executable tests" in error for error in errors),
            errors,
        )

    def test_blocked_case_requires_review_and_real_test_evidence(self):
        corpus = build_rule_conformance(self.rule_index)
        case = corpus["cases"][1]
        case.update(
            {
                "classification": "behavioral",
                "status": "blocked",
                "assertion_kind": "unsupported_fail_closed",
                "reviewed": False,
                "executable_test_ids": [
                    "tests.missing.Case.test_rule"
                ],
                "blockers": ["missing_generic_semantics"],
            }
        )
        errors = validate_rule_conformance(
            corpus,
            self.rule_index,
            known_test_ids=set(),
        )
        self.assertTrue(
            any("without completed review" in error for error in errors),
            errors,
        )
        self.assertTrue(
            any("unknown reviewed tests" in error for error in errors),
            errors,
        )

    def test_test_id_discovery_uses_fully_qualified_static_methods(self):
        discovered = discover_unittest_ids(
            Path(__file__).resolve().parents[1]
        )
        self.assertIn(
            (
                "tests.test_rule_conformance.RuleConformanceTests."
                "test_build_creates_one_honest_inventory_case_per_rule"
            ),
            discovered,
        )

    def test_coverage_never_counts_inventory_as_semantic_pass(self):
        corpus = build_rule_conformance(self.rule_index)
        coverage = rule_conformance_coverage(corpus)
        self.assertEqual(11, coverage["total_cases"])
        self.assertEqual(11, coverage["inventory_only_cases"])
        self.assertEqual(0, coverage["semantic_passing_cases"])
        self.assertEqual(11, coverage["unreviewed_cases"])
        self.assertFalse(coverage["current_snapshot_complete"])

    def test_inventory_assertion_is_scoped_to_one_pinned_rule(self):
        corpus = build_rule_conformance(self.rule_index)
        rule = self.rule_index["rules"][2]
        case = corpus["cases"][2]
        self.assertEqual(
            [],
            inventory_case_errors(
                case,
                rule,
                effective_date=self.rule_index["effective_date"],
                source_sha256=self.rule_index["source_sha256"],
            ),
        )
        stale = dict(case)
        stale["rule_text_sha256"] = "f" * 64
        self.assertEqual(
            ["rule_text_sha256 does not match the pinned rule"],
            list(
                inventory_case_errors(
                    stale,
                    rule,
                    effective_date=self.rule_index["effective_date"],
                    source_sha256=self.rule_index["source_sha256"],
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
