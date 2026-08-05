from __future__ import annotations

import unittest

from scripts.quick_gate import build_plan


class QuickGatePlanTests(unittest.TestCase):
    def test_changed_test_and_subsystem_are_deduplicated(self):
        plan = build_plan(
            (
                "mtg_commander_sim/life_change.py",
                "tests/test_life_change.py",
            )
        )
        self.assertEqual(1, plan["test_modules"].count("test_life_change"))
        names = [step.name for step in plan["steps"]]
        self.assertIn("affected-tests", names)
        self.assertIn("architecture", names)

    def test_docs_only_plan_skips_database_and_tests(self):
        plan = build_plan(("README.md",))
        names = [step.name for step in plan["steps"]]
        self.assertNotIn("build-test-database", names)
        self.assertNotIn("affected-tests", names)
        self.assertIn("documentation", names)

    def test_browser_plan_builds_without_running_e2e(self):
        plan = build_plan(("web/src/App.tsx",))
        names = [step.name for step in plan["steps"]]
        self.assertIn("browser-build", names)
        self.assertFalse(any("e2e" in name for name in names))

    def test_compiler_plan_checks_card_unlock_frontier(self):
        plan = build_plan(("mtg_commander_sim/compiler/oracle_parser.py",))
        names = [step.name for step in plan["steps"]]
        self.assertIn("card-unlock-frontier", names)
        self.assertIn("reusable-pieces", names)

    def test_reusable_piece_change_checks_inventory(self):
        plan = build_plan(("mtg_commander_sim/reusable_pieces/generation.py",))
        names = [step.name for step in plan["steps"]]
        self.assertIn("reusable-pieces", names)


if __name__ == "__main__":
    unittest.main()
