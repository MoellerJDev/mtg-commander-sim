from __future__ import annotations

from typing import Hashable, Protocol, Sequence, TypeVar


HostT = TypeVar("HostT")
ChangeT = TypeVar("ChangeT")
TransitionT = TypeVar("TransitionT")
KeyT = TypeVar("KeyT", bound=Hashable)


class StateChangeAdapter(Protocol[HostT, ChangeT, TransitionT, KeyT]):
    """Typed domain adapter for an atomic shadow-state transaction."""

    def validate_change(self, change: ChangeT) -> None: ...

    def key(self, change: ChangeT) -> KeyT: ...

    def current_value(self, host: HostT, change: ChangeT) -> int: ...

    def next_value(self, before: int, change: ChangeT) -> int: ...

    def transition(
        self,
        change: ChangeT,
        *,
        before: int,
        after: int,
    ) -> TransitionT: ...

    def change_from_transition(self, transition: TransitionT) -> ChangeT: ...

    def transition_before(self, transition: TransitionT) -> int: ...

    def transition_after(self, transition: TransitionT) -> int: ...

    def validate_transition(self, transition: TransitionT) -> None: ...

    def apply_final(self, host: HostT, transition: TransitionT) -> None: ...


def plan_state_changes(
    host: HostT,
    changes: Sequence[ChangeT],
    adapter: StateChangeAdapter[HostT, ChangeT, TransitionT, KeyT],
) -> tuple[TransitionT, ...]:
    """Build deterministic transitions against an isolated shadow state."""

    shadow: dict[KeyT, int] = {}
    transitions: list[TransitionT] = []
    for change in tuple(changes):
        adapter.validate_change(change)
        key = adapter.key(change)
        before = shadow.get(key)
        if before is None:
            before = adapter.current_value(host, change)
        after = adapter.next_value(before, change)
        transition = adapter.transition(
            change,
            before=before,
            after=after,
        )
        adapter.validate_transition(transition)
        transitions.append(transition)
        shadow[key] = after
    return tuple(transitions)


def validate_state_plan(
    host: HostT,
    transitions: Sequence[TransitionT],
    adapter: StateChangeAdapter[HostT, ChangeT, TransitionT, KeyT],
) -> None:
    """Validate the complete plan before any final value is written."""

    expected: dict[KeyT, int] = {}
    initial: dict[KeyT, tuple[ChangeT, int]] = {}
    for transition in tuple(transitions):
        adapter.validate_transition(transition)
        change = adapter.change_from_transition(transition)
        adapter.validate_change(change)
        key = adapter.key(change)
        before = adapter.transition_before(transition)
        if key not in expected:
            current = adapter.current_value(host, change)
            expected[key] = current
            initial[key] = (change, before)
        if before != expected[key]:
            raise ValueError("State plan is stale")
        expected[key] = adapter.transition_after(transition)
    for change, before in initial.values():
        if adapter.current_value(host, change) != before:
            raise ValueError("State plan changed before commit")


def apply_state_plan(
    host: HostT,
    transitions: Sequence[TransitionT],
    adapter: StateChangeAdapter[HostT, ChangeT, TransitionT, KeyT],
) -> tuple[TransitionT, ...]:
    """Write one validated final transition per typed domain key."""

    stable = tuple(transitions)
    final: dict[KeyT, TransitionT] = {}
    for transition in stable:
        change = adapter.change_from_transition(transition)
        final[adapter.key(change)] = transition
    for transition in final.values():
        adapter.apply_final(host, transition)
    return stable


def commit_state_plan(
    host: HostT,
    transitions: Sequence[TransitionT],
    adapter: StateChangeAdapter[HostT, ChangeT, TransitionT, KeyT],
) -> tuple[TransitionT, ...]:
    validate_state_plan(host, transitions, adapter)
    return apply_state_plan(host, transitions, adapter)
