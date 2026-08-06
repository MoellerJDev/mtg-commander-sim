from __future__ import annotations

from collections.abc import Sequence

from .combat_damage_values import CreatureDamageState, DamageAssignment
from . import deathtouch as deathtouch_rules


def trample_assignment_error(
    *,
    attacker_ref: str,
    spill_target: str,
    blockers: Sequence[tuple[str, CreatureDamageState]],
    assignments: Sequence[DamageAssignment],
    attacking_source_refs: frozenset[str],
    deathtouch_source_refs: frozenset[str],
) -> str | None:
    """Validate ordinary trample's lethal-before-spill rule (CR 702.19b)."""

    spilled = sum(
        assignment.amount
        for assignment in assignments
        if assignment.source == attacker_ref
        and assignment.target == spill_target
    )
    if spilled <= 0:
        return None
    for blocker_ref, state in blockers:
        assigned = [
            assignment
            for assignment in assignments
            if assignment.target == blocker_ref
            and assignment.source in attacking_source_refs
            and assignment.amount > 0
        ]
        assigned_amount = sum(assignment.amount for assignment in assigned)
        lethal = (
            any(
                deathtouch_rules.deathtouch_assignment_is_lethal(
                    source=assignment.source,
                    amount=assignment.amount,
                    deathtouch_sources=deathtouch_source_refs,
                )
                for assignment in assigned
            )
            or state.marked_damage + assigned_amount >= state.toughness
        )
        if not lethal:
            needed = max(0, state.toughness - state.marked_damage)
            return (
                f"{attacker_ref} cannot assign combat damage to "
                f"{spill_target} until {blocker_ref} has lethal damage "
                f"assigned (needs {needed}, has {assigned_amount})"
            )
    return None


__all__ = ["trample_assignment_error"]
