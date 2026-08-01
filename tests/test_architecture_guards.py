from __future__ import annotations

import ast
import json
from types import SimpleNamespace
import unittest

from scripts.architecture_support import (
    decode_card_name_hash_index,
    printed_name_digest,
)
from scripts.update_architecture_audit import ROOT
from scripts.validate_architecture import (
    _counter_extras,
    _game_state_imports,
    evaluate_architecture,
    forbidden_import_violations,
    mutation_ownership_violations,
    printed_name_literal_identities,
)


class ArchitectureGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(
            (ROOT / "platform" / "architecture-policy.json").read_text(
                encoding="utf-8"
            )
        )
        cls.card_index_path = ROOT / cls.policy["card_name_hash_index"]
        cls.card_index = decode_card_name_hash_index(
            json.loads(cls.card_index_path.read_text(encoding="utf-8"))
        )

    def test_current_repository_passes_every_architecture_guard(self):
        result = evaluate_architecture()
        self.assertEqual(result["status"], "pass", result["failures"])
        self.assertEqual(result["failures"], [])

    def test_forbidden_rules_import_is_rejected(self):
        protected = self.policy["protected_rules_modules"][0]
        analyses = {protected: SimpleNamespace(imports=("fastapi",))}
        self.assertEqual(
            forbidden_import_violations(analyses, self.policy),
            [{"file": protected, "import": "fastapi"}],
        )

    def test_game_state_access_and_nonowner_mutation_are_rejected(self):
        tree = ast.parse("from mtg_commander_sim.model import GameState\n")
        self.assertTrue(_game_state_imports(tree))
        location = {
            "file": "mtg_commander_sim/rules/zones.py",
            "symbol": "move",
            "line": 10,
        }
        self.assertEqual(
            mutation_ownership_violations(
                [location], self.policy["game_state_access"]["mutable_owners"]
            ),
            [location],
        )

    def test_card_name_index_contains_no_plaintext_and_detects_new_literal(self):
        raw = self.card_index_path.read_text(encoding="utf-8")
        self.assertNotIn("Black Lotus", raw)
        self.assertIn(printed_name_digest("Black Lotus"), self.card_index)
        relative = self.policy["specificity_scope"][0]
        literal = {
            "file": relative,
            "symbol": "bad_branch",
            "value": "Black Lotus",
            "in_condition": True,
        }
        identities = printed_name_literal_identities(
            {relative: SimpleNamespace(string_literals=(literal,))},
            [relative],
            self.card_index,
        )
        self.assertEqual(
            _counter_extras(identities, []),
            [(relative, "bad_branch", "Black Lotus", True)],
        )


if __name__ == "__main__":
    unittest.main()
