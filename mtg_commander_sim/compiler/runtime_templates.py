from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .continuous_templates import basic_land_type_addition_handler
from .damage_templates import static_damage_handler


@dataclass(frozen=True, slots=True)
class StaticRuntimeTemplate:
    compiled: tuple[str, Mapping[str, Any], str]
    kind: str
    event: str
    dependency_reason: str


def static_runtime_template(
    text: str,
    *,
    source_damageable: bool | None = None,
) -> StaticRuntimeTemplate | None:
    """Select one closed static runtime production for an Oracle line."""

    basic_land_type = basic_land_type_addition_handler(text)
    if basic_land_type is not None:
        return StaticRuntimeTemplate(
            compiled=basic_land_type,
            kind="static_ability",
            event="characteristics.evaluate",
            dependency_reason=(
                "generic basic-land-type addition depends on an untrusted "
                "rules capability"
            ),
        )
    static_damage = static_damage_handler(text)
    if static_damage is None:
        return None
    if (
        static_damage[1]["handler_id"]
        == "replacement.damage.redirect-to-source.v1"
        and source_damageable is False
    ):
        # Damage can be redirected only to an object that can receive damage.
        # Keeping this type check at compilation prevents a future artifact or
        # enchantment with superficially similar wording from being promoted
        # to a trusted program that can only fail at runtime.
        return None
    return StaticRuntimeTemplate(
        compiled=static_damage,
        kind=(
            "prevention_effect"
            if static_damage[1]["handler_id"].startswith("prevention.")
            else "replacement_effect"
        ),
        event="damage",
        dependency_reason=(
            "generic damage replacement depends on an untrusted rules "
            "capability"
        ),
    )
