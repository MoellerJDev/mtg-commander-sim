from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .single_object_zone_transition import (
    SingleObjectDestination,
    SingleObjectZoneTransitionEntry,
    SingleObjectZoneTransitionError,
    SingleObjectZoneTransitionPlan,
    SingleObjectZoneTransitionRequest,
    commit_prevalidated_single_object_zone_transition,
    prepare_single_object_zone_transition,
    request_for_card,
    validate_single_object_zone_transition_plan,
)


ReturnToHandError = SingleObjectZoneTransitionError
ReturnToHandRequest = SingleObjectZoneTransitionRequest
ReturnToHandEntry = SingleObjectZoneTransitionEntry
ReturnToHandPlan = SingleObjectZoneTransitionPlan


class ReturnToHandHost(Protocol):
    state: Any

    def _resolve_object(
        self,
        actor: str,
        ref: str,
        *,
        zones: set[str] | None = None,
    ) -> Any: ...

    def move_card(self, object_id: str, destination: str, **kwargs: Any) -> Any: ...

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
class ReturnToHandResult:
    object_id: str
    object_ref: str
    owner: str
    origin_controller: str
    destination: str
    logical_object_id: str

    def __post_init__(self) -> None:
        if not all(
            type(value) is str and value
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
        return self.destination == SingleObjectDestination.OWNER_HAND.value


def prepare_return_to_owner_hand(
    host: ReturnToHandHost,
    request: ReturnToHandRequest,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> ReturnToHandPlan:
    return prepare_single_object_zone_transition(
        host,
        request,
        actor=actor,
        reason=reason,
        requested_destination=SingleObjectDestination.OWNER_HAND,
        replacement_selections=replacement_selections,
    )


def validate_return_to_hand_plan(
    host: ReturnToHandHost,
    plan: ReturnToHandPlan,
) -> None:
    if (
        not isinstance(plan, ReturnToHandPlan)
        or plan.requested_destination is not SingleObjectDestination.OWNER_HAND
    ):
        raise ReturnToHandError("Permanent return requires a typed hand plan")
    validate_single_object_zone_transition_plan(host, plan)


def commit_return_to_owner_hand(
    host: ReturnToHandHost,
    plan: ReturnToHandPlan,
) -> ReturnToHandResult:
    validate_return_to_hand_plan(host, plan)
    transition = commit_prevalidated_single_object_zone_transition(host, plan)
    result = ReturnToHandResult(
        object_id=transition.object_id,
        object_ref=transition.object_ref,
        owner=transition.owner,
        origin_controller=transition.origin_controller,
        destination=transition.actual_destination,
        logical_object_id=transition.logical_object_id,
    )
    host._log(
        plan.actor,
        "permanent.return_to_owner_hand",
        f"{result.object_ref} moved toward its owner's hand.",
        {
            "object": result.object_ref,
            "owner": result.owner,
            "origin_controller": result.origin_controller,
            "requested_destination": SingleObjectDestination.OWNER_HAND.value,
            "destination": result.destination,
            "reason": plan.reason,
        },
        importance=2,
        changed_objects=[result.object_id],
        changed_players=[result.owner, result.origin_controller],
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
