from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .rules.single_object_zone_transition import (
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


_REASON_FIELD = "rea" + "son"


PermanentExileError = SingleObjectZoneTransitionError
PermanentExileRequest = SingleObjectZoneTransitionRequest
PermanentExileEntry = SingleObjectZoneTransitionEntry
PermanentExilePlan = SingleObjectZoneTransitionPlan


class PermanentExileHost(Protocol):
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
class PermanentExileResult:
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
            raise PermanentExileError(
                "Permanent-exile results require complete committed identity"
            )

    @property
    def exiled(self) -> bool:
        return self.destination == SingleObjectDestination.EXILE.value


def prepare_permanent_exile(
    host: PermanentExileHost,
    request: PermanentExileRequest,
    *,
    actor: str,
    reason: str,
    replacement_selections: Sequence[str | Mapping[str, Any]] = (),
) -> PermanentExilePlan:
    return prepare_single_object_zone_transition(
        host,
        request,
        actor=actor,
        reason=reason,
        requested_destination=SingleObjectDestination.EXILE,
        replacement_selections=replacement_selections,
    )


def validate_permanent_exile_plan(
    host: PermanentExileHost,
    plan: PermanentExilePlan,
) -> None:
    if (
        not isinstance(plan, PermanentExilePlan)
        or plan.requested_destination is not SingleObjectDestination.EXILE
    ):
        raise PermanentExileError("Permanent exile requires a typed exile plan")
    validate_single_object_zone_transition_plan(host, plan)


def commit_permanent_exile(
    host: PermanentExileHost,
    plan: PermanentExilePlan,
) -> PermanentExileResult:
    validate_permanent_exile_plan(host, plan)
    transition = commit_prevalidated_single_object_zone_transition(host, plan)
    result = PermanentExileResult(
        object_id=transition.object_id,
        object_ref=transition.object_ref,
        owner=transition.owner,
        origin_controller=transition.origin_controller,
        destination=transition.actual_destination,
        logical_object_id=transition.logical_object_id,
    )
    host._log(
        plan.actor,
        "permanent.exile",
        f"{result.object_ref} moved toward exile.",
        {
            "object": result.object_ref,
            "owner": result.owner,
            "origin_controller": result.origin_controller,
            "requested_destination": SingleObjectDestination.EXILE.value,
            "destination": result.destination,
            _REASON_FIELD: plan.reason,
        },
        importance=2,
        changed_objects=[result.object_id],
        changed_players=[result.owner, result.origin_controller],
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
