from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from typing import Any

from .combat_damage_values import (
    CombatDamageAssignmentError,
    DamageAssignment,
)


def canonical_combat_assignment_values(
    assignments: Sequence[Mapping[str, Any]],
) -> tuple[tuple[int, DamageAssignment], ...]:
    """Validate the closed batch shape while retaining legacy row indices."""

    if (
        not isinstance(assignments, Sequence)
        or isinstance(assignments, (str, bytes, Mapping))
    ):
        raise CombatDamageAssignmentError(
            "Combat damage assignments must be an array"
        )
    values: list[tuple[int, DamageAssignment]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, raw in enumerate(assignments):
        if not isinstance(raw, Mapping) or set(raw) != {
            "source",
            "target",
            "amount",
        }:
            raise CombatDamageAssignmentError(
                "Combat damage assignments are malformed"
            )
        assignment = DamageAssignment(
            source=raw["source"],
            target=raw["target"],
            amount=raw["amount"],
        )
        pair = (assignment.source, assignment.target)
        if pair in seen_pairs:
            raise CombatDamageAssignmentError(
                "Combat damage assignments cannot repeat a "
                "source-recipient pair"
            )
        seen_pairs.add(pair)
        values.append((index, assignment))
    return tuple(values)


def replacement_event_identity_values(
    event_ids: Sequence[str],
) -> tuple[str, ...]:
    if (
        not isinstance(event_ids, Sequence)
        or isinstance(event_ids, (str, bytes, Mapping))
        or any(type(event_id) is not str or not event_id for event_id in event_ids)
    ):
        raise CombatDamageAssignmentError(
            "Combat replacement event identities are malformed"
        )
    values = tuple(event_ids)
    if len(values) != len(set(values)):
        raise CombatDamageAssignmentError(
            "Combat replacement event identities must be unique"
        )
    return values


def combat_damage_event_identity(
    *,
    damage_step_id: str,
    source_logical_object_id: str,
    recipient_logical_object_id: str,
    amount: int,
) -> str:
    """Return an order-independent identity for one canonical damage event."""

    for value, label in (
        (damage_step_id, "damage-step"),
        (source_logical_object_id, "source"),
        (recipient_logical_object_id, "recipient"),
    ):
        if type(value) is not str or not value:
            raise CombatDamageAssignmentError(
                f"Combat damage {label} identity is malformed"
            )
    if type(amount) is not int or amount <= 0:
        raise CombatDamageAssignmentError(
            "Combat damage event amount must be a positive exact integer"
        )
    payload = (
        f"{damage_step_id}\0{source_logical_object_id}\0"
        f"{recipient_logical_object_id}\0{amount}"
    )
    return "damage.combat:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "canonical_combat_assignment_values",
    "combat_damage_event_identity",
    "replacement_event_identity_values",
]
