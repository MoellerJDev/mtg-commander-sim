from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from scripts.change_impact import (
    _symbols_for_ranges,
    changed_python_symbols,
    classify_changes,
    load_impact_policy,
)


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
        self.assertEqual(3, policy["schema_version"])
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

    def test_rules_paths_select_only_their_focused_browser_journey(self):
        cases = {
            "mtg_commander_sim/fixed_mana_abilities.py": ("mana-action",),
            "mtg_commander_sim/declaration_restrictions.py": ("combat",),
            "mtg_commander_sim/drawing/coordinator.py": ("turn-draw",),
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                plan = classify_changes([path])
                self.assertFalse(plan.browser_full)
                self.assertEqual(expected, plan.browser_focuses)

    def test_compiler_and_engine_only_changes_keep_compact_smoke_only(self):
        for path in (
            "mtg_commander_sim/compiler/damage_templates.py",
            "mtg_commander_sim/engine.py",
            "mtg_commander_sim/session.py",
        ):
            with self.subTest(path=path):
                plan = classify_changes([path])
                self.assertFalse(plan.browser_full)
                self.assertEqual((), plan.browser_focuses)

    def test_engine_priority_or_yield_symbols_require_complete_browser(self):
        for symbol in (
            "CommanderEngine._grant_priority",
            "CommanderEngine._set_yield",
            "CommanderEngine._record_action_opportunity",
        ):
            with self.subTest(symbol=symbol):
                plan = classify_changes(
                    ["mtg_commander_sim/engine.py"],
                    changed_symbols=(f"mtg_commander_sim/engine.py:{symbol}",),
                )
                self.assertTrue(plan.browser_full)
                self.assertIn(
                    "browser-facing-priority-and-yield",
                    plan.matched_rule_ids,
                )

    def test_changed_line_ranges_resolve_the_smallest_qualified_symbol(self):
        source = """\
class CommanderEngine:
    def _grant_priority(self):
        value = 1
        return value

    def unrelated(self):
        return 2
"""
        self.assertEqual(
            ("CommanderEngine._grant_priority",),
            _symbols_for_ranges(source, ((3, 3, ""),)),
        )

    def test_changed_symbol_discovery_includes_deleted_base_method(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(
                ["git", "config", "user.email", "tests@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Impact Tests"],
                cwd=root,
                check=True,
            )
            module = root / "mtg_commander_sim" / "engine.py"
            module.parent.mkdir()
            module.write_text(
                "class CommanderEngine:\n"
                "    def _grant_priority(self):\n"
                "        return True\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "base"],
                cwd=root,
                check=True,
            )
            base = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                text=True,
                encoding="ascii",
            ).strip()
            module.write_text(
                "class CommanderEngine:\n"
                "    def unrelated(self):\n"
                "        return False\n",
                encoding="utf-8",
            )

            symbols = changed_python_symbols(
                base,
                include_worktree=True,
                root=root,
            )

        self.assertIn(
            "mtg_commander_sim/engine.py:CommanderEngine._grant_priority",
            symbols,
        )

    def test_persistence_and_projection_still_require_complete_browser(self):
        for path in (
            "mtg_commander_sim/persistence.py",
            "mtg_commander_sim/projection.py",
        ):
            with self.subTest(path=path):
                self.assertTrue(classify_changes([path]).browser_full)

    def test_natural_winner_rules_owners_require_soak_group(self):
        for path in (
            "mtg_commander_sim/commander.py",
            "mtg_commander_sim/damage_results.py",
            "mtg_commander_sim/state_based_actions.py",
        ):
            with self.subTest(path=path):
                plan = classify_changes([path])
                self.assertTrue(plan.browser_full)
                self.assertIn(
                    "natural-winner-critical-path", plan.matched_rule_ids
                )

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

    def test_labels_can_select_focused_browser_journeys(self):
        plan = classify_changes(
            ["README.md"],
            labels=("browser-combat", "browser-turn-draw"),
        )
        self.assertFalse(plan.browser_full)
        self.assertEqual(("combat", "turn-draw"), plan.browser_focuses)
        self.assertEqual(("@combat", "@turn-draw"), plan.browser_focus_patterns)


if __name__ == "__main__":
    unittest.main()
