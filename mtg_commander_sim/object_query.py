from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .object_predicate import (
    ObjectQueryError,
    ObjectQuerySpec,
    validate_chosen_damage_source_predicate,
)
from .replacement.immutable import FrozenMap


@dataclass(frozen=True, slots=True)
class ObjectQueryResult:
    object_id: str
    ref: str
    printed_name: str
    owner: str
    controller: str
    zone: str
    types: tuple[str, ...] = ()
    subtypes: tuple[str, ...] = ()
    supertypes: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    counters: FrozenMap = field(default_factory=FrozenMap)
    mana_value: int = 0
    token: bool = False
    tapped: bool = False
    phased_out: bool = False
    known_to_actor: bool = True
    attached_to_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.counters, FrozenMap):
            object.__setattr__(self, "counters", FrozenMap(self.counters))


def object_query_result(
    card: Any,
    effective: Mapping[str, Any],
    *,
    type_parts: tuple[Iterable[str], Iterable[str], Iterable[str]],
    known_to_actor: bool,
    attached_to_ref: str | None,
) -> ObjectQueryResult:
    types, subtypes, supertypes = type_parts
    return ObjectQueryResult(
        object_id=str(card.object_id),
        ref=str(card.ref),
        printed_name=str(card.printed_name),
        owner=str(card.owner),
        controller=str(card.controller),
        zone=str(card.zone),
        types=tuple(sorted(str(value).casefold() for value in types)),
        subtypes=tuple(sorted(str(value).casefold() for value in subtypes)),
        supertypes=tuple(
            sorted(str(value).casefold() for value in supertypes)
        ),
        colors=tuple(
            str(value).upper() for value in effective.get("colors", ())
        ),
        keywords=tuple(
            str(value).casefold() for value in effective.get("keywords", ())
        ),
        counters=FrozenMap(card.counters),
        mana_value=int(effective.get("mana_value") or 0),
        token=bool(card.is_token),
        tapped=bool(card.tapped),
        phased_out=bool(card.phased_out),
        known_to_actor=known_to_actor,
        attached_to_ref=attached_to_ref,
    )


def object_matches_query(
    row: ObjectQueryResult,
    spec: ObjectQuerySpec,
) -> bool:
    types = frozenset(row.types)
    return bool(
        (not spec.zones or row.zone in spec.zones)
        and (spec.owner is None or row.owner == spec.owner)
        and (spec.controller is None or row.controller == spec.controller)
        and set(spec.types_all).issubset(types)
        and (not spec.types_any or not types.isdisjoint(spec.types_any))
        and types.isdisjoint(spec.excluded_types)
        and set(spec.subtypes_all).issubset(row.subtypes)
        and set(spec.supertypes_all).issubset(row.supertypes)
        and set(spec.colors_all).issubset(row.colors)
        and (not spec.colors_any or not set(spec.colors_any).isdisjoint(row.colors))
        and set(spec.keywords_all).issubset(row.keywords)
        and (spec.token is None or row.token is spec.token)
        and (spec.tapped is None or row.tapped is spec.tapped)
        and (spec.include_phased_out or not row.phased_out)
        and (
            spec.known_to_actor is None
            or row.known_to_actor is spec.known_to_actor
        )
        and (spec.exclude_ref is None or row.ref != spec.exclude_ref)
    )


def query_objects(
    rows: Iterable[ObjectQueryResult],
    spec: ObjectQuerySpec,
) -> tuple[ObjectQueryResult, ...]:
    """Filter immutable rules facts without applying target legality."""

    return tuple(row for row in rows if object_matches_query(row, spec))


__all__ = [
    "ObjectQueryError",
    "ObjectQueryResult",
    "ObjectQuerySpec",
    "object_matches_query",
    "object_query_result",
    "query_objects",
    "validate_chosen_damage_source_predicate",
]
