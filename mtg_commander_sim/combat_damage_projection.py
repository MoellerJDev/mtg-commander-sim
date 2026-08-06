from __future__ import annotations

from typing import TYPE_CHECKING

from .combat_damage_assignment import (
    build_combat_damage_assignment_proposal,
    CombatDamageAssignmentProposal,
    CombatDamageParticipant,
)

if TYPE_CHECKING:
    from .engine import CommanderEngine


def project_combat_damage_assignment(
    engine: CommanderEngine,
    seat: str,
) -> CombatDamageAssignmentProposal:
    """Project authoritative combat state into an immutable CR 510 proposal."""

    participants = tuple(
        CombatDamageParticipant(
            object_id=card.object_id,
            reference=card.ref,
            controller=card.controller,
            power=engine._numeric_stat(card.object_id, "power"),
            toughness=engine._numeric_stat(card.object_id, "toughness"),
            marked_damage=card.marked_damage,
            keywords=engine._combat_keywords(card),
            assigns_damage=engine._assigns_combat_damage_this_step(card),
        )
        for card in engine._combat_damage_participants()
    )
    return build_combat_damage_assignment_proposal(
        seat=seat,
        attackers=engine.state.combat.attackers,
        blockers=engine.state.combat.blockers,
        participants=participants,
        valid_spill_targets={
            attacker_id: str(target)
            for attacker_id, target in engine.state.combat.attackers.items()
            if engine._combat_damage_target_exists(
                str(target), attacker_id=attacker_id
            )
        },
    )


__all__ = ["project_combat_damage_assignment"]
