from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Protocol

from ...abilities import ActivatedAbility, parse_activated_abilities
from ...card_overrides.game_record_v3 import (
    historical_granted_activated_ability_descriptors,
)
from ...mana import BASIC_LAND_MANA
from ...util import normalize_mana_bundle


_GRANTED_ABILITY_PREFIX = "granted_activated_ability:"


class ActivatedAbilityQueryHost(Protocol):
    def _effective_card_data(self, card: Any) -> dict[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...


def activated_abilities(
    host: ActivatedAbilityQueryHost,
    card: Any,
) -> tuple[ActivatedAbility, ...]:
    """Compile printed, intrinsic, and explicitly granted activated abilities."""

    data = host._effective_card_data(card)
    abilities = list(
        parse_activated_abilities(
            card_name=str(data.get("name") or card.printed_name),
            oracle_text=str(data.get("oracle_text") or ""),
            keywords=tuple(data.get("keywords") or ()),
        )
    )
    _append_intrinsic_land_abilities(host, data, abilities)
    abilities.extend(_granted_abilities(card, data))
    return tuple(abilities)


def _append_intrinsic_land_abilities(
    host: ActivatedAbilityQueryHost,
    data: dict[str, Any],
    abilities: list[ActivatedAbility],
) -> None:
    card_types, subtypes, _ = host._type_parts(str(data.get("type_line") or ""))
    if "land" not in card_types:
        return
    represented = {
        color
        for ability in abilities
        if ability.mana_ability
        for color in re.findall(
            r"Add\s+\{([WUBRG])\}", ability.effect_text, re.IGNORECASE
        )
    }
    for subtype, color in BASIC_LAND_MANA.items():
        if subtype in subtypes and color not in represented:
            abilities.append(
                ActivatedAbility(
                    ability_id=f"intrinsic_{subtype}",
                    line_index=20_000 + len(abilities),
                    oracle_line=f"{{T}}: Add {{{color}}}.",
                    cost_text="{T}",
                    effect_text=f"Add {{{color}}}.",
                    zones=("battlefield",),
                    mana=normalize_mana_bundle(None),
                    tap_source=True,
                    mana_ability=True,
                )
            )


def _granted_abilities(
    card: Any,
    data: dict[str, Any],
) -> tuple[ActivatedAbility, ...]:
    result: list[ActivatedAbility] = []
    descriptors = [
        str(marker).removeprefix(_GRANTED_ABILITY_PREFIX)
        for marker, active in sorted(card.annotations.items())
        if active and str(marker).startswith(_GRANTED_ABILITY_PREFIX)
    ]
    descriptors.extend(
        historical_granted_activated_ability_descriptors(card.annotations)
    )
    for descriptor in descriptors:
        ability_id, separator, oracle_line = descriptor.partition(":")
        if not separator or not ability_id or not oracle_line:
            continue
        parsed = parse_activated_abilities(
            card_name=str(data.get("name") or card.printed_name),
            oracle_text=oracle_line,
            keywords=(),
        )
        if len(parsed) != 1:
            continue
        result.append(
            replace(
                parsed[0],
                ability_id=ability_id,
                line_index=30_000 + len(result),
            )
        )
    return tuple(result)


__all__ = ["ActivatedAbilityQueryHost", "activated_abilities"]
