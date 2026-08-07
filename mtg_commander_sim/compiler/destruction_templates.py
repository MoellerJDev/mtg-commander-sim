from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class DestructionTarget(str, Enum):
    ARTIFACT = "artifact"
    CREATURE = "creature"
    ENCHANTMENT = "enchantment"
    LAND = "land"
    PERMANENT = "permanent"
    ARTIFACT_OR_ENCHANTMENT = "artifact or enchantment"
    CREATURE_OR_PLANESWALKER = "creature or planeswalker"

    @property
    def card_types(self) -> tuple[str, ...]:
        return tuple(self.value.split(" or "))


@dataclass(frozen=True, slots=True)
class TargetedDestructionEffectTemplate:
    """Closed lowering for one mandatory direct-target destruction."""

    target: DestructionTarget

    def __post_init__(self) -> None:
        if not isinstance(self.target, DestructionTarget):
            raise ValueError("Destruction target domain is unsupported")

    @property
    def template_id(self) -> str:
        return (
            "destroy-target-"
            + "-or-".join(self.target.card_types)
            + "-v2"
        )

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return ({"op": "destroy", "card": "$target.0"},)

    @property
    def target_schema(self) -> Mapping[str, Any]:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if self.target is not DestructionTarget.PERMANENT:
            schema["types_any"] = list(self.target.card_types)
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return ("destroy", "cr-115-targets")

    def compiled(
        self,
    ) -> tuple[
        str,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any],
        tuple[str, ...],
    ]:
        return (
            self.template_id,
            self.effects,
            self.target_schema,
            self.mechanics,
        )


def targeted_destruction_effect_template(
    text: str,
) -> TargetedDestructionEffectTemplate | None:
    match = re.fullmatch(
        r"destroy target (?P<target>artifact|creature|enchantment|land|"
        r"permanent|artifact or enchantment|creature or planeswalker)\.?",
        text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    return TargetedDestructionEffectTemplate(
        DestructionTarget(match.group("target").casefold())
    )


__all__ = [
    "DestructionTarget",
    "TargetedDestructionEffectTemplate",
    "targeted_destruction_effect_template",
]
