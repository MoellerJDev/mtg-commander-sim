from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .direct_target import (
    compiled_direct_target,
    direct_target_effect,
    permanent_target_schema,
)


class ReturnToHandTarget(str, Enum):
    ARTIFACT = "artifact"
    CREATURE = "creature"
    ENCHANTMENT = "enchantment"
    LAND = "land"
    NONLAND_PERMANENT = "nonland permanent"
    PERMANENT = "permanent"
    ARTIFACT_OR_ENCHANTMENT = "artifact or enchantment"
    CREATURE_OR_PLANESWALKER = "creature or planeswalker"

    @property
    def card_types(self) -> tuple[str, ...]:
        if self is ReturnToHandTarget.NONLAND_PERMANENT:
            return ()
        return tuple(self.value.split(" or "))


@dataclass(frozen=True, slots=True)
class TargetedReturnToHandEffectTemplate:
    """Closed lowering for one mandatory direct battlefield return."""

    target: ReturnToHandTarget

    def __post_init__(self) -> None:
        if not isinstance(self.target, ReturnToHandTarget):
            raise ValueError("Return-to-hand target domain is unsupported")

    @property
    def template_id(self) -> str:
        return "return-target-" + self.target.value.replace(" ", "-") + "-v2"

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return direct_target_effect("bounce", reference_field="card")

    @property
    def target_schema(self) -> Mapping[str, Any]:
        return permanent_target_schema(
            types_none=(
                ("land",)
                if self.target is ReturnToHandTarget.NONLAND_PERMANENT
                else ()
            ),
            types_any=(
                self.target.card_types
                if self.target
                not in {
                    ReturnToHandTarget.NONLAND_PERMANENT,
                    ReturnToHandTarget.PERMANENT,
                }
                else ()
            ),
        )

    @property
    def mechanics(self) -> tuple[str, ...]:
        return ("return-to-owner-hand", "cr-115-targets")

    def compiled(
        self,
    ) -> tuple[
        str,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any],
        tuple[str, ...],
    ]:
        return compiled_direct_target(
            template_id=self.template_id,
            effects=self.effects,
            target_schema=self.target_schema,
            mechanics=self.mechanics,
        )


def targeted_return_to_hand_effect_template(
    text: str,
) -> TargetedReturnToHandEffectTemplate | None:
    match = re.fullmatch(
        r"return target (?P<target>artifact|creature|enchantment|land|"
        r"nonland permanent|permanent|artifact or enchantment|"
        r"creature or planeswalker) to its owner['’]s hand\.?",
        text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    return TargetedReturnToHandEffectTemplate(
        ReturnToHandTarget(match.group("target").casefold())
    )


__all__ = [
    "ReturnToHandTarget",
    "TargetedReturnToHandEffectTemplate",
    "targeted_return_to_hand_effect_template",
]
