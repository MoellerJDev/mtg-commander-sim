from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from mtg_commander_sim import CardDatabase
from scripts.build_test_database import build_fixture_database
from scripts.local_merge_gate import (
    DEFAULT_FOCUSED_TESTS,
    PRIVACY_TESTS,
    build_steps,
    gate_environment,
)


class LocalMergeGateTests(unittest.TestCase):
    def test_compact_card_fixtures_compose_without_external_data(self):
        root = Path(__file__).resolve().parents[1]
        fixtures = [
            root / "tests" / "fixtures" / "scryfall-exact-lists.json",
            root / "tests" / "fixtures" / "browser-lifecycle-cards.json",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "test-ci.sqlite3"
            result = build_fixture_database(fixtures, database)
            with CardDatabase(database) as card_db:
                self.assertEqual("Zimone and Dina", card_db.lookup("Zimone and Dina").name)
                self.assertEqual(
                    "Yargle and Multani",
                    card_db.lookup("Yargle and Multani").name,
                )

        self.assertEqual([str(fixture) for fixture in fixtures], result["fixtures"])
        primary = json.loads(fixtures[0].read_text(encoding="utf-8"))
        self.assertEqual(len(primary["rulings"]), result["rulings"])

    def test_gate_orchestrates_every_required_existing_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            steps = build_steps(
                "python-under-test",
                database=output / "test-ci.sqlite3",
                output=output,
                focused_tests=DEFAULT_FOCUSED_TESTS,
            )

        by_name = {step.name: step.command for step in steps}
        self.assertEqual(
            {
                "generated_platform_freshness",
                "compile",
                "build_test_database",
                "full_deterministic_suite",
                "rules_corpus_verify",
                "architecture_policy",
                "focused_regressions",
                "four_player_natural_winner",
                "projection_and_privacy",
                "protocol_demo",
                "dependency_check",
                "repository_security_validation",
                "wheel_build",
                "wheel_clean_install",
                "browser_dependencies",
                "generated_protocol_types",
                "generated_protocol_freshness",
                "browser_production_build",
                "browser_four_context_e2e",
            },
            set(by_name),
        )
        self.assertIn("discover", by_name["full_deterministic_suite"])
        self.assertIn(
            "tests/fixtures/scryfall-exact-lists.json",
            by_name["build_test_database"],
        )
        self.assertIn(
            "tests/fixtures/browser-lifecycle-cards.json",
            by_name["build_test_database"],
        )
        self.assertIn(
            "tests.test_seed_20260730_regression",
            by_name["focused_regressions"],
        )
        self.assertIn(
            "tests.test_command_zone_rules",
            by_name["focused_regressions"],
        )
        self.assertIn(
            "tests.test_deterministic_full_game",
            by_name["four_player_natural_winner"],
        )
        for test_module in PRIVACY_TESTS:
            self.assertIn(
                test_module,
                by_name["projection_and_privacy"],
            )
        self.assertEqual(
            (
                "python-under-test",
                "scripts/validate_architecture.py",
                "--check",
            ),
            by_name["architecture_policy"],
        )
        self.assertEqual(
            (
                "python-under-test",
                "scripts/validate_repository.py",
            ),
            by_name["repository_security_validation"],
        )
        self.assertEqual(
            (
                "python-under-test",
                "scripts/update_platform_status.py",
                "--check",
            ),
            by_name["generated_platform_freshness"],
        )
        self.assertEqual(
            ("npm", "run", "e2e", "--prefix", "web"),
            by_name["browser_four_context_e2e"],
        )

    def test_additional_focused_tests_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            steps = build_steps(
                "python-under-test",
                database=output / "test-ci.sqlite3",
                output=output,
                focused_tests=(
                    *DEFAULT_FOCUSED_TESTS,
                    "tests.test_stack_rules",
                ),
            )

        focused = next(
            step.command
            for step in steps
            if step.name == "focused_regressions"
        )
        self.assertEqual(
            "tests.test_stack_rules",
            focused[-1],
        )

    def test_gate_environment_supports_discovery_style_common_imports(self):
        with tempfile.TemporaryDirectory() as temporary:
            database = Path(temporary) / "test-ci.sqlite3"
            environment = gate_environment(database)

        self.assertEqual(
            str(database),
            environment["MTG_CARD_DB"],
        )
        self.assertIn(
            str(Path(__file__).resolve().parent),
            environment["PYTHONPATH"].split(os.pathsep),
        )


if __name__ == "__main__":
    unittest.main()
