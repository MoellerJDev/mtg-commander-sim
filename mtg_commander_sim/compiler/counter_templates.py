from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class CounterTarget(str, Enum):
    SPELL = "spell"
    NONCREATURE_SPELL = "noncreature spell"
    CREATURE_SPELL = "creature spell"
    CREATURE_OR_PLANESWALKER_SPELL = "creature or planeswalker spell"
    INSTANT_OR_SORCERY_SPELL = "instant or sorcery spell"
    SORCERY_SPELL = "sorcery spell"
    INSTANT_SPELL = "instant spell"
    ARTIFACT_OR_ENCHANTMENT_SPELL = "artifact or enchantment spell"
    ARTIFACT_SPELL = "artifact spell"
    CREATURE_OR_ENCHANTMENT_SPELL = "creature or enchantment spell"
    ARTIFACT_OR_CREATURE_SPELL = "artifact or creature spell"
    BLUE_SPELL = "blue spell"
    RED_SPELL = "red spell"
    GREEN_SPELL = "green spell"
    RED_OR_GREEN_SPELL = "red or green spell"
    NONBLUE_SPELL = "nonblue spell"
    COLORLESS_SPELL = "colorless spell"
    ACTIVATED_ABILITY = "activated ability"
    TRIGGERED_ABILITY = "triggered ability"
    ACTIVATED_OR_TRIGGERED_ABILITY = "activated or triggered ability"
    SPELL_OR_ABILITY = "spell, activated ability, or triggered ability"


_TYPE_DOMAINS: dict[CounterTarget, tuple[str, ...]] = {
    CounterTarget.CREATURE_SPELL: ("creature",),
    CounterTarget.CREATURE_OR_PLANESWALKER_SPELL: (
        "creature",
        "planeswalker",
    ),
    CounterTarget.INSTANT_OR_SORCERY_SPELL: ("instant", "sorcery"),
    CounterTarget.SORCERY_SPELL: ("sorcery",),
    CounterTarget.INSTANT_SPELL: ("instant",),
    CounterTarget.ARTIFACT_OR_ENCHANTMENT_SPELL: (
        "artifact",
        "enchantment",
    ),
    CounterTarget.ARTIFACT_SPELL: ("artifact",),
    CounterTarget.CREATURE_OR_ENCHANTMENT_SPELL: (
        "creature",
        "enchantment",
    ),
    CounterTarget.ARTIFACT_OR_CREATURE_SPELL: ("artifact", "creature"),
}
_COLOR_DOMAINS: dict[CounterTarget, tuple[str, ...]] = {
    CounterTarget.BLUE_SPELL: ("U",),
    CounterTarget.RED_SPELL: ("R",),
    CounterTarget.GREEN_SPELL: ("G",),
    CounterTarget.RED_OR_GREEN_SPELL: ("R", "G"),
}


@dataclass(frozen=True, slots=True)
class TargetedCounterEffectTemplate:
    """Closed lowering for one mandatory direct stack counter instruction."""

    target: CounterTarget

    def __post_init__(self) -> None:
        if not isinstance(self.target, CounterTarget):
            raise ValueError("Counter target domain is unsupported")

    @property
    def template_id(self) -> str:
        slug = (
            self.target.value.replace(",", "")
            .replace(" or ", "-or-")
            .replace(" ", "-")
        )
        return f"counter-target-{slug}-v2"

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return ({"op": "counter_stack_target", "stack": "$target.0"},)

    @property
    def target_schema(self) -> Mapping[str, Any]:
        categories = (
            ["spell", "ability"]
            if self.target is CounterTarget.SPELL_OR_ABILITY
            else ["ability"]
            if self.target in {
                CounterTarget.ACTIVATED_ABILITY,
                CounterTarget.TRIGGERED_ABILITY,
                CounterTarget.ACTIVATED_OR_TRIGGERED_ABILITY,
            }
            else ["spell"]
        )
        schema: dict[str, Any] = {
            "zones": ["stack"],
            "categories": categories,
            "source_exclusion": True,
            "count": 1,
        }
        if self.target in _TYPE_DOMAINS:
            schema["types_any"] = list(_TYPE_DOMAINS[self.target])
        elif self.target is CounterTarget.NONCREATURE_SPELL:
            schema["types_none"] = ["creature"]
        elif self.target in _COLOR_DOMAINS:
            schema["colors_any"] = list(_COLOR_DOMAINS[self.target])
        elif self.target is CounterTarget.NONBLUE_SPELL:
            schema["predicate"] = "nonblue_spell"
        elif self.target is CounterTarget.COLORLESS_SPELL:
            schema["colorless"] = True
        elif self.target is CounterTarget.ACTIVATED_ABILITY:
            schema["predicate"] = "activated_ability"
        elif self.target is CounterTarget.TRIGGERED_ABILITY:
            schema["predicate"] = "triggered_ability"
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return ("counter", "cr-115-targets")

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


def targeted_counter_effect_template(
    text: str,
) -> TargetedCounterEffectTemplate | None:
    match = re.fullmatch(
        r"counter target (?P<target>spell|noncreature spell|creature spell|"
        r"creature or planeswalker spell|instant or sorcery spell|"
        r"sorcery spell|instant spell|artifact or enchantment spell|"
        r"artifact spell|creature or enchantment spell|"
        r"artifact or creature spell|blue spell|red spell|green spell|"
        r"red or green spell|nonblue spell|colorless spell|"
        r"activated ability|triggered ability|"
        r"activated or triggered ability|"
        r"spell, activated ability, or triggered ability)\.?",
        text.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return None
    return TargetedCounterEffectTemplate(
        CounterTarget(match.group("target").casefold())
    )


def is_intrinsically_uncounterable_spell(text: str) -> bool:
    """Recognize only the complete intrinsic counter prohibition sentence."""

    return bool(
        re.fullmatch(
            r"this spell can(?:not|'t) be countered\.?",
            text.strip(),
            re.IGNORECASE,
        )
    )


__all__ = [
    "CounterTarget",
    "TargetedCounterEffectTemplate",
    "is_intrinsically_uncounterable_spell",
    "targeted_counter_effect_template",
]
