from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Sequence

from .model import DrawError


def _text(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise DrawError(f"{field} must be a nonempty string")
    return value


def _count(value: Any, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise DrawError(f"{field} must be a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class DrawRestriction:
    """One currently applicable continuous prohibition on card draws."""

    restriction_id: str
    source_ref: str
    maximum_per_turn: int

    def __post_init__(self) -> None:
        _text(self.restriction_id, field="Draw restriction ID")
        _text(self.source_ref, field="Draw restriction source")
        _count(
            self.maximum_per_turn,
            field="Draw restriction maximum",
        )


@dataclass(frozen=True, slots=True)
class DrawPermission:
    """Immutable CR 121.2b/121.3 feasibility for one prospective drawer."""

    player: str
    drawn_this_turn: int
    maximum_per_turn: int | None = None
    restriction_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.player, field="Draw permission player")
        _count(self.drawn_this_turn, field="Drawn-this-turn count")
        if self.maximum_per_turn is not None:
            _count(
                self.maximum_per_turn,
                field="Draw permission maximum",
            )
        if any(type(value) is not str or not value for value in self.restriction_ids):
            raise DrawError(
                "Draw permission restriction IDs must be nonempty strings"
            )
        if (
            len(self.restriction_ids) != len(set(self.restriction_ids))
            or tuple(sorted(self.restriction_ids)) != self.restriction_ids
        ):
            raise DrawError(
                "Draw permission restriction IDs must be unique and canonical"
            )
        if self.maximum_per_turn is None and self.restriction_ids:
            raise DrawError(
                "An unlimited draw permission cannot carry restrictions"
            )

    @property
    def remaining(self) -> int | None:
        if self.maximum_per_turn is None:
            return None
        return max(0, self.maximum_per_turn - self.drawn_this_turn)

    def allows_individual_draw(self) -> bool:
        remaining = self.remaining
        return remaining is None or remaining > 0

    def allows_complete_draw(self, count: int) -> bool:
        """Return whether an optional instruction or draw cost is legal."""

        requested = _count(count, field="Prospective draw count")
        remaining = self.remaining
        return remaining is None or requested <= remaining

    def to_dict(self) -> dict[str, Any]:
        return {
            "player": self.player,
            "drawn_this_turn": self.drawn_this_turn,
            "maximum_per_turn": self.maximum_per_turn,
            "restriction_ids": list(self.restriction_ids),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DrawPermission":
        if not isinstance(value, Mapping):
            raise DrawError("Draw permission must be an object")
        expected = {
            "player",
            "drawn_this_turn",
            "maximum_per_turn",
            "restriction_ids",
        }
        if set(value) != expected:
            raise DrawError("Draw permission fields are invalid")
        restriction_ids = value["restriction_ids"]
        if not isinstance(restriction_ids, (list, tuple)):
            raise DrawError("Draw permission restriction IDs must be a list")
        return cls(
            player=value["player"],
            drawn_this_turn=value["drawn_this_turn"],
            maximum_per_turn=value["maximum_per_turn"],
            restriction_ids=tuple(restriction_ids),
        )


class DrawRestrictionPlayer(Protocol):
    stats: Mapping[str, Any]


class DrawRestrictionState(Protocol):
    turn_sequence: int
    players: Mapping[str, DrawRestrictionPlayer]


class DrawRestrictionHost(Protocol):
    state: DrawRestrictionState


def evaluate_draw_permission(
    player: str,
    *,
    drawn_this_turn: int,
    restrictions: Sequence[DrawRestriction] = (),
) -> DrawPermission:
    _text(player, field="Prospective draw player")
    drawn = _count(drawn_this_turn, field="Drawn-this-turn count")
    typed = tuple(restrictions)
    if any(not isinstance(value, DrawRestriction) for value in typed):
        raise DrawError("Draw restrictions must be typed values")
    identifiers = tuple(sorted(value.restriction_id for value in typed))
    if len(identifiers) != len(set(identifiers)):
        raise DrawError("Draw restriction IDs must be unique")
    return DrawPermission(
        player=player,
        drawn_this_turn=drawn,
        maximum_per_turn=(
            min(value.maximum_per_turn for value in typed)
            if typed
            else None
        ),
        restriction_ids=identifiers,
    )


def drawn_this_turn(host: DrawRestrictionHost, player: str) -> int:
    if player not in host.state.players:
        raise DrawError(f"Unknown draw player {player!r}")
    tracker = host.state.players[player].stats.get("cards_drawn_by_turn", {})
    if not isinstance(tracker, Mapping):
        raise DrawError("Draw-count tracker is malformed")
    value = tracker.get(str(host.state.turn_sequence), 0)
    return _count(value, field="Draw-count tracker value")


def require_payable_draw_cost(
    permission: DrawPermission,
    count: int,
) -> None:
    if not isinstance(permission, DrawPermission):
        raise DrawError("Draw costs require a typed permission")
    if not permission.allows_complete_draw(count):
        raise DrawError(
            f"{permission.player} cannot pay a cost that requires drawing "
            f"{count} card(s)"
        )


__all__ = [
    "DrawPermission",
    "DrawRestriction",
    "DrawRestrictionHost",
    "drawn_this_turn",
    "evaluate_draw_permission",
    "require_payable_draw_cost",
]
