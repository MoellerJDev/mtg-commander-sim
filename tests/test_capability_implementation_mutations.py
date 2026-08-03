from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim import damage_results as damage_results_module
from mtg_commander_sim import replacement_effects
from mtg_commander_sim import tap_state
from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    evaluate_continuous_effects,
)
from mtg_commander_sim import damage as damage_module
from mtg_commander_sim import damage_prevention as damage_prevention_module
from mtg_commander_sim.damage import DamageEvent
from mtg_commander_sim.damage_prevention import (
    DamageModifierDuration,
    DamagePreventionShield,
    DamageSubject,
    PreventionMode,
)
from mtg_commander_sim.damage_modifier_state import (
    ChosenDamageSource,
    DamageAftermathRecipient,
    DealDamagePreventionAftermath,
    GainLifePreventionAftermath,
)
from mtg_commander_sim.damage_source import DamageSourceSnapshot
from mtg_commander_sim.prevention_triggers import (
    DrawCardsPreventionTrigger,
    PreventionTriggeredAbility,
    PreventionTriggerOccurrence,
)
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim import oracle_ir as oracle_ir_module
from mtg_commander_sim import object_predicate as object_predicate_module
from mtg_commander_sim import object_query as object_query_module
from mtg_commander_sim.object_query import ObjectQueryError, ObjectQuerySpec
from mtg_commander_sim.semantic_runtime.counter_replacements import (
    CounterPlacementEventSpec,
    CounterQuantityReplacementHandler,
    CounterReplacementSourceContext,
    resolve_counter_placement_replacements,
)
from mtg_commander_sim.semantic_runtime.continuous_components import (
    AddBasicLandTypeHandler,
    ContinuousEffectSourceContext,
)
from mtg_commander_sim.semantic_runtime.damage_replacements import (
    DamageQuantityReplacementHandler,
    DamageReplacementSourceContext,
    FixedDamagePreventionHandler,
    StaticDamageRedirectionHandler,
)
from mtg_commander_sim.semantic_runtime.damage_results import (
    DamageResultLifeFloorHandler,
    DamageResultReplacementSourceContext,
)
from mtg_commander_sim.semantic_runtime.life_replacements import (
    LifeGainMultiplierHandler,
    LifeReplacementSourceContext,
)
from mtg_commander_sim.targets import PUBLIC_TARGET_ZONES, TargetGroup


def _event(*, assigned: int, dealt: int, prevented: int) -> DamageEvent:
    return DamageEvent(
        source="C1",
        source_object_id="source-object",
        source_logical_object_id="source-incarnation",
        source_oracle_id=None,
        source_commander_designation_id=None,
        source_controller="A",
        source_owner="A",
        source_types=("instant",),
        source_subtypes=(),
        source_colors=("R",),
        source_keywords=(),
        source_is_commander=False,
        target="B",
        target_kind="player",
        target_object_id=None,
        target_controller="B",
        target_types=(),
        target_subtypes=(),
        assigned_amount=assigned,
        dealt_amount=dealt,
        prevented_amount=prevented,
        combat=False,
    )


class CapabilityImplementationMutationTests(unittest.TestCase):
    """Small executable mutations proving critical assertions kill defects.

    These are implementation mutations, not registry-dependency mutations.
    Each test first proves the behavioral assertion against the real code,
    then installs a deliberately broken implementation and proves that the
    same assertion fails.
    """

    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_target_validation_mutant_is_killed(self):
        def assert_hidden_target_rejected() -> None:
            with self.assertRaisesRegex(ValueError, "hidden/nonpublic"):
                TargetGroup.from_mapping({"zones": ["hand"]})

        assert_hidden_target_rejected()
        mutated_zones = set(PUBLIC_TARGET_ZONES) | {"hand"}
        with patch(
            "mtg_commander_sim.targets.PUBLIC_TARGET_ZONES", mutated_zones
        ):
            with self.assertRaises(AssertionError):
                assert_hidden_target_rejected()

    def test_object_query_string_coercion_mutant_is_killed(self):
        def assert_malformed_term_rejected() -> None:
            with self.assertRaises(ObjectQueryError):
                ObjectQuerySpec(types_all=(1,))

        assert_malformed_term_rejected()

        def coercing_terms(values, *, field_name, upper=False):
            del field_name
            normalize = str.upper if upper else str.casefold
            return tuple(sorted(normalize(str(value)) for value in values))

        with patch.object(
            object_predicate_module,
            "_normalized_terms",
            coercing_terms,
        ):
            with self.assertRaises(AssertionError):
                assert_malformed_term_rejected()

    def test_chosen_source_predicate_validator_mutant_is_killed(self):
        predicate = ObjectQuerySpec(
            zones=("battlefield",),
            known_to_actor=True,
            token=True,
        )

        def assert_unsupported_predicate_rejected() -> None:
            with self.assertRaises(ObjectQueryError):
                object_query_module.validate_chosen_damage_source_predicate(
                    predicate
                )

        assert_unsupported_predicate_rejected()
        with patch.object(
            object_query_module,
            "validate_chosen_damage_source_predicate",
            lambda value: value,
        ):
            with self.assertRaises(AssertionError):
                assert_unsupported_predicate_rejected()

    def test_prevention_immediate_sequence_mutants_are_killed(self):
        record = replace(
            self.db.lookup("Force of Vigor"),
            oracle_id="fixture:prevention-immediate-mutation",
            name="Fixture Prevention Immediate Mutation",
            oracle_text=(
                "Prevent the next 3 damage that would be dealt to any target "
                "this turn by a source of your choice. You gain 3 life."
            ),
        )

        def assert_sequence() -> None:
            node = oracle_ir_module.compile_oracle_card(
                record
            ).faces[0].nodes[0]
            self.assertEqual(
                "damage-prevention-chosen-source-fixed-life-v2",
                node.template_id,
            )
            self.assertEqual(2, len(node.effects))
            source_choice, life_gain = node.effects
            self.assertEqual("choose_damage_source", source_choice["op"])
            self.assertNotIn("aftermath", source_choice["shield"])
            self.assertEqual("life", life_gain["op"])
            self.assertEqual(3, life_gain["delta"])

        assert_sequence()
        original = oracle_ir_module.fixed_prevention_effect_template

        def mutated(mutator):
            def compile_template(text, **kwargs):
                result = original(text, **kwargs)
                if result is None:
                    return None
                template_id, effects, targets, rules = result
                return template_id, mutator(effects), targets, rules

            return compile_template

        def remove_life(effects):
            return effects[:1]

        def move_life_to_aftermath(effects):
            choice = dict(effects[0])
            shield = dict(choice["shield"])
            shield["aftermath"] = [
                {
                    "kind": "gain_life",
                    "player": "$controller",
                    "per_prevented": 0,
                    "fixed_amount": 3,
                }
            ]
            choice["shield"] = shield
            return (choice,)

        mutants = (
            remove_life,
            move_life_to_aftermath,
            lambda effects: (*effects, effects[1]),
            lambda effects: tuple(reversed(effects)),
        )
        for mutant in mutants:
            with self.subTest(mutant=mutant.__name__):
                with patch.object(
                    oracle_ir_module,
                    "fixed_prevention_effect_template",
                    mutated(mutant),
                ):
                    with self.assertRaises(AssertionError):
                        assert_sequence()

    def test_basic_land_type_intrinsic_mana_mutant_is_killed(self):
        descriptor = {
            "handler_id": "continuous.basic_land_type.add_all_lands.v1",
            "schema_version": 1,
            "event": "characteristics.evaluate",
            "condition": {"target_types_all": ["land"]},
            "modifier": {"basic_land_type": "swamp"},
        }
        context = ContinuousEffectSourceContext(
            source_object_id="urborg",
            source_ref="U1",
            source_controller="A",
            source_timestamp=1,
            component_id="mutation",
        )

        def assert_swamp_is_added() -> None:
            effects = AddBasicLandTypeHandler().lower(
                descriptor, context
            )
            result = evaluate_continuous_effects(
                CharacteristicState(
                    name="Darksteel Citadel",
                    controller="A",
                    card_types={"Artifact", "Land"},
                    subtypes=set(),
                    abilities=["Indestructible", "{T}: Add {C}."],
                ),
                effects,
            )
            self.assertIn("swamp", result.characteristics["subtypes"])

        assert_swamp_is_added()
        with patch.object(
            AddBasicLandTypeHandler,
            "lower",
            lambda _handler, _descriptor, _context: (),
        ):
            with self.assertRaises(AssertionError):
                assert_swamp_is_added()

    def test_damage_amount_guard_mutant_is_killed(self):
        def assert_negative_assignment_rejected() -> None:
            with self.assertRaisesRegex(ValueError, "positive assignment"):
                _event(assigned=-1, dealt=-1, prevented=0)

        assert_negative_assignment_rejected()
        with patch.object(DamageEvent, "__post_init__", lambda _event: None):
            with self.assertRaises(AssertionError):
                assert_negative_assignment_rejected()

    def test_commander_identity_mutant_is_killed(self):
        def assert_physical_designations_remain_separate() -> None:
            first = damage_module.commander_damage_key(
                source_is_commander=True,
                designation_id="commander:A:1",
                oracle_id="shared-oracle-id",
                identity_version=2,
            )
            second = damage_module.commander_damage_key(
                source_is_commander=True,
                designation_id="commander:C:1",
                oracle_id="shared-oracle-id",
                identity_version=2,
            )
            self.assertNotEqual(first, second)

        assert_physical_designations_remain_separate()

        def oracle_identity_mutant(**values):
            return (
                values["oracle_id"]
                if values["source_is_commander"]
                else None
            )

        with patch.object(
            damage_module,
            "commander_damage_key",
            oracle_identity_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_physical_designations_remain_separate()

    def test_damage_result_dispatch_mutant_is_killed(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=1203,
        )
        keep_all(session)
        engine = session.engine
        card = next(
            value
            for value in engine.state.cards.values()
            if value.owner == "A" and not value.is_commander
            and not engine._type_parts(
                str(engine._effective_card_data(value).get("type_line") or "")
            )[0].intersection({"instant", "sorcery"})
        )
        card = engine.move_card(
            card.object_id,
            "battlefield",
            controller="A",
            reason="implementation mutation fixture",
            semantic_events=False,
        )
        card.annotations["copy_overrides"] = {
            "name": "Mutation Fixture",
            "type_line": "Creature Planeswalker Battle",
            "oracle_text": "",
        }
        card.counters["loyalty"] = 4
        card.counters["defense"] = 5
        source_ref = engine.create_token(
            "A",
            name="Damage Result Mutation Source",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        source = engine._resolve_object(
            "A", source_ref, zones={"battlefield"}
        )

        def assert_all_permanent_results() -> None:
            card.marked_damage = 0
            card.counters["loyalty"] = 4
            card.counters["defense"] = 5
            damage = damage_module.damage_proposal(
                engine,
                proposal_id="damage:result-dispatch-mutation",
                actor="A",
                source_ref=source.ref,
                target=card.ref,
                amount=2,
                combat=False,
                reason="implementation mutation fixture",
            ).event()
            prepared = damage_results_module.prepare_damage_results(
                engine,
                (damage,),
                effects=(),
            )
            plan = damage_results_module.plan_damage_result_commit(
                engine, prepared
            )
            damage_results_module.commit_damage_result_plan(engine, plan)
            self.assertEqual(2, card.marked_damage)
            self.assertEqual(2, card.counters["loyalty"])
            self.assertEqual(3, card.counters["defense"])

        assert_all_permanent_results()

        with patch.object(
            damage_results_module,
            "materialize_damage_results",
            lambda _host, _events: (),
        ):
            with self.assertRaises(AssertionError):
                assert_all_permanent_results()

    def test_keyword_damage_result_mutants_are_killed(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=12031,
        )
        keep_all(session)
        engine = session.engine

        def token(name: str, *, keywords=(), oracle_text=""):
            ref = engine.create_token(
                "A" if "Source" in name else "B",
                name=name,
                characteristics={
                    "type_line": "Token Creature — Test",
                    "power": "3",
                    "toughness": "5",
                    "keywords": list(keywords),
                    "oracle_text": oracle_text,
                },
            )[0]
            return engine._resolve_object(
                "A" if "Source" in name else "B",
                ref,
                zones={"battlefield"},
            )

        infect = token(
            "Infect Lifelink Toxic Source",
            keywords=("Infect", "Lifelink", "Toxic"),
            oracle_text="Toxic 2",
        )
        wither = token("Wither Source", keywords=("Wither",))
        target = token("Mutation Target")
        damage_events = (
            damage_module.damage_proposal(
                engine,
                proposal_id="damage:keyword-mutation:player",
                actor="A",
                source_ref=infect.ref,
                target="B",
                amount=3,
                combat=True,
                reason="implementation mutation fixture",
            ).event(),
            damage_module.damage_proposal(
                engine,
                proposal_id="damage:keyword-mutation:creature",
                actor="A",
                source_ref=wither.ref,
                target=target.ref,
                amount=2,
                combat=True,
                reason="implementation mutation fixture",
            ).event(),
        )

        def assert_keyword_results() -> None:
            roots = damage_results_module.materialize_damage_results(
                engine, damage_events
            )
            leaves = [child for root in roots for child in root.children]
            amounts = {
                str(child.payload.get("cause")): int(
                    child.payload.get("amount", 0)
                )
                for child in leaves
            }
            self.assertEqual(3, amounts["infect"])
            self.assertEqual(2, amounts["toxic"])
            self.assertEqual(3, amounts["lifelink"])
            self.assertEqual(2, amounts["infect_or_wither"])

        assert_keyword_results()
        original = damage_results_module.materialize_damage_results

        def strip_cause(cause: str):
            def mutant(host, events):
                def visit(event):
                    return replace(
                        event,
                        children=tuple(
                            visit(child)
                            for child in event.children
                            if child.payload.get("cause") != cause
                        ),
                    )

                return tuple(visit(event) for event in original(host, events))

            return mutant

        for cause in ("infect", "toxic", "lifelink", "infect_or_wither"):
            with self.subTest(cause=cause), patch.object(
                damage_results_module,
                "materialize_damage_results",
                strip_cause(cause),
            ):
                with self.assertRaises((AssertionError, KeyError)):
                    assert_keyword_results()

    def test_damage_result_replacement_component_mutants_are_killed(self):
        gain_descriptor = {
            "handler_id": "replacement.life.gain.multiplier.v1",
            "schema_version": 1,
            "event": "life.change",
            "condition": {
                "affected_player_relation": "source_controller",
            },
            "modification": {"multiplier": 2},
        }
        floor_descriptor = {
            "handler_id": "replacement.damage.result.life_floor.v1",
            "schema_version": 1,
            "event": "damage.results",
            "condition": {
                "affected_player_relation": "source_controller",
                "requires_controlled_creature": True,
            },
            "modification": {"minimum_life": 1},
        }
        context = LifeReplacementSourceContext(
            source_ref="result-replacement-mutation-source",
            source_controller="A",
        )
        gain = replacement_effects.ReplaceableEvent(
            event_id="life:gain:mutation",
            kind="life.change",
            affected_player="A",
            payload={"direction": "gain", "amount": 3},
        )
        loss = replacement_effects.ReplaceableEvent(
            event_id="life:loss:mutation",
            kind="life.change",
            affected_player="A",
            payload={
                "direction": "loss",
                "amount": 5,
                "requested_amount": 5,
            },
        )
        root = replacement_effects.ReplaceableEvent(
            event_id="damage:results:mutation",
            kind="damage.results",
            affected_player="A",
            payload={
                "subject_kind": "player",
                "life_before": 5,
                "life_loss_amount": 5,
                "life_after_without_replacement": 0,
                "controls_creature": True,
            },
            children=(loss,),
        )

        def assert_components_transform_results() -> None:
            gain_effect = LifeGainMultiplierHandler().replacement_effect(
                gain_descriptor, context
            )
            floor_effect = DamageResultLifeFloorHandler().replacement_effect(
                floor_descriptor, context
            )
            doubled = replacement_effects.resolve_replacements(
                gain, (gain_effect,), selections=(gain_effect.effect_id,)
            )
            floored = replacement_effects.resolve_replacements(
                root, (floor_effect,), selections=(floor_effect.effect_id,)
            )
            self.assertEqual(6, doubled.payload["amount"])
            self.assertEqual(4, floored.children[0].payload["amount"])

        assert_components_transform_results()
        original_gain = LifeGainMultiplierHandler.replacement_effect

        def identity_gain(handler, descriptor, source_context):
            effect = original_gain(handler, descriptor, source_context)
            return replace(
                effect,
                operations=(
                    {"op": "multiply", "field": "amount", "factor": 1},
                ),
            )

        with patch.object(
            LifeGainMultiplierHandler,
            "replacement_effect",
            identity_gain,
        ):
            with self.assertRaises(AssertionError):
                assert_components_transform_results()

        original_floor = DamageResultLifeFloorHandler.replacement_effect

        def skip_floor(handler, descriptor, source_context):
            effect = original_floor(handler, descriptor, source_context)
            return replace(
                effect,
                operations=(
                    {"op": "cap_result_life_loss", "minimum": -100},
                ),
            )

        with patch.object(
            DamageResultLifeFloorHandler,
            "replacement_effect",
            skip_floor,
        ):
            with self.assertRaises(
                (AssertionError, replacement_effects.ReplacementEffectError)
            ):
                assert_components_transform_results()

    def test_semantic_tap_state_mutants_are_killed(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=7012699,
        )
        keep_all(session)
        engine = session.engine
        first_ref = engine.create_token(
            "A",
            name="Tap Mutation Witness",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        second_ref = engine.create_token(
            "B",
            name="Untap Mutation Witness",
            tapped=True,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        first = engine._resolve_object("A", first_ref, zones={"battlefield"})
        second = engine._resolve_object("B", second_ref, zones={"battlefield"})

        def assert_single_tap() -> None:
            first.tapped = False
            engine.apply_effect({"op": "tap", "card": first.ref}, actor="A")
            self.assertTrue(first.tapped)

        assert_single_tap()
        with patch.object(
            tap_state,
            "set_permanent_tapped",
            lambda _host, object_ref, **_kwargs: object_ref,
        ):
            with self.assertRaises(AssertionError):
                assert_single_tap()

        def assert_stun_replaces_untap() -> None:
            second.tapped = True
            second.counters["stun"] = 1
            engine.apply_effect(
                {"op": "untap", "card": second.ref}, actor="A"
            )
            self.assertTrue(second.tapped)
            self.assertNotIn("stun", second.counters)

        assert_stun_replaces_untap()

        def ignore_stun_mutant(
            _engine: CommanderEngine,
            card,
            *,
            actor,
            reason,
        ) -> bool:
            card.tapped = False
            return True

        with patch.object(
            CommanderEngine,
            "_untap_permanent",
            ignore_stun_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_stun_replaces_untap()

        def assert_aggregate_untap() -> None:
            first.tapped = True
            second.tapped = True
            second.counters.pop("stun", None)
            engine.apply_effect({"op": "untap_all_creatures"}, actor="A")
            self.assertFalse(first.tapped)
            self.assertFalse(second.tapped)

        assert_aggregate_untap()
        with patch.object(
            tap_state,
            "untap_all_creatures",
            lambda _host, **_kwargs: [],
        ):
            with self.assertRaises(AssertionError):
                assert_aggregate_untap()

    def test_replacement_nested_order_mutant_is_killed(self):
        child = replacement_effects.ReplaceableEvent(
            event_id="counter:child",
            kind="counter.add",
            affected_player="A",
            payload={"amount": 1},
        )
        root = replacement_effects.ReplaceableEvent(
            event_id="token:root",
            kind="token.create",
            affected_player="A",
            payload={"quantity": 1},
            children=(child,),
        )
        effects = (
            replacement_effects.ReplacementEffect(
                effect_id="outer",
                source_id="outer-source",
                event_kind="token.create",
                replacement_class=replacement_effects.ReplacementClass.OTHER,
                operations=(
                    {"op": "multiply", "field": "quantity", "factor": 2},
                ),
            ),
            replacement_effects.ReplacementEffect(
                effect_id="inner",
                source_id="inner-source",
                event_kind="counter.add",
                replacement_class=replacement_effects.ReplacementClass.OTHER,
                operations=(
                    {"op": "multiply", "field": "amount", "factor": 2},
                ),
            ),
        )

        def assert_containing_event_first() -> None:
            pending = replacement_effects.replacement_tree_choice(
                root, effects
            )
            self.assertEqual((), pending.path)
            self.assertEqual(("outer",), pending.choice.options)

        assert_containing_event_first()

        def child_first_mutant(event, available_effects):
            choice = replacement_effects.replacement_choice(
                event.children[0], available_effects
            )
            return replacement_effects.ReplacementTreeChoice(
                path=(0,), choice=choice
            )

        with patch.object(
            replacement_effects,
            "replacement_tree_choice",
            child_first_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_containing_event_first()

    def test_counter_quantity_replacement_mutant_is_killed(self):
        descriptor = {
            "handler_id": "replacement.counter.quantity.v1",
            "schema_version": 1,
            "event": "counter.place",
            "condition": {
                "placing_player_relation": "any",
                "target_controller_relation": "source_controller",
                "counter_names": [],
                "target_types_all": [],
                "effect_generated": True,
            },
            "modification": {"multiplier": 2, "additional": 0},
        }
        context = CounterReplacementSourceContext(
            source_ref="doubling",
            source_controller="A",
        )
        event = CounterPlacementEventSpec(
            event_id="counter-mutation",
            object_id="target",
            owner="A",
            controller="A",
            target_zone="battlefield",
            target_types=("creature",),
            placing_player="A",
            counter_name="+1/+1",
            amount=2,
            source_ref=None,
            effect_generated=True,
        ).event()

        def assert_quantity_replaced() -> None:
            effect = CounterQuantityReplacementHandler().replacement_effect(
                descriptor,
                context,
            )
            resolution = resolve_counter_placement_replacements(
                batch_id="counter-mutation-batch",
                events=(event,),
                effects=(effect,),
                apnap_order=("A",),
            )
            self.assertEqual(
                4,
                resolution.batch.events[0].payload["amount"],
            )

        assert_quantity_replaced()
        original = CounterQuantityReplacementHandler.replacement_effect

        def identity_quantity_mutant(handler, mapping, source_context):
            effect = original(handler, mapping, source_context)
            return replace(
                effect,
                operations=(
                    {"op": "multiply", "field": "amount", "factor": 1},
                ),
            )

        with patch.object(
            CounterQuantityReplacementHandler,
            "replacement_effect",
            identity_quantity_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_quantity_replaced()

    def test_prevention_aftermath_quantity_mutant_is_killed(self):
        aftermath = GainLifePreventionAftermath(
            player="A", per_prevented=2, fixed_amount=1
        )

        def assert_scaled_aftermath() -> None:
            self.assertEqual(7, aftermath.amount(3))

        assert_scaled_aftermath()
        with patch.object(
            GainLifePreventionAftermath,
            "amount",
            lambda value, _prevented: value.fixed_amount,
        ):
            with self.assertRaises(AssertionError):
                assert_scaled_aftermath()

    def test_prevention_damage_aftermath_quantity_mutant_is_killed(self):
        aftermath = DealDamagePreventionAftermath(
            source=damage_module.DamageSourceSnapshot(
                ref="palm",
                object_id="palm-object",
                logical_object_id="palm-incarnation",
                controller="A",
                owner="A",
            ),
            recipient=DamageAftermathRecipient(
                kind="prevented_source_controller"
            ),
            per_prevented=1,
        )

        def assert_scaled_damage() -> None:
            self.assertEqual(3, aftermath.amount(3))

        assert_scaled_damage()
        with patch.object(
            DealDamagePreventionAftermath,
            "amount",
            lambda value, _prevented: value.fixed_amount,
        ):
            with self.assertRaises(AssertionError):
                assert_scaled_damage()

    def test_damage_replacement_prevention_mutants_are_killed(self):
        condition = {
            "source_controller_relation": "any",
            "target_controller_relation": "any",
            "target_kinds": [],
            "source_types_all": [],
            "target_types_all": [],
            "combat": None,
        }
        quantity_descriptor = {
            "handler_id": "replacement.damage.quantity.v1",
            "schema_version": 1,
            "event": "damage",
            "condition": condition,
            "modification": {"multiplier": 2, "additional": 0},
        }
        prevention_descriptor = {
            "handler_id": "prevention.damage.fixed.v1",
            "schema_version": 1,
            "event": "damage",
            "condition": condition,
            "modification": {"amount": 1},
        }
        context = DamageReplacementSourceContext(
            source_ref="damage-mutation-source",
            source_controller="A",
        )
        event = replacement_effects.ReplaceableEvent(
            event_id="damage:mutation",
            kind="damage",
            affected_player="B",
            payload={
                "amount": 3,
                "prevented": 0,
                "unpreventable": False,
            },
        )

        def assert_prevent_then_double() -> None:
            quantity = (
                DamageQuantityReplacementHandler().replacement_effect(
                    quantity_descriptor, context
                )
            )
            prevention = FixedDamagePreventionHandler().replacement_effect(
                prevention_descriptor, context
            )
            resolved = replacement_effects.resolve_replacements(
                event,
                (quantity, prevention),
                selections=(prevention.effect_id, quantity.effect_id),
            )
            self.assertEqual(4, resolved.payload["amount"])
            self.assertEqual(1, resolved.payload["prevented"])

        assert_prevent_then_double()
        original_quantity = (
            DamageQuantityReplacementHandler.replacement_effect
        )

        def identity_quantity_mutant(handler, descriptor, source_context):
            effect = original_quantity(handler, descriptor, source_context)
            return replace(
                effect,
                operations=(
                    {"op": "multiply", "field": "amount", "factor": 1},
                ),
            )

        with patch.object(
            DamageQuantityReplacementHandler,
            "replacement_effect",
            identity_quantity_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_prevent_then_double()

        original_prevention = FixedDamagePreventionHandler.replacement_effect

        def skip_prevention_mutant(handler, descriptor, source_context):
            effect = original_prevention(
                handler, descriptor, source_context
            )
            return replace(effect, operations=({"op": "prevent", "amount": 0},))

        with patch.object(
            FixedDamagePreventionHandler,
            "replacement_effect",
            skip_prevention_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_prevent_then_double()

    def test_persistent_prevention_commit_mutant_is_killed(self):
        def assert_shield_is_consumed() -> None:
            session = make_session(
                self.db,
                self.mishra,
                self.zimone,
                players=2,
                seed=615_900,
            )
            keep_all(session)
            engine = session.engine
            source_ref = engine.create_token(
                "A",
                name="Damage Source",
                characteristics={
                    "type_line": "Token Creature — Test",
                    "power": "1",
                    "toughness": "1",
                },
            )[0]
            engine.state.damage_prevention_shields.append(
                DamagePreventionShield(
                    shield_id="mutation-shield",
                    source_id="mutation-effect",
                    controller="B",
                    subject=DamageSubject("B", "player", "B"),
                    mode=PreventionMode.AMOUNT,
                    remaining=3,
                    duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                    created_turn_sequence=engine.state.turn_sequence,
                )
            )
            proposal = damage_module.damage_proposal(
                engine,
                proposal_id="damage:prevention-mutation",
                actor="A",
                source_ref=source_ref,
                target="B",
                amount=2,
                combat=False,
                reason="prevention mutation witness",
            )
            prepared = damage_module.prepare_damage_batch(
                engine, (proposal,)
            )
            damage_module.commit_prepared_damage_batch(engine, prepared)
            self.assertEqual(
                1, engine.state.damage_prevention_shields[0].remaining
            )

        assert_shield_is_consumed()
        with patch.object(
            damage_module,
            "commit_damage_modifier_plan",
            lambda _host, _plan: None,
        ):
            with self.assertRaises(AssertionError):
                assert_shield_is_consumed()

    def test_prevention_trigger_quantity_mutant_is_killed(self):
        source = DamageSourceSnapshot(
            ref="prevention-source",
            object_id="prevention-source-object",
            logical_object_id="prevention-source-incarnation",
            controller="B",
            owner="B",
            zone="stack",
            types=("instant",),
        )
        result = DrawCardsPreventionTrigger(
            player="B",
            per_prevented=1,
        )
        occurrence = PreventionTriggerOccurrence(
            ability=PreventionTriggeredAbility(
                controller="B",
                source=source,
                label="Damage prevented this way",
                results=(result,),
            ),
            effect_id="prevention.shield:mutation",
            prevented_amount=4,
            damage_event_ids=("damage:mutation",),
            prevented_source_controllers=("A",),
        )

        def assert_scaled_draw() -> None:
            effects = occurrence.runtime_effects()
            self.assertEqual(1, len(effects))
            self.assertEqual(4, effects[0]["count"])

        assert_scaled_draw()
        with patch.object(
            DrawCardsPreventionTrigger,
            "amount",
            lambda value, prevented: value.fixed_amount,
        ):
            with self.assertRaises(AssertionError):
                assert_scaled_draw()

    def test_trigger_apnap_grouping_mutant_is_killed(self):
        host = SimpleNamespace(
            apnap_order=lambda: ("C", "D", "A", "B")
        )
        values = (
            {"controller": "A", "ref": "trigger-a"},
            {"controller": "C", "ref": "trigger-c"},
            {"controller": "B", "ref": "trigger-b"},
        )

        def assert_apnap_grouping() -> None:
            groups = CommanderEngine._semantic_trigger_groups(host, values)
            self.assertEqual(
                ["C", "A", "B"],
                [group["controller"] for group in groups],
            )

        def alphabetical_grouping(_host, candidates):
            return [
                {
                    "controller": controller,
                    "items": [
                        dict(value)
                        for value in candidates
                        if value["controller"] == controller
                    ],
                }
                for controller in ("A", "B", "C", "D")
                if any(
                    value["controller"] == controller
                    for value in candidates
                )
            ]

        assert_apnap_grouping()
        with patch.object(
            CommanderEngine,
            "_semantic_trigger_groups",
            alphabetical_grouping,
        ):
            with self.assertRaises(AssertionError):
                assert_apnap_grouping()

    def test_chosen_source_incarnation_mutants_are_killed(self):
        chosen = ChosenDamageSource(
            ref="C1",
            object_id="physical-source",
            snapshot_version=2,
            logical_object_id="spell-incarnation",
            oracle_id="source-oracle",
            printed_name="Chosen Source",
            controller="A",
            owner="A",
            zone="stack",
            types=("creature",),
            identity_keys=(
                "spell-incarnation|stack",
                "spell-incarnation|battlefield",
            ),
        )
        shield = DamagePreventionShield(
            shield_id="chosen-source-shield",
            source_id="prevention-effect",
            controller="B",
            subject=DamageSubject("B", "player", "B"),
            mode=PreventionMode.NEXT_INSTANCE,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=1,
            chosen_source=chosen,
        )

        def damage_event(identity_key: str) -> replacement_effects.ReplaceableEvent:
            return replacement_effects.ReplaceableEvent(
                event_id=f"damage:{identity_key}",
                kind="damage",
                affected_player="B",
                payload={
                    "amount": 1,
                    "target": "B",
                    "target_kind": "player",
                    "source_object_id": "physical-source",
                    "source_identity_key": identity_key,
                },
            )

        def assert_incarnation_boundary() -> None:
            effect = damage_prevention_module._shield_replacement_effect(shield)
            self.assertIsNotNone(
                replacement_effects.replacement_choice(
                    damage_event("spell-incarnation|battlefield"),
                    (effect,),
                )
            )
            self.assertIsNone(
                replacement_effects.replacement_choice(
                    damage_event("new-incarnation|battlefield"),
                    (effect,),
                )
            )

        assert_incarnation_boundary()

        with patch.object(
            ChosenDamageSource,
            "event_conditions",
            lambda value: {
                "source_object_id": {"eq": value.object_id},
            },
        ):
            with self.assertRaises(AssertionError):
                assert_incarnation_boundary()

        with patch.object(
            ChosenDamageSource,
            "event_conditions",
            lambda value: {
                "source_identity_key": {
                    "eq": next(
                        key
                        for key in value.identity_keys
                        if key.endswith("|stack")
                    ),
                },
            },
        ):
            with self.assertRaises(AssertionError):
                assert_incarnation_boundary()

    def test_static_redirection_mutant_is_killed(self):
        descriptor = {
            "handler_id": "replacement.damage.redirect-to-source.v1",
            "schema_version": 1,
            "event": "damage",
            "condition": {
                "source_controller_relation": "any",
                "target_controller_relation": "source_controller",
                "target_kinds": ["player"],
                "source_types_all": [],
                "target_types_all": [],
                "combat": None,
            },
            "modification": {"destination": "source"},
        }
        destination = replacement_effects.RedirectDamage(
            target="C1",
            target_kind="permanent",
            target_controller="B",
            target_object_id="destination-object",
            target_logical_object_id="destination-incarnation",
            target_owner="B",
            target_types=("creature",),
        )
        context = DamageReplacementSourceContext(
            source_ref="C1",
            source_controller="B",
            source_destination=destination,
        )
        event = replacement_effects.ReplaceableEvent(
            event_id="damage:redirection-mutation",
            kind="damage",
            affected_player="B",
            payload={
                "source_controller": "A",
                "target": "B",
                "target_kind": "player",
                "target_controller": "B",
                "amount": 2,
                "prevented": 0,
                "unpreventable": False,
                "combat": False,
            },
        )

        def assert_redirected() -> None:
            effect = StaticDamageRedirectionHandler().replacement_effect(
                descriptor, context
            )
            resolved = replacement_effects.resolve_replacements(
                event, (effect,), selections=(effect.effect_id,)
            )
            self.assertEqual("C1", resolved.payload["target"])
            self.assertEqual(
                "destination-object", resolved.affected_object.object_id
            )

        assert_redirected()
        original = StaticDamageRedirectionHandler.replacement_effect

        def retain_recipient_mutant(handler, mapping, source_context):
            effect = original(handler, mapping, source_context)
            return replace(
                effect,
                operations=(
                    replacement_effects.RedirectDamage(
                        target="B",
                        target_kind="player",
                        target_controller="B",
                    ),
                ),
            )

        with patch.object(
            StaticDamageRedirectionHandler,
            "replacement_effect",
            retain_recipient_mutant,
        ):
            with self.assertRaises(AssertionError):
                assert_redirected()
