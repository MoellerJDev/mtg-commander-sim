from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Protocol, Sequence

from .counter_state import (
    CounterChange,
    CounterStateError,
    commit_counter_changes,
    plan_counter_changes,
)
from .replacement import (
    CreateAffectedObjectCounter,
    ReplacementClass,
    ReplacementEffect,
)


class EntryCounterError(ValueError):
    """An intrinsic as-enters counter instruction is not representable."""


class EntryCounterCommitHost(Protocol):
    state: Any


@dataclass(frozen=True, slots=True)
class IntrinsicEntryCounter:
    counter_name: str
    amount: int
    required_type: str
    rule_id: str

    def __post_init__(self) -> None:
        counter_name = " ".join(self.counter_name.casefold().split())
        required_type = " ".join(self.required_type.casefold().split())
        rule_id = str(self.rule_id or "")
        if not counter_name or not required_type or not rule_id:
            raise EntryCounterError(
                "Intrinsic entry counters require a counter, type, and rule"
            )
        if type(self.amount) is not int or self.amount < 0:
            raise EntryCounterError(
                "Intrinsic entry counter amounts must be nonnegative integers"
            )
        object.__setattr__(self, "counter_name", counter_name)
        object.__setattr__(self, "required_type", required_type)
        object.__setattr__(self, "rule_id", rule_id)


def _printed_nonnegative_integer(
    value: Any,
    *,
    characteristic: str,
) -> int:
    if type(value) is int:
        amount = value
    elif type(value) is str and re.fullmatch(r"-?\d+", value.strip()):
        amount = int(value.strip())
    else:
        raise EntryCounterError(
            f"{characteristic} must be a represented nonnegative integer"
        )
    if amount < 0:
        raise EntryCounterError(
            f"{characteristic} cannot be negative"
        )
    return amount


def intrinsic_entry_counters(
    characteristics: Mapping[str, Any],
    *,
    card_types: Sequence[str],
) -> tuple[IntrinsicEntryCounter, ...]:
    """Return the closed CR 306.5b/310.4b entry-counter instructions."""

    if not isinstance(characteristics, Mapping):
        raise EntryCounterError(
            "Entry counter characteristics must be a mapping"
        )
    types = {" ".join(str(value).casefold().split()) for value in card_types}
    counters: list[IntrinsicEntryCounter] = []
    if "planeswalker" in types:
        counters.append(
            IntrinsicEntryCounter(
                counter_name="loyalty",
                amount=_printed_nonnegative_integer(
                    characteristics.get("loyalty"),
                    characteristic="Starting loyalty",
                ),
                required_type="planeswalker",
                rule_id="306.5b",
            )
        )
    if "battle" in types:
        counters.append(
            IntrinsicEntryCounter(
                counter_name="defense",
                amount=_printed_nonnegative_integer(
                    characteristics.get("defense"),
                    characteristic="Battle defense",
                ),
                required_type="battle",
                rule_id="310.4b",
            )
        )
    return tuple(counters)


def intrinsic_entry_counter_effects(
    *,
    object_ref: str,
    destination_controller: str,
    counters: Sequence[IntrinsicEntryCounter],
) -> tuple[ReplacementEffect, ...]:
    """Lower intrinsic instructions to mandatory self-replacement effects."""

    if not object_ref or not destination_controller:
        raise EntryCounterError(
            "Entry counter effects require object and controller identity"
        )
    effects: list[ReplacementEffect] = []
    for sequence, counter in enumerate(counters):
        if not isinstance(counter, IntrinsicEntryCounter):
            raise EntryCounterError(
                "Entry counter effects require typed counter instructions"
            )
        if counter.amount == 0:
            continue
        source_ref = f"rule:{counter.rule_id}:{object_ref}"
        effects.append(
            ReplacementEffect(
                effect_id=(
                    "replacement.intrinsic-entry-counter:"
                    f"{object_ref}:{counter.counter_name}:{counter.rule_id}"
                ),
                source_id=source_ref,
                event_kind="zone.change",
                replacement_class=ReplacementClass.SELF_REPLACEMENT,
                conditions={
                    "destination": {"eq": "battlefield"},
                    "object_ref": {"eq": object_ref},
                    "object_types": {
                        "contains": counter.required_type,
                    },
                },
                operations=(
                    CreateAffectedObjectCounter(
                        counter_name=counter.counter_name,
                        amount=counter.amount,
                        placing_player=destination_controller,
                        source_ref=source_ref,
                        sequence=sequence,
                    ),
                ),
                label=(
                    f"{object_ref}: enter with {counter.amount} "
                    f"{counter.counter_name} counter(s)"
                ),
            )
        )
    return tuple(effects)


def validate_battle_entry_protector(
    *,
    card_types: Sequence[str],
    subtypes: Sequence[str],
    controller: str,
    supplied_protector: str | None,
    active_seats: Sequence[str],
) -> str | None:
    """Validate the represented ordinary Battle protector assignment."""

    types = {str(value).casefold() for value in card_types}
    if "battle" not in types:
        return None
    normalized_subtypes = {str(value).casefold() for value in subtypes}
    if "siege" in normalized_subtypes:
        if (
            supplied_protector not in active_seats
            or supplied_protector == controller
        ):
            raise EntryCounterError(
                "A Siege must enter protected by one of its controller's opponents"
            )
        return supplied_protector
    if normalized_subtypes:
        raise EntryCounterError(
            "The protector predicate for Battle type(s) "
            f"{sorted(normalized_subtypes)} is not compiled"
        )
    return controller


def commit_unreplaced_intrinsic_entry_counters(
    host: EntryCounterCommitHost,
    *,
    object_id: str,
    logical_object_id: str,
    counters: Sequence[IntrinsicEntryCounter],
) -> None:
    """Commit a preflight-proven replacement-free token compatibility path."""

    changes = tuple(
        CounterChange(
            subject_kind="permanent",
            subject_id=object_id,
            counter_name=counter.counter_name,
            amount=counter.amount,
            expected_zone="battlefield",
            expected_logical_object_id=logical_object_id,
        )
        for counter in counters
        if counter.amount
    )
    if not changes:
        return
    try:
        commit_counter_changes(host, plan_counter_changes(host, changes))
    except CounterStateError as exc:
        raise EntryCounterError(str(exc)) from exc


__all__ = [
    "EntryCounterError",
    "IntrinsicEntryCounter",
    "commit_unreplaced_intrinsic_entry_counters",
    "intrinsic_entry_counter_effects",
    "intrinsic_entry_counters",
    "validate_battle_entry_protector",
]
