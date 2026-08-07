from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path
import unittest

from common import DB_PATH
from quorune.carddb import CardDatabase
from quorune.compiler.unlock_frontier import (
    BASE_RESIDUAL_FAMILIES,
    build_card_unlock_frontier,
    canonical_residual_families,
    render_card_unlock_frontier_markdown,
    validate_card_unlock_frontier,
)
from quorune.mechanic_contracts import load_mechanic_contracts
from quorune.rules.capabilities import (
    load_default_capability_registry,
)
from quorune.semantics import SemanticRegistry
from scripts.update_card_unlock_frontier import _canonical_gzip


ROOT = Path(__file__).resolve().parents[1]


def _contracts() -> list[dict]:
    manifest = json.loads(
        (ROOT / "rules" / "manifest.json").read_text(encoding="utf-8")
    )
    rules = json.loads(
        (ROOT / "rules" / "rule-index.json").read_text(encoding="utf-8")
    )
    return load_mechanic_contracts(
        ROOT,
        expected_effective_date=manifest["effective_date"],
        expected_source_sha256=manifest["source_sha256"],
        known_rule_ids={row["rule_id"] for row in rules["rules"]},
    )


class CardUnlockFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.capabilities = load_default_capability_registry()
        cls.report = build_card_unlock_frontier(
            cls.db,
            registry=SemanticRegistry(),
            capabilities=cls.capabilities,
            mechanic_contracts=_contracts(),
            limit=20,
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_residual_classifier_uses_dependency_sized_canonical_families(self):
        keyword = canonical_residual_families(
            {
                "kind": "dependency_contract",
                "reason": "recognized keyword lacks a trusted contract",
                "blockers": ["mechanic:flying"],
            }
        )
        capability = canonical_residual_families(
            {
                "kind": "dependency_contract",
                "reason": "capability closure failed",
                "blockers": [
                    "capability:status:damage.result.toxic:implemented"
                ],
            }
        )
        trigger = canonical_residual_families(
            {
                "kind": "trigger",
                "reason": "trigger condition/event binding is not exact",
                "blockers": ["normalized event binding"],
            }
        )

        self.assertEqual(("keyword_dependency:flying",), keyword)
        self.assertEqual(
            ("capability_dependency:damage.result.toxic",), capability
        )
        self.assertEqual(
            ("event_binding:normalized-event-binding",), trigger
        )

        compound = canonical_residual_families(
            {
                "kind": "spell_effect",
                "reason": "spell effect has no exact generic template",
                "blockers": [],
                "text": (
                    "Destroy target creature with power 4 or greater. "
                    "Its controller creates a 3/3 green Beast creature token."
                ),
            }
        )
        self.assertEqual(
            (
                "effect_clause:create-token",
                "effect_clause:destroy-target",
                "reference_binding:linked-result-reference",
                "target_or_choice:target-predicate",
            ),
            compound,
        )

    def test_limited_frontier_accounts_for_every_card_and_material_ability(self):
        report = self.report
        validate_card_unlock_frontier(report)

        self.assertEqual(20, report["cards_considered"])
        self.assertEqual(20, len(report["cards"]))
        self.assertEqual(
            sorted(BASE_RESIDUAL_FAMILIES),
            report["base_residual_families"],
        )
        self.assertFalse(report["complete_snapshot_claimed"])
        self.assertEqual(
            {
                "blockers": {},
                "lowerable": False,
                "residuals": [],
                "template_id": None,
            },
            report["ability_field_defaults"],
        )
        for card in report["cards"]:
            self.assertEqual(
                sorted(card["minimum_known_blocker_set"]),
                card["minimum_known_blocker_set"],
            )
            for ability in card["abilities"]:
                self.assertIn(
                    ability["status"],
                    {"exact", "lowerable_untrusted", "unresolved"},
                )
                blockers = ability.get("blockers", {})
                self.assertEqual(
                    blockers.get("canonical_family_ids", []),
                    sorted(blockers.get("canonical_family_ids", [])),
                )
                self.assertNotIn("exact", ability)
                self.assertNotIn("source_text_sha256", ability)
                self.assertNotEqual(False, ability.get("lowerable"))
                if "template_id" in ability:
                    self.assertIsNotNone(ability["template_id"])

    def test_frontier_fingerprint_and_markdown_fail_closed(self):
        markdown = render_card_unlock_frontier_markdown(self.report)
        self.assertIn("not a claim of complete", markdown)
        self.assertIn("Highest-leverage bounded bundles", markdown)

        tampered = deepcopy(self.report)
        tampered["cards"][0]["card_name"] = "Tampered"
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            validate_card_unlock_frontier(tampered)

        malformed = deepcopy(self.report)
        malformed["cards"][0]["abilities"][0]["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "ability fields"):
            validate_card_unlock_frontier(malformed)

        malformed = deepcopy(self.report)
        malformed["cards"][0]["minimum_known_blocker_set"] = [
            "effect_clause:not-a-real-observed-blocker"
        ]
        with self.assertRaisesRegex(ValueError, "minimum blocker"):
            validate_card_unlock_frontier(malformed)

    def test_bundle_evaluation_is_bounded_and_optimizes_full_cards(self):
        evaluation = self.report["bundle_evaluation"]
        self.assertEqual(3, evaluation["maximum_size"])
        self.assertGreater(evaluation["evaluated_bundle_count"], 0)
        gains = [
            row["expected_exact_card_gain"]
            for row in evaluation["top_bundles"]
        ]
        self.assertEqual(sorted(gains, reverse=True), gains)

    def test_tracked_gzip_is_deterministic_and_round_trips(self):
        payload = b'{"frontier":"complete machine-readable rows"}\n'
        encoded = _canonical_gzip(payload)

        self.assertEqual(encoded, _canonical_gzip(payload))
        self.assertEqual(b"\x00\x00\x00\x00", encoded[4:8])
        self.assertEqual(payload, gzip.decompress(encoded))


if __name__ == "__main__":
    unittest.main()
