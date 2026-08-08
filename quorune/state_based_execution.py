from __future__ import annotations

from dataclasses import dataclass

from .counter_removal import (
    commit_counter_removals,
    CounterRemoval,
    CounterRemovalError,
    CounterRemovalPlan,
    plan_counter_removals,
)
from .counter_state import (
    CounterStateError,
    CounterTransition,
    normalized_counter_name,
)
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
class CounterPairRemoval:
    object_id: str
    pairs_removed: int


@dataclass(frozen=True, slots=True)
class CounterMaximumRemoval:
    object_id: str
    counter_name: str
    maximum: int
    required_removal: int


@dataclass(frozen=True, slots=True)
class StateBasedCounterRemovalPlan:
    counters: CounterRemovalPlan
    pairs: tuple[CounterPairRemoval, ...]
    maximums: tuple[CounterMaximumRemoval, ...]


@dataclass(frozen=True, slots=True)
class CounterMaximumRemovalResult:
    object_id: str
    counter_name: str
    before: int
    maximum: int
    required_removal: int
    after: int


@dataclass(frozen=True, slots=True)
class StateBasedCounterRemovalResult:
    pairs: tuple[CounterPairRemoval, ...]
    maximums: tuple[CounterMaximumRemovalResult, ...]


@dataclass(frozen=True, slots=True)
class StateBasedExecutionPlan:
    destruction: DestructionPlan
    ordinary_move_to_grave: tuple[str, ...]
    move_to_grave: tuple[str, ...]
    simultaneous_changes: tuple[tuple[str, str], ...]
    destruction_companions: tuple[tuple[str, str], ...]
    counter_removals: StateBasedCounterRemovalPlan
    state_changed: bool


def _prepare_counter_removals(
    host: DestructionHost,
    batch: StateBasedActionBatch,
    *,
    moving: frozenset[str],
) -> StateBasedCounterRemovalPlan:
    required: dict[tuple[str, str], int] = {}
    pairs: list[CounterPairRemoval] = []
    maximums: list[CounterMaximumRemoval] = []
    pair_objects: set[str] = set()
    maximum_keys: set[tuple[str, str]] = set()

    def surviving_card(object_id: str):
        if type(object_id) is not str or not object_id:
            raise StateBasedExecutionError(
                "State-based counter removal requires object identity"
            )
        card = host.state.cards.get(object_id)
        if card is None:
            raise StateBasedExecutionError(
                "State-based counter removal names an unknown object"
            )
        if object_id in moving or card.zone != "battlefield":
            return None
        return card

    for object_id, amount in batch.counter_pairs_to_remove:
        card = surviving_card(object_id)
        if card is None:
            continue
        if object_id in pair_objects:
            raise StateBasedExecutionError(
                "Opposing-counter removal names an object twice"
            )
        pair_objects.add(object_id)
        if type(amount) is not int or amount <= 0:
            raise StateBasedExecutionError(
                "Opposing-counter removal must be a positive integer"
            )
        pairs.append(CounterPairRemoval(object_id, amount))
        for counter_name in ("+1/+1", "-1/-1"):
            key = (object_id, counter_name)
            required[key] = max(required.get(key, 0), amount)

    for object_id, counter_name, amount in (
        batch.counter_maximums_to_remove
    ):
        card = surviving_card(object_id)
        if card is None:
            continue
        if type(counter_name) is not str:
            raise StateBasedExecutionError(
                "Maximum-counter removal requires a counter name"
            )
        try:
            counter_name = normalized_counter_name(counter_name)
        except CounterStateError as exc:
            raise StateBasedExecutionError(str(exc)) from exc
        maximum_key = (object_id, counter_name)
        if maximum_key in maximum_keys:
            raise StateBasedExecutionError(
                "Maximum-counter removal names a counter twice"
            )
        maximum_keys.add(maximum_key)
        if type(amount) is not int or amount <= 0:
            raise StateBasedExecutionError(
                "Maximum-counter removal must be a positive integer"
            )
        before_value = card.counters.get(counter_name, 0)
        if type(before_value) is not int or before_value < amount:
            raise StateBasedExecutionError(
                "Maximum-counter snapshot is malformed"
            )
        before = before_value
        maximums.append(
            CounterMaximumRemoval(
                object_id=object_id,
                counter_name=counter_name,
                maximum=before - amount,
                required_removal=amount,
            )
        )
        key = (object_id, counter_name)
        # Simultaneous SBA instructions may name the same indistinguishable
        # counters. The greatest required removal satisfies both instructions.
        required[key] = max(required.get(key, 0), amount)

    removals = tuple(
        CounterRemoval(
            object_id=object_id,
            counter_name=counter_name,
            amount=amount,
            expected_logical_object_id=(
                host.state.cards[object_id].logical_object_id
            ),
        )
        for (object_id, counter_name), amount in sorted(required.items())
    )
    try:
        counter_plan = plan_counter_removals(host, removals)
    except CounterRemovalError as exc:
        raise StateBasedExecutionError(str(exc)) from exc
    return StateBasedCounterRemovalPlan(
        counters=counter_plan,
        pairs=tuple(
            sorted(pairs, key=lambda value: value.object_id)
        ),
        maximums=tuple(
            sorted(
                maximums,
                key=lambda value: (
                    value.object_id,
                    value.counter_name,
                ),
            )
        ),
    )


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
    counter_removals = _prepare_counter_removals(
        host,
        batch,
        moving=frozenset(moved),
    )
    return StateBasedExecutionPlan(
        destruction=destruction,
        ordinary_move_to_grave=ordinary,
        move_to_grave=moved,
        simultaneous_changes=simultaneous,
        destruction_companions=companions,
        counter_removals=counter_removals,
        state_changed=bool(
            ordinary
            or batch.detach
            or counter_removals.counters.removals
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


def commit_state_based_counter_removals(
    host: DestructionHost,
    plan: StateBasedCounterRemovalPlan,
) -> StateBasedCounterRemovalResult:
    """Commit the surviving portion of one simultaneous SBA snapshot."""

    if not isinstance(plan, StateBasedCounterRemovalPlan):
        raise StateBasedExecutionError(
            "State-based counter commit requires a typed plan"
        )
    try:
        transitions = commit_counter_removals(host, plan.counters)
    except CounterRemovalError as exc:
        raise StateBasedExecutionError(str(exc)) from exc
    by_key: dict[tuple[str, str], CounterTransition] = {
        (transition.subject_id, transition.counter_name): transition
        for transition in transitions
    }
    maximum_results = tuple(
        CounterMaximumRemovalResult(
            object_id=value.object_id,
            counter_name=value.counter_name,
            before=by_key[(value.object_id, value.counter_name)].before,
            maximum=value.maximum,
            required_removal=value.required_removal,
            after=by_key[(value.object_id, value.counter_name)].after,
        )
        for value in plan.maximums
    )
    return StateBasedCounterRemovalResult(
        pairs=plan.pairs,
        maximums=maximum_results,
    )


__all__ = [
    "commit_state_based_counter_removals",
    "commit_state_based_zone_changes",
    "CounterMaximumRemoval",
    "CounterMaximumRemovalResult",
    "CounterPairRemoval",
    "prepare_state_based_execution",
    "StateBasedCounterRemovalPlan",
    "StateBasedCounterRemovalResult",
    "StateBasedExecutionError",
    "StateBasedExecutionPlan",
]
