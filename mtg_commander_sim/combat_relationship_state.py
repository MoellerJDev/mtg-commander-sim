from __future__ import annotations

from dataclasses import dataclass

from .model import CombatState


class CombatRelationshipStateError(ValueError):
    """A combat relationship mutation request is malformed."""


@dataclass(frozen=True, slots=True)
class CombatRelationshipRemoval:
    was_attacker: bool
    removed_as_blocker: bool
    unlinked_blocker_object_ids: tuple[str, ...]


def remove_combat_relationships(
    combat: CombatState,
    object_id: str,
) -> CombatRelationshipRemoval:
    """Remove one object and all incident edges from represented combat."""

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

    unlinked_blockers: tuple[str, ...] = ()
    if was_attacker:
        unlinked_blockers = tuple(combat.blockers.pop(object_id, ()))
        combat.attackers.pop(object_id, None)
        combat.attack_target_context.pop(object_id, None)

    return CombatRelationshipRemoval(
        was_attacker=was_attacker,
        removed_as_blocker=removed_as_blocker,
        unlinked_blocker_object_ids=unlinked_blockers,
    )


__all__ = [
    "CombatRelationshipRemoval",
    "CombatRelationshipStateError",
    "remove_combat_relationships",
]
