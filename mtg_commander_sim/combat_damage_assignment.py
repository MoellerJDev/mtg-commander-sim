from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class CombatDamageAssignmentError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DamageAssignment:
    source: str
    target: str
    amount: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "amount": self.amount,
        }


@dataclass(frozen=True, slots=True)
class CreatureDamageState:
    toughness: int
    marked_damage: int


@dataclass(frozen=True, slots=True)
class CombatDamageSourceSpec:
    source: str
    power: int
    targets: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.source:
            raise CombatDamageAssignmentError("Damage source is required")
        if self.power < 0:
            raise CombatDamageAssignmentError("Damage power cannot be negative")
        if not all(self.targets) or len(self.targets) != len(set(self.targets)):
            raise CombatDamageAssignmentError(
                "Damage targets must be unique nonempty references"
            )


@dataclass(frozen=True, slots=True)
class TrampleDamageSpec:
    attacker: str
    spill_target: str
    blockers: tuple[tuple[str, CreatureDamageState], ...]

    def __post_init__(self) -> None:
        blocker_refs = [reference for reference, _state in self.blockers]
        if not self.attacker or not self.spill_target:
            raise CombatDamageAssignmentError(
                "Trample source and spill target are required"
            )
        if len(blocker_refs) != len(set(blocker_refs)) or not all(blocker_refs):
            raise CombatDamageAssignmentError(
                "Trample blockers must have unique nonempty references"
            )


@dataclass(frozen=True, slots=True)
class CombatDamageAssignmentProposal:
    sources: tuple[CombatDamageSourceSpec, ...]
    attacking_sources: frozenset[str]
    deathtouch_sources: frozenset[str]
    trample_sources: tuple[TrampleDamageSpec, ...]

    def __post_init__(self) -> None:
        source_refs = [source.source for source in self.sources]
        if len(source_refs) != len(set(source_refs)):
            raise CombatDamageAssignmentError(
                "Combat damage sources must be unique"
            )
        source_set = set(source_refs)
        if not self.attacking_sources <= source_set:
            raise CombatDamageAssignmentError(
                "Attacking damage sources must be proposal sources"
            )
        if not self.deathtouch_sources <= self.attacking_sources:
            raise CombatDamageAssignmentError(
                "Deathtouch damage sources must be attacking sources"
            )
        tramplers = [source.attacker for source in self.trample_sources]
        if len(tramplers) != len(set(tramplers)) or not set(tramplers) <= source_set:
            raise CombatDamageAssignmentError(
                "Trample sources must be unique proposal sources"
            )

    def projected_options(self) -> dict[str, dict[str, Any]]:
        return {
            source.source: {
                "power": source.power,
                "targets": list(source.targets),
            }
            for source in self.sources
        }

    def validate(
        self, submitted: Sequence[Mapping[str, Any]]
    ) -> tuple[DamageAssignment, ...]:
        if (
            not isinstance(submitted, Sequence)
            or isinstance(submitted, (str, bytes, Mapping))
        ):
            raise CombatDamageAssignmentError(
                "Combat-damage assignments must be an array"
            )
        source_map = {source.source: source for source in self.sources}
        totals: dict[str, int] = {}
        canonical: list[DamageAssignment] = []
        seen_pairs: set[tuple[str, str]] = set()
        for raw in submitted:
            assignment = _parse_assignment(raw, source_map)
            pair = (assignment.source, assignment.target)
            if pair in seen_pairs:
                raise CombatDamageAssignmentError(
                    "A combat-damage source/target pair may appear only once"
                )
            seen_pairs.add(pair)
            totals[assignment.source] = (
                totals.get(assignment.source, 0) + assignment.amount
            )
            canonical.append(assignment)

        for source in self.sources:
            required = source.power if source.targets else 0
            assigned = totals.get(source.source, 0)
            if assigned != required:
                raise CombatDamageAssignmentError(
                    f"{source.source} must assign exactly {required} combat "
                    f"damage, not {assigned}"
                )

        assignments = tuple(canonical)
        for trample in self.trample_sources:
            error = trample_assignment_error(
                attacker_ref=trample.attacker,
                spill_target=trample.spill_target,
                blockers=trample.blockers,
                assignments=assignments,
                attacking_source_refs=self.attacking_sources,
                deathtouch_source_refs=self.deathtouch_sources,
            )
            if error is not None:
                raise CombatDamageAssignmentError(error)
        return assignments


def _parse_assignment(
    raw: Mapping[str, Any],
    source_map: Mapping[str, CombatDamageSourceSpec],
) -> DamageAssignment:
    if not isinstance(raw, Mapping):
        raise CombatDamageAssignmentError(
            "Each combat-damage assignment must be an object"
        )
    if set(raw) != {"source", "target", "amount"}:
        raise CombatDamageAssignmentError(
            "Combat-damage assignment requires exactly source, target, and amount"
        )
    if not isinstance(raw["source"], str):
        raise CombatDamageAssignmentError(
            "Combat-damage assignment source must be a string"
        )
    source_ref = raw["source"]
    source = source_map.get(source_ref)
    if source is None:
        raise CombatDamageAssignmentError(
            f"{source_ref or 'Object'} is not assigning combat damage"
        )
    if source.power <= 0:
        raise CombatDamageAssignmentError(
            f"{source_ref} does not assign combat damage because its power is 0 or less"
        )
    if not isinstance(raw["target"], str):
        raise CombatDamageAssignmentError(
            "Combat-damage assignment target must be a string"
        )
    target_ref = raw["target"]
    if target_ref not in source.targets:
        raise CombatDamageAssignmentError(
            f"{target_ref or 'Object'} is an illegal combat-damage target for {source_ref}"
        )
    value = raw["amount"]
    if not isinstance(value, int) or isinstance(value, bool):
        raise CombatDamageAssignmentError("Combat damage must be an integer")
    if value < 0:
        raise CombatDamageAssignmentError("Damage cannot be negative")
    return DamageAssignment(source_ref, target_ref, value)


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
                assignment.source in deathtouch_source_refs
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


__all__ = [
    "CombatDamageAssignmentError",
    "CombatDamageAssignmentProposal",
    "CombatDamageSourceSpec",
    "CreatureDamageState",
    "DamageAssignment",
    "TrampleDamageSpec",
    "trample_assignment_error",
]
