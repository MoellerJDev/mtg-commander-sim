from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .combat_damage_assignment import DamageAssignment


class CombatDamageSequenceError(ValueError):
    pass


def _identity(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CombatDamageSequenceError(f"{label} must be a nonempty string")
    return value


def _index(value: object, *, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise CombatDamageSequenceError(
            f"{label} must be an exact nonnegative integer"
        )
    return value


@dataclass(frozen=True, slots=True)
class CombatDamageAnnouncement:
    actor: str
    announcement_index: int
    automatic: bool
    proposal_id: str
    assignments: tuple[DamageAssignment, ...]

    def __post_init__(self) -> None:
        _identity(self.actor, label="Announcement actor")
        _index(self.announcement_index, label="Announcement index")
        if not isinstance(self.automatic, bool):
            raise CombatDamageSequenceError(
                "Automatic announcement state must be boolean"
            )
        _identity(self.proposal_id, label="Announcement proposal identity")
        assignments = tuple(self.assignments)
        if not all(isinstance(value, DamageAssignment) for value in assignments):
            raise CombatDamageSequenceError(
                "Announcements require typed canonical assignments"
            )
        pairs = [(value.source, value.target) for value in assignments]
        if len(pairs) != len(set(pairs)):
            raise CombatDamageSequenceError(
                "Announcement source-recipient pairs must be unique"
            )
        if any(value.amount <= 0 for value in assignments):
            raise CombatDamageSequenceError(
                "Announcements cannot contain zero damage assignments"
            )
        object.__setattr__(self, "assignments", assignments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor": self.actor,
            "announcement_index": self.announcement_index,
            "automatic": self.automatic,
            "proposal_id": self.proposal_id,
            "assignments": [value.to_dict() for value in self.assignments],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CombatDamageAnnouncement":
        if not isinstance(value, Mapping) or set(value) != {
            "actor",
            "announcement_index",
            "automatic",
            "proposal_id",
            "assignments",
        }:
            raise CombatDamageSequenceError(
                "Combat damage announcements have a closed schema"
            )
        raw_assignments = value["assignments"]
        if (
            not isinstance(raw_assignments, Sequence)
            or isinstance(raw_assignments, (str, bytes, Mapping))
        ):
            raise CombatDamageSequenceError(
                "Announcement assignments must be an array"
            )
        assignments: list[DamageAssignment] = []
        for raw in raw_assignments:
            if not isinstance(raw, Mapping) or set(raw) != {
                "source",
                "target",
                "amount",
            }:
                raise CombatDamageSequenceError(
                    "Announcement assignments have a closed schema"
                )
            assignments.append(
                DamageAssignment(
                    source=raw["source"],
                    target=raw["target"],
                    amount=raw["amount"],
                )
            )
        return cls(
            actor=value["actor"],
            announcement_index=value["announcement_index"],
            automatic=value["automatic"],
            proposal_id=value["proposal_id"],
            assignments=tuple(assignments),
        )


@dataclass(frozen=True, slots=True)
class CombatDamageAssignmentSequence:
    actors: tuple[str, ...]
    cursor: int = 0
    announcements: tuple[CombatDamageAnnouncement, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.actors, (str, bytes)):
            raise CombatDamageSequenceError(
                "Assignment actors must be a collection of seats"
            )
        actors = tuple(self.actors)
        announcements = tuple(self.announcements)
        object.__setattr__(self, "actors", actors)
        object.__setattr__(self, "announcements", announcements)
        if not all(isinstance(value, str) and value for value in actors):
            raise CombatDamageSequenceError(
                "Assignment actors must be nonempty strings"
            )
        if len(actors) != len(set(actors)):
            raise CombatDamageSequenceError(
                "Assignment actors must be unique"
            )
        _index(self.cursor, label="Assignment cursor")
        if self.cursor > len(actors):
            raise CombatDamageSequenceError(
                "Assignment cursor exceeds the APNAP order"
            )
        if len(announcements) != self.cursor:
            raise CombatDamageSequenceError(
                "Assignment announcements must exactly precede the cursor"
            )
        for index, announcement in enumerate(announcements):
            if not isinstance(announcement, CombatDamageAnnouncement):
                raise CombatDamageSequenceError(
                    "Assignment sequence announcements must be typed"
                )
            if (
                announcement.announcement_index != index
                or announcement.actor != actors[index]
            ):
                raise CombatDamageSequenceError(
                    "Assignment announcements must follow exact APNAP order"
                )

    @property
    def pending_actor(self) -> str | None:
        return self.actors[self.cursor] if self.cursor < len(self.actors) else None

    @property
    def collected_assignments(self) -> tuple[DamageAssignment, ...]:
        return tuple(
            assignment
            for announcement in self.announcements
            for assignment in announcement.assignments
        )

    def announce(
        self,
        *,
        actor: str,
        proposal_id: str,
        assignments: Sequence[DamageAssignment],
        automatic: bool,
    ) -> "CombatDamageAssignmentSequence":
        if actor != self.pending_actor:
            raise CombatDamageSequenceError(
                "Only the current APNAP actor may announce combat damage"
            )
        announcement = CombatDamageAnnouncement(
            actor=actor,
            announcement_index=self.cursor,
            automatic=automatic,
            proposal_id=proposal_id,
            assignments=tuple(assignments),
        )
        return CombatDamageAssignmentSequence(
            actors=self.actors,
            cursor=self.cursor + 1,
            announcements=(*self.announcements, announcement),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "actors": list(self.actors),
            "cursor": self.cursor,
            "announcements": [value.to_dict() for value in self.announcements],
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "CombatDamageAssignmentSequence":
        if not isinstance(value, Mapping) or set(value) != {
            "version",
            "actors",
            "cursor",
            "announcements",
        }:
            raise CombatDamageSequenceError(
                "Combat damage assignment sequences have a closed schema"
            )
        if value["version"] != 1:
            raise CombatDamageSequenceError(
                "Unsupported combat damage assignment sequence version"
            )
        actors = value["actors"]
        announcements = value["announcements"]
        if (
            not isinstance(actors, Sequence)
            or isinstance(actors, (str, bytes, Mapping))
            or not isinstance(announcements, Sequence)
            or isinstance(announcements, (str, bytes, Mapping))
        ):
            raise CombatDamageSequenceError(
                "Assignment actors and announcements must be arrays"
            )
        return cls(
            actors=tuple(actors),
            cursor=value["cursor"],
            announcements=tuple(
                CombatDamageAnnouncement.from_dict(item)
                for item in announcements
            ),
        )


__all__ = [
    "CombatDamageAnnouncement",
    "CombatDamageAssignmentSequence",
    "CombatDamageSequenceError",
]
