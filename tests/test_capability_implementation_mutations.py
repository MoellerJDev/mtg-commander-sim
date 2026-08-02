from __future__ import annotations

import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim import replacement_effects
from mtg_commander_sim import tap_state
from mtg_commander_sim.damage import DamageEvent
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.targets import PUBLIC_TARGET_ZONES, TargetGroup


def _event(*, assigned: int, dealt: int, prevented: int) -> DamageEvent:
    return DamageEvent(
        source="C1",
        source_object_id="source-object",
        source_logical_object_id="source-incarnation",
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

    def test_damage_amount_guard_mutant_is_killed(self):
        def assert_negative_assignment_rejected() -> None:
            with self.assertRaisesRegex(ValueError, "positive assignment"):
                _event(assigned=-1, dealt=-1, prevented=0)

        assert_negative_assignment_rejected()
        with patch.object(DamageEvent, "__post_init__", lambda _event: None):
            with self.assertRaises(AssertionError):
                assert_negative_assignment_rejected()

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
        )
        engine.move_card(
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

        def assert_all_permanent_results() -> None:
            card.marked_damage = 0
            card.counters["loyalty"] = 4
            card.counters["defense"] = 5
            result = engine._apply_damage_results_to_permanent(card, 2)
            self.assertEqual(2, result["marked_damage"])
            self.assertEqual(2, result["loyalty_removed"])
            self.assertEqual(2, result["defense_removed"])

        assert_all_permanent_results()

        def creature_only_mutant(
            _engine: CommanderEngine,
            target,
            amount: int,
            *,
            deathtouch: bool = False,
        ):
            target.marked_damage += int(amount)
            target.deathtouch_damage = target.deathtouch_damage or deathtouch
            return {"amount": int(amount), "marked_damage": int(amount)}

        with patch.object(
            CommanderEngine,
            "_apply_damage_results_to_permanent",
            creature_only_mutant,
        ):
            with self.assertRaises((AssertionError, KeyError)):
                assert_all_permanent_results()

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
