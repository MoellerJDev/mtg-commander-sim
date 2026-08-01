from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
)
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantic_runtime import (
    ContinuousEffectSourceContext,
    FixedPowerToughnessAnthemHandler,
    SemanticNodeError,
    default_continuous_effect_component_registry,
)
from mtg_commander_sim.semantics import SemanticProgram, SemanticRegistry


def anthem_descriptor() -> dict:
    return {
        "handler_id": "continuous.anthem.power_toughness.v1",
        "schema_version": 1,
        "event": "characteristics.evaluate",
        "condition": {
            "target_controller": "source_controller",
            "target_subtypes_all": ["thopter"],
        },
        "modifier": {"power": 1, "toughness": 1},
    }


class ContinuousEffectComponentTests(unittest.TestCase):
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

    @staticmethod
    def raw_thopter(engine, controller: str = "A"):
        object_id = engine._create_replacement_token_instance(
            controller,
            name="Test Thopter",
            characteristics={
                "type_line": "Token Artifact Creature — Thopter",
                "colors": [],
                "power": "1",
                "toughness": "1",
                "keywords": ["Flying"],
            },
        )
        return engine.state.cards[object_id]

    def test_registered_anthem_component_replaces_name_dispatch(self):
        session = self.session(1250601)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        automaton.printed_name = "Renamed static source"
        thopter = self.raw_thopter(engine)

        self.assertEqual(2, engine._numeric_stat(thopter.object_id, "power"))
        self.assertEqual(
            2, engine._numeric_stat(thopter.object_id, "toughness")
        )
        descriptor = default_continuous_effect_component_registry().describe(
            "continuous.anthem.power_toughness.v1"
        )
        self.assertEqual(
            ["continuous.power_toughness.fixed_anthem"],
            descriptor["capability_dependencies"],
        )

    def test_anthem_component_rejects_malformed_descriptors(self):
        handler = FixedPowerToughnessAnthemHandler()
        malformed = anthem_descriptor()
        malformed["modifier"]["power"] = True
        with self.assertRaisesRegex(SemanticNodeError, "integers"):
            handler.validate(malformed)

        wrong_controller = anthem_descriptor()
        wrong_controller["condition"]["target_controller"] = "any"
        with self.assertRaisesRegex(SemanticNodeError, "source_controller"):
            handler.validate(wrong_controller)

        with self.assertRaisesRegex(ValueError, "event must match"):
            SemanticProgram(
                key="test:mismatched-continuous-event",
                label="Mismatched continuous event",
                event="resolve",
                handlers=[anthem_descriptor()],
            )

    def test_multiple_anthem_components_stack_and_respect_control(self):
        session = self.session(1250602)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        created = engine.create_token(
            "A",
            name="Stridehangar Automaton",
            copy_of=automaton.ref,
            reason="second anthem source characterization",
        )
        copied = next(
            engine._resolve_object("A", ref)
            for ref in created
            if engine._resolve_object("A", ref).oracle_id
            == automaton.oracle_id
        )
        thopter_a = self.raw_thopter(engine, "A")
        self.assertEqual(
            3, engine._numeric_stat(thopter_a.object_id, "power")
        )

        engine.change_control(
            copied.object_id,
            "B",
            reason="control applicability characterization",
        )
        thopter_b = self.raw_thopter(engine, "B")
        self.assertEqual(
            2, engine._numeric_stat(thopter_a.object_id, "power")
        )
        self.assertEqual(
            2, engine._numeric_stat(thopter_b.object_id, "power")
        )
        copied.phased_out = True
        self.assertEqual(
            1, engine._numeric_stat(thopter_b.object_id, "power")
        )

    def test_layer_four_subtype_change_enables_layer_seven_anthem(self):
        handler = FixedPowerToughnessAnthemHandler()
        anthem = handler.lower(
            anthem_descriptor(),
            ContinuousEffectSourceContext(
                source_object_id="source",
                source_ref="S1",
                source_controller="A",
                source_timestamp=2,
                component_id="test:anthem:0",
            ),
        )[0]
        result = evaluate_continuous_effects(
            CharacteristicState(
                name="Test Creature",
                controller="A",
                card_types={"Creature"},
                subtypes={"Goblin"},
                power=1,
                toughness=1,
            ),
            [
                anthem,
                ContinuousEffect(
                    effect_id="type-change",
                    source_id="type-source",
                    layer=Layer.TYPE,
                    sublayer="4",
                    timestamp=9,
                    operations=(
                        ContinuousOperation(
                            "add_types",
                            ["Thopter"],
                            field="subtypes",
                        ),
                    ),
                ),
            ],
        )
        self.assertEqual(
            ("type-change", anthem.effect_id), result.applied_effects
        )
        self.assertEqual(2, result.characteristics["power"])
        self.assertEqual(2, result.characteristics["toughness"])

    def test_anthem_component_replays_exactly(self):
        session = self.session(1250603)
        engine = session.engine
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        program = SemanticProgram(
            key="test:continuous-anthem-token",
            label="Create an anthem witness",
            effects=[
                {
                    "op": "create_token",
                    "controller": "A",
                    "name": "Thopter",
                    "characteristics": {
                        "type_line": "Token Creature — Thopter",
                        "power": "1",
                        "toughness": "1",
                    },
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="continuous-anthem-token",
                ref="S-continuous-anthem-token",
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
        thopter = next(
            card
            for card in engine.state.cards.values()
            if card.is_token and card.printed_name == "Thopter"
        )
        self.assertEqual(2, engine._numeric_stat(thopter.object_id, "power"))

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "continuous-anthem-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])

    def test_complete_legacy_registry_uses_continuous_component(self):
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

        session = self.session(1250604)
        engine = session.engine
        engine.semantics = registry
        engine._semantic_trust_cache.clear()
        automaton = self.card(engine, "Stridehangar Automaton")
        engine.move_card(automaton.object_id, "battlefield", controller="A")
        thopter = self.raw_thopter(engine)
        self.assertEqual(2, engine._numeric_stat(thopter.object_id, "power"))


if __name__ == "__main__":
    unittest.main()
