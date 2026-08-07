from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class TapStateAction(str, Enum):
    """Closed action vocabulary for one permanent tap-state instruction."""

    TAP = "tap"
    UNTAP = "untap"


class TapStateTarget(str, Enum):
    """Closed public permanent domains supported by the direct clause."""

    ARTIFACT = "artifact"
    CREATURE = "creature"
    LAND = "land"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class TargetedTapStateEffectTemplate:
    """Typed lowering for one whole ``tap/untap target`` instruction."""

    action: TapStateAction
    target: TapStateTarget

    def __post_init__(self) -> None:
        if not isinstance(self.action, TapStateAction):
            raise ValueError("Tap-state action is unsupported")
        if not isinstance(self.target, TapStateTarget):
            raise ValueError("Tap-state target is unsupported")

    @property
    def template_id(self) -> str:
        return f"{self.action.value}-target-{self.target.value}-v2"

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "op": self.action.value,
                "card": "$target.0",
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any]:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if self.target is not TapStateTarget.PERMANENT:
            schema["types_any"] = [self.target.value]
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return ("tap-and-untap", "cr-115-targets")

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


def targeted_tap_state_effect_template(
    text: str,
) -> TargetedTapStateEffectTemplate | None:
    """Recognize only one complete mandatory direct-target instruction."""

    match = re.fullmatch(
        r"(?P<action>tap|untap) target "
        r"(?P<target>artifact|creature|land|permanent)\.?",
        text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    return TargetedTapStateEffectTemplate(
        action=TapStateAction(match.group("action").casefold()),
        target=TapStateTarget(match.group("target").casefold()),
    )


__all__ = [
    "TapStateAction",
    "TapStateTarget",
    "TargetedTapStateEffectTemplate",
    "targeted_tap_state_effect_template",
]
