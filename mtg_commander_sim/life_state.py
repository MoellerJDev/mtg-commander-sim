from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


class LifeStateError(ValueError):
    """A typed life-total change cannot be planned or committed exactly."""


class LifeStateHost(Protocol):
    state: Any


@dataclass(frozen=True, slots=True)
class LifeChange:
    player: str
    amount: int

    def __post_init__(self) -> None:
        if not self.player:
            raise LifeStateError("Life changes require a player")
        if type(self.amount) is not int:
            raise LifeStateError("Life change amounts must be integers")


@dataclass(frozen=True, slots=True)
class LifeTransition:
    player: str
    requested_delta: int
    before: int
    after: int


@dataclass(frozen=True, slots=True)
class LifeStatePlan:
    transitions: tuple[LifeTransition, ...]

    @property
    def changed_players(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    transition.player
                    for transition in self.transitions
                    if transition.before != transition.after
                }
            )
        )


def _current_life(host: LifeStateHost, player: str) -> int:
    state = host.state.players.get(player)
    if state is None or player not in host.state.active_seats():
        raise LifeStateError("Life-change player is not active")
    return int(state.life)


def plan_life_changes(
    host: LifeStateHost,
    changes: Sequence[LifeChange],
) -> LifeStatePlan:
    """Validate and aggregate a simultaneous life-change batch."""

    shadow: dict[str, int] = {}
    transitions: list[LifeTransition] = []
    for change in changes:
        if not isinstance(change, LifeChange):
            raise LifeStateError("Life plans require typed changes")
        before = shadow.get(change.player)
        if before is None:
            before = _current_life(host, change.player)
        after = before + change.amount
        transitions.append(
            LifeTransition(
                player=change.player,
                requested_delta=change.amount,
                before=before,
                after=after,
            )
        )
        shadow[change.player] = after
    return LifeStatePlan(tuple(transitions))


def validate_life_changes(host: LifeStateHost, plan: LifeStatePlan) -> None:
    """Fail before mutation if any planned life total is stale."""

    if not isinstance(plan, LifeStatePlan):
        raise LifeStateError("Life commits require a typed plan")
    expected: dict[str, int] = {}
    first: dict[str, int] = {}
    for transition in plan.transitions:
        if transition.player not in expected:
            current = _current_life(host, transition.player)
            expected[transition.player] = current
            first[transition.player] = transition.before
        if transition.before != expected[transition.player]:
            raise LifeStateError("Life plan is stale")
        if transition.after != transition.before + transition.requested_delta:
            raise LifeStateError("Life transition arithmetic is invalid")
        expected[transition.player] = transition.after
    for player, before in first.items():
        if _current_life(host, player) != before:
            raise LifeStateError("Life plan changed before commit")


def apply_life_changes(
    host: LifeStateHost,
    plan: LifeStatePlan,
) -> tuple[LifeTransition, ...]:
    """Apply a life plan after the caller completed precommit validation."""

    final: dict[str, LifeTransition] = {}
    for transition in plan.transitions:
        final[transition.player] = transition
    for transition in final.values():
        host.state.players[transition.player].life = transition.after
    return plan.transitions


def commit_life_changes(
    host: LifeStateHost,
    plan: LifeStatePlan,
) -> tuple[LifeTransition, ...]:
    """Validate and commit one typed life-total batch."""

    validate_life_changes(host, plan)
    return apply_life_changes(host, plan)
