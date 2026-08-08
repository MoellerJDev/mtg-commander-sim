from __future__ import annotations

import json
from pathlib import Path
import unittest

from common import DB_PATH, keep_all, load_assets, make_session
from quorune.carddb import CardDatabase, CardRecord
from quorune.oracle_ir import (
    compile_oracle_card,
    generated_programs,
)
from quorune.rules.capabilities import (
    CapabilityRegistry,
    load_default_capability_registry,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "quorune" / "rules" / "capability-registry.json"


def fabricate_record(text: str, suffix: int = 1) -> CardRecord:
    return CardRecord(
        oracle_id=f"00000000-0000-4000-8000-{suffix:012d}",
        name="Generic Fabricate Fixture",
        mana_cost="{2}",
        mana_value=2.0,
        type_line="Artifact Creature — Artificer",
        oracle_text=text,
        power="2",
        toughness="2",
        loyalty=None,
        defense=None,
        colors=(),
        color_identity=(),
        keywords=("Fabricate",),
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class FabricateCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_fabricate_keyword_lowers_to_source_spanned_capability_closed_trigger(
        self,
    ):
        text = "Flying, fabricate 2"
        record = fabricate_record(text)
        ir = compile_oracle_card(
            record,
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )
        nodes = [node for face in ir.faces for node in face.nodes]
        fabricate = next(
            node
            for node in nodes
            if node.template_id == "fabricate-enter-choice-v1"
        )

        self.assertEqual("exact", ir.status)
        self.assertTrue(fabricate.exact)
        self.assertEqual("permanent.enter.self", fabricate.event)
        self.assertEqual(({"op": "fabricate", "amount": 2},), fabricate.effects)
        self.assertEqual(("counter.producer.fabricate",), fabricate.capability_dependencies)
        self.assertEqual(text, record.oracle_text[fabricate.span.start : fabricate.span.end])
        self.assertEqual(
            {"flying", "fabricate"},
            {node.mechanics[0] for node in nodes},
        )

        programs = generated_programs(
            self.db,
            record,
            trust_level="trusted",
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )
        program = next(
            value
            for value in programs
            if value.provenance.get("template_id") == "fabricate-enter-choice-v1"
        )
        self.assertEqual("trusted", program.trust_level)
        self.assertTrue(program.capability_closure["trusted"])
        self.assertEqual(
            {"line": 1, "start": 0, "end": len(text)},
            program.provenance["source_span"],
        )

    def test_unsupported_fabricate_values_remain_material_residuals(self):
        for suffix, text in enumerate(
            (
                "Fabricate X",
                "Fabricate 0",
                "Fabricate -1",
                "Fabricate one",
                "Fabricate 1, fabricate 2",
            ),
            start=10,
        ):
            with self.subTest(text=text):
                ir = compile_oracle_card(
                    fabricate_record(text, suffix),
                    capability_registry=self.capabilities,
                    capability_profile="commander_review",
                )
                self.assertNotEqual("exact", ir.status)
                self.assertTrue(ir.material_residuals)
                self.assertTrue(
                    any(
                        "fabricate-unsupported-wording" in blocker
                        for residual in ir.material_residuals
                        for blocker in residual.blockers
                    )
                )

    def test_fabricate_dependency_mutation_fails_closed(self):
        value = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        dependency = next(
            row
            for row in value["capabilities"]
            if row["id"] == "counter.placement.quantity_replacement"
        )
        dependency["status"] = "blocked"
        dependency["blockers"] = ["test mutation"]
        mutated = CapabilityRegistry(value)
        ir = compile_oracle_card(
            fabricate_record("Fabricate 2", 20),
            capability_registry=mutated,
            capability_profile="commander_review",
        )

        self.assertNotEqual("exact", ir.status)
        self.assertTrue(
            any(
                "counter.placement.quantity_replacement" in blocker
                for residual in ir.material_residuals
                for blocker in residual.blockers
            )
        )


class GeneratedFabricateRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, *, players: int, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        apprentice = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Marionette Apprentice"
        )
        record = self.db.lookup("Marionette Apprentice")
        for program in tuple(engine.semantics.programs_for_oracle(record.oracle_id)):
            if program.event == "permanent.enter.self":
                engine.semantics.remove(program.key)
        generated = next(
            program
            for program in generated_programs(
                self.db,
                record,
                trust_level="trusted",
                capability_registry=self.capabilities,
                capability_profile="commander_review",
            )
            if program.provenance.get("template_id")
            == "fabricate-enter-choice-v1"
        )
        engine.semantics.put(generated)
        return session, apprentice, generated

    @staticmethod
    def resolve_top(engine):
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()

    def test_generated_fabricate_program_drives_counter_choice_without_name_dispatch(
        self,
    ):
        session, apprentice, program = self.session(players=2, seed=70212301)
        engine = session.engine
        engine.move_card(
            apprentice.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(program.key, engine.state.stack[-1].semantic_key)
        self.resolve_top(engine)
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choice": "counter",
                "plan": "DEVELOP_BOARD",
                "reason": "Choose the generated Fabricate counter result.",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual(1, apprentice.counters["+1/+1"])
        self.assertEqual("oracle-ir-v52", program.provenance["authored_by"])

    def test_four_player_fabricate_choice_uses_one_persistent_affected_seat(self):
        session, apprentice, _program = self.session(players=4, seed=70212302)
        engine = session.engine
        engine.move_card(
            apprentice.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)

        self.assertEqual(["pilot:A"], session.pending_principals())
        self.assertEqual("semantic.choice", engine.state.pending_decision.kind)
        from quorune.projection import StateProjector

        projector = StateProjector(self.db, engine.state)
        self.assertIsNotNone(projector._decision("pilot:A"))
        for seat in ("B", "C", "D"):
            self.assertIsNone(projector._decision(f"pilot:{seat}"))


if __name__ == "__main__":
    unittest.main()
