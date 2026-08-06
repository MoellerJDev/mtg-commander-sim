from __future__ import annotations

from typing import TYPE_CHECKING

from .characteristic_evaluation import type_parts
from .combat_evasion import CombatEvasionVerdict, combat_evasion_verdict
from .landwalk import BASIC_LAND_TYPES, LandwalkRuleError

if TYPE_CHECKING:
    from .engine import CommanderEngine


def defending_basic_land_types(
    engine: CommanderEngine,
    defending_player: str,
) -> frozenset[str]:
    """Read the defender's current effective public battlefield land types."""

    if (
        not isinstance(defending_player, str)
        or not defending_player
        or defending_player not in engine.state.players
    ):
        raise LandwalkRuleError("Landwalk requires a current defending player")
    result: set[str] = set()
    for card in sorted(engine.state.cards.values(), key=lambda value: value.ref):
        if (
            card.zone != "battlefield"
            or card.phased_out
            or card.controller != defending_player
        ):
            continue
        data = engine._effective_card_data(card)
        type_line = data.get("type_line", "")
        if not isinstance(type_line, str):
            raise LandwalkRuleError("Effective type line must be a string")
        card_types, subtypes, _ = type_parts(type_line)
        if "land" in card_types:
            result.update(subtypes.intersection(BASIC_LAND_TYPES))
    return frozenset(result)


def engine_combat_evasion_verdict(
    engine: CommanderEngine,
    attacker_keywords: frozenset[str],
    blocker_keywords: frozenset[str],
    defending_player: str,
) -> CombatEvasionVerdict:
    """Compose the pure verdict from one narrow authoritative-state query."""

    return combat_evasion_verdict(
        attacker_keywords,
        blocker_keywords,
        defending_basic_land_types(engine, defending_player),
    )


__all__ = [
    "defending_basic_land_types",
    "engine_combat_evasion_verdict",
]
