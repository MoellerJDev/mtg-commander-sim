from __future__ import annotations

from types import SimpleNamespace
import unittest

from mtg_commander_sim.life_state import (
    LifeChange,
    LifeStateError,
    commit_life_changes,
    plan_life_changes,
)
from mtg_commander_sim.model import PlayerState


class LifeStateTests(unittest.TestCase):
    @staticmethod
    def host():
        state = SimpleNamespace(
            players={
                "A": PlayerState("A", "A", life=20),
                "B": PlayerState("B", "B", life=40),
            },
            active_seats=lambda: ["A", "B"],
        )
        return SimpleNamespace(state=state)

    def test_gain_and_loss_share_one_typed_plan(self):
        host = self.host()
        plan = plan_life_changes(
            host,
            (
                LifeChange("A", 3),
                LifeChange("B", -5),
                LifeChange("A", 2),
            ),
        )

        self.assertEqual(20, host.state.players["A"].life)
        self.assertEqual(40, host.state.players["B"].life)
        transitions = commit_life_changes(host, plan)

        self.assertEqual(25, host.state.players["A"].life)
        self.assertEqual(35, host.state.players["B"].life)
        self.assertEqual(3, len(transitions))
        self.assertEqual(("A", "B"), plan.changed_players)

    def test_stale_life_plan_fails_before_mutation(self):
        host = self.host()
        plan = plan_life_changes(
            host,
            (LifeChange("A", 3), LifeChange("B", -5)),
        )
        host.state.players["B"].life = 39

        with self.assertRaisesRegex(
            LifeStateError, "stale|changed before commit"
        ):
            commit_life_changes(host, plan)
        self.assertEqual(20, host.state.players["A"].life)
        self.assertEqual(39, host.state.players["B"].life)

    def test_inactive_player_and_malformed_change_fail_closed(self):
        host = self.host()
        host.state.active_seats = lambda: ["A"]
        with self.assertRaisesRegex(LifeStateError, "not active"):
            plan_life_changes(host, (LifeChange("B", -1),))
        with self.assertRaisesRegex(LifeStateError, "integers"):
            LifeChange("A", 1.5)  # type: ignore[arg-type]
        with self.assertRaisesRegex(LifeStateError, "require a player"):
            LifeChange("", 1)


if __name__ == "__main__":
    unittest.main()
