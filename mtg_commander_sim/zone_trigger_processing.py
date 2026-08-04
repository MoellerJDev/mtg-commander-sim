from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from .model import CardInstance, StackItem
from .trigger_processing import enqueue_trigger_batch
from .zone_trigger_events import (
    ZoneChangeOccurrence,
    normalized_zone_trigger_events,
)


class ZoneTriggerProcessingHost(Protocol):
    def _dispatch_semantic_event(
        self,
        event: str,
        context: Mapping[str, Any],
        *,
        sources: Sequence[CardInstance] | None = None,
        source_zones: Mapping[str, str] | None = None,
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


def dispatch_zone_change_occurrence(
    host: ZoneTriggerProcessingHost,
    occurrence: ZoneChangeOccurrence,
    card: CardInstance,
    *,
    departure_sources: Sequence[CardInstance],
    departure_source_zones: Mapping[str, str],
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
    "dispatch_zone_change_occurrence",
]
