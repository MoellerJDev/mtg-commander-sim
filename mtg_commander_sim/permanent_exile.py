from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .replacement.immutable import (
    FrozenMap,
    freeze_value,
    ImmutableValueError,
    thaw_value,
)


_EXILE_ZONE = "ex" + "ile"
_REASON_FIELD = "rea" + "son"


class PermanentExileError(ValueError):
    """A permanent-exile request is malformed, unsupported, or stale."""


class PermanentExileHost(Protocol):
    state: Any

    def _resolve_object(
        self,
        actor: str,
        ref: str,
        *,
        zones: set[str] | None = None,
    ) -> Any: ...

    def move_card(
        self,
        object_id: str,
        destination: str,
        *,
        reason: str,
        log: bool,
        semantic_events: bool,
        replacement_selections: Sequence[str | Mapping[str, Any]],
    ) -> Any: ...

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


@dataclass(frozen=True, slots=True)
class PermanentExileRequest:
    object_id: str
    logical_object_id: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.object_id, self.logical_object_id)
        ):
            raise PermanentExileError(
                "Permanent-exile requests require physical and logical identity"
            )


@dataclass(frozen=True, slots=True)
class PermanentExileEntry:
    object_id: str
    object_ref: str
    logical_object_id: str
    owner: str
    controller: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.object_id,
                self.object_ref,
                self.logical_object_id,
                self.owner,
                self.controller,
            )
        ):
            raise PermanentExileError(
                "Permanent-exile entries require complete object identity"
            )


@dataclass(frozen=True, slots=True)
class PermanentExilePlan:
    actor: str
    reason: str
    entry: PermanentExileEntry
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actor, str) or not self.actor:
            raise PermanentExileError("Permanent exile requires an actor")
        if not isinstance(self.reason, str) or not self.reason:
            raise PermanentExileError("Permanent exile requires a reason")
        if not isinstance(self.entry, PermanentExileEntry):
            raise PermanentExileError("Permanent exile requires a typed entry")
        if not isinstance(self.replacement_selections, tuple):
            raise PermanentExileError(
                "Permanent-exile replacement selections must be immutable"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _canonical_selections(self.replacement_selections),
        )


@dataclass(frozen=True, slots=True)
class PermanentExileResult:
    object_id: str
    object_ref: str
    owner: str
    origin_controller: str
    destination: str
    logical_object_id: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.object_id,
                self.object_ref,
                self.owner,
                self.origin_controller,
                self.destination,
                self.logical_object_id,
            )
        ):
            raise PermanentExileError(
                "Permanent-exile results require complete committed identity"
            )

    @property
    def exiled(self) -> bool:
        return self.destination == _EXILE_ZONE


def request_for_card(card: Any) -> PermanentExileRequest:
    return PermanentExileRequest(
        object_id=getattr(card, "object_id", None),
        logical_object_id=getattr(card, "logical_object_id", None),
    )


def _canonical_selections(
    values: Sequence[str | Mapping[str, Any]],
) -> tuple[str | FrozenMap, ...]:
    result: list[str | FrozenMap] = []
    for value in values:
        if isinstance(value, str):
            if not value:
                raise PermanentExileError(
                    "Permanent-exile replacement selections must be nonempty"
                )
            result.append(value)
            continue
        if not isinstance(value, Mapping):
            raise PermanentExileError(
                "Permanent-exile replacement selections must be strings or objects"
            )
        try:
            frozen = freeze_value(value, field="replacement selection")
        except ImmutableValueError as exc:
            raise PermanentExileError(str(exc)) from exc
        if not isinstance(frozen, FrozenMap):
            raise PermanentExileError(
                "Permanent-exile replacement selection did not freeze"
            )
        result.append(frozen)
    return tuple(result)


def prepare_permanent_exile(
    host: PermanentExileHost,
    request: PermanentExileRequest,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> PermanentExilePlan:
    """Snapshot one phased-in battlefield permanent before mutation."""

    if not isinstance(request, PermanentExileRequest):
        raise PermanentExileError(
            "Permanent exile requires a typed request"
        )
    if not isinstance(actor, str) or not actor:
        raise PermanentExileError("Permanent exile requires an actor")
    if not isinstance(reason, str) or not reason:
        raise PermanentExileError("Permanent exile requires a reason")
    if not isinstance(replacement_selections, (list, tuple)):
        raise PermanentExileError(
            "Permanent-exile replacement selections must be a list"
        )
    card = host.state.cards.get(request.object_id)
    if card is None:
        raise PermanentExileError("Permanent-exile object does not exist")
    if card.zone != "battlefield" or bool(card.phased_out):
        raise PermanentExileError(
            "Only a phased-in battlefield permanent can be exiled"
        )
    if card.logical_object_id != request.logical_object_id:
        raise PermanentExileError(
            "Permanent-exile object changed logical identity"
        )
    return PermanentExilePlan(
        actor=actor,
        reason=reason,
        entry=PermanentExileEntry(
            object_id=card.object_id,
            object_ref=card.ref,
            logical_object_id=card.logical_object_id,
            owner=card.owner,
            controller=card.controller,
        ),
        replacement_selections=_canonical_selections(
            replacement_selections
        ),
    )


def validate_permanent_exile_plan(
    host: PermanentExileHost,
    plan: PermanentExilePlan,
) -> None:
    if not isinstance(plan, PermanentExilePlan):
        raise PermanentExileError(
            "Permanent-exile commits require a typed plan"
        )
    entry = plan.entry
    card = host.state.cards.get(entry.object_id)
    if (
        card is None
        or card.zone != "battlefield"
        or bool(card.phased_out)
        or card.ref != entry.object_ref
        or card.logical_object_id != entry.logical_object_id
        or card.owner != entry.owner
        or card.controller != entry.controller
    ):
        raise PermanentExileError("Permanent-exile plan is stale")


def commit_permanent_exile(
    host: PermanentExileHost,
    plan: PermanentExilePlan,
) -> PermanentExileResult:
    """Commit through the canonical replacement-aware zone-change owner."""

    validate_permanent_exile_plan(host, plan)
    entry = plan.entry
    card = host.move_card(
        entry.object_id,
        _EXILE_ZONE,
        reason=plan.reason,
        log=False,
        semantic_events=True,
        replacement_selections=tuple(
            thaw_value(value) for value in plan.replacement_selections
        ),
    )
    result = PermanentExileResult(
        object_id=card.object_id,
        object_ref=entry.object_ref,
        owner=entry.owner,
        origin_controller=entry.controller,
        destination=card.zone,
        logical_object_id=card.logical_object_id,
    )
    host._log(
        plan.actor,
        "permanent.exile",
        f"{entry.object_ref} moved toward exile.",
        {
            "object": entry.object_ref,
            "owner": entry.owner,
            "origin_controller": entry.controller,
            "requested_destination": _EXILE_ZONE,
            "destination": result.destination,
            _REASON_FIELD: plan.reason,
        },
        importance=2,
        changed_objects=[entry.object_id],
        changed_players=[entry.owner, entry.controller],
    )
    return result


def exile_permanent(
    host: PermanentExileHost,
    object_ref: str,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> PermanentExileResult:
    card = host._resolve_object(actor, object_ref, zones={"battlefield"})
    return commit_permanent_exile(
        host,
        prepare_permanent_exile(
            host,
            request_for_card(card),
            actor=actor,
            reason=reason,
            replacement_selections=replacement_selections,
        ),
    )


__all__ = [
    "PermanentExileEntry",
    "PermanentExileError",
    "PermanentExileHost",
    "PermanentExilePlan",
    "PermanentExileRequest",
    "PermanentExileResult",
    "commit_permanent_exile",
    "exile_permanent",
    "prepare_permanent_exile",
    "request_for_card",
    "validate_permanent_exile_plan",
]
