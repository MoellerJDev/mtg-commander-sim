from __future__ import annotations

from .combat_damage_assignment import (
    build_combat_damage_assignment_proposal,
    CombatDamageAssignmentProposal,
)
from .combat_damage_snapshot import (
    build_combat_damage_snapshot,
    CombatDamageQuery,
)


def project_combat_damage_assignment(
    query: CombatDamageQuery,
    seat: str,
) -> CombatDamageAssignmentProposal:
    """Project authoritative combat state into an immutable CR 510 proposal."""

    return build_combat_damage_assignment_proposal(
        seat=seat,
        snapshot=build_combat_damage_snapshot(query),
    )


__all__ = ["project_combat_damage_assignment"]
