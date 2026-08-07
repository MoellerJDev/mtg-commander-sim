from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class EffectiveKeywordError(ValueError):
    """The represented current keyword snapshot is malformed."""


class EffectiveKeywordHost(Protocol):
    """Read-only characteristic port shared by keyword rule owners."""

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...


def normalized_effective_keywords(
    host: EffectiveKeywordHost,
    card: Any,
) -> frozenset[str]:
    """Return current represented keywords case-insensitively and redundantly."""

    return normalized_characteristic_keywords(host._effective_card_data(card))


def normalized_characteristic_keywords(
    data: Mapping[str, Any],
) -> frozenset[str]:
    """Normalize one already-computed effective-characteristic snapshot."""

    if not isinstance(data, Mapping):
        raise EffectiveKeywordError(
            "Effective characteristics must be a mapping"
        )
    raw_keywords = data.get("keywords", ())
    if not isinstance(raw_keywords, (list, tuple, set, frozenset)) or any(
        not isinstance(keyword, str) or not keyword.strip()
        for keyword in raw_keywords
    ):
        raise EffectiveKeywordError("Effective keywords are malformed")
    return frozenset(keyword.strip().casefold() for keyword in raw_keywords)


__all__ = [
    "EffectiveKeywordError",
    "EffectiveKeywordHost",
    "normalized_characteristic_keywords",
    "normalized_effective_keywords",
]
