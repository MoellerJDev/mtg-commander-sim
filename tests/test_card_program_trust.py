from __future__ import annotations

import copy
import unittest

from common import DB_PATH
from mtg_commander_sim.card_programs import (
    bind_card_program_runtime,
    bind_semantic_program_runtime,
    compute_match_trust_closure,
)
from mtg_commander_sim.card_programs.adapters import compile_card_program
from mtg_commander_sim.card_programs.commands import runtime_component_status
from mtg_commander_sim.carddb import CardDatabase, CardRecord
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantics import SemanticRegistry


def _bolt() -> CardRecord:
    return CardRecord(
        oracle_id="00000000-0000-4000-8000-00000000b017",
        name="Lightning Bolt",
        mana_cost="{R}",
        mana_value=1.0,
        type_line="Instant",
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        power=None,
        toughness=None,
        loyalty=None,
        defense=None,
        colors=("R",),
        color_identity=("R",),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="1993-08-05",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class CardProgramTrustTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.capabilities = load_default_capability_registry()
        cls.bolt = compile_card_program(
            cls.db,
            _bolt(),
            capability_registry=cls.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_generated_program_exposes_capability_closed_intrinsic_basis(self):
        trust = self.bolt.trust_closure
        self.assertEqual("capability_closed", trust["trust_basis"])
        self.assertTrue(trust["strict_capability_ready"])
        self.assertTrue(trust["closure_layers"]["intrinsic"]["trusted"])
        self.assertEqual(
            "unbound", trust["closure_layers"]["match"]["status"]
        )
        self.assertTrue(trust["evidence_fingerprints"])
        binding = bind_card_program_runtime(
            self.bolt,
            capability_registry=self.capabilities,
            profile="commander_duel",
        )
        self.assertTrue(binding["strict_capability_ready"])
        self.assertFalse(binding["blockers"])

    def test_reviewed_pack_is_compatibility_not_capability_closed(self):
        program = SemanticRegistry().card_program_for_oracle(
            "9070c98b-fd01-4eeb-a4ec-fc464946c7c0"
        )
        self.assertIsNotNone(program)
        trust = program.trust_closure
        self.assertEqual("legacy_reviewed", trust["trust_basis"])
        self.assertTrue(trust["trusted"])
        self.assertFalse(trust["strict_capability_ready"])
        self.assertTrue(trust["compatibility_provenance"])
        self.assertTrue(
            all(
                row["removal_condition"]
                for row in trust["compatibility_provenance"]
            )
        )
        binding = bind_card_program_runtime(
            program,
            capability_registry=self.capabilities,
            profile="commander_review",
        )
        self.assertFalse(binding["strict_capability_ready"])
        self.assertTrue(binding["compatible_ready"])
        self.assertTrue(
            any(
                "legacy_runtime_dependencies_unbound" in blocker
                for blocker in binding["blockers"]
            )
        )

    def test_match_closure_is_conservative_and_dynamic_fail_closed(self):
        match = compute_match_trust_closure(
            [self.bolt],
            registry=self.capabilities,
            profile="commander_duel",
        )
        self.assertFalse(match["strict_capability_ready"])
        self.assertTrue(match["compatible_ready"])
        self.assertIn(
            "format_profile:capability_inventory_incomplete:commander_duel",
            match["blockers"],
        )
        self.assertNotIn(
            "damage.result.infect",
            match["match_closure"]["reachable"],
        )
        blocked = compute_match_trust_closure(
            [self.bolt],
            registry=self.capabilities,
            profile="commander_duel",
            dynamic_capabilities=["damage.combat.excess"],
        )
        self.assertFalse(blocked["strict_capability_ready"])
        self.assertTrue(
            any(
                "damage.combat.excess" in blocker
                for blocker in blocked["blockers"]
            )
        )

    def test_global_handler_and_component_inventory_is_capability_bound(self):
        status = runtime_component_status("commander_review")
        self.assertEqual(83, len(status["semantic_handlers"]))
        self.assertEqual(10, len(status["runtime_components"]))
        self.assertEqual(
            {
                "continuous.fixed_power_toughness_anthem",
                "continuous.basic_land_type.add_all_lands",
                "prevention.damage.fixed",
                "replacement.counter.quantity",
                "replacement.damage.quantity",
                "replacement.damage.redirection.static",
                "replacement.damage.result.life_floor",
                "replacement.fixed_additional_token",
                "replacement.life.gain.multiplier",
                "replacement.zone.destination",
            },
            {row["family"] for row in status["runtime_components"]},
        )
        self.assertFalse(status["strict_capability_ready"])
        self.assertTrue(
            all(
                row["capability_closure"]["registry_fingerprint"]
                == status["capability_registry_fingerprint"]
                for row in [
                    *status["semantic_handlers"],
                    *status["runtime_components"],
                ]
            )
        )

    def test_runtime_binding_fails_closed_on_stale_closure(self):
        ability = copy.deepcopy(self.bolt.abilities[0])
        ability.capability_closure["fingerprint"] = "0" * 64
        binding = bind_semantic_program_runtime(
            ability,
            capability_registry=self.capabilities,
            profile="commander_duel",
        )
        self.assertIn(
            "capability:closure_binding_mismatch",
            binding["blockers"],
        )
        self.assertFalse(binding["strict"])
        self.assertEqual(
            self.capabilities.evidence_fingerprint,
            binding["capability_evidence_fingerprint"],
        )

    def test_registered_handler_dependency_cannot_hide_in_legacy_program(self):
        program = next(
            value
            for value in SemanticRegistry().programs()
            if any(effect.get("op") == "draw" for effect in value.effects)
        )
        binding = bind_semantic_program_runtime(
            program,
            capability_registry=self.capabilities,
            profile="commander_review",
        )
        self.assertIn(
            "capability:undeclared_runtime_dependency:zone.draw.library_to_hand",
            binding["blockers"],
        )
        self.assertIn(
            "capability:legacy_runtime_dependencies_unbound",
            binding["blockers"],
        )


if __name__ == "__main__":
    unittest.main()
