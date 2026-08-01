from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantic_runtime import (
    AdditionalTokenReplacementHandler,
    SemanticNodeError,
    TokenCreationReplacementContext,
    default_token_creation_replacement_registry,
)
from mtg_commander_sim.semantics import SemanticProgram, SemanticRegistry


def additional_token_descriptor(
    *, name: str = "Map", created_type: str = "artifact"
) -> dict:
    return {
        "handler_id": "replacement.token.additional.v1",
        "schema_version": 1,
        "event": "token.create",
        "condition": {
            "event_controller": "source_controller",
            "created_types_all": [created_type],
        },
        "quantity": 1,
        "token": {
            "name": name,
            "type_line": f"Token Artifact — {name}",
        },
    }


class TokenCreationReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def card(engine, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == name
        )

    def test_registered_additional_token_components_replace_without_name_dispatch(
        self,
    ):
        session = self.session(1250501)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        automaton.printed_name = "Renamed replacement source"

        created = engine.create_token(
            "A",
            name="Treasure",
            characteristics={"type_line": "Token Artifact — Treasure"},
            reason="typed replacement characterization",
        )

        self.assertEqual(
            {"Treasure", "Thopter"},
            {engine._resolve_object("A", ref).printed_name for ref in created},
        )
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "token.create"
        )
        self.assertEqual(
            [
                {
                    "handler_id": "replacement.token.additional.v1",
                    "source": automaton.ref,
                    "quantity": 1,
                }
            ],
            event.details["replacement_components"],
        )
        self.assertEqual(
            "token.creation.additional_replacement",
            default_token_creation_replacement_registry().inventory()[0][
                "capability_dependencies"
            ][0],
        )

    def test_additional_token_component_rejects_malformed_or_nonmatching_events(
        self,
    ):
        handler = AdditionalTokenReplacementHandler()
        malformed = additional_token_descriptor()
        malformed["quantity"] = 0
        with self.assertRaisesRegex(SemanticNodeError, "quantity"):
            handler.validate(malformed)

        descriptor = additional_token_descriptor()
        creature_context = TokenCreationReplacementContext(
            source_ref="P1",
            source_controller="A",
            event_controller="A",
            created_types=("creature",),
        )
        opponent_context = TokenCreationReplacementContext(
            source_ref="P1",
            source_controller="A",
            event_controller="B",
            created_types=("artifact",),
        )
        self.assertEqual((), handler.lower(descriptor, creature_context))
        self.assertEqual((), handler.lower(descriptor, opponent_context))
        with self.assertRaisesRegex(SemanticNodeError, "Unknown runtime handler"):
            SemanticProgram(
                key="test:unknown-runtime-handler",
                label="Unknown runtime handler",
                handlers=[
                    {
                        **descriptor,
                        "handler_id": "replacement.token.unknown.v1",
                    }
                ],
            )

    def test_multiple_additional_token_components_share_one_creation_timestamp(
        self,
    ):
        session = self.session(1250502)
        engine = session.engine
        for name in ("Stridehangar Automaton", "Worldwalker Helm"):
            source = self.card(engine, name)
            engine.move_card(source.object_id, "battlefield", controller="A")

        created = engine.create_token(
            "A",
            name="Treasure",
            quantity=2,
            characteristics={"type_line": "Token Artifact — Treasure"},
            reason="simultaneous replacement characterization",
        )
        cards = [engine._resolve_object("A", ref) for ref in created]

        self.assertEqual(4, len(cards))
        self.assertEqual(
            {"Treasure": 2, "Thopter": 1, "Map": 1},
            {
                name: sum(card.printed_name == name for card in cards)
                for name in ("Treasure", "Thopter", "Map")
            },
        )
        self.assertEqual(1, len({card.zone_timestamp for card in cards}))

    def test_source_created_by_event_does_not_replace_its_own_creation(self):
        session = self.session(1250505)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")

        created = engine.create_token(
            "A",
            name="Stridehangar Automaton",
            copy_of=automaton.ref,
            reason="replacement source timing characterization",
        )

        self.assertEqual(2, len(created))
        self.assertEqual(
            {"Stridehangar Automaton": 1, "Thopter": 1},
            {
                name: sum(
                    engine._resolve_object("A", ref).printed_name == name
                    for ref in created
                )
                for name in ("Stridehangar Automaton", "Thopter")
            },
        )

    def test_additional_token_component_replays_exactly(self):
        session = self.session(1250503)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        program = SemanticProgram(
            key="test:artifact-token-effect",
            label="Create an artifact token",
            effects=[
                {
                    "op": "create_token",
                    "controller": "A",
                    "name": "Treasure",
                    "characteristics": {
                        "type_line": "Token Artifact — Treasure"
                    },
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="artifact-token-effect",
                ref="S-artifact-token-effect",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in ("pilot:A", "pilot:B"):
            result = session.act(principal, {"action_id": "pass"})
            self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            {"Treasure", "Thopter"},
            {
                card.printed_name
                for card in engine.state.cards.values()
                if card.is_token and card.zone == "battlefield"
            },
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "additional-token-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])

    def test_complete_legacy_registry_uses_pinned_compatibility_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            semantics_path = Path(temporary) / "semantics.json"
            semantics_path.write_text(
                json.dumps(
                    {
                        "schema_version": 3,
                        "include_builtin_packs": False,
                        "programs": {},
                    }
                ),
                encoding="utf-8",
            )
            registry = SemanticRegistry(semantics_path)

        oracle_id = "9070c98b-fd01-4eeb-a4ec-fc464946c7c0"
        self.assertEqual([], registry.programs_for_oracle(oracle_id))
        programs = registry.runtime_handler_programs_for_oracle(
            oracle_id,
            active_zone="battlefield",
            event="token.create",
        )
        self.assertEqual(
            [f"{oracle_id}:replacement:additional-thopter"],
            [program.key for program in programs],
        )
        self.assertTrue(
            registry.is_runtime_handler_compatibility_program(programs[0])
        )

        session = self.session(1250504)
        session.engine.semantics = registry
        session.engine._semantic_trust_cache.clear()
        automaton = self.card(session.engine, "Stridehangar Automaton")
        session.engine.move_card(
            automaton.object_id, "battlefield", controller="A"
        )
        created = session.engine.create_token(
            "A",
            name="Treasure",
            characteristics={"type_line": "Token Artifact — Treasure"},
            reason="legacy compatibility characterization",
        )
        self.assertEqual(
            {"Treasure", "Thopter"},
            {
                session.engine._resolve_object("A", ref).printed_name
                for ref in created
            },
        )


if __name__ == "__main__":
    unittest.main()
