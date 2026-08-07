from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .characteristic_evaluation import type_parts
from .combat_constraints import DeclarationRestriction
from .keyword_abilities import (
    EffectiveKeywordError,
    normalized_characteristic_keywords,
)


MENACE_KEYWORD = "menace"


class MenaceRuleError(ValueError):
    """A represented Menace input or blocker count is malformed."""


def _validate_attacker_ref(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise MenaceRuleError(
            "Menace attacker reference must be a canonical nonempty string"
        )
    return value


@dataclass(frozen=True, slots=True)
class MenaceBlockRestriction:
    """The conditional minimum for one current Menace attacker."""

    attacker_ref: str
    minimum_blockers: int = 2

    def __post_init__(self) -> None:
        _validate_attacker_ref(self.attacker_ref)
        if (
            isinstance(self.minimum_blockers, bool)
            or not isinstance(self.minimum_blockers, int)
            or self.minimum_blockers != 2
        ):
            raise MenaceRuleError(
                "Ordinary Menace requires exactly two blockers when blocked"
            )

    def declaration_restriction(self) -> DeclarationRestriction:
        return DeclarationRestriction(
            restriction_id=f"block:{self.attacker_ref}:menace",
            kind="minimum_option_uses",
            option=self.attacker_ref,
            count=self.minimum_blockers,
            when_used=True,
            label=(
                f"{self.attacker_ref} has menace and must be blocked by "
                "zero or at least two creatures"
            ),
        )


def current_menace_restriction(
    data: Mapping[str, Any],
    attacker_ref: str,
    *,
    is_attacking: bool,
) -> MenaceBlockRestriction | None:
    """Return the ordinary restriction for one current represented attacker."""

    if not isinstance(data, Mapping):
        raise MenaceRuleError("Effective characteristics must be a mapping")
    _validate_attacker_ref(attacker_ref)
    if not isinstance(is_attacking, bool):
        raise MenaceRuleError("Menace combat participation must be boolean")
    type_line = data.get("type_line", "")
    if not isinstance(type_line, str):
        raise MenaceRuleError("Effective type line must be a string")
    if "creature" not in type_parts(type_line)[0]:
        return None
    try:
        keywords = normalized_characteristic_keywords(data)
    except EffectiveKeywordError as exc:
        raise MenaceRuleError(str(exc)) from exc
    if not is_attacking or MENACE_KEYWORD not in keywords:
        return None
    return MenaceBlockRestriction(attacker_ref=attacker_ref)


__all__ = [
    "MENACE_KEYWORD",
    "MenaceBlockRestriction",
    "MenaceRuleError",
    "current_menace_restriction",
]
