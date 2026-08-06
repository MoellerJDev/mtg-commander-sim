from __future__ import annotations

from typing import TYPE_CHECKING

from .characteristic_evaluation import type_parts
from .combat_evasion import (
    CombatantEvasionCharacteristics,
    CombatEvasionRuleError,
    CombatEvasionVerdict,
    combat_evasion_verdict,
)
from .keyword_abilities import normalized_characteristic_keywords
from .landwalk import BASIC_LAND_TYPES, LandwalkRuleError

if TYPE_CHECKING:
    from .engine import CommanderEngine
    from .model import CardInstance


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
    attacker: CardInstance,
    blocker: CardInstance,
    defending_player: str,
) -> CombatEvasionVerdict:
    """Compose the pure verdict from one narrow authoritative-state query."""

    return combat_evasion_verdict(
        combatant_evasion_characteristics(engine, attacker),
        combatant_evasion_characteristics(engine, blocker),
        defending_basic_land_types(engine, defending_player),
    )


def combatant_evasion_characteristics(
    engine: CommanderEngine,
    card: CardInstance,
) -> CombatantEvasionCharacteristics:
    """Project one combatant's current public represented characteristics."""

    data = engine._effective_card_data(card)
    type_line = data.get("type_line", "")
    if not isinstance(type_line, str):
        raise CombatEvasionRuleError("Effective type line must be a string")
    raw_colors = data.get("colors", ())
    if not isinstance(raw_colors, (list, tuple, set, frozenset)) or any(
        not isinstance(color, str) or not color.strip()
        for color in raw_colors
    ):
        raise CombatEvasionRuleError("Effective colors are malformed")
    raw_power = data.get("power")
    try:
        int(str(raw_power))
    except (TypeError, ValueError):
        power = None
    else:
        power = engine._numeric_stat(card.object_id, "power")
    return CombatantEvasionCharacteristics(
        keywords=normalized_characteristic_keywords(data),
        colors=frozenset(color.strip().upper() for color in raw_colors),
        card_types=frozenset(type_parts(type_line)[0]),
        power=power,
    )


__all__ = [
    "combatant_evasion_characteristics",
    "defending_basic_land_types",
    "engine_combat_evasion_verdict",
]
