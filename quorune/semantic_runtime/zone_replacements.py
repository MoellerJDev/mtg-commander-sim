from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Protocol, Sequence

from ..entry_counters import (
    EntryCounterError,
    intrinsic_entry_counter_effects,
    intrinsic_entry_counters,
)
from ..replacement_effects import (
    AffectedObject,
    CreateAffectedObjectCounter,
    ReplaceableEvent,
    ReplacementBatchChoice,
    ReplacementClass,
    ReplacementEffect,
    ReplacementEventBatch,
    ReplacementSelection,
    ReplacementChoiceRequired,
    advance_replacement_batch,
    replacement_choice,
)
from ..rules.capabilities import load_default_capability_registry
from .component_registry import RuntimeComponentRegistry, exact_fields
from .context import SemanticNodeError
from .counter_replacements import (
    collect_counter_placement_replacement_effects,
)
from .zone_replacement_model import (
    PreparedZoneChange,
    SUPPORTED_ZONE_DESTINATIONS,
    ZoneChangeReplacementContext,
    ZoneChangeReplacementResolution,
    ZoneChangeReplacementSnapshot,
    ZoneChangeSubjectSnapshot,
    ZoneDestinationIntent,
    ZoneDestinationReplacementNode,
    ZoneReplacementError,
)


_DESTINATION_HANDLER_ID = "replacement.zone.destination.v1"
_COUNTERS_FIELD = "counter" + "s"


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

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

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
            destination not in SUPPORTED_ZONE_DESTINATIONS
            or replacement_destination not in SUPPORTED_ZONE_DESTINATIONS
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
        return self._source_replacement_effect(
            node,
            source_ref=context.source_ref,
            source_controller=context.source_controller,
            component_id=(
                context.component_id or node.replacement_destination
            ),
        )

    def source_replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        *,
        source_ref: str,
        source_controller: str,
        component_id: str,
    ) -> ReplacementEffect:
        return self._source_replacement_effect(
            self.validate(descriptor),
            source_ref=source_ref,
            source_controller=source_controller,
            component_id=component_id,
        )

    def _source_replacement_effect(
        self,
        node: ZoneDestinationReplacementNode,
        *,
        source_ref: str,
        source_controller: str,
        component_id: str,
    ) -> ReplacementEffect:
        if not source_ref or not source_controller or not component_id:
            raise SemanticNodeError(
                "Zone replacement sources require stable identity"
            )
        operations: list[Mapping[str, Any]] = [
            {
                "op": "set",
                "field": "destination",
                "value": node.replacement_destination,
            }
        ]
        for index, (name, amount) in enumerate(node.counters):
            operations.append(
                CreateAffectedObjectCounter(
                    counter_name=name,
                    amount=amount,
                    placing_player=source_controller,
                    source_ref=source_ref,
                    sequence=index,
                )
            )
        return ReplacementEffect(
            effect_id=(
                f"{self.handler_id}:{source_ref}:{component_id}"
            ),
            source_id=source_ref,
            event_kind=self.event,
            replacement_class=ReplacementClass.OTHER,
            conditions={
                "destination": {"eq": node.destination},
                "object_kind": {"eq": node.object_kind},
                "owner": {"not_in": [source_controller]},
            },
            operations=tuple(operations),
            label=(
                f"{source_ref}: put the card into "
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

    def source_replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        *,
        source_ref: str,
        source_controller: str,
        component_id: str,
    ) -> ReplacementEffect:
        handler = self._handler(descriptor)
        compiler = getattr(handler, "source_replacement_effect", None)
        if compiler is None:
            raise SemanticNodeError(
                f"Runtime handler {handler.handler_id} cannot compile a "
                "source replacement effect"
            )
        return compiler(
            descriptor,
            source_ref=source_ref,
            source_controller=source_controller,
            component_id=component_id,
        )


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
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> tuple[ReplacementEffect, ...]:
    """Compile trusted ambient zone replacements without card dispatch.

    The returned effects contain only source semantics.  Affected-object facts
    are bound later by the immutable event snapshot, so one effect can safely
    participate in every event of a simultaneous batch.
    """

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
                    registry.source_replacement_effect(
                        descriptor,
                        source_ref=source.ref,
                        source_controller=source.controller,
                        component_id=f"{program.key}:{descriptor_index}",
                    )
                )
    effects.extend(
        collect_counter_placement_replacement_effects(
            host,
            sources=candidates,
            source_zones=source_zones,
        )
    )
    return tuple(effects)


def capture_zone_change_replacement_snapshot(
    host: ZoneReplacementHost,
    changes: Sequence[tuple[str, str]],
    *,
    destination_controllers: Mapping[str, str | None] | None = None,
    entry_characteristics: Mapping[str, Mapping[str, Any]] | None = None,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
    error_type: type[Exception] = ZoneReplacementError,
) -> ZoneChangeReplacementSnapshot:
    """Capture every represented source and affected object before mutation."""

    supplied = tuple(changes)
    if any(
        not isinstance(change, tuple)
        or len(change) != 2
        or any(type(value) is not str or not value for value in change)
        for change in supplied
    ):
        raise error_type(
            "Zone replacement snapshots require object and destination pairs"
        )
    object_ids = tuple(object_id for object_id, _destination in supplied)
    if len(object_ids) != len(set(object_ids)):
        raise error_type(
            "Zone replacement snapshots cannot repeat one object"
        )
    destination_controllers = destination_controllers or {}
    if set(destination_controllers) - set(object_ids):
        raise error_type(
            "Zone replacement destination controllers reference unknown objects"
        )
    entry_characteristics = entry_characteristics or {}
    if set(entry_characteristics) - set(object_ids):
        raise error_type(
            "Zone replacement entry characteristics reference unknown objects"
        )
    if any(
        not isinstance(value, Mapping)
        for value in entry_characteristics.values()
    ):
        raise error_type(
            "Zone replacement entry characteristics must be mappings"
        )

    subjects: list[ZoneChangeSubjectSnapshot] = []
    for object_id, destination in supplied:
        card = host.state.cards.get(object_id)
        if card is None:
            raise error_type(
                "Zone replacement snapshot references an unknown object"
            )
        try:
            characteristics = dict(
                entry_characteristics.get(
                    object_id, host._effective_card_data(card)
                )
            )
            card_types, subtypes, supertypes = host._type_parts(
                str(characteristics.get("type_line") or "")
            )
            types = tuple(
                sorted({*card_types, *subtypes, *supertypes})
            )
            destination_controller = (
                destination_controllers[object_id]
                if object_id in destination_controllers
                else (
                    card.controller
                    if card.zone == "stack"
                    else card.owner
                )
            )
            subjects.append(
                ZoneChangeSubjectSnapshot(
                    object_id=card.object_id,
                    object_ref=card.ref,
                    logical_object_id=card.logical_object_id,
                    owner=card.owner,
                    controller=(
                        card.controller
                        if card.zone in {"battlefield", "stack"}
                        else None
                    ),
                    origin=card.zone,
                    destination=destination,
                    destination_controller=destination_controller,
                    intrinsic_entry_counters=intrinsic_entry_counters(
                        characteristics,
                        card_types=tuple(sorted(card_types)),
                    ),
                    object_types=types,
                    is_card_object=card.is_card_object,
                )
            )
        except (
            EntryCounterError,
            SemanticNodeError,
            ZoneReplacementError,
        ) as exc:
            raise error_type(str(exc)) from exc

    candidates = (
        tuple(sources)
        if sources is not None
        else tuple(host._semantic_event_sources(zones={"battlefield"}))
    )
    active_sources = tuple(
        source
        for source in candidates
        if (
            (
                source_zones.get(source.object_id, source.zone)
                if source_zones is not None
                else source.zone
            )
            == "battlefield"
            and not source.phased_out
            and source.controller in host.active_seats
        )
    )
    try:
        ambient_effects = collect_zone_change_replacement_effects(
            host,
            sources=active_sources,
            source_zones={source.object_id: "battlefield" for source in active_sources},
        )
        intrinsic_effects = tuple(
            effect
            for subject in subjects
            if subject.destination_controller is not None
            for effect in intrinsic_entry_counter_effects(
                object_ref=subject.object_ref,
                destination_controller=subject.destination_controller,
                counters=subject.intrinsic_entry_counters,
            )
        )
        return ZoneChangeReplacementSnapshot(
            revision=host.state.revision,
            event_sequence=host.state.event_sequence,
            apnap_order=tuple(host.apnap_order()),
            source_refs=tuple(source.ref for source in active_sources),
            subjects=tuple(subjects),
            effects=tuple(
                sorted(
                    (*ambient_effects, *intrinsic_effects),
                    key=lambda effect: effect.effect_id,
                )
            ),
        )
    except (SemanticNodeError, ZoneReplacementError) as exc:
        raise error_type(str(exc)) from exc


def _snapshot_event(
    snapshot: ZoneChangeReplacementSnapshot,
    subject: ZoneChangeSubjectSnapshot,
) -> ReplaceableEvent:
    return ReplaceableEvent(
        event_id=(
            f"zone.change:{snapshot.revision}:"
            f"{snapshot.event_sequence + 1}:{subject.object_ref}"
        ),
        kind="zone.change",
        affected_player=None,
        affected_object=AffectedObject(
            object_id=subject.object_id,
            owner=subject.owner,
            controller=subject.controller,
        ),
        payload={
            "origin": subject.origin,
            "destination": subject.destination,
            "destination_controller": subject.destination_controller,
            "object_kind": "card" if subject.is_card_object else "noncard",
            "object_ref": subject.object_ref,
            "object_types": list(subject.object_types),
            "logical_object_id": subject.logical_object_id,
            "owner": subject.owner,
        },
    )


def _prepared_from_event(
    subject: ZoneChangeSubjectSnapshot,
    event: ReplaceableEvent,
    *,
    effects: tuple[ReplacementEffect, ...],
    journal: tuple[ReplacementSelection, ...],
) -> PreparedZoneChange:
    counter_events: list[ReplaceableEvent] = []

    def visit(current: ReplaceableEvent) -> None:
        if current.kind == "counter.place":
            counter_events.append(current)
        for child in current.children:
            visit(child)

    visit(event)
    return PreparedZoneChange(
        object_id=subject.object_id,
        logical_object_id=subject.logical_object_id,
        origin=subject.origin,
        requested_destination=subject.destination,
        destination=str(event.payload["destination"]),
        event=event,
        effects=effects,
        counter_events=tuple(counter_events),
        journal=journal,
    )


def prepare_zone_change_replacement(
    host: ZoneReplacementHost,
    card: Any,
    destination: str,
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
    destination_controller: str | None = None,
    entry_characteristics: Mapping[str, Any] | None = None,
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    prepared: PreparedZoneChange | None = None,
    error_type: type[Exception] = ZoneReplacementError,
) -> PreparedZoneChange:
    """Resolve ambient destination replacements before a zone mutation."""

    if prepared is not None:
        if (
            prepared.object_id != card.object_id
            or prepared.logical_object_id != card.logical_object_id
            or prepared.origin != card.zone
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
    return prepare_zone_change_replacement_batch(
        host,
        ((card.object_id, destination),),
        destination_controllers=(
            {card.object_id: destination_controller}
            if destination_controller is not None
            else None
        ),
        entry_characteristics=(
            {card.object_id: entry_characteristics}
            if entry_characteristics is not None
            else None
        ),
        sources=sources,
        source_zones=source_zones,
        selections=selections,
        error_type=error_type,
    )[card.object_id]


def prepare_zone_change_replacement_batch(
    host: ZoneReplacementHost,
    changes: Sequence[tuple[str, str]],
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
    destination_controllers: Mapping[str, str | None] | None = None,
    entry_characteristics: Mapping[
        str, Mapping[str, Any]
    ] | None = None,
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    error_type: type[Exception] = ZoneReplacementError,
) -> dict[str, PreparedZoneChange]:
    """Resolve one immutable simultaneous batch before mutating any object."""

    snapshot = capture_zone_change_replacement_snapshot(
        host,
        changes,
        destination_controllers=destination_controllers,
        entry_characteristics=entry_characteristics,
        sources=sources,
        source_zones=source_zones,
        error_type=error_type,
    )
    return prepare_zone_change_replacement_snapshot(
        snapshot,
        selections=selections,
        error_type=error_type,
    )


def prepare_zone_change_replacement_snapshot(
    snapshot: ZoneChangeReplacementSnapshot,
    *,
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    error_type: type[Exception] = ZoneReplacementError,
) -> dict[str, PreparedZoneChange]:
    """Resolve a captured batch without consulting mutable game state."""

    if not isinstance(snapshot, ZoneChangeReplacementSnapshot):
        raise error_type(
            "Zone replacement preparation requires an immutable snapshot"
        )
    events = tuple(
        _snapshot_event(snapshot, subject) for subject in snapshot.subjects
    )
    applicable = tuple(
        (subject, event)
        for subject, event in zip(snapshot.subjects, events, strict=True)
        if replacement_choice(event, snapshot.effects) is not None
    )
    if not applicable:
        if selections:
            raise error_type(
                "Replacement selections were supplied without an applicable "
                "zone-change replacement"
            )
        return {
            subject.object_id: _prepared_from_event(
                subject,
                event,
                effects=snapshot.effects,
                journal=(),
            )
            for subject, event in zip(snapshot.subjects, events, strict=True)
        }
    applicable_subjects = tuple(subject for subject, _event in applicable)
    applicable_events = tuple(event for _subject, event in applicable)
    progress = advance_replacement_batch(
        ReplacementEventBatch(
            batch_id=(
                f"replacement:zone.batch:{snapshot.revision}:"
                f"{snapshot.event_sequence + 1}"
            ),
            events=applicable_events,
            apnap_order=snapshot.apnap_order,
        ),
        snapshot.effects,
        selections=tuple(selections),
    )
    if progress.pending is not None:
        raise ReplacementChoiceRequired(
            batch=progress.batch,
            effects=snapshot.effects,
            pending=progress.pending,
        )
    prepared: dict[str, PreparedZoneChange] = {
        subject.object_id: _prepared_from_event(
            subject,
            event,
            effects=snapshot.effects,
            journal=(),
        )
        for subject, event in zip(snapshot.subjects, events, strict=True)
    }
    for subject, event in zip(
        applicable_subjects,
        progress.batch.events,
        strict=True,
    ):
        event_journal = tuple(
            selection
            for selection in progress.batch.journal
            if selection.event_id == event.event_id
        )
        prepared[subject.object_id] = _prepared_from_event(
            subject,
            event,
            effects=snapshot.effects,
            journal=event_journal,
        )
    return prepared


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
        if replacement.event_kind != "zone.change":
            continue
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
                        "name": str(
                            event.payload.get("counter_name") or ""
                        ),
                        "amount": int(event.payload.get("amount", 0)),
                    }
                    for event in prepared.counter_events
                    if event.payload.get("source")
                    == replacement.source_id
                ],
            },
            importance=2,
            changed_objects=[card.object_id],
        )


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
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    object_ref: str | None = None,
    logical_object_id: str | None = None,
    object_types: Sequence[str] = (),
    destination_controller: str | None = None,
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
            "destination_controller": (
                destination_controller
                if destination_controller is not None
                else controller
            ),
            "object_kind": "card" if is_card_object else "noncard",
            "object_ref": object_ref or object_id,
            "object_types": sorted(set(object_types)),
            "logical_object_id": logical_object_id or object_id,
            "owner": owner,
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
