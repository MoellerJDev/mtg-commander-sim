from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from .counter_state import (
    commit_counter_changes,
    CounterChange,
    CounterStateError,
    CounterStateHost,
    CounterStatePlan,
    CounterTransition,
    normalized_counter_name,
    plan_counter_changes,
)


class CounterRemovalError(ValueError):
    """A mandatory counter-removal transaction is malformed or stale."""


class CounterRemovalHost(CounterStateHost, Protocol):
    pass


@dataclass(frozen=True, slots=True)
class CounterRemoval:
    object_id: str
    counter_name: str
    amount: int
    expected_zone: str = "battlefield"
    expected_logical_object_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.object_id) is not str or not self.object_id:
            raise CounterRemovalError(
                "Counter removal requires permanent identity"
            )
        if type(self.counter_name) is not str:
            raise CounterRemovalError(
                "Counter removal requires a counter name"
            )
        try:
            normalized_name = normalized_counter_name(self.counter_name)
        except CounterStateError as exc:
            raise CounterRemovalError(str(exc)) from exc
        object.__setattr__(self, "counter_name", normalized_name)
        if type(self.amount) is not int or self.amount <= 0:
            raise CounterRemovalError(
                "Counter removal amounts must be positive integers"
            )
        if type(self.expected_zone) is not str or not self.expected_zone:
            raise CounterRemovalError(
                "Counter removal requires an expected zone"
            )
        if self.expected_logical_object_id is not None and (
            type(self.expected_logical_object_id) is not str
            or not self.expected_logical_object_id
        ):
            raise CounterRemovalError(
                "Counter removal logical identity must be a nonempty string"
            )

    @property
    def key(self) -> tuple[str, str]:
        return self.object_id, self.counter_name


@dataclass(frozen=True, slots=True)
class CounterRemovalPlan:
    removals: tuple[CounterRemoval, ...]
    counter_plan: CounterStatePlan

    def __post_init__(self) -> None:
        if not isinstance(self.counter_plan, CounterStatePlan):
            raise CounterRemovalError(
                "Counter-removal plan requires a typed counter plan"
            )
        if len(self.removals) != len(self.counter_plan.transitions):
            raise CounterRemovalError(
                "Counter-removal plan shape is inconsistent"
            )


def _counter_change(removal: CounterRemoval) -> CounterChange:
    return CounterChange(
        subject_kind="permanent",
        subject_id=removal.object_id,
        counter_name=removal.counter_name,
        amount=-removal.amount,
        expected_zone=removal.expected_zone,
        expected_logical_object_id=removal.expected_logical_object_id,
    )


def _validate_exact_removal(
    removal: CounterRemoval,
    transition: CounterTransition,
) -> None:
    if (
        transition.subject_kind != "permanent"
        or transition.subject_id != removal.object_id
        or transition.counter_name != removal.counter_name
        or transition.requested_delta != -removal.amount
        or transition.applied_delta != -removal.amount
    ):
        raise CounterRemovalError(
            "The permanent does not have enough counters to remove"
        )


def plan_counter_removals(
    host: CounterRemovalHost,
    removals: Sequence[CounterRemoval],
) -> CounterRemovalPlan:
    """Canonicalize and preflight an exact permanent-counter removal batch."""

    supplied = tuple(removals)
    if any(not isinstance(removal, CounterRemoval) for removal in supplied):
        raise CounterRemovalError(
            "Counter-removal plans require typed removals"
        )
    canonical = tuple(sorted(supplied, key=lambda value: value.key))
    keys = tuple(removal.key for removal in canonical)
    if len(keys) != len(set(keys)):
        raise CounterRemovalError(
            "Counter-removal plans require one request per counter kind"
        )
    try:
        counter_plan = plan_counter_changes(
            host,
            tuple(_counter_change(removal) for removal in canonical),
        )
    except CounterStateError as exc:
        raise CounterRemovalError(str(exc)) from exc
    for removal, transition in zip(
        canonical,
        counter_plan.transitions,
        strict=True,
    ):
        _validate_exact_removal(removal, transition)
    return CounterRemovalPlan(canonical, counter_plan)


def commit_counter_removals(
    host: CounterRemovalHost,
    plan: CounterRemovalPlan,
) -> tuple[CounterTransition, ...]:
    """Commit an exact preflighted removal batch through counter state."""

    if not isinstance(plan, CounterRemovalPlan):
        raise CounterRemovalError(
            "Counter-removal commit requires a typed plan"
        )
    for removal, transition in zip(
        plan.removals,
        plan.counter_plan.transitions,
        strict=True,
    ):
        _validate_exact_removal(removal, transition)
    try:
        return commit_counter_changes(host, plan.counter_plan)
    except CounterStateError as exc:
        raise CounterRemovalError(str(exc)) from exc


__all__ = [
    "commit_counter_removals",
    "CounterRemoval",
    "CounterRemovalError",
    "CounterRemovalHost",
    "CounterRemovalPlan",
    "plan_counter_removals",
]
