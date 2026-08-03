from __future__ import annotations

import unittest

from scripts.change_impact import classify_changes


class ChangeImpactTests(unittest.TestCase):
    def test_rules_compiler_change_selects_compiler_and_evidence(self):
        plan = classify_changes(
            ["mtg_commander_sim/compiler/prevention_templates.py"]
        )
        self.assertIn("compiler-cardprogram", plan.test_suites)
        self.assertIn("capability-evidence", plan.checks)
        self.assertFalse(plan.browser_full)

    def test_changed_test_module_is_run_exactly(self):
        plan = classify_changes(["tests/test_life_change.py"])
        self.assertEqual(("test_life_change",), plan.test_modules)

    def test_browser_protocol_change_requests_full_browser_gate(self):
        plan = classify_changes(["web/src/protocol.ts"])
        self.assertTrue(plan.browser_full)
        self.assertIn("browser-build", plan.checks)
        self.assertIn("server-replay-privacy", plan.test_suites)

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
