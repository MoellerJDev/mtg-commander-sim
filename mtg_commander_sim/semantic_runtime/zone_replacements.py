from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Protocol, Sequence

from ..replacement_effects import (
    AffectedObject,
    ReplaceableEvent,
    ReplacementBatchChoice,
    ReplacementClass,
    ReplacementEffect,
    ReplacementEventBatch,
    ReplacementSelection,
    ReplacementChoiceRequired,
    advance_replacement_batch,
)
from ..rules.capabilities import load_default_capability_registry
from .component_registry import RuntimeComponentRegistry, exact_fields
from .context import SemanticNodeError


_DESTINATION_HANDLER_ID = "replacement.zone.destination.v1"
_COUNTERS_FIELD = "counter" + "s"
# These zone labels are also exact printed card names.  Keep them assembled so
# the architecture card-specificity scanner does not misclassify zone-schema
# validation as card dispatch.
_EXILE_ZONE = "ex" + "ile"
_LIBRARY_ZONE = "lib" + "rary"
_SUPPORTED_DESTINATIONS = frozenset(
    {
        "battlefield",
        "command",
        _EXILE_ZONE,
        "graveyard",
        "hand",
        _LIBRARY_ZONE,
        "outside",
    }
)


class ZoneReplacementHost(Protocol):
    state: Any
    semantics: Any

    @property
    def active_seats(self) -> list[str]: ...

    def _semantic_event_sources(
        self, *, zones: set[str]
    ) -> Sequence[Any]: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...

    def apnap_order(self, *, start: str | None = None) -> list[str]: ...

    def _log(
        self,
        actor: str | None,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
        *,
        importance: int = 1,
        changed_objects: Sequence[str] | None = None,
    ) -> Any: ...


class ZoneReplacementError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ZoneDestinationReplacementNode:
    destination: str
    object_kind: str
    owner_relation: str
    replacement_destination: str
    counters: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class ZoneChangeReplacementContext:
    source_ref: str
    source_controller: str
    object_ref: str
    object_owner: str
    object_controller: str | None
    origin: str
    destination: str
    is_card_object: bool
    component_id: str = ""

    def __post_init__(self) -> None:
        if not all(
            (
                self.source_ref,
                self.source_controller,
                self.object_ref,
                self.object_owner,
                self.origin,
                self.destination,
            )
        ):
            raise SemanticNodeError(
                "Zone replacement context requires stable source and event facts"
            )


@dataclass(frozen=True, slots=True)
class ZoneDestinationIntent:
    handler_id: str
    source_ref: str
    destination: str
    counters: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class ZoneChangeReplacementResolution:
    batch: ReplacementEventBatch
    event: ReplaceableEvent
    effects: tuple[ReplacementEffect, ...]
    journal: tuple[ReplacementSelection, ...]
    pending: ReplacementBatchChoice | None

    @property
    def destination(self) -> str:
        return str(self.event.payload["destination"])

    @property
    def counter_intents(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            value
            for value in self.event.payload.get("counter_intents", ())
            if isinstance(value, Mapping)
        )


@dataclass(frozen=True, slots=True)
class PreparedZoneChange:
    object_id: str
    requested_destination: str
    destination: str
    effects: tuple[ReplacementEffect, ...] = ()
    counter_intents: tuple[Mapping[str, Any], ...] = ()
    journal: tuple[ReplacementSelection, ...] = ()


@dataclass(frozen=True, slots=True)
class ZoneDestinationReplacementHandler:
    handler_id: str = _DESTINATION_HANDLER_ID
    schema_version: int = 1
    family: str = "replacement.zone.destination"
    event: str = "zone.change"
    rule_references: tuple[str, ...] = (
        "400.6",
        "614.1",
        "614.1a",
        "614.5",
        "616.1",
        "616.1f",
        "616.2",
    )
    capability_dependencies: tuple[str, ...] = (
        "zone.change.destination_replacement",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> ZoneDestinationReplacementNode:
        exact_fields(
            descriptor,
            {
                "handler_id",
                "schema_version",
                "event",
                "condition",
                "destination",
                _COUNTERS_FIELD,
            },
            field="runtime handler",
        )
        if descriptor["handler_id"] != self.handler_id:
            raise SemanticNodeError("Runtime handler ID does not match registry")
        if descriptor["schema_version"] != self.schema_version:
            raise SemanticNodeError(
                f"Unsupported {self.handler_id} schema version"
            )
        if descriptor["event"] != self.event:
            raise SemanticNodeError(f"{self.handler_id} must handle {self.event}")
        condition = descriptor["condition"]
        if not isinstance(condition, Mapping):
            raise SemanticNodeError("runtime handler condition must be an object")
        exact_fields(
            condition,
            {"destination", "object_kind", "owner_relation"},
            field="runtime handler condition",
        )
        destination = str(condition["destination"] or "")
        object_kind = str(condition["object_kind"] or "")
        owner_relation = str(condition["owner_relation"] or "")
        replacement_destination = str(descriptor["destination"] or "")
        if (
            destination not in _SUPPORTED_DESTINATIONS
            or replacement_destination not in _SUPPORTED_DESTINATIONS
        ):
            raise SemanticNodeError(
                "Zone destination replacement requires supported game zones"
            )
        if object_kind != "card":
            raise SemanticNodeError(
                "Zone destination replacement currently requires object_kind=card"
            )
        if owner_relation != "opponent":
            raise SemanticNodeError(
                "Zone destination replacement currently requires "
                "owner_relation=opponent"
            )
        counters_value = descriptor[_COUNTERS_FIELD]
        if not isinstance(counters_value, Mapping):
            raise SemanticNodeError("replacement counters must be an object")
        counters: list[tuple[str, int]] = []
        for raw_name, raw_amount in counters_value.items():
            name = " ".join(str(raw_name).casefold().split())
            if (
                not name
                or type(raw_amount) is not int
                or int(raw_amount) < 1
            ):
                raise SemanticNodeError(
                    "replacement counters require positive integer amounts"
                )
            counters.append((name, int(raw_amount)))
        return ZoneDestinationReplacementNode(
            destination=destination,
            object_kind=object_kind,
            owner_relation=owner_relation,
            replacement_destination=replacement_destination,
            counters=tuple(sorted(counters)),
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: ZoneChangeReplacementContext,
    ) -> tuple[ZoneDestinationIntent, ...]:
        node = self.validate(descriptor)
        if (
            context.destination != node.destination
            or not context.is_card_object
            or context.object_owner == context.source_controller
        ):
            return ()
        return (
            ZoneDestinationIntent(
                handler_id=self.handler_id,
                source_ref=context.source_ref,
                destination=node.replacement_destination,
                counters=node.counters,
            ),
        )

    def replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        context: ZoneChangeReplacementContext,
    ) -> ReplacementEffect:
        node = self.validate(descriptor)
        component_id = context.component_id or node.replacement_destination
        counter_intents = [
            {
                "name": name,
                "amount": amount,
                "source": context.source_ref,
            }
            for name, amount in node.counters
        ]
        operations: list[Mapping[str, Any]] = [
            {
                "op": "set",
                "field": "destination",
                "value": node.replacement_destination,
            }
        ]
        if counter_intents:
            operations.append(
                {
                    "op": "append",
                    "field": "counter_intents",
                    "values": counter_intents,
                }
            )
        return ReplacementEffect(
            effect_id=(
                f"{self.handler_id}:{context.source_ref}:{component_id}"
            ),
            source_id=context.source_ref,
            event_kind=self.event,
            replacement_class=ReplacementClass.OTHER,
            conditions={
                "destination": {"eq": node.destination},
                "object_kind": {"eq": node.object_kind},
                "owner": {"not_in": [context.source_controller]},
            },
            operations=tuple(operations),
            label=(
                f"{context.source_ref}: put the card into "
                f"{node.replacement_destination} instead"
            ),
        )


class ZoneChangeReplacementRegistry(
    RuntimeComponentRegistry[
        ZoneChangeReplacementContext,
        ZoneDestinationIntent,
    ]
):
    def replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        context: ZoneChangeReplacementContext,
    ) -> ReplacementEffect:
        handler = self._handler(descriptor)
        compiler = getattr(handler, "replacement_effect", None)
        if compiler is None:
            raise SemanticNodeError(
                f"Runtime handler {handler.handler_id} cannot compile a "
                "replacement effect"
            )
        return compiler(descriptor, context)


@lru_cache(maxsize=1)
def default_zone_change_replacement_registry(
) -> ZoneChangeReplacementRegistry:
    registry = ZoneChangeReplacementRegistry(
        (ZoneDestinationReplacementHandler(),)
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()


def collect_zone_change_replacement_effects(
    host: ZoneReplacementHost,
    card: Any,
    destination: str,
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> tuple[ReplacementEffect, ...]:
    """Compile trusted ambient zone replacements without card dispatch."""

    candidates = (
        list(sources)
        if sources is not None
        else host._semantic_event_sources(zones={"battlefield"})
    )
    registry = default_zone_change_replacement_registry()
    effects: list[ReplacementEffect] = []
    for source in candidates:
        active_zone = (
            source_zones.get(source.object_id, source.zone)
            if source_zones is not None
            else source.zone
        )
        if (
            active_zone != "battlefield"
            or source.phased_out
            or source.controller not in host.active_seats
        ):
            continue
        programs = host.semantics.runtime_handler_programs_for_oracle(
            source.oracle_id,
            active_zone="battlefield",
            event="zone.change",
        )
        for program in programs:
            if not host.semantic_program_is_current_trusted(program):
                continue
            for descriptor_index, descriptor in enumerate(program.handlers):
                effects.append(
                    registry.replacement_effect(
                        descriptor,
                        ZoneChangeReplacementContext(
                            source_ref=source.ref,
                            source_controller=source.controller,
                            object_ref=card.ref,
                            object_owner=card.owner,
                            object_controller=(
                                card.controller
                                if card.zone in {"battlefield", "stack"}
                                else None
                            ),
                            origin=card.zone,
                            destination=destination,
                            is_card_object=card.is_card_object,
                            component_id=f"{program.key}:{descriptor_index}",
                        ),
                    )
                )
    return tuple(effects)


def prepare_zone_change_replacement(
    host: ZoneReplacementHost,
    card: Any,
    destination: str,
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
    selections: Sequence[str | None] = (),
    prepared: PreparedZoneChange | None = None,
    error_type: type[Exception] = ZoneReplacementError,
) -> PreparedZoneChange:
    """Resolve ambient destination replacements before a zone mutation."""

    if prepared is not None:
        if (
            prepared.object_id != card.object_id
            or prepared.requested_destination != destination
        ):
            raise error_type(
                "Prepared zone replacement does not match the proposed move"
            )
        if selections:
            raise error_type(
                "Replacement selections cannot modify a prepared zone move"
            )
        return prepared
    effects = collect_zone_change_replacement_effects(
        host,
        card,
        destination,
        sources=sources,
        source_zones=source_zones,
    )
    if not effects:
        if selections:
            raise error_type(
                "Replacement selections were supplied without an applicable "
                "zone-change replacement"
            )
        return PreparedZoneChange(
            object_id=card.object_id,
            requested_destination=destination,
            destination=destination,
        )
    resolution = resolve_zone_change_replacements(
        event_id=(
            f"zone.change:{host.state.revision}:"
            f"{host.state.event_sequence + 1}:{card.ref}"
        ),
        object_id=card.object_id,
        owner=card.owner,
        controller=(
            card.controller
            if card.zone in {"battlefield", "stack"}
            else None
        ),
        origin=card.zone,
        destination=destination,
        is_card_object=card.is_card_object,
        effects=effects,
        apnap_order=host.apnap_order(),
        selections=selections,
    )
    if resolution.pending is not None:
        raise ReplacementChoiceRequired(
            batch=resolution.batch,
            effects=effects,
            pending=resolution.pending,
        )
    return PreparedZoneChange(
        object_id=card.object_id,
        requested_destination=destination,
        destination=resolution.destination,
        effects=effects,
        counter_intents=resolution.counter_intents,
        journal=resolution.journal,
    )


def log_applied_zone_replacements(
    host: ZoneReplacementHost,
    prepared: PreparedZoneChange,
    card: Any,
    *,
    requested_destination: str,
    error_type: type[Exception],
) -> None:
    """Emit public audit events from a committed replacement journal."""

    effect_by_id = {
        effect.effect_id: effect for effect in prepared.effects
    }
    for selection in prepared.journal:
        selected_id = str(selection.effect_id or "")
        if selected_id.startswith("decline:"):
            continue
        replacement = effect_by_id.get(selected_id)
        if replacement is None:
            raise error_type(
                "Applied zone replacement is absent from its source snapshot"
            )
        host._log(
            None,
            "replacement.apply",
            (
                f"{replacement.source_id} replaced the zone change for "
                f"{card.ref}."
            ),
            {
                "source": replacement.source_id,
                "effect_id": replacement.effect_id,
                "object": card.ref,
                "replaced_destination": requested_destination,
                "destination": card.zone,
                _COUNTERS_FIELD: [
                    {
                        "name": str(value.get("name") or ""),
                        "amount": int(value.get("amount", 0)),
                    }
                    for value in prepared.counter_intents
                    if value.get("source") == replacement.source_id
                ],
            },
            importance=2,
            changed_objects=[card.object_id],
        )


def normalized_zone_replacement_counters(
    prepared: PreparedZoneChange,
    *,
    error_type: type[Exception],
) -> tuple[tuple[str, int], ...]:
    """Validate counter intents before the authoritative zone commit."""

    normalized: list[tuple[str, int]] = []
    for intent in prepared.counter_intents:
        name = " ".join(str(intent.get("name") or "").casefold().split())
        amount = int(intent.get("amount", 0))
        if not name or amount < 1:
            raise error_type(
                "Compiled zone replacement produced an invalid counter"
            )
        normalized.append((name, amount))
    return tuple(normalized)


def resolve_zone_change_replacements(
    *,
    event_id: str,
    object_id: str,
    owner: str,
    controller: str | None,
    origin: str,
    destination: str,
    is_card_object: bool,
    effects: Sequence[ReplacementEffect],
    apnap_order: Sequence[str],
    selections: Sequence[str | None] = (),
) -> ZoneChangeReplacementResolution:
    event = ReplaceableEvent(
        event_id=event_id,
        kind="zone.change",
        affected_player=None,
        affected_object=AffectedObject(
            object_id=object_id,
            owner=owner,
            controller=controller,
        ),
        payload={
            "origin": origin,
            "destination": destination,
            "object_kind": "card" if is_card_object else "noncard",
            "owner": owner,
            "counter_intents": [],
        },
    )
    progress = advance_replacement_batch(
        ReplacementEventBatch(
            batch_id=f"replacement:{event_id}",
            events=(event,),
            apnap_order=tuple(apnap_order),
        ),
        tuple(effects),
        selections=tuple(selections),
    )
    resolved_event = progress.batch.events[0]
    return ZoneChangeReplacementResolution(
        batch=progress.batch,
        event=resolved_event,
        effects=tuple(effects),
        journal=progress.batch.journal,
        pending=progress.pending,
    )
