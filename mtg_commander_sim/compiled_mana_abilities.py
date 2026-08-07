from __future__ import annotations

"""Runtime access to trusted, source-pinned activated mana descriptors."""

from typing import Any

from .color_set_mana_abilities import (
    COLOR_SET_MANA_HANDLER_ID,
    ColorSetActivatedManaAbilitySpec,
)
from .compiled_activated_abilities import (
    CompiledActivatedAbilityHost,
    trusted_face_handler_family_present,
    trusted_face_handler_programs,
)
from .fixed_mana_abilities import (
    FIXED_MANA_HANDLER_ID,
    FixedActivatedManaAbilitySpec,
)
from .semantic_runtime.color_set_mana_abilities import (
    color_set_mana_specs_from_descriptors,
)
from .semantic_runtime.mana_abilities import fixed_mana_specs_from_descriptors


CompiledManaAbilityHost = CompiledActivatedAbilityHost


def compiled_fixed_mana_abilities(
    host: CompiledManaAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
) -> tuple[FixedActivatedManaAbilitySpec, ...]:
    """Return exact descriptors only for the unchanged current printed face."""

    result: list[FixedActivatedManaAbilitySpec] = []
    programs = trusted_face_handler_programs(
        host,
        card,
        executable_oracle_text=executable_oracle_text,
        active_zone="battlefield",
        event="activate",
    )
    for program in programs:
        result.extend(fixed_mana_specs_from_descriptors(program.handlers))
    return tuple(sorted(result, key=lambda spec: spec.line_index))


def compiled_color_set_mana_abilities(
    host: CompiledManaAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
) -> tuple[ColorSetActivatedManaAbilitySpec, ...]:
    """Return exact dynamic descriptors for the unchanged current face."""

    result: list[ColorSetActivatedManaAbilitySpec] = []
    programs = trusted_face_handler_programs(
        host,
        card,
        executable_oracle_text=executable_oracle_text,
        active_zone="battlefield",
        event="activate",
    )
    for program in programs:
        result.extend(
            color_set_mana_specs_from_descriptors(program.handlers)
        )
    return tuple(sorted(result, key=lambda spec: spec.line_index))


def compiled_fixed_mana_family_present(
    host: CompiledManaAbilityHost,
    card: Any,
) -> bool:
    """Return whether the current face has a trusted fixed-mana owner."""

    return trusted_face_handler_family_present(
        host,
        card,
        active_zone="battlefield",
        event="activate",
        handler_id=FIXED_MANA_HANDLER_ID,
    )


def compiled_color_set_mana_family_present(
    host: CompiledManaAbilityHost,
    card: Any,
) -> bool:
    """Return whether the current face has a trusted color-set mana owner."""

    return trusted_face_handler_family_present(
        host,
        card,
        active_zone="battlefield",
        event="activate",
        handler_id=COLOR_SET_MANA_HANDLER_ID,
    )


__all__ = [
    "CompiledManaAbilityHost",
    "compiled_color_set_mana_abilities",
    "compiled_color_set_mana_family_present",
    "compiled_fixed_mana_abilities",
    "compiled_fixed_mana_family_present",
]
