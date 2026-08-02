from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .counter_state import (
    CounterChange,
    CounterStateError,
    commit_counter_changes,
    plan_counter_changes,
)
from .replacement_effects import (
    ReplaceableEvent,
    ReplacementChoiceRequired,
    ReplacementEffect,
    ReplacementSelection,
)
from .semantic_runtime.counter_replacements import (
    CounterPlacementEventSpec,
    collect_counter_placement_replacement_effects,
    resolve_counter_placement_replacements,
)


class CounterPlacementError(ValueError):
    pass


class CounterPlacementHost(Protocol):
    state: Any
    semantics: Any
    active_seats: list[str]

    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> list[Any]: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...

    def apnap_order(self, *, start: str | None = None) -> list[str]: ...

    def _effective_card_data(self, card: Any) -> Mapping[str, Any]: ...

    def _resolve_object(
        self,
        actor: str,
        ref: str,
        *,
        zones: set[str] | None = None,
    ) -> Any: ...

    def _type_parts(
        self, type_line: str
    ) -> tuple[set[str], set[str], set[str]]: ...

    def _log(
        self,
        actor: str | None,
        code: str,
        summary: str,
        details: Mapping[str, Any] | None = None,
        *,
        importance: int = 1,
        changed_objects: Sequence[str] = (),
        changed_players: Sequence[str] = (),
    ) -> None: ...


class CounterEventTreeResolution(Protocol):
    event: ReplaceableEvent | None
    effects: Sequence[ReplacementEffect]
    journal: Sequence[ReplacementSelection]


@dataclass(frozen=True, slots=True)
class CounterPlacementRequest:
    object_id: str
    counter_name: str
    amount: int
    placing_player: str
    source_ref: str | None = None
    effect_generated: bool = True

    def __post_init__(self) -> None:
        normalized = " ".join(self.counter_name.casefold().split())
        if not self.object_id or not normalized:
            raise CounterPlacementError(
                "Counter placements require an object and counter name"
            )
        if type(self.amount) is not int or self.amount < 0:
            raise CounterPlacementError(
                "Counter placement amounts cannot be negative"
            )
        if not self.placing_player:
            raise CounterPlacementError(
                "Counter placements require the placing player"
            )

    @property
    def normalized_name(self) -> str:
        return " ".join(self.counter_name.casefold().split())


@dataclass(frozen=True, slots=True)
class PreparedCounterPlacements:
    events: tuple[ReplaceableEvent, ...]
    effects: tuple[ReplacementEffect, ...]
    journal: tuple[ReplacementSelection, ...]


@dataclass(frozen=True, slots=True)
class CounterPlacementResult:
    object_id: str
    counter_name: str
    requested: int
    placed: int
    before: int
    after: int


def _event_spec(
    host: CounterPlacementHost,
    request: CounterPlacementRequest,
    *,
    event_id: str,
) -> CounterPlacementEventSpec:
    card = host.state.cards.get(request.object_id)
    if card is None:
        raise CounterPlacementError(
            "Counter placement target no longer exists"
        )
    data = host._effective_card_data(card)
    card_types, subtypes, supertypes = host._type_parts(
        str(data.get("type_line") or "")
    )
    controller = card.controller if card.zone == "battlefield" else None
    return CounterPlacementEventSpec(
        event_id=event_id,
        object_id=card.object_id,
        owner=card.owner,
        controller=controller,
        target_zone=card.zone,
        target_types=tuple(
            sorted({*card_types, *subtypes, *supertypes})
        ),
        placing_player=request.placing_player,
        counter_name=request.normalized_name,
        amount=request.amount,
        source_ref=request.source_ref,
        effect_generated=request.effect_generated,
        logical_object_id=card.logical_object_id,
    )


def prepare_counter_placements(
    host: CounterPlacementHost,
    requests: Sequence[CounterPlacementRequest],
    *,
    selections: Sequence[str | None] = (),
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> PreparedCounterPlacements:
    """Resolve one simultaneous counter-placement batch before mutation."""

    nonzero = tuple(request for request in requests if request.amount > 0)
    if not nonzero:
        if selections:
            raise CounterPlacementError(
                "Replacement selections were supplied without counters"
            )
        return PreparedCounterPlacements(events=(), effects=(), journal=())
    events = tuple(
        _event_spec(
            host,
            request,
            event_id=(
                f"counter.place:{host.state.revision}:"
                f"{host.state.event_sequence + 1}:{index}:"
                f"{host.state.cards[request.object_id].ref}"
            ),
        ).event()
        for index, request in enumerate(nonzero)
    )
    effects = collect_counter_placement_replacement_effects(
        host,
        sources=sources,
        source_zones=source_zones,
    )
    if not effects:
        if selections:
            raise CounterPlacementError(
                "Replacement selections were supplied without an applicable "
                "counter replacement"
            )
        return PreparedCounterPlacements(
            events=events,
            effects=(),
            journal=(),
        )
    resolution = resolve_counter_placement_replacements(
        batch_id=(
            f"replacement:counter.place:{host.state.revision}:"
            f"{host.state.event_sequence + 1}"
        ),
        events=events,
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
    return PreparedCounterPlacements(
        events=resolution.batch.events,
        effects=effects,
        journal=resolution.journal,
    )


def _resolved_amount(event: ReplaceableEvent) -> tuple[str, int, int]:
    name = " ".join(
        str(event.payload.get("counter_name") or "").casefold().split()
    )
    requested = int(event.payload.get("requested_amount", 0))
    amount = int(event.payload.get("amount", -1))
    if not name or requested < 1 or amount < 0:
        raise CounterPlacementError(
            "Resolved counter placement produced invalid data"
        )
    return name, requested, amount


def _log_replacements(
    host: CounterPlacementHost,
    prepared: PreparedCounterPlacements,
) -> None:
    effects = {effect.effect_id: effect for effect in prepared.effects}
    events = {event.event_id: event for event in prepared.events}
    for selection in prepared.journal:
        selected_id = str(selection.effect_id or "")
        if selected_id.startswith("decline:"):
            continue
        effect = effects.get(selected_id)
        event = events.get(selection.event_id)
        if effect is None or event is None:
            raise CounterPlacementError(
                "Counter replacement journal does not match its snapshot"
            )
        name, requested, amount = _resolved_amount(event)
        host._log(
            None,
            "replacement.apply",
            f"{effect.source_id} changed a counter placement.",
            {
                "source": effect.source_id,
                "effect_id": effect.effect_id,
                "object_id": event.affected_object.object_id,
                "counter": name,
                "requested": requested,
                "resolved": amount,
            },
            importance=2,
            changed_objects=[event.affected_object.object_id],
        )


def commit_prepared_counter_placements(
    host: CounterPlacementHost,
    prepared: PreparedCounterPlacements,
    *,
    reason: str,
    log: bool = True,
) -> tuple[CounterPlacementResult, ...]:
    """Commit a choice-complete batch without rediscovering effects."""

    validated: list[tuple[ReplaceableEvent, Any, str, int, int]] = []
    for event in prepared.events:
        affected = event.affected_object
        if affected is None:
            raise CounterPlacementError(
                "Counter placement event lost its affected object"
            )
        card = host.state.cards.get(affected.object_id)
        if card is None:
            raise CounterPlacementError(
                "Counter placement target no longer exists"
            )
        target_zone = str(event.payload.get("target_zone") or "")
        if card.zone != target_zone:
            raise CounterPlacementError(
                "Counter placement target changed zones before commit"
            )
        name, requested, amount = _resolved_amount(event)
        validated.append((event, card, name, requested, amount))

    try:
        counter_plan = plan_counter_changes(
            host,
            tuple(
                CounterChange(
                    subject_kind="permanent",
                    subject_id=card.object_id,
                    counter_name=name,
                    amount=amount,
                    expected_zone=str(event.payload.get("target_zone") or ""),
                    expected_logical_object_id=(
                        str(event.payload["target_logical_object_id"])
                        if event.payload.get("target_logical_object_id")
                        is not None
                        else None
                    ),
                )
                for event, card, name, _requested, amount in validated
            ),
        )
        transitions = commit_counter_changes(host, counter_plan)
    except CounterStateError as exc:
        raise CounterPlacementError(str(exc)) from exc

    results: list[CounterPlacementResult] = []
    for (event, card, name, requested, amount), transition in zip(
        validated, transitions, strict=True
    ):
        results.append(
            CounterPlacementResult(
                object_id=card.object_id,
                counter_name=name,
                requested=requested,
                placed=amount,
                before=transition.before,
                after=transition.after,
            )
        )
        if log:
            host._log(
                str(event.payload.get("placing_player") or "") or None,
                "counter.add",
                f"Put {amount} {name} counter(s) on {card.ref}.",
                {
                    "object": card.ref,
                    "counter": name,
                    "requested": requested,
                    "placed": amount,
                    "before": transition.before,
                    "after": transition.after,
                    "source": event.payload.get("source"),
                    "placement_reason": reason,
                },
                importance=2,
                changed_objects=[card.object_id],
            )
    if log:
        _log_replacements(host, prepared)
    return tuple(results)


def place_counters(
    host: CounterPlacementHost,
    requests: Sequence[CounterPlacementRequest],
    *,
    selections: Sequence[str | None] = (),
    reason: str,
    log: bool = True,
) -> tuple[CounterPlacementResult, ...]:
    prepared = prepare_counter_placements(
        host,
        requests,
        selections=selections,
    )
    return commit_prepared_counter_placements(
        host,
        prepared,
        reason=reason,
        log=log,
    )


def place_counters_on_refs(
    host: CounterPlacementHost,
    *,
    actor: str,
    object_refs: Sequence[str],
    counter_name: str,
    amount: int,
    selections: Sequence[str | None] = (),
    reason: str,
    source_ref: str | None = None,
) -> tuple[CounterPlacementResult, ...]:
    """Resolve battlefield refs and route one effect placement batch."""

    cards = tuple(
        host._resolve_object(actor, ref, zones={"battlefield"})
        for ref in object_refs
    )
    return place_counters(
        host,
        tuple(
            CounterPlacementRequest(
                object_id=card.object_id,
                counter_name=counter_name,
                amount=amount,
                placing_player=actor,
                source_ref=source_ref,
            )
            for card in cards
        ),
        selections=selections,
        reason=reason,
    )


def place_counters_on_controlled_subtype(
    host: CounterPlacementHost,
    *,
    actor: str,
    controller: str,
    subtype: str,
    counter_name: str,
    amount: int,
    selections: Sequence[str | None] = (),
    reason: str,
    source_ref: str | None = None,
) -> tuple[CounterPlacementResult, ...]:
    """Build one simultaneous batch from a controller's effective subtype."""

    normalized_subtype = " ".join(subtype.casefold().split())
    if not normalized_subtype:
        raise CounterPlacementError(
            "Subtype counter placement requires a subtype"
        )
    refs = tuple(
        card.ref
        for object_id in host.state.players[controller].zones["battlefield"]
        for card in (host.state.cards[object_id],)
        if card.controller == controller
        and not card.phased_out
        and normalized_subtype
        in host._type_parts(
            str(host._effective_card_data(card).get("type_line") or "")
        )[1]
    )
    return place_counters_on_refs(
        host,
        actor=actor,
        object_refs=refs,
        counter_name=counter_name,
        amount=amount,
        selections=selections,
        reason=reason,
        source_ref=source_ref,
    )


def prepared_counter_events_from_tree(
    event: ReplaceableEvent,
    *,
    effects: Sequence[ReplacementEffect],
    journal: Sequence[ReplacementSelection],
) -> PreparedCounterPlacements:
    """Extract resolved nested counter events from a containing event."""

    counter_events: list[ReplaceableEvent] = []

    def visit(current: ReplaceableEvent) -> None:
        if current.kind == "counter.place":
            counter_events.append(current)
        for child in current.children:
            visit(child)

    visit(event)
    counter_ids = {current.event_id for current in counter_events}
    return PreparedCounterPlacements(
        events=tuple(counter_events),
        effects=tuple(
            effect for effect in effects if effect.event_kind == "counter.place"
        ),
        journal=tuple(
            selection
            for selection in journal
            if selection.event_id in counter_ids
        ),
    )


def commit_counter_events_from_resolution(
    host: CounterPlacementHost,
    resolution: CounterEventTreeResolution,
    *,
    reason: str,
    log: bool,
    error_type: type[Exception] = CounterPlacementError,
) -> tuple[CounterPlacementResult, ...]:
    """Commit resolved nested counters without growing the zone-move owner."""

    if resolution.event is None:
        return ()
    try:
        return commit_prepared_counter_placements(
            host,
            prepared_counter_events_from_tree(
                resolution.event,
                effects=resolution.effects,
                journal=resolution.journal,
            ),
            reason=reason,
            log=log,
        )
    except CounterPlacementError as exc:
        raise error_type(str(exc)) from exc
