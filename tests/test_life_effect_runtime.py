from __future__ import annotations

from types import SimpleNamespace
import unittest

from mtg_commander_sim.effect_runtime import life_effects
from mtg_commander_sim.errors import GameRuleError


class _State:
    def __init__(self, seats: tuple[str, ...]) -> None:
        self._seats = seats
        self.revision = 0
        self.event_sequence = 0
        self.players = {
            seat: SimpleNamespace(life=40)
            for seat in seats
            if seat != "missing"
        }

    def active_seats(self) -> tuple[str, ...]:
        return self._seats


class _Host:
    def __init__(self, seats: tuple[str, ...] = ("A", "B", "C")) -> None:
        self.state = _State(seats)
        self.active_seats = list(seats)
        self.logs: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _log(self, *args, **kwargs) -> None:
        self.logs.append((args, kwargs))

    def apnap_order(self, *, start: str | None = None) -> list[str]:
        seats = list(self.active_seats)
        if start is None or start not in seats:
            return seats
        index = seats.index(start)
        return [*seats[index:], *seats[:index]]

    def _semantic_event_sources(self, *, zones=None) -> list[object]:
        return []

    def semantic_program_is_current_trusted(self, program: object) -> bool:
        return False


class LifeEffectRuntimeTests(unittest.TestCase):
    @staticmethod
    def apply(host: _Host, effect: dict[str, object], actor: str = "A"):
        operation = str(effect["op"])
        return life_effects.apply_effect(
            host,
            effect,
            actor=actor,
            operation=operation,
            reason="test life effect",
        )

    def test_life_and_loss_commit_through_the_typed_batch_owner(self):
        host = _Host()

        self.assertEqual(
            43,
            self.apply(host, {"op": "life", "player": "A", "delta": 3}),
        )
        self.assertEqual(
            35,
            self.apply(
                host,
                {"op": "lose_life", "player": "B", "amount": 5},
            ),
        )
        self.assertEqual(43, host.state.players["A"].life)
        self.assertEqual(35, host.state.players["B"].life)

    def test_table_wide_loss_and_drain_are_simultaneous_typed_batches(self):
        host = _Host()

        self.assertEqual(
            2,
            self.apply(host, {"op": "lose_life_each_opponent", "amount": 2}),
        )
        self.assertEqual((40, 38, 38), self._life(host))

        self.assertEqual(
            1,
            self.apply(host, {"op": "drain_each_opponent", "amount": 1}),
        )
        self.assertEqual((41, 37, 37), self._life(host))

    def test_invalid_batch_member_rolls_back_every_life_change(self):
        host = _Host(("A", "B", "missing"))

        with self.assertRaises(GameRuleError):
            self.apply(host, {"op": "lose_life_each_opponent", "amount": 2})

        self.assertEqual(40, host.state.players["B"].life)

    def test_family_rejects_an_operation_it_does_not_own(self):
        host = _Host()

        with self.assertRaisesRegex(GameRuleError, "Unsupported owned effect"):
            life_effects.apply_effect(
                host,
                {"op": "damage"},
                actor="A",
                operation="damage",
                reason="wrong family",
            )

    @staticmethod
    def _life(host: _Host) -> tuple[int, ...]:
        return tuple(host.state.players[seat].life for seat in ("A", "B", "C"))


if __name__ == "__main__":
    unittest.main()
