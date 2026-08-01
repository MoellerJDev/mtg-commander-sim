from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class SemanticNodeError(ValueError):
    """A registered semantic node is malformed for the current rules view."""


@dataclass(frozen=True, slots=True)
class ReadOnlyRulesQuery:
    """Minimum immutable rules facts exposed to generic semantic handlers."""

    seats: tuple[str, ...]
    active_seats: tuple[str, ...]
    apnap_order: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.seats or len(self.seats) != len(set(self.seats)):
            raise SemanticNodeError("Rules query seats must be unique and nonempty")
        if any(seat not in self.seats for seat in self.active_seats):
            raise SemanticNodeError("Active seats must belong to the game")
        if len(self.active_seats) != len(set(self.active_seats)):
            raise SemanticNodeError("Active seats must be unique")
        if (
            len(self.apnap_order) != len(self.active_seats)
            or len(self.apnap_order) != len(set(self.apnap_order))
            or set(self.apnap_order) != set(self.active_seats)
        ):
            raise SemanticNodeError(
                "APNAP order must contain each active seat exactly once"
            )

    def require_known_seat(self, seat: str) -> str:
        if seat not in self.seats:
            raise SemanticNodeError(f"Unknown seat {seat!r}")
        return seat

    def require_active_seat(self, seat: str) -> str:
        self.require_known_seat(seat)
        if seat not in self.active_seats:
            raise SemanticNodeError(f"{seat} is no longer in the game")
        return seat


@dataclass(frozen=True, slots=True)
class ReadOnlyHandlerContext:
    """Handler input that deliberately excludes GameState and hidden zones."""

    actor: str
    default_reason: str
    query: ReadOnlyRulesQuery

    @classmethod
    def from_sequences(
        cls,
        *,
        actor: str,
        default_reason: str,
        seats: Iterable[str],
        active_seats: Iterable[str],
        apnap_order: Iterable[str],
    ) -> "ReadOnlyHandlerContext":
        return cls(
            actor=actor,
            default_reason=default_reason,
            query=ReadOnlyRulesQuery(
                seats=tuple(seats),
                active_seats=tuple(active_seats),
                apnap_order=tuple(apnap_order),
            ),
        )

    def __post_init__(self) -> None:
        self.query.require_known_seat(self.actor)
        if not self.default_reason:
            raise SemanticNodeError("A semantic effect requires a reason")
