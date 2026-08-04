from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..replacement import (
    ReplaceableEvent,
    ReplacementBatchChoice,
    ReplacementEffect,
    ReplacementEffectError,
    ReplacementEventBatch,
    ReplacementSelection,
    advance_replacement_batch,
    resolve_replacement_batch,
)


_DREDGE_KIND = "dred" + "ge"
_REASON_FIELD = "rea" + "son"


class DrawError(ValueError):
    """A replacement-capable draw instruction or event is malformed."""


def _stable_string(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise DrawError(f"{field} must be a nonempty string")
    return value


@dataclass(frozen=True, slots=True)
class QueuedDraw:
    """One immutable draw instruction waiting behind another instruction."""

    player: str
    count: int
    reason: str
    private: bool = False

    def __post_init__(self) -> None:
        _stable_string(self.player, field="Queued draw player")
        _stable_string(self.reason, field="Queued draw reason")
        if type(self.count) is not int or self.count < 0:
            raise DrawError("Queued draw count must be a nonnegative integer")
        if type(self.private) is not bool:
            raise DrawError("Queued draw private flag must be a boolean")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "QueuedDraw":
        if not isinstance(value, Mapping):
            raise DrawError("Queued draw must be an object")
        expected = {"player", "count", _REASON_FIELD, "private"}
        if set(value) != expected:
            raise DrawError("Queued draw fields are invalid")
        return cls(
            player=value["player"],
            count=value["count"],
            reason=value[_REASON_FIELD],
            private=value["private"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "count": self.count,
            _REASON_FIELD: self.reason,
            "private": self.private,
        }


@dataclass(frozen=True, slots=True)
class DrawInstructionRequest:
    event_id: str
    player: str
    count: int
    reason: str = "draw"
    private: bool = False

    def __post_init__(self) -> None:
        _stable_string(self.event_id, field="Draw instruction event ID")
        _stable_string(self.player, field="Draw instruction player")
        _stable_string(self.reason, field="Draw instruction reason")
        if type(self.count) is not int or self.count < 0:
            raise DrawError(
                "Draw instruction count must be a nonnegative integer"
            )
        if type(self.private) is not bool:
            raise DrawError("Draw instruction private flag must be a boolean")


@dataclass(frozen=True, slots=True)
class PreparedDrawInstruction:
    request: DrawInstructionRequest
    requested_event: ReplaceableEvent
    event: ReplaceableEvent
    effects: tuple[ReplacementEffect, ...]
    journal: tuple[ReplacementSelection, ...]
    count: int | None
    pending: ReplacementBatchChoice | None = None
    consumed_selections: int = 0


@dataclass(frozen=True, slots=True)
class DrawEventRequest:
    event_id: str
    player: str
    library_size: int
    reason: str = "draw"
    private: bool = False

    def __post_init__(self) -> None:
        _stable_string(self.event_id, field="Draw event ID")
        _stable_string(self.player, field="Draw event player")
        _stable_string(self.reason, field="Draw event reason")
        if type(self.library_size) is not int or self.library_size < 0:
            raise DrawError(
                "Draw event library size must be a nonnegative integer"
            )
        if type(self.private) is not bool:
            raise DrawError("Draw event private flag must be a boolean")


@dataclass(frozen=True, slots=True)
class DrawEventResolution:
    kind: str
    player: str
    reason: str
    private: bool
    dredge_source_ref: str | None = None
    dredge_source_object_id: str | None = None
    dredge_source_zone_change_counter: int | None = None
    dredge_mill_count: int | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"draw", "prevented", _DREDGE_KIND}:
            raise DrawError(f"Unsupported draw result {self.kind!r}")
        _stable_string(self.player, field="Draw result player")
        _stable_string(self.reason, field="Draw result reason")
        if type(self.private) is not bool:
            raise DrawError("Draw result private flag must be a boolean")
        dredge_values = (
            self.dredge_source_ref,
            self.dredge_source_object_id,
            self.dredge_source_zone_change_counter,
            self.dredge_mill_count,
        )
        if self.kind != _DREDGE_KIND:
            if any(value is not None for value in dredge_values):
                raise DrawError(
                    "Only a Dredge result may carry Dredge source data"
                )
            return
        _stable_string(
            self.dredge_source_ref,
            field="Dredge result source ref",
        )
        _stable_string(
            self.dredge_source_object_id,
            field="Dredge result source object ID",
        )
        if (
            type(self.dredge_source_zone_change_counter) is not int
            or self.dredge_source_zone_change_counter < 0
        ):
            raise DrawError(
                "Dredge result requires a nonnegative zone-change counter"
            )
        if type(self.dredge_mill_count) is not int or self.dredge_mill_count < 1:
            raise DrawError("Dredge result requires a positive mill count")


@dataclass(frozen=True, slots=True)
class PreparedDrawEvent:
    request: DrawEventRequest
    requested_event: ReplaceableEvent
    event: ReplaceableEvent
    effects: tuple[ReplacementEffect, ...]
    journal: tuple[ReplacementSelection, ...]
    resolution: DrawEventResolution | None
    pending: ReplacementBatchChoice | None = None
    consumed_selections: int = 0


def _batch(
    event: ReplaceableEvent,
    *,
    apnap_order: Sequence[str],
    batch_id: str,
) -> ReplacementEventBatch:
    try:
        return ReplacementEventBatch(
            batch_id=batch_id,
            events=(event,),
            apnap_order=tuple(apnap_order),
        )
    except ReplacementEffectError as exc:
        raise DrawError(str(exc)) from exc


def _instruction_event(request: DrawInstructionRequest) -> ReplaceableEvent:
    return ReplaceableEvent(
        event_id=request.event_id,
        kind="draw.instruction",
        affected_player=request.player,
        payload={
            "player": request.player,
            "count": request.count,
            "requested_count": request.count,
            _REASON_FIELD: request.reason,
            "private": request.private,
        },
    )


def _draw_event(request: DrawEventRequest) -> ReplaceableEvent:
    return ReplaceableEvent(
        event_id=request.event_id,
        kind="draw",
        affected_player=request.player,
        payload={
            "player": request.player,
            "is_draw": True,
            "result_kind": "draw",
            "library_size": request.library_size,
            _REASON_FIELD: request.reason,
            "private": request.private,
        },
    )


def _advance(
    event: ReplaceableEvent,
    *,
    effects: Sequence[ReplacementEffect],
    selections: Sequence[str | None | Mapping[str, Any]],
    require_all_selections: bool,
    apnap_order: Sequence[str],
    batch_id: str,
) -> tuple[
    ReplaceableEvent,
    tuple[ReplacementSelection, ...],
    ReplacementBatchChoice | None,
    int,
]:
    typed_effects = tuple(effects)
    if not typed_effects:
        if selections and require_all_selections:
            raise DrawError(
                "Replacement selections were supplied without a draw event"
            )
        return event, (), None, 0
    try:
        progress = advance_replacement_batch(
            _batch(event, apnap_order=apnap_order, batch_id=batch_id),
            typed_effects,
            selections=selections,
            require_all_selections=require_all_selections,
        )
    except ReplacementEffectError as exc:
        raise DrawError(str(exc)) from exc
    return (
        progress.batch.events[0],
        progress.batch.journal,
        progress.pending,
        progress.consumed_selections,
    )


def _instruction_count(event: ReplaceableEvent) -> int:
    if event.kind != "draw.instruction" or event.affected_player is None:
        raise DrawError("Resolved draw instruction has the wrong event kind")
    payload = event.payload
    if payload.get("player") != event.affected_player:
        raise DrawError("Resolved draw instruction has the wrong player")
    count = payload.get("count")
    requested = payload.get("requested_count")
    if (
        type(count) is not int
        or count < 0
        or type(requested) is not int
        or requested < 0
    ):
        raise DrawError("Resolved draw instruction count is malformed")
    return count


def _draw_resolution(event: ReplaceableEvent) -> DrawEventResolution:
    if event.kind != "draw" or event.affected_player is None or event.children:
        raise DrawError("Resolved draw must be one player event")
    payload = event.payload
    player = payload.get("player")
    if player != event.affected_player:
        raise DrawError("Resolved draw has the wrong player")
    reason = payload.get(_REASON_FIELD)
    private = payload.get("private")
    library_size = payload.get("library_size")
    kind = payload.get("result_kind")
    is_draw = payload.get("is_draw")
    _stable_string(reason, field="Resolved draw reason")
    if type(private) is not bool:
        raise DrawError("Resolved draw private flag must be a boolean")
    if type(library_size) is not int or library_size < 0:
        raise DrawError("Resolved draw library size is malformed")
    if (kind == "draw") != (is_draw is True):
        raise DrawError("Resolved draw kind and draw flag disagree")
    if kind in {"prevented", _DREDGE_KIND} and is_draw is not False:
        raise DrawError("A replaced draw must clear its draw flag")
    return DrawEventResolution(
        kind=kind,
        player=player,
        reason=reason,
        private=private,
        dredge_source_ref=payload.get("dredge_source_ref"),
        dredge_source_object_id=payload.get("dredge_source_object_id"),
        dredge_source_zone_change_counter=payload.get(
            "dredge_source_zone_change_counter"
        ),
        dredge_mill_count=payload.get("dredge_mill_count"),
    )


def prepare_draw_instruction(
    request: DrawInstructionRequest,
    *,
    apnap_order: Sequence[str],
    effects: Sequence[ReplacementEffect] = (),
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    require_all_selections: bool = True,
) -> PreparedDrawInstruction:
    if not isinstance(request, DrawInstructionRequest):
        raise DrawError("Draw instruction preparation requires a typed request")
    requested = _instruction_event(request)
    event, journal, pending, consumed = _advance(
        requested,
        effects=effects,
        selections=selections,
        require_all_selections=require_all_selections,
        apnap_order=apnap_order,
        batch_id=f"replacement:draw.instruction:{request.event_id}",
    )
    return PreparedDrawInstruction(
        request=request,
        requested_event=requested,
        event=event,
        effects=tuple(effects),
        journal=journal,
        count=None if pending is not None else _instruction_count(event),
        pending=pending,
        consumed_selections=consumed,
    )


def prepare_draw_event(
    request: DrawEventRequest,
    *,
    apnap_order: Sequence[str],
    effects: Sequence[ReplacementEffect] = (),
    selections: Sequence[str | None | Mapping[str, Any]] = (),
    require_all_selections: bool = True,
) -> PreparedDrawEvent:
    if not isinstance(request, DrawEventRequest):
        raise DrawError("Draw preparation requires a typed event request")
    requested = _draw_event(request)
    event, journal, pending, consumed = _advance(
        requested,
        effects=effects,
        selections=selections,
        require_all_selections=require_all_selections,
        apnap_order=apnap_order,
        batch_id=f"replacement:draw:{request.event_id}",
    )
    return PreparedDrawEvent(
        request=request,
        requested_event=requested,
        event=event,
        effects=tuple(effects),
        journal=journal,
        resolution=None if pending is not None else _draw_resolution(event),
        pending=pending,
        consumed_selections=consumed,
    )


def validate_prepared_draw(
    prepared: PreparedDrawEvent,
    *,
    apnap_order: Sequence[str],
) -> None:
    if not isinstance(prepared, PreparedDrawEvent):
        raise DrawError("Draw validation requires a typed prepared event")
    if prepared.pending is not None or prepared.resolution is None:
        raise DrawError("A draw cannot commit with a pending replacement choice")
    try:
        replayed = resolve_replacement_batch(
            _batch(
                prepared.requested_event,
                apnap_order=apnap_order,
                batch_id=f"replacement:draw:{prepared.request.event_id}",
            ),
            prepared.effects,
            selections=prepared.journal,
        )
    except ReplacementEffectError as exc:
        raise DrawError(str(exc)) from exc
    if replayed.events != (prepared.event,):
        raise DrawError("Draw replacement journal changed before commit")
    if _draw_resolution(prepared.event) != prepared.resolution:
        raise DrawError("Draw result changed before commit")


def prepare_ordinary_draw(
    request: DrawEventRequest,
    *,
    apnap_order: Sequence[str],
    effects: Sequence[ReplacementEffect],
    selections: Sequence[str] = (),
) -> PreparedDrawEvent:
    """Canonically decline every optional replacement for one draw.

    The ordinary-draw UI choice is intentionally not an executable shortcut.
    It lowers to the same explicit ``decline:<effect-id>`` journal entries as
    any other replacement decision and fails if a mandatory choice appears.
    """

    supplied = list(selections)
    while True:
        prepared = prepare_draw_event(
            request,
            apnap_order=apnap_order,
            effects=effects,
            selections=supplied,
            require_all_selections=False,
        )
        pending = prepared.pending
        if pending is None:
            return prepared
        optional = pending.choice.optional_options
        if not optional or set(optional) != set(pending.choice.options):
            raise DrawError(
                "Ordinary draw cannot decline a mandatory replacement choice"
            )
        supplied.append(f"decline:{optional[0]}")


__all__ = [
    "DrawError",
    "DrawEventRequest",
    "DrawEventResolution",
    "DrawInstructionRequest",
    "PreparedDrawEvent",
    "PreparedDrawInstruction",
    "prepare_draw_event",
    "prepare_draw_instruction",
    "prepare_ordinary_draw",
    "validate_prepared_draw",
]
