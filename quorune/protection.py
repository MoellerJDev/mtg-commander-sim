from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol

from .ability_fragments import (
    AbilityFragmentError,
    ProtectionQualityKind,
    ProtectionSpec,
    ability_fragment_from_dict,
    protection_specs,
)
from .characteristic_evaluation import type_parts


class ProtectionVerdict(str, Enum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ProtectionSource:
    colors: frozenset[str] = frozenset()
    card_types: frozenset[str] = frozenset()
    subtypes: frozenset[str] = frozenset()

    @classmethod
    def from_characteristics(
        cls, value: Mapping[str, Any]
    ) -> "ProtectionSource":
        parsed_types, parsed_subtypes, _ = type_parts(
            str(value.get("type_line") or "")
        )
        type_values = value.get(
            "card_types",
            value.get("types", parsed_types),
        )
        subtype_values = value.get("subtypes", parsed_subtypes)
        return cls(
            colors=frozenset(
                str(item).upper() for item in value.get("colors", ())
            ),
            card_types=frozenset(
                str(item).casefold() for item in type_values
            ),
            subtypes=frozenset(
                str(item).casefold() for item in subtype_values
            ),
        )


class ProtectionQueryHost(Protocol):
    state: Any

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...


def source_characteristics_for_ref(
    host: ProtectionQueryHost,
    source_ref: str | None,
) -> Mapping[str, Any] | None:
    """Resolve current typed source characteristics from a public reference."""

    if not source_ref:
        return None
    card = next(
        (
            candidate
            for candidate in host.state.cards.values()
            if candidate.ref == source_ref
        ),
        None,
    )
    if card is None:
        stack_item = next(
            (
                candidate
                for candidate in host.state.stack
                if candidate.ref == source_ref
            ),
            None,
        )
        if stack_item is not None:
            source_id = (
                stack_item.card_object_id
                or stack_item.source_object_id
            )
            card = host.state.cards.get(source_id) if source_id else None
    return host._effective_card_data(card) if card is not None else None


def _typed_protection_specs(
    characteristics: Mapping[str, Any],
) -> tuple[ProtectionSpec, ...] | None:
    raw = characteristics.get("ability_fragments", ())
    if not isinstance(raw, (list, tuple)):
        return None
    try:
        fragments = tuple(
            ability_fragment_from_dict(value)
            for value in raw
        )
    except (AbilityFragmentError, TypeError):
        return None
    return protection_specs(fragments)


def _has_untyped_protection_keyword(
    characteristics: Mapping[str, Any],
) -> bool:
    return any(
        str(value).casefold() == "protection"
        for value in characteristics.get("keywords", ())
    )


def protection_verdict(
    protected_characteristics: Mapping[str, Any],
    source: ProtectionSource | None,
) -> ProtectionVerdict:
    """Evaluate represented DEBT protection qualities without Oracle text.

    A printed Protection keyword without an exact typed fragment is material
    semantic uncertainty.  Callers fail closed instead of assuming that the
    source does or does not match an unparsed quality.
    """

    specs = _typed_protection_specs(protected_characteristics)
    if specs is None:
        return ProtectionVerdict.UNRESOLVED
    if not specs:
        return (
            ProtectionVerdict.UNRESOLVED
            if _has_untyped_protection_keyword(protected_characteristics)
            else ProtectionVerdict.ALLOWED
        )
    if any(
        spec.quality_kind is ProtectionQualityKind.EVERYTHING
        for spec in specs
    ):
        return ProtectionVerdict.BLOCKED
    if source is None:
        return ProtectionVerdict.UNRESOLVED
    for spec in specs:
        if (
            spec.quality_kind is ProtectionQualityKind.COLOR
            and spec.quality in source.colors
        ):
            return ProtectionVerdict.BLOCKED
        if (
            spec.quality_kind is ProtectionQualityKind.CARD_TYPE
            and spec.quality in source.card_types
        ):
            return ProtectionVerdict.BLOCKED
        if (
            spec.quality_kind is ProtectionQualityKind.SUBTYPE
            and spec.quality in source.subtypes
        ):
            return ProtectionVerdict.BLOCKED
    return ProtectionVerdict.ALLOWED


def protection_verdict_for_ref(
    host: ProtectionQueryHost,
    protected_characteristics: Mapping[str, Any],
    source_ref: str | None,
) -> ProtectionVerdict:
    """Apply typed protection using one canonical source-reference query."""

    source_data = source_characteristics_for_ref(host, source_ref)
    source = (
        ProtectionSource.from_characteristics(source_data)
        if source_data is not None
        else None
    )
    return protection_verdict(protected_characteristics, source)


def protection_fragments_to_dicts(
    values: Iterable[ProtectionSpec],
) -> list[dict[str, Any]]:
    from .ability_fragments import ability_fragment_to_dict

    return [ability_fragment_to_dict(value) for value in values]


__all__ = [
    "ProtectionSource",
    "ProtectionVerdict",
    "ProtectionQueryHost",
    "protection_fragments_to_dicts",
    "protection_verdict",
    "protection_verdict_for_ref",
    "source_characteristics_for_ref",
]
