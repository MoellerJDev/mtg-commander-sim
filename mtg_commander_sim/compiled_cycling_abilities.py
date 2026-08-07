from __future__ import annotations

"""Runtime access to trusted, source-pinned ordinary Cycling descriptors."""

from typing import Any

from .compiled_activated_abilities import (
    CompiledActivatedAbilityHost,
    trusted_face_handler_family_present,
    trusted_face_handler_programs,
)
from .cycling_abilities import CYCLING_HANDLER_ID, OrdinaryCyclingAbilitySpec
from .semantic_runtime.cycling_abilities import (
    ordinary_cycling_specs_from_descriptors,
)


def compiled_ordinary_cycling_abilities(
    host: CompiledActivatedAbilityHost,
    card: Any,
    *,
    executable_oracle_text: str,
) -> tuple[OrdinaryCyclingAbilitySpec, ...]:
    result = [
        spec
        for program in trusted_face_handler_programs(
            host,
            card,
            executable_oracle_text=executable_oracle_text,
            active_zone="hand",
            event="activate",
        )
        for spec in ordinary_cycling_specs_from_descriptors(program.handlers)
    ]
    return tuple(sorted(result, key=lambda spec: spec.line_index))


def compiled_ordinary_cycling_family_present(
    host: CompiledActivatedAbilityHost,
    card: Any,
) -> bool:
    return trusted_face_handler_family_present(
        host,
        card,
        active_zone="hand",
        event="activate",
        handler_id=CYCLING_HANDLER_ID,
    )


__all__ = [
    "compiled_ordinary_cycling_abilities",
    "compiled_ordinary_cycling_family_present",
]
