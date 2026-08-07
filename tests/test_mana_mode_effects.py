from __future__ import annotations

from types import SimpleNamespace
import unittest

from quorune.errors import GameRuleError
from quorune.mana_mode_effects import (
    apply_mana_mode_effects,
    compile_mana_mode_effects,
    DealDamageToController,
    PayLife,
    SacrificeManaSource,
)


class _State:
    def __init__(self) -> None:
        self.players = {"A": SimpleNamespace(life=10)}
        self.revision = 0
        self.event_sequence = 0

    def active_seats(self) -> tuple[str, ...]:
        return ("A",)


class _Host:
    def __init__(self) -> None:
        self.state = _State()
        self.moves: list[tuple[str, str, str, bool]] = []

    def move_card(
        self,
        object_id: str,
        destination: str,
        *,
        reason: str,
        semantic_events: bool,
    ) -> None:
        self.moves.append((object_id, destination, reason, semantic_events))


class ManaModeEffectTests(unittest.TestCase):
    def test_closed_effect_vocabulary_lowers_to_typed_values(self):
        effects = compile_mana_mode_effects(
            (
                {"op": "damage_self", "amount": 1},
                {"op": "pay_life", "amount": 2},
                {"op": "sacrifice_source"},
            )
        )

        self.assertEqual(
            (
                DealDamageToController(0, 1),
                PayLife(1, 2),
                SacrificeManaSource(2),
            ),
            effects,
        )

    def test_malformed_or_unknown_effects_fail_closed(self):
        invalid = (
            ({"op": "damage_self", "amount": True},),
            ({"op": "pay_life", "amount": -1},),
            ({"op": "sacrifice_source", "extra": 1},),
            ({"op": "arbitrary_callback"},),
            ("damage_self",),
        )

        for effects in invalid:
            with self.subTest(effects=effects):
                with self.assertRaises(GameRuleError):
                    compile_mana_mode_effects(effects)  # type: ignore[arg-type]

    def test_complete_vocabulary_is_validated_before_life_mutation(self):
        host = _Host()

        with self.assertRaises(GameRuleError):
            apply_mana_mode_effects(
                host,
                "A",
                (
                    {"op": "pay_life", "amount": 2},
                    {"op": "unsupported"},
                ),
            )

        self.assertEqual(10, host.state.players["A"].life)

    def test_life_payment_and_source_sacrifice_use_typed_owners(self):
        host = _Host()
        source = SimpleNamespace(
            object_id="source-1",
            controller="A",
            zone="battlefield",
        )

        apply_mana_mode_effects(
            host,
            "A",
            (
                {"op": "pay_life", "amount": 3},
                {"op": "sacrifice_source"},
            ),
            source=source,
        )

        self.assertEqual(7, host.state.players["A"].life)
        self.assertEqual(
            [("source-1", "graveyard", "mana ability cost", True)],
            host.moves,
        )

    def test_unpayable_life_cost_fails_without_mutation(self):
        host = _Host()

        with self.assertRaisesRegex(GameRuleError, "Cannot pay more life"):
            apply_mana_mode_effects(
                host,
                "A",
                ({"op": "pay_life", "amount": 11},),
            )

        self.assertEqual(10, host.state.players["A"].life)


if __name__ == "__main__":
    unittest.main()
