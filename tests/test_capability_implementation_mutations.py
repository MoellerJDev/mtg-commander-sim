from __future__ import annotations

import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
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
