from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from .keyword_abilities import (
    EffectiveKeywordError,
    normalized_characteristic_keywords,
)


DEFENDER_KEYWORD = "defender"


class DefenderRuleError(ValueError):
    """The current characteristic snapshot is malformed."""


class DefenderRuleHost(Protocol):
    """Read-only port used by the bounded CR 702.3 attack restriction."""

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...


def defender_prohibits_attack(
    host: DefenderRuleHost,
    card: Any,
) -> bool:
    """Whether the current represented creature has Defender.

    The declaration coordinator owns every other attacker restriction. This
    query consumes only the current effective type and keyword snapshot, so
    advertised candidates and accepted declarations can share one verdict.
    """

    data = host._effective_card_data(card)
    if not isinstance(data, Mapping):
        raise DefenderRuleError("Effective characteristics must be a mapping")
    type_line = data.get("type_line", "")
    if not isinstance(type_line, str):
        raise DefenderRuleError("Effective type line must be a string")
    if "creature" not in host._type_parts(type_line)[0]:
        return False
    try:
        keywords = normalized_characteristic_keywords(data)
    except EffectiveKeywordError as exc:
        raise DefenderRuleError(str(exc)) from exc
    return DEFENDER_KEYWORD in keywords


__all__ = [
    "DEFENDER_KEYWORD",
    "DefenderRuleError",
    "DefenderRuleHost",
    "defender_prohibits_attack",
]
