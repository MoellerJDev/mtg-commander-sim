from __future__ import annotations

from types import SimpleNamespace
import unittest

from quorune.counter_state import (
    CounterChange,
    CounterStateError,
    commit_counter_changes,
    plan_counter_changes,
)
from quorune.model import CardInstance, PlayerState


class CounterStateTests(unittest.TestCase):
    @staticmethod
    def host():
        card = CardInstance(
            object_id="permanent:1",
            ref="A01",
            oracle_id="oracle:1",
            printed_name="Counter Fixture",
            owner="A",
            controller="A",
            zone="battlefield",
            counters={"loyalty": 3},
        )
        state = SimpleNamespace(
            players={"A": PlayerState("A", "A")},
            cards={card.object_id: card},
        )
        return SimpleNamespace(state=state), card

    def test_player_and_permanent_counters_share_one_atomic_plan(self):
        host, card = self.host()
        plan = plan_counter_changes(
            host,
            (
                CounterChange("player", "A", "Poison", 2),
                CounterChange(
                    "permanent",
                    card.object_id,
                    "loyalty",
                    -5,
                    expected_zone="battlefield",
                    expected_logical_object_id=card.logical_object_id,
                ),
                CounterChange(
                    "permanent",
                    card.object_id,
                    "-1/-1",
                    2,
                    expected_zone="battlefield",
                    expected_logical_object_id=card.logical_object_id,
                ),
            ),
        )

        self.assertEqual(0, host.state.players["A"].poison)
        self.assertEqual({"loyalty": 3}, card.counters)
        transitions = commit_counter_changes(host, plan)

        self.assertEqual(2, host.state.players["A"].poison)
        self.assertEqual({"-1/-1": 2}, card.counters)
        self.assertEqual(-3, transitions[1].applied_delta)
        self.assertEqual(("A",), plan.changed_players)
        self.assertEqual((card.object_id,), plan.changed_objects)

    def test_unsupported_player_counter_fails_before_mutation(self):
        host, _card = self.host()
        with self.assertRaisesRegex(
            CounterStateError, "no represented state owner"
        ):
            plan_counter_changes(
                host,
                (CounterChange("player", "A", "experience", 1),),
            )
        self.assertEqual(0, host.state.players["A"].poison)

    def test_stale_permanent_identity_rolls_back_whole_batch(self):
        host, card = self.host()
        plan = plan_counter_changes(
            host,
            (
                CounterChange("player", "A", "poison", 1),
                CounterChange(
                    "permanent",
                    card.object_id,
                    "loyalty",
                    -1,
                    expected_zone="battlefield",
                    expected_logical_object_id=card.logical_object_id,
                ),
            ),
        )
        card.zone_change_counter += 1

        with self.assertRaisesRegex(
            CounterStateError, "changed object identity"
        ):
            commit_counter_changes(host, plan)
        self.assertEqual(0, host.state.players["A"].poison)
        self.assertEqual({"loyalty": 3}, card.counters)

    def test_malformed_change_is_rejected(self):
        with self.assertRaisesRegex(
            CounterStateError, "players or permanents"
        ):
            CounterChange("spell", "A01", "charge", 1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(CounterStateError, "integers"):
            CounterChange("player", "A", "poison", 1.5)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
