from __future__ import annotations

import copy
from typing import Any, Mapping, Protocol, Sequence

from .characteristic_evaluation import type_parts
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
from .entry_counter_model import (
    EntryCounterError,
    IntrinsicEntryCounter,
    intrinsic_entry_counters,
)


class EntryCounterCommitHost(Protocol):
    state: Any


class EntryCharacteristicsQuery(Protocol):
    def _effective_card_data(
        self,
        card: Any,
        *,
        printed_entry_characteristics: bool = False,
    ) -> Mapping[str, Any]: ...


def capture_prospective_entry_characteristics(
    host: EntryCharacteristicsQuery,
    *,
    card: Any,
    enter_face: str | None,
) -> tuple[Mapping[str, Any], str]:
    """Snapshot printed entry characteristics before replacement ordering."""

    prospective_card = copy.deepcopy(card)
    if enter_face is not None:
        prospective_card.active_face = enter_face
    characteristics = host._effective_card_data(
        prospective_card,
        printed_entry_characteristics=True,
    )
    return characteristics, str(characteristics.get("type_line") or "")


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


def prospective_battle_entry_protector(
    *,
    destination: str,
    entry_characteristics: Mapping[str, Any],
    controller: str,
    supplied_protector: str | None,
    active_seats: Sequence[str],
    error_type: type[Exception],
) -> str | None:
    """Validate the Battle protector against prospective entry data."""

    if destination != "battlefield":
        return None
    card_types, subtypes, _ = type_parts(
        str(entry_characteristics.get("type_line") or "")
    )
    try:
        return validate_battle_entry_protector(
            card_types=tuple(sorted(card_types)),
            subtypes=tuple(sorted(subtypes)),
            controller=controller,
            supplied_protector=supplied_protector,
            active_seats=active_seats,
        )
    except EntryCounterError as exc:
        raise error_type(str(exc)) from exc


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
    "capture_prospective_entry_characteristics",
    "EntryCounterError",
    "EntryCharacteristicsQuery",
    "IntrinsicEntryCounter",
    "commit_unreplaced_intrinsic_entry_counters",
    "intrinsic_entry_counter_effects",
    "intrinsic_entry_counters",
    "prospective_battle_entry_protector",
    "validate_battle_entry_protector",
]
