from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


FIRST_STRIKE = "first strike"
DOUBLE_STRIKE = "double strike"
DEATHTOUCH = "deathtouch"
TRAMPLE = "trample"
LIFELINK = "lifelink"
MENACE = "menace"
DEFENDER = "defender"


def normalized_keywords(values: Iterable[object]) -> frozenset[str]:
    """Return the rules-facing, case-insensitive keyword set."""

    return frozenset(str(value).casefold() for value in values)


def first_strike_step_required(
    keywords_by_object: Mapping[str, frozenset[str]],
) -> bool:
    return any(
        keywords.intersection({FIRST_STRIKE, DOUBLE_STRIKE})
        for keywords in keywords_by_object.values()
    )


def ordinary_second_step_combatants(
    keywords_by_object: Mapping[str, frozenset[str]],
) -> frozenset[str]:
    """Snapshot creatures that had neither strike ability as step one began."""

    return frozenset(
        object_id
        for object_id, keywords in keywords_by_object.items()
        if not keywords.intersection({FIRST_STRIKE, DOUBLE_STRIKE})
    )


def assigns_in_damage_step(
    *,
    object_id: str,
    current_keywords: frozenset[str],
    step_index: int,
    first_strike_step: bool,
    ordinary_second_step: frozenset[str],
) -> bool:
    """Implement the participant split in CR 510.4.

    The ordinary second-step set is frozen when the first damage step begins.
    Double strike is checked again for the second step, as required when the
    ability is gained or lost between steps.
    """

    if not first_strike_step:
        return step_index == 0
    if step_index == 0:
        return bool(
            current_keywords.intersection({FIRST_STRIKE, DOUBLE_STRIKE})
        )
    if step_index == 1:
        return (
            object_id in ordinary_second_step
            or DOUBLE_STRIKE in current_keywords
        )
    return False


def menace_block_error(
    attacker_ref: str,
    attacker_keywords: frozenset[str],
    blocker_count: int,
) -> str | None:
    if MENACE in attacker_keywords and blocker_count == 1:
        return (
            f"{attacker_ref} has menace and must be blocked by zero or "
            "at least two creatures"
        )
    return None


@dataclass(frozen=True, slots=True)
class DamageAssignment:
    source: str
    target: str
    amount: int


@dataclass(frozen=True, slots=True)
class CreatureDamageState:
    toughness: int
    marked_damage: int


def trample_assignment_error(
    *,
    attacker_ref: str,
    spill_target: str,
    blocker_refs: Sequence[str],
    assignments: Sequence[DamageAssignment],
    attacking_source_refs: frozenset[str],
    deathtouch_source_refs: frozenset[str],
    blocker_state: Mapping[str, CreatureDamageState],
) -> str | None:
    """Validate CR 702.19b before trample damage may spill over.

    Damage already marked and damage assigned by every attacking creature in
    this combat-damage announcement count. Prevention is deliberately ignored:
    CR 702.19b checks assignment, not the amount that will actually be dealt.
    """

    spilled = sum(
        assignment.amount
        for assignment in assignments
        if assignment.source == attacker_ref
        and assignment.target == spill_target
    )
    if spilled <= 0:
        return None

    for blocker_ref in blocker_refs:
        state = blocker_state.get(blocker_ref)
        if state is None:
            continue
        assigned = [
            assignment
            for assignment in assignments
            if assignment.target == blocker_ref
            and assignment.source in attacking_source_refs
            and assignment.amount > 0
        ]
        deathtouch_is_lethal = any(
            assignment.source in deathtouch_source_refs
            for assignment in assigned
        )
        assigned_amount = sum(
            assignment.amount for assignment in assigned
        )
        lethal = (
            deathtouch_is_lethal
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
