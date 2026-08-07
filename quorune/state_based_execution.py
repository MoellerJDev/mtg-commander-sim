from __future__ import annotations

from dataclasses import dataclass

from .destruction import (
    commit_destruction_plan,
    DestructionCause,
    DestructionHost,
    DestructionPlan,
    prepare_destructions,
    request_for_card,
)
from .state_based_actions import StateBasedActionBatch
from .util import unique_preserving_order


class StateBasedExecutionError(ValueError):
    """A state-based action batch cannot be prepared transactionally."""


@dataclass(frozen=True, slots=True)
class StateBasedExecutionPlan:
    destruction: DestructionPlan
    ordinary_move_to_grave: tuple[str, ...]
    move_to_grave: tuple[str, ...]
    simultaneous_changes: tuple[tuple[str, str], ...]
    destruction_companions: tuple[tuple[str, str], ...]
    state_changed: bool


def prepare_state_based_execution(
    host: DestructionHost,
    batch: StateBasedActionBatch,
) -> StateBasedExecutionPlan:
    """Bind one pure SBA snapshot to typed destruction and zone owners."""

    if not isinstance(batch, StateBasedActionBatch):
        raise StateBasedExecutionError(
            "State-based execution requires a typed action batch"
        )
    destruction = prepare_destructions(
        host,
        tuple(
            request_for_card(host.state.cards[object_id])
            for object_id in batch.destroy
        ),
        cause=DestructionCause.STATE_BASED_ACTION,
        actor=None,
        reason="state-based action",
    )
    ordinary = tuple(
        unique_preserving_order(
            (*batch.put_in_graveyard, *destruction.destroyed_object_ids)
        )
    )
    moved = tuple(
        unique_preserving_order((*ordinary, *batch.world_rule))
    )
    if any(
        not isinstance(object_id, str)
        or not object_id
        or object_id not in host.state.cards
        for object_id in moved
    ):
        raise StateBasedExecutionError(
            "State-based zone changes contain an unknown object"
        )
    simultaneous = tuple(
        (object_id, "graveyard")
        for object_id in moved
        if host.state.cards[object_id].zone == "battlefield"
    )
    destroyed = set(destruction.destroyed_object_ids)
    companions = tuple(
        change for change in simultaneous if change[0] not in destroyed
    )
    return StateBasedExecutionPlan(
        destruction=destruction,
        ordinary_move_to_grave=ordinary,
        move_to_grave=moved,
        simultaneous_changes=simultaneous,
        destruction_companions=companions,
        state_changed=bool(
            ordinary
            or batch.detach
            or batch.counter_pairs_to_remove
            or batch.counter_maximums_to_remove
            or batch.cease
            or batch.world_rule
        ),
    )


def commit_state_based_zone_changes(
    host: DestructionHost,
    plan: StateBasedExecutionPlan,
) -> None:
    if not isinstance(plan, StateBasedExecutionPlan):
        raise StateBasedExecutionError(
            "State-based commit requires a typed execution plan"
        )
    if not plan.simultaneous_changes:
        return
    commit_destruction_plan(
        host,
        plan.destruction,
        companion_changes=plan.destruction_companions,
    )


__all__ = [
    "commit_state_based_zone_changes",
    "prepare_state_based_execution",
    "StateBasedExecutionError",
    "StateBasedExecutionPlan",
]
