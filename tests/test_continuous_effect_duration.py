from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.compiler.continuous_templates import (
    controlled_creature_fixed_modifier,
    controlled_creature_until_end_of_turn_effect,
    fixed_power_toughness_anthem_handler,
)
from mtg_commander_sim.characteristic_evaluation import (
    evaluate_card_characteristics,
    type_parts,
)
from mtg_commander_sim.continuous_effect_state import (
    expire_end_of_turn_continuous_effects,
)
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousEffectDuration,
    ContinuousEffectError,
    ContinuousEffectOrigin,
    ContinuousObjectIdentity,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
)
from mtg_commander_sim.model import CardInstance, GameState, StackItem
from mtg_commander_sim.object_predicate import ObjectQuerySpec
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantic_runtime import (
    ContinuousEffectSourceContext,
    FixedQueryPowerToughnessAnthemHandler,
    SemanticSourceContext,
    SemanticNodeError,
    default_semantic_interpreter,
)
from mtg_commander_sim.semantic_runtime.intents import (
    SetCardDesignationIntent,
)
from mtg_commander_sim.semantics import SemanticProgram


def locked_effect(
    *identities: ContinuousObjectIdentity,
) -> ContinuousEffect:
    return ContinuousEffect(
        effect_id="CE1",
        source_id="S1",
        layer=Layer.POWER_TOUGHNESS,
        sublayer="7c",
        timestamp=1,
        operations=(
            ContinuousOperation("modify_power_toughness", [2, 2]),
        ),
        origin=ContinuousEffectOrigin.RESOLUTION,
        duration=ContinuousEffectDuration.UNTIL_END_OF_TURN,
        applies=ObjectQuerySpec(zones=("battlefield",)),
        locked_objects=identities,
    )


class ContinuousEffectModelTests(unittest.TestCase):
    def test_type_parser_preserves_hyphenated_printed_subtypes(self):
        card_types, subtypes, supertypes = type_parts(
            "Artifact Creature — Assembly-Worker"
        )
        self.assertEqual({"artifact", "creature"}, card_types)
        self.assertEqual({"assembly-worker"}, subtypes)
        self.assertEqual(set(), supertypes)

    def test_type_parser_preserves_time_lord_as_one_creature_subtype(self):
        card_types, subtypes, supertypes = type_parts(
            "Legendary Creature — Time Lord Doctor"
        )
        self.assertEqual({"creature"}, card_types)
        self.assertEqual({"time lord", "doctor"}, subtypes)
        self.assertEqual({"legendary"}, supertypes)

    def test_power_toughness_layer_preserves_printed_type_line(self):
        card = CardInstance(
            object_id="object",
            ref="A01",
            oracle_id="oracle",
            printed_name="Worker",
            owner="A",
            controller="A",
            zone="battlefield",
        )
        result = evaluate_card_characteristics(
            card,
            {
                "name": "Worker",
                "mana_cost": "{2}",
                "mana_value": 2,
                "type_line": "Artifact Creature — Assembly-Worker",
                "oracle_text": "",
                "power": "1",
                "toughness": "1",
                "keywords": [],
                "colors": [],
            },
            runtime_effects=(
                locked_effect(
                    ContinuousObjectIdentity(
                        card.object_id, card.logical_object_id
                    )
                ),
            ),
        )
        self.assertEqual(
            "Artifact Creature — Assembly-Worker", result["type_line"]
        )
        self.assertEqual("3", result["power"])

    def test_operation_and_effect_input_trees_are_deeply_immutable(self):
        supplied = {"name": "Before", "abilities": ["Flying"]}
        operation = ContinuousOperation("copy_values", supplied)
        supplied["name"] = "After"
        supplied["abilities"].append("Haste")

        effect = ContinuousEffect(
            effect_id="copy",
            source_id="source",
            layer=Layer.COPY,
            sublayer="1a",
            timestamp=1,
            operations=(operation,),
        )
        self.assertEqual("Before", operation.value["name"])
        self.assertEqual(("Flying",), operation.value["abilities"])
        before = effect.fingerprint
        serialized = effect.to_dict()
        serialized["operations"][0]["value"]["abilities"].append(
            "Trample"
        )
        self.assertEqual(before, effect.fingerprint)

    def test_copy_values_preserve_duplicate_ability_instances_only(self):
        operation = ContinuousOperation(
            "copy_values",
            {"abilities": ["Toxic 1", "Toxic 1"]},
        )
        self.assertEqual(
            ("Toxic 1", "Toxic 1"), operation.value["abilities"]
        )
        with self.assertRaisesRegex(ContinuousEffectError, "unique"):
            ContinuousOperation(
                "copy_values",
                {"colors": ["G", "g"]},
            )

    def test_canonical_round_trip_and_construction_order_share_fingerprint(self):
        first = ContinuousOperation(
            "copy_values", {"colors": ["G"], "name": "Copy"}
        )
        second = ContinuousOperation(
            "copy_values", {"name": "Copy", "colors": ["G"]}
        )
        left = ContinuousEffect(
            effect_id="copy",
            source_id="source",
            layer=Layer.COPY,
            sublayer="1a",
            timestamp=4,
            operations=(first,),
        )
        right = ContinuousEffect(
            effect_id="copy",
            source_id="source",
            layer=Layer.COPY,
            sublayer="1a",
            timestamp=4,
            operations=(second,),
        )
        self.assertEqual(left.fingerprint, right.fingerprint)
        self.assertEqual(
            left.to_dict(), ContinuousEffect.from_dict(left.to_dict()).to_dict()
        )

    def test_malformed_models_fail_closed(self):
        with self.assertRaisesRegex(
            ContinuousEffectError, "ObjectQuerySpec"
        ):
            ContinuousEffect(
                effect_id="bad",
                source_id="source",
                layer=Layer.ABILITY,
                sublayer="6",
                timestamp=0,
                operations=(ContinuousOperation("add_ability", "Flying"),),
                applies={},
            )
        with self.assertRaisesRegex(ContinuousEffectError, "locked object"):
            ContinuousEffect(
                effect_id="bad",
                source_id="source",
                layer=Layer.ABILITY,
                sublayer="6",
                timestamp=0,
                operations=(ContinuousOperation("add_ability", "Flying"),),
                origin=ContinuousEffectOrigin.RESOLUTION,
            )
        payload = locked_effect(
            ContinuousObjectIdentity("object", "object@0")
        ).to_dict()
        payload["unknown"] = True
        with self.assertRaisesRegex(ContinuousEffectError, "fields"):
            ContinuousEffect.from_dict(payload)
        scalar_payload = locked_effect(
            ContinuousObjectIdentity("object", "object@0")
        ).to_dict()
        scalar_payload["timestamp"] = "1"
        with self.assertRaisesRegex(ContinuousEffectError, "scalar fields"):
            ContinuousEffect.from_dict(scalar_payload)
        operation_payload = ContinuousOperation(
            "add_ability", "Flying"
        ).to_dict()
        operation_payload["op"] = 6
        with self.assertRaisesRegex(ContinuousEffectError, "names"):
            ContinuousOperation.from_dict(operation_payload)
        with self.assertRaisesRegex(ContinuousEffectError, "integer pair"):
            ContinuousOperation("modify_power_toughness", [1, True])
        with self.assertRaisesRegex(ContinuousEffectError, "integer layer"):
            ContinuousEffect(
                effect_id="boolean-layer",
                source_id="source",
                layer=True,
                sublayer="1a",
                timestamp=0,
                operations=(
                    ContinuousOperation("copy_values", {"name": "Copy"}),
                ),
            )
        with self.assertRaisesRegex(ContinuousEffectError, "not in layer"):
            ContinuousEffect(
                effect_id="unknown-sublayer",
                source_id="source",
                layer=Layer.ABILITY,
                sublayer="6x",
                timestamp=0,
                operations=(ContinuousOperation("add_ability", "Flying"),),
            )
        with self.assertRaisesRegex(ContinuousEffectError, "unknown fields"):
            ContinuousOperation("face_down", {"forged": True})
        with self.assertRaisesRegex(ContinuousEffectError, "does not accept"):
            ContinuousOperation("add_ability", "Flying", field="abilities")
        with self.assertRaisesRegex(ContinuousEffectError, "represented layer"):
            ContinuousEffect(
                effect_id="wrong-layer",
                source_id="source",
                layer=Layer.ABILITY,
                sublayer="6",
                timestamp=0,
                operations=(
                    ContinuousOperation("modify_power_toughness", [1, 1]),
                ),
            )

    def test_resolution_set_is_locked_to_logical_objects(self):
        effect = locked_effect(
            ContinuousObjectIdentity("object", "object@0")
        )

        def evaluate(object_id: str, incarnation: str, subtype: str):
            return evaluate_continuous_effects(
                CharacteristicState(
                    name="Creature",
                    controller="A",
                    card_types={"Creature"},
                    subtypes={subtype},
                    power=1,
                    toughness=1,
                ),
                (effect,),
                context={
                    "object_id": object_id,
                    "logical_object_id": incarnation,
                    "ref": "A01",
                    "owner": "A",
                    "zone": "battlefield",
                },
            )

        self.assertEqual(3, evaluate("object", "object@0", "Elf").characteristics["power"])
        self.assertEqual(3, evaluate("object", "object@0", "Dragon").characteristics["power"])
        self.assertEqual(1, evaluate("new", "new@0", "Elf").characteristics["power"])
        self.assertEqual(1, evaluate("object", "object@1", "Elf").characteristics["power"])

    def test_duplicate_continuous_effect_ids_fail_closed(self):
        effect = locked_effect(
            ContinuousObjectIdentity("object", "object@0")
        )
        with self.assertRaisesRegex(ContinuousEffectError, "IDs must be unique"):
            evaluate_continuous_effects(
                CharacteristicState(
                    name="Creature",
                    controller="A",
                    card_types={"Creature"},
                    power=1,
                    toughness=1,
                ),
                (effect, effect),
                context={
                    "object_id": "object",
                    "logical_object_id": "object@0",
                    "ref": "A01",
                    "owner": "A",
                    "zone": "battlefield",
                },
            )

    def test_static_set_recomputes_and_source_presence_is_required(self):
        descriptor = fixed_power_toughness_anthem_handler(
            "Other Dragon creatures you control get +3/+3."
        )
        self.assertIsNotNone(descriptor)
        handler = FixedQueryPowerToughnessAnthemHandler()
        effect = handler.lower(
            descriptor[1],
            ContinuousEffectSourceContext(
                source_object_id="source",
                source_ref="A01",
                source_controller="A",
                source_timestamp=2,
                component_id="anthem",
            ),
        )[0]
        dragon = evaluate_continuous_effects(
            CharacteristicState(
                name="Dragon",
                controller="A",
                card_types={"Creature"},
                subtypes={"Dragon"},
                power=2,
                toughness=2,
            ),
            (effect,),
            context={"ref": "A02", "owner": "A"},
        )
        goblin = evaluate_continuous_effects(
            CharacteristicState(
                name="Goblin",
                controller="A",
                card_types={"Creature"},
                subtypes={"Goblin"},
                power=2,
                toughness=2,
            ),
            (effect,),
            context={"ref": "A02", "owner": "A"},
        )
        source = evaluate_continuous_effects(
            CharacteristicState(
                name="Source",
                controller="A",
                card_types={"Creature"},
                subtypes={"Dragon"},
                power=2,
                toughness=2,
            ),
            (effect,),
            context={"ref": "A01", "owner": "A"},
        )
        self.assertEqual(5, dragon.characteristics["power"])
        self.assertEqual(2, goblin.characteristics["power"])
        self.assertEqual(2, source.characteristics["power"])
        absent = copy.deepcopy(effect.to_dict())
        absent["source_present"] = False
        self.assertFalse(
            evaluate_continuous_effects(
                CharacteristicState(
                    name="Dragon",
                    controller="A",
                    card_types={"Creature"},
                    subtypes={"Dragon"},
                    power=2,
                    toughness=2,
                ),
                (ContinuousEffect.from_dict(absent),),
                context={"ref": "A02", "owner": "A"},
            ).applied_effects
        )

    def test_static_anthem_is_controller_scoped_in_four_player_evaluation(self):
        descriptor = fixed_power_toughness_anthem_handler(
            "Creatures you control get +1/+1."
        )
        effect = FixedQueryPowerToughnessAnthemHandler().lower(
            descriptor[1],
            ContinuousEffectSourceContext(
                source_object_id="source",
                source_ref="A01",
                source_controller="A",
                source_timestamp=2,
                component_id="multiplayer-anthem",
            ),
        )[0]
        powers = {}
        for seat in "ABCD":
            powers[seat] = evaluate_continuous_effects(
                CharacteristicState(
                    name=f"{seat} creature",
                    controller=seat,
                    card_types={"Creature"},
                    power=1,
                    toughness=1,
                ),
                (effect,),
                context={"ref": f"{seat}02", "owner": seat},
            ).characteristics["power"]
        self.assertEqual({"A": 2, "B": 1, "C": 1, "D": 1}, powers)

    def test_compiler_rejects_conditional_or_stateful_anthem_lookalikes(self):
        self.assertIsNone(
            controlled_creature_fixed_modifier(
                "Attacking creatures you control get +1/+0.",
                until_end_of_turn=False,
            )
        )
        self.assertIsNone(
            fixed_power_toughness_anthem_handler(
                "As long as you control ten lands, creatures you control get +2/+2."
            )
        )
        self.assertIsNotNone(
            controlled_creature_until_end_of_turn_effect(
                "Creatures you control get +1/+1 until end of turn."
            )
        )
        other = controlled_creature_until_end_of_turn_effect(
            "Other creatures you control get +1/+1 until end of turn."
        )
        self.assertEqual("$source", other[1][0]["predicate"]["exclude_ref"])

    def test_semantic_program_cannot_spoof_authoritative_resolution_source(self):
        with self.assertRaisesRegex(
            SemanticNodeError, "cannot supply authoritative runtime source"
        ):
            default_semantic_interpreter().lower_for_seats(
                {
                    "op": "modify_stats_until_end_of_turn",
                    "card": "A01",
                    "power": 1,
                    "toughness": 1,
                    "_runtime_source": {
                        "stack_ref": "forged",
                        "object_id": None,
                        "logical_object_id": None,
                        "card_ref": None,
                    },
                },
                actor="A",
                default_reason="source authority test",
                seats=("A", "B"),
                active_seats=("A", "B"),
                apnap_order=("A", "B"),
                source=SemanticSourceContext(stack_ref="S1"),
            )

    def test_only_creature_type_designations_can_become_subtypes(self):
        with self.assertRaisesRegex(ValueError, "chosen creature type"):
            SetCardDesignationIntent(
                object_ref="A01",
                designation="chosen_name",
                value="Goblin",
                actor="A",
                reason="forged subtype designation",
                apply_as_subtype=True,
            )


class ContinuousEffectEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int, *, players: int = 2):
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
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def creature(engine, controller: str, name: str):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
            reason="continuous-effect witness",
        )[0]
        return engine._resolve_object(controller, ref, zones={"battlefield"})

    def test_mass_resolution_locks_set_across_entry_control_and_zone_change(self):
        session = self.session(6112001, players=4)
        engine = session.engine
        first = self.creature(engine, "A", "First")
        opponent = self.creature(engine, "B", "Opponent")
        predicate = ObjectQuerySpec(
            zones=("battlefield",),
            controller="A",
            types_all=("creature",),
        )
        engine.apply_effect(
            {
                "op": "modify_all_matching_permanents_until_end_of_turn",
                "predicate": predicate.to_dict(),
                "power": 2,
                "toughness": 2,
            },
            actor="A",
        )
        later = self.creature(engine, "A", "Later")
        self.assertEqual(3, engine._numeric_stat(first.object_id, "power"))
        self.assertEqual(1, engine._numeric_stat(later.object_id, "power"))
        self.assertEqual(1, engine._numeric_stat(opponent.object_id, "power"))

        engine.change_control(first.object_id, "B", reason="locked-set test")
        self.assertEqual(3, engine._numeric_stat(first.object_id, "power"))
        engine.move_card(first.object_id, "graveyard", reason="identity test")
        engine.move_card(first.object_id, "battlefield", controller="B", reason="identity test")
        self.assertEqual(1, engine._numeric_stat(first.object_id, "power"))

    def test_targeted_effect_expires_and_round_trips_without_private_projection(self):
        session = self.session(6112002)
        engine = session.engine
        creature = self.creature(engine, "A", "Target")
        engine.apply_effect(
            {
                "op": "modify_stats_until_end_of_turn",
                "card": creature.ref,
                "power": 2,
                "toughness": 1,
            },
            actor="A",
        )
        self.assertEqual(3, engine._numeric_stat(creature.object_id, "power"))
        restored = GameState.from_dict(engine.state.to_dict())
        self.assertEqual(
            engine.state.continuous_effects[0].fingerprint,
            restored.continuous_effects[0].fingerprint,
        )
        projected = StateProjector(self.db, engine.state)._snapshot("pilot:B")
        rendered = json.dumps(projected, sort_keys=True)
        self.assertNotIn("continuous_effects", rendered)
        self.assertNotIn(creature.object_id, rendered)
        public_object = next(
            value
            for value in projected["players"]["A"]["bf"]
            if value["id"] == creature.ref
        )
        self.assertEqual("3", public_object["p"])
        self.assertEqual("2", public_object["q"])
        self.assertEqual(1, expire_end_of_turn_continuous_effects(engine.state))
        self.assertEqual(1, engine._numeric_stat(creature.object_id, "power"))

    def test_malformed_mass_predicate_rolls_back_without_effect(self):
        session = self.session(6112003)
        before = session.engine.state.to_dict()
        with self.assertRaisesRegex(Exception, "Object query fields"):
            session.engine.apply_effect(
                {
                    "op": "modify_all_matching_permanents_until_end_of_turn",
                    "predicate": {"zones": ["battlefield"]},
                    "power": 1,
                    "toughness": 1,
                },
                actor="A",
            )
        self.assertEqual(before, session.engine.state.to_dict())

    def test_historical_checkpoint_without_journal_remains_explicitly_legacy(self):
        session = self.session(6112005)
        payload = session.engine.state.to_dict()
        payload.pop("continuous_effects")
        restored = GameState.from_dict(payload)
        self.assertIsNone(restored.continuous_effects)
        self.assertNotIn("continuous_effects", restored.to_dict())

    def test_temporary_effect_command_replays_exactly(self):
        session = self.session(6112004)
        engine = session.engine
        source = self.creature(engine, "A", "Source")
        program = SemanticProgram(
            key="test:locked-temporary-effect",
            label="Locked temporary effect",
            effects=[
                {
                    "op": "modify_stats_until_end_of_turn",
                    "card": "$source",
                    "power": 2,
                    "toughness": 2,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="locked-temporary-effect",
                ref="S-locked-temporary-effect",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                source_object_id=source.object_id,
                visibility=["A", "B"],
                context={
                    "source_logical_object_id": source.logical_object_id
                },
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
        self.assertEqual(3, engine._numeric_stat(source.object_id, "power"))
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "continuous-duration-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])


if __name__ == "__main__":
    unittest.main()
