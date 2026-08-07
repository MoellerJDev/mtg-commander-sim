from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .replacement.immutable import (
    FrozenMap,
    freeze_value,
    ImmutableValueError,
    thaw_value,
)


class ReturnToHandError(ValueError):
    """A permanent-return request is malformed, unsupported, or stale."""


class ReturnToHandHost(Protocol):
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
class ReturnToHandRequest:
    object_id: str
    logical_object_id: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.object_id, self.logical_object_id)
        ):
            raise ReturnToHandError(
                "Return requests require physical and logical identity"
            )


@dataclass(frozen=True, slots=True)
class ReturnToHandEntry:
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
            raise ReturnToHandError(
                "Return entries require complete object identity"
            )


@dataclass(frozen=True, slots=True)
class ReturnToHandPlan:
    actor: str
    reason: str
    entry: ReturnToHandEntry
    replacement_selections: tuple[str | FrozenMap, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.actor, str) or not self.actor:
            raise ReturnToHandError("Permanent return requires an actor")
        if not isinstance(self.reason, str) or not self.reason:
            raise ReturnToHandError("Permanent return requires a reason")
        if not isinstance(self.entry, ReturnToHandEntry):
            raise ReturnToHandError("Permanent return requires a typed entry")
        if not isinstance(self.replacement_selections, tuple):
            raise ReturnToHandError(
                "Return replacement selections must be immutable"
            )
        object.__setattr__(
            self,
            "replacement_selections",
            _canonical_selections(self.replacement_selections),
        )


@dataclass(frozen=True, slots=True)
class ReturnToHandResult:
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
            raise ReturnToHandError(
                "Return results require complete committed identity"
            )

    @property
    def returned_to_hand(self) -> bool:
        return self.destination == "hand"


def request_for_card(card: Any) -> ReturnToHandRequest:
    return ReturnToHandRequest(
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
                raise ReturnToHandError(
                    "Return replacement selections must be nonempty"
                )
            result.append(value)
            continue
        if not isinstance(value, Mapping):
            raise ReturnToHandError(
                "Return replacement selections must be strings or objects"
            )
        try:
            frozen = freeze_value(value, field="replacement selection")
        except ImmutableValueError as exc:
            raise ReturnToHandError(str(exc)) from exc
        if not isinstance(frozen, FrozenMap):
            raise ReturnToHandError("Replacement selection did not freeze")
        result.append(frozen)
    return tuple(result)


def prepare_return_to_owner_hand(
    host: ReturnToHandHost,
    request: ReturnToHandRequest,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> ReturnToHandPlan:
    """Snapshot one phased-in battlefield permanent before mutation."""

    if not isinstance(request, ReturnToHandRequest):
        raise ReturnToHandError("Permanent return requires a typed request")
    if not isinstance(actor, str) or not actor:
        raise ReturnToHandError("Permanent return requires an actor")
    if not isinstance(reason, str) or not reason:
        raise ReturnToHandError("Permanent return requires a reason")
    if not isinstance(replacement_selections, (list, tuple)):
        raise ReturnToHandError("Return replacement selections must be a list")
    card = host.state.cards.get(request.object_id)
    if card is None:
        raise ReturnToHandError("Return permanent does not exist")
    if card.zone != "battlefield" or bool(card.phased_out):
        raise ReturnToHandError(
            "Only a phased-in battlefield permanent can be returned"
        )
    if card.logical_object_id != request.logical_object_id:
        raise ReturnToHandError("Return permanent changed logical identity")
    return ReturnToHandPlan(
        actor=actor,
        reason=reason,
        entry=ReturnToHandEntry(
            object_id=card.object_id,
            object_ref=card.ref,
            logical_object_id=card.logical_object_id,
            owner=card.owner,
            controller=card.controller,
        ),
        replacement_selections=_canonical_selections(replacement_selections),
    )


def validate_return_to_hand_plan(
    host: ReturnToHandHost,
    plan: ReturnToHandPlan,
) -> None:
    if not isinstance(plan, ReturnToHandPlan):
        raise ReturnToHandError("Permanent return commits require a typed plan")
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
        raise ReturnToHandError("Permanent return plan is stale")


def commit_return_to_owner_hand(
    host: ReturnToHandHost,
    plan: ReturnToHandPlan,
) -> ReturnToHandResult:
    """Commit through the canonical replacement-aware zone-change owner."""

    validate_return_to_hand_plan(host, plan)
    entry = plan.entry
    card = host.move_card(
        entry.object_id,
        "hand",
        reason=plan.reason,
        log=False,
        semantic_events=True,
        replacement_selections=tuple(
            thaw_value(value) for value in plan.replacement_selections
        ),
    )
    result = ReturnToHandResult(
        object_id=card.object_id,
        object_ref=entry.object_ref,
        owner=entry.owner,
        origin_controller=entry.controller,
        destination=card.zone,
        logical_object_id=card.logical_object_id,
    )
    host._log(
        plan.actor,
        "permanent.return_to_owner_hand",
        f"{entry.object_ref} moved toward its owner's hand.",
        {
            "object": entry.object_ref,
            "owner": entry.owner,
            "origin_controller": entry.controller,
            "requested_destination": "hand",
            "destination": result.destination,
            "reason": plan.reason,
        },
        importance=2,
        changed_objects=[entry.object_id],
        changed_players=[entry.owner, entry.controller],
    )
    return result


def return_permanent_to_owner_hand(
    host: ReturnToHandHost,
    object_ref: str,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> ReturnToHandResult:
    card = host._resolve_object(actor, object_ref, zones={"battlefield"})
    return commit_return_to_owner_hand(
        host,
        prepare_return_to_owner_hand(
            host,
            request_for_card(card),
            actor=actor,
            reason=reason,
            replacement_selections=replacement_selections,
        ),
    )


__all__ = [
    "ReturnToHandEntry",
    "ReturnToHandError",
    "ReturnToHandHost",
    "ReturnToHandPlan",
    "ReturnToHandRequest",
    "ReturnToHandResult",
    "commit_return_to_owner_hand",
    "prepare_return_to_owner_hand",
    "request_for_card",
    "return_permanent_to_owner_hand",
    "validate_return_to_hand_plan",
]
