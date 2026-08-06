from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol


class DeathtouchError(ValueError):
    """A represented deathtouch fact is malformed."""


class DeathtouchSource(Protocol):
    keywords: tuple[str, ...]


def _normalized_strings(
    values: Iterable[object],
    *,
    label: str,
) -> frozenset[str]:
    if (
        not isinstance(values, Iterable)
        or isinstance(values, (str, bytes, Mapping))
    ):
        raise DeathtouchError(f"{label} must be a collection")
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise DeathtouchError(
                f"{label} must contain nonempty strings"
            )
        result.add(" ".join(value.casefold().split()))
    return frozenset(result)


def _identity_strings(
    values: Iterable[object],
    *,
    label: str,
) -> frozenset[str]:
    if (
        not isinstance(values, Iterable)
        or isinstance(values, (str, bytes, Mapping))
    ):
        raise DeathtouchError(f"{label} must be a collection")
    result: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value:
            raise DeathtouchError(
                f"{label} must contain nonempty strings"
            )
        result.add(value)
    return frozenset(result)


def source_has_deathtouch(source: DeathtouchSource) -> bool:
    """Read CR 702.2 from an already-pinned source characteristic snapshot."""

    return "deathtouch" in _normalized_strings(
        source.keywords,
        label="Damage source keywords",
    )


def deathtouch_assignment_is_lethal(
    *,
    source: str,
    amount: int,
    deathtouch_sources: Iterable[str],
) -> bool:
    """Return CR 702.2c's lethal-assignment contribution."""

    if not isinstance(source, str) or not source:
        raise DeathtouchError(
            "Deathtouch assignment source must be a nonempty string"
        )
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise DeathtouchError(
            "Deathtouch assignment amount must be a nonnegative integer"
        )
    sources = _identity_strings(
        deathtouch_sources,
        label="Deathtouch assignment sources",
    )
    return amount > 0 and source in sources


def deathtouch_damage_result_applies(
    *,
    amount: int,
    source_keywords: Iterable[str],
    target_types: Iterable[str],
) -> bool:
    """Return whether final dealt damage creates the CR 702.2b marker."""

    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise DeathtouchError(
            "Deathtouch damage amount must be a nonnegative integer"
        )
    keywords = _normalized_strings(
        source_keywords,
        label="Damage source keywords",
    )
    types = _normalized_strings(
        target_types,
        label="Damage recipient types",
    )
    return amount > 0 and "deathtouch" in keywords and "creature" in types


__all__ = [
    "deathtouch_assignment_is_lethal",
    "deathtouch_damage_result_applies",
    "DeathtouchError",
    "DeathtouchSource",
    "source_has_deathtouch",
]
