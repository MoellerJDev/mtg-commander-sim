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
class CombatDamageParticipant:
    object_id: str
    reference: str
    controller: str
    power: int
    toughness: int
    marked_damage: int
    keywords: frozenset[str]
    assigns_damage: bool

    def __post_init__(self) -> None:
        if not self.object_id or not self.reference or not self.controller:
            raise CombatDamageAssignmentError(
                "Combat-damage participants require stable identities"
            )
        object.__setattr__(
            self,
            "keywords",
            frozenset(str(value).casefold() for value in self.keywords),
        )


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


def build_combat_damage_assignment_proposal(
    *,
    seat: str,
    attackers: Mapping[str, str],
    blockers: Mapping[str, Sequence[str]],
    participants: Sequence[CombatDamageParticipant],
    valid_spill_targets: Mapping[str, str],
) -> CombatDamageAssignmentProposal:
    """Lower a current immutable combat snapshot into one CR 510 proposal."""

    participants_by_id = {item.object_id: item for item in participants}
    if len(participants_by_id) != len(participants):
        raise CombatDamageAssignmentError(
            "Combat-damage participant object identities must be unique"
        )
    references = {item.reference for item in participants}
    if len(references) != len(participants):
        raise CombatDamageAssignmentError(
            "Combat-damage participant references must be unique"
        )

    source_targets, source_power, attacking = _attacking_sources(
        seat=seat,
        attackers=attackers,
        blockers=blockers,
        participants=participants_by_id,
        valid_spill_targets=valid_spill_targets,
    )
    blocker_targets, blocker_power = _blocking_sources(
        seat=seat,
        blockers=blockers,
        participants=participants_by_id,
    )
    source_targets.update(blocker_targets)
    source_power.update(blocker_power)
    attacking_refs = frozenset(item.reference for item in attacking)
    return CombatDamageAssignmentProposal(
        sources=tuple(
            CombatDamageSourceSpec(
                source=source,
                power=source_power[source],
                targets=tuple(sorted(targets)),
            )
            for source, targets in sorted(source_targets.items())
        ),
        attacking_sources=attacking_refs,
        deathtouch_sources=frozenset(
            item.reference
            for item in attacking
            if "deathtouch" in item.keywords
        ),
        trample_sources=_trample_sources(
            attackers=attackers,
            blockers=blockers,
            participants=participants_by_id,
            source_targets=source_targets,
            attacking=attacking,
        ),
    )


def _attacking_sources(
    *,
    seat: str,
    attackers: Mapping[str, str],
    blockers: Mapping[str, Sequence[str]],
    participants: Mapping[str, CombatDamageParticipant],
    valid_spill_targets: Mapping[str, str],
) -> tuple[
    dict[str, set[str]],
    dict[str, int],
    tuple[CombatDamageParticipant, ...],
]:
    targets_by_source: dict[str, set[str]] = {}
    power_by_source: dict[str, int] = {}
    attacking: list[CombatDamageParticipant] = []
    for attacker_id in attackers:
        attacker = participants.get(attacker_id)
        if (
            attacker is None
            or attacker.controller != seat
            or not attacker.assigns_damage
        ):
            continue
        if attacker_id in blockers:
            targets = {
                blocker.reference
                for blocker_id in blockers.get(attacker_id, ())
                if (blocker := participants.get(blocker_id)) is not None
            }
            if "trample" in attacker.keywords:
                if spill_target := valid_spill_targets.get(attacker_id):
                    targets.add(spill_target)
        else:
            spill_target = valid_spill_targets.get(attacker_id)
            targets = {spill_target} if spill_target is not None else set()
        targets_by_source[attacker.reference] = targets
        power_by_source[attacker.reference] = max(0, attacker.power)
        attacking.append(attacker)
    return targets_by_source, power_by_source, tuple(attacking)


def _blocking_sources(
    *,
    seat: str,
    blockers: Mapping[str, Sequence[str]],
    participants: Mapping[str, CombatDamageParticipant],
) -> tuple[dict[str, set[str]], dict[str, int]]:
    targets_by_source: dict[str, set[str]] = {}
    power_by_source: dict[str, int] = {}
    for attacker_id, blocker_ids in blockers.items():
        attacker = participants.get(attacker_id)
        if attacker is None:
            continue
        for blocker_id in blocker_ids:
            blocker = participants.get(blocker_id)
            if (
                blocker is None
                or blocker.controller != seat
                or not blocker.assigns_damage
            ):
                continue
            targets_by_source.setdefault(blocker.reference, set()).add(
                attacker.reference
            )
            power_by_source[blocker.reference] = max(0, blocker.power)
    return targets_by_source, power_by_source


def _trample_sources(
    *,
    attackers: Mapping[str, str],
    blockers: Mapping[str, Sequence[str]],
    participants: Mapping[str, CombatDamageParticipant],
    source_targets: Mapping[str, set[str]],
    attacking: Sequence[CombatDamageParticipant],
) -> tuple[TrampleDamageSpec, ...]:
    trample_sources: list[TrampleDamageSpec] = []
    for attacker in attacking:
        if (
            "trample" not in attacker.keywords
            or attacker.object_id not in blockers
        ):
            continue
        current_targets = source_targets.get(attacker.reference, set())
        blocker_states = tuple(
            (
                blocker.reference,
                CreatureDamageState(
                    toughness=blocker.toughness,
                    marked_damage=blocker.marked_damage,
                ),
            )
            for blocker_id in blockers.get(attacker.object_id, ())
            if (blocker := participants.get(blocker_id)) is not None
            and blocker.reference in current_targets
        )
        trample_sources.append(
            TrampleDamageSpec(
                attacker=attacker.reference,
                spill_target=str(attackers[attacker.object_id]),
                blockers=blocker_states,
            )
        )
    return tuple(trample_sources)


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
    "build_combat_damage_assignment_proposal",
    "CombatDamageAssignmentError",
    "CombatDamageParticipant",
    "CombatDamageAssignmentProposal",
    "CombatDamageSourceSpec",
    "CreatureDamageState",
    "DamageAssignment",
    "TrampleDamageSpec",
    "trample_assignment_error",
]
