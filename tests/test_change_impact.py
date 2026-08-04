from __future__ import annotations

import unittest

from scripts.change_impact import classify_changes, load_impact_policy


class ChangeImpactTests(unittest.TestCase):
    def test_rules_compiler_change_selects_compiler_and_evidence(self):
        plan = classify_changes(
            ["mtg_commander_sim/compiler/prevention_templates.py"]
        )
        self.assertIn("compiler-cardprogram", plan.test_suites)
        self.assertIn("capability-evidence", plan.checks)
        self.assertIn("card-unlock-frontier", plan.checks)
        self.assertFalse(plan.browser_full)

    def test_policy_is_versioned_and_fingerprinted(self):
        policy, fingerprint = load_impact_policy()
        self.assertEqual(1, policy["schema_version"])
        self.assertEqual(64, len(fingerprint))

    def test_changed_test_module_is_run_exactly(self):
        plan = classify_changes(["tests/test_life_change.py"])
        self.assertEqual(("test_life_change",), plan.test_modules)

    def test_browser_protocol_change_requests_full_browser_gate(self):
        plan = classify_changes(["web/src/protocol.ts"])
        self.assertTrue(plan.browser_full)
        self.assertIn("browser-build", plan.checks)
        self.assertIn("server-replay-privacy", plan.test_suites)

    def test_internal_action_and_choice_modules_do_not_force_browser(self):
        for path in (
            "mtg_commander_sim/rules/action_proposals.py",
            "mtg_commander_sim/semantic_choices/optional_draw.py",
        ):
            with self.subTest(path=path):
                plan = classify_changes([path])
                self.assertFalse(plan.browser_full)

    def test_protection_changes_cover_each_interaction_owner(self):
        plan = classify_changes(["mtg_commander_sim/protection.py"])

        self.assertEqual(
            {
                "compiler-cardprogram",
                "rules-events-replacements",
                "state-actions-damage",
                "targets-choices-continuations",
            },
            set(plan.test_suites),
        )
        self.assertIn(
            "protection-and-attachment-interactions",
            plan.matched_rule_ids,
        )
        self.assertFalse(plan.browser_full)

    def test_browser_action_and_choice_contracts_are_explicit(self):
        for path in (
            "mtg_commander_sim/rules/action_catalog.py",
            "mtg_commander_sim/choice_forms.py",
            "mtg_commander_sim/projection.py",
        ):
            with self.subTest(path=path):
                plan = classify_changes([path])
                self.assertTrue(plan.browser_full)
                self.assertTrue(plan.browser_full_reasons)

    def test_windows_sensitive_change_requests_full_windows_gate(self):
        plan = classify_changes(["server/launcher.py"])
        self.assertTrue(plan.windows_full)

    def test_workflow_change_exercises_both_platform_gates(self):
        plan = classify_changes([".github/workflows/ci.yml"])
        self.assertTrue(plan.browser_full)
        self.assertTrue(plan.windows_full)
        self.assertIn("generated-validation", plan.test_suites)

    def test_unknown_core_module_falls_back_to_core_domain(self):
        plan = classify_changes(["mtg_commander_sim/example_future.py"])
        self.assertEqual(("core-domain",), plan.test_suites)

    def test_labels_can_force_expensive_platform_gates(self):
        plan = classify_changes(
            ["README.md"], labels=("browser-full", "windows-full")
        )
        self.assertTrue(plan.browser_full)
        self.assertTrue(plan.windows_full)


if __name__ == "__main__":
    unittest.main()
