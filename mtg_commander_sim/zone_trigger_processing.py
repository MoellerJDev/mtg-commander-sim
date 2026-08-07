from __future__ import annotations

import copy
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from .model import CardInstance, StackItem
from .trigger_processing import enqueue_trigger_batch
from .zone_trigger_events import (
    ZoneChangeOccurrence,
    normalized_zone_trigger_events,
)


_EXILE_ZONE = "ex" + "ile"
_DEFAULT_SEMANTIC_SOURCE_ZONES = frozenset(
    {"battlefield", "graveyard", _EXILE_ZONE, "command", "hand"}
)


class ZoneTriggerProcessingHost(Protocol):
    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> Sequence[CardInstance]: ...

    def _effective_card_data(
        self, card: CardInstance
    ) -> Mapping[str, Any]: ...

    def _dispatch_semantic_event(
        self,
        event: str,
        context: Mapping[str, Any],
        *,
        sources: Sequence[CardInstance] | None = None,
        source_zones: Mapping[str, str] | None = None,
        source_characteristics: Mapping[
            str, Mapping[str, Any]
        ] | None = None,
        trigger_batch: list[StackItem] | None = None,
    ) -> list[str]: ...

    def _record_turn_history(
        self,
        kind: str,
        *,
        actor: str,
        object_incarnation: str,
        types: set[str],
    ) -> None: ...

    def _add_saga_lore(
        self,
        saga: CardInstance,
        *,
        trigger_batch: list[StackItem] | None = None,
        reason: str,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class DepartureTriggerSnapshot:
    sources: tuple[CardInstance, ...] = ()
    source_zones: Mapping[str, str] = field(default_factory=dict)
    source_characteristics: Mapping[
        str, Mapping[str, Any]
    ] = field(default_factory=dict)


def semantic_event_sources(
    cards: Iterable[CardInstance],
    *,
    active_seats: Collection[str],
    zones: set[str] | None = None,
) -> list[CardInstance]:
    """Select zone-visible sources without coupling discovery to the engine."""

    active_zones = zones or _DEFAULT_SEMANTIC_SOURCE_ZONES
    return [
        card
        for card in cards
        if card.zone in active_zones
        and (card.controller in active_seats or card.owner in active_seats)
    ]


def capture_departure_trigger_sources(
    host: ZoneTriggerProcessingHost,
    *,
    semantic_events: bool,
    origin: str,
) -> DepartureTriggerSnapshot:
    """Snapshot battlefield trigger sources and LKI before zone mutation."""

    if not semantic_events or origin not in {"battlefield", "stack"}:
        return DepartureTriggerSnapshot((), {}, {})
    source_zones = None
    if origin == "stack":
        source_zones = {
            "battlefield",
            "graveyard",
            _EXILE_ZONE,
            "command",
            "hand",
            "stack",
        }
    sources = tuple(
        copy.deepcopy(source)
        for source in host._semantic_event_sources(zones=source_zones)
    )
    return DepartureTriggerSnapshot(
        sources=sources,
        source_zones={source.object_id: source.zone for source in sources},
        source_characteristics={
            source.object_id: copy.deepcopy(
                host._effective_card_data(source)
            )
            for source in sources
        },
    )


def dispatch_zone_change_occurrence(
    host: ZoneTriggerProcessingHost,
    occurrence: ZoneChangeOccurrence,
    card: CardInstance,
    *,
    departure_sources: Sequence[CardInstance],
    departure_source_zones: Mapping[str, str],
    departure_source_characteristics: Mapping[
        str, Mapping[str, Any]
    ],
    trigger_batch: list[StackItem] | None = None,
) -> None:
    """Detect represented events from immutable facts, then use CR 603.3."""

    owns_trigger_batch = trigger_batch is None
    pending = trigger_batch if trigger_batch is not None else []
    events = normalized_zone_trigger_events(occurrence)
    for event in events:
        context = event.context
        if event.source_timing == "before":
            host._dispatch_semantic_event(
                event.kind,
                context,
                sources=departure_sources,
                source_zones=departure_source_zones,
                source_characteristics=departure_source_characteristics,
                trigger_batch=pending,
            )
        else:
            host._dispatch_semantic_event(
                event.kind,
                context,
                trigger_batch=pending,
            )
    previous_types = set(
        str(value)
        for event in events
        if event.kind == "permanent.leave"
        for value in event.context.get("types", ())
    )
    if (
        occurrence.origin == "battlefield"
        and occurrence.destination == "graveyard"
        and "creature" in previous_types
    ):
        host._record_turn_history(
            "creature_died",
            actor=occurrence.previous_controller,
            object_incarnation=occurrence.previous_logical_object_id,
            types=previous_types,
        )
    if any(
        event.kind == "permanent.enter"
        and "saga" in event.context.get("subtypes", ())
        for event in events
    ):
        host._add_saga_lore(
            card,
            trigger_batch=pending,
            reason="Saga entered",
        )
    if owns_trigger_batch:
        enqueue_trigger_batch(host, pending)


__all__ = [
    "ZoneTriggerProcessingHost",
    "DepartureTriggerSnapshot",
    "capture_departure_trigger_sources",
    "dispatch_zone_change_occurrence",
    "semantic_event_sources",
]
