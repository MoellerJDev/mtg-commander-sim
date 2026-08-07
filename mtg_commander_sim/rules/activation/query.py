from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Protocol

from ...abilities import ActivatedAbility, parse_activated_abilities
from ...ability_fragments import (
    canonical_ability_fragments,
    granted_activated_specs,
)
from ...card_overrides.game_record_v3 import (
    historical_granted_activated_ability_descriptors,
)
from ...compiled_mana_abilities import (
    compiled_color_set_mana_abilities,
    compiled_color_set_mana_family_present,
    compiled_fixed_mana_abilities,
    compiled_fixed_mana_family_present,
)
from ...compiled_cycling_abilities import (
    compiled_ordinary_cycling_abilities,
    compiled_ordinary_cycling_family_present,
)
from ...fixed_mana_abilities import FixedManaMode
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
    executable_oracle_text = str(
        data.get(
            "executable_oracle_text",
            data.get("oracle_text") or "",
        )
    )
    compiled_mana = compiled_fixed_mana_abilities(
        host,
        card,
        executable_oracle_text=executable_oracle_text,
    )
    compiled_color_set_mana = compiled_color_set_mana_abilities(
        host,
        card,
        executable_oracle_text=executable_oracle_text,
    )
    compiled_cycling = compiled_ordinary_cycling_abilities(
        host,
        card,
        executable_oracle_text=executable_oracle_text,
    )
    stale_compiled_family = (
        (
            not compiled_mana
            and compiled_fixed_mana_family_present(host, card)
        )
        or (
            not compiled_color_set_mana
            and compiled_color_set_mana_family_present(host, card)
        )
        or (
            not compiled_cycling
            and compiled_ordinary_cycling_family_present(host, card)
        )
    )
    owned_lines = {
        spec.line_index
        for spec in (
            *compiled_mana,
            *compiled_color_set_mana,
            *compiled_cycling,
        )
    }
    runtime_lines = executable_oracle_text.splitlines()
    for line_index in owned_lines:
        if 0 <= line_index < len(runtime_lines):
            runtime_lines[line_index] = ""
    runtime_oracle_text = (
        "" if stale_compiled_family else "\n".join(runtime_lines)
    )
    abilities = list(
        parse_activated_abilities(
            card_name=str(data.get("name") or card.printed_name),
            oracle_text=runtime_oracle_text,
            keywords=tuple(data.get("keywords") or ()),
        )
    )
    abilities.extend(
        spec.to_activated_ability() for spec in compiled_mana
    )
    abilities.extend(
        spec.to_activated_ability() for spec in compiled_color_set_mana
    )
    abilities.extend(
        spec.to_activated_ability() for spec in compiled_cycling
    )
    abilities.sort(key=lambda ability: ability.line_index)
    _append_intrinsic_land_abilities(host, data, abilities)
    abilities.extend(_typed_granted_abilities(data))
    abilities.extend(_granted_abilities(card, data))
    return tuple(abilities)


def _typed_granted_abilities(
    data: dict[str, Any],
) -> tuple[ActivatedAbility, ...]:
    specs = granted_activated_specs(
        canonical_ability_fragments(data.get("ability_fragments", ()))
    )
    counts: dict[str, int] = {}
    result: list[ActivatedAbility] = []
    for index, spec in enumerate(specs):
        ordinal = counts.get(spec.ability_id, 0) + 1
        counts[spec.ability_id] = ordinal
        result.append(
            ActivatedAbility(
                ability_id=(
                    spec.ability_id
                    if ordinal == 1
                    else f"{spec.ability_id}#{ordinal}"
                ),
                line_index=25_000 + index,
                oracle_line=f"{spec.cost_text}: {spec.effect_text}",
                cost_text=spec.cost_text,
                effect_text=spec.effect_text,
                zones=("battlefield",),
                mana={
                    key: spec.mana_bundle.get(key, 0)
                    for key in ("GENERIC", "W", "U", "B", "R", "G", "C")
                },
                tap_source=spec.tap_source,
                sorcery_speed=spec.sorcery_speed,
                builtin_semantic_key=spec.semantic_key,
            )
        )
    return tuple(result)


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
                    fixed_mana_outputs=(
                        FixedManaMode.from_bundle({color: 1}),
                    ),
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
