from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .model import CombatState


class CombatRelationshipStateError(ValueError):
    """A combat relationship mutation request is malformed."""


@dataclass(frozen=True, slots=True)
class CombatRelationshipRemoval:
    was_attacker: bool
    removed_as_blocker: bool


@dataclass(frozen=True, slots=True)
class BlockDeclarationAssignment:
    """One validated ordinary blocker relationship ready to commit."""

    blocker_object_id: str
    attacker_object_id: str

    def __post_init__(self) -> None:
        for field in ("blocker_object_id", "attacker_object_id"):
            value = getattr(self, field)
            if type(value) is not str or not value:
                raise CombatRelationshipStateError(
                    "Block declaration identities must be nonempty strings"
                )
        if self.blocker_object_id == self.attacker_object_id:
            raise CombatRelationshipStateError(
                "A creature cannot block itself"
            )


def commit_block_declaration(
    combat: CombatState,
    cards: Mapping[str, Any],
    *,
    controller: str,
    assignments: Sequence[BlockDeclarationAssignment],
) -> tuple[BlockDeclarationAssignment, ...]:
    """Commit one defender's already-validated declaration atomically.

    Selection, restriction, cost, and payment legality remain outside this
    narrow relationship mutation owner. A blocker invalidated during payment
    is omitted exactly as it was at the former engine-owned write boundary.
    """

    if not isinstance(combat, CombatState):
        raise CombatRelationshipStateError(
            "Block declaration commit requires CombatState"
        )
    if type(controller) is not str or not controller:
        raise CombatRelationshipStateError(
            "Block declaration controller must be a nonempty string"
        )
    values = tuple(assignments)
    if any(not isinstance(value, BlockDeclarationAssignment) for value in values):
        raise CombatRelationshipStateError(
            "Block declaration commit requires typed assignments"
        )
    blocker_ids = [value.blocker_object_id for value in values]
    if len(blocker_ids) != len(set(blocker_ids)):
        raise CombatRelationshipStateError(
            "A blocker cannot be committed more than once"
        )
    committed: list[BlockDeclarationAssignment] = []
    for assignment in values:
        attacker = cards.get(assignment.attacker_object_id)
        blocker = cards.get(assignment.blocker_object_id)
        if (
            attacker is None
            or assignment.attacker_object_id not in combat.attackers
        ):
            raise CombatRelationshipStateError(
                "A committed block requires a current attacker"
            )
        if blocker is None:
            raise CombatRelationshipStateError(
                "A committed block requires a known blocker"
            )
        if (
            blocker.zone != "battlefield"
            or blocker.controller != controller
            or blocker.phased_out
        ):
            continue
        existing = combat.blockers.setdefault(
            assignment.attacker_object_id, []
        )
        if assignment.blocker_object_id in existing:
            raise CombatRelationshipStateError(
                "A blocker relationship is already committed"
            )
        existing.append(assignment.blocker_object_id)
        blocker.blocking = assignment.attacker_object_id
        committed.append(assignment)
    return tuple(committed)


def remove_combat_relationships(
    combat: CombatState,
    object_id: str,
) -> CombatRelationshipRemoval:
    """Remove one current combat role while preserving CR 506.4 history."""

    if not isinstance(combat, CombatState):
        raise CombatRelationshipStateError(
            "Combat relationship mutation requires CombatState"
        )
    if not isinstance(object_id, str) or not object_id:
        raise CombatRelationshipStateError(
            "Combat relationship mutation requires an object identity"
        )

    was_attacker = object_id in combat.attackers
    removed_as_blocker = False
    for blocker_ids in combat.blockers.values():
        if object_id not in blocker_ids:
            continue
        blocker_ids[:] = [
            blocker_id
            for blocker_id in blocker_ids
            if blocker_id != object_id
        ]
        removed_as_blocker = True

    if was_attacker:
        # CR 506.4 removes the attacker from combat but does not remove the
        # creatures that blocked it. Preserve that historical relationship so
        # those creatures remain blocking, while current-damage snapshots omit
        # relationships whose attacker is no longer in combat.
        combat.attackers.pop(object_id, None)
        combat.attack_target_context.pop(object_id, None)

    return CombatRelationshipRemoval(
        was_attacker=was_attacker,
        removed_as_blocker=removed_as_blocker,
    )


__all__ = [
    "BlockDeclarationAssignment",
    "CombatRelationshipRemoval",
    "CombatRelationshipStateError",
    "commit_block_declaration",
    "remove_combat_relationships",
]
