from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Literal

from .errors import GameRuleError
from .replacement.immutable import (
    FrozenMap,
    ImmutableValueError,
    thaw_value,
)
from .util import stable_json


ZoneEventSourceTiming = Literal["before", "after"]


class ZoneTransitionKind(str, Enum):
    """Closed semantic cause needed by normalized zone-event derivation."""

    ORDINARY = "ordinary"
    COUNTERED_SPELL = "countered_spell"


class ZoneTriggerEventError(ValueError):
    """A normalized zone-change trigger occurrence is malformed."""


_EXILE_ZONE = "ex" + "ile"
_ZONE_CHANGE_DESTINATIONS = frozenset(
    {"library", "hand", "battlefield", "graveyard", _EXILE_ZONE, "command", "outside"}
)


def validate_zone_transition_request(
    cards: Mapping[str, Any],
    object_id: str,
    destination: Any,
    transition_kind: Any,
) -> Any:
    """Fail before mutation when a committed move has an invalid event cause."""

    if destination not in _ZONE_CHANGE_DESTINATIONS:
        raise GameRuleError(f"Unsupported destination {destination}")
    if not isinstance(transition_kind, ZoneTransitionKind):
        raise GameRuleError("Zone transitions require a supported typed event kind")
    card = cards[object_id]
    if transition_kind is ZoneTransitionKind.COUNTERED_SPELL and card.zone != "stack":
        raise GameRuleError(
            "Only a physical spell on the stack can use the countered-spell transition"
        )
    return card


def _string(value: Any, *, field: str) -> str:
    if type(value) is not str or not value:
        raise ZoneTriggerEventError(f"{field} must be a nonempty string")
    return value


def _optional_string(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _string(value, field=field)


def _string_tuple(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ZoneTriggerEventError(f"{field} must be an array")
    result = tuple(
        _string(item, field=f"{field}[{index}]")
        for index, item in enumerate(value)
    )
    if len(set(result)) != len(result):
        raise ZoneTriggerEventError(f"{field} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class ZoneChangeOccurrence:
    """Immutable CR 603.6 facts captured around one committed zone change."""

    object_id: str
    card_ref: str
    owner: str
    origin: str
    destination: str
    previous_controller: str
    current_controller: str
    previous_logical_object_id: str
    current_logical_object_id: str
    zone_change_counter: int
    token: bool
    card_object: bool
    previous_characteristics: FrozenMap
    current_characteristics: FrozenMap
    previous_attachments: tuple[str, ...] = ()
    previous_attached_to: str | None = None
    tapped: bool = False
    cause: str = ""
    transition_kind: ZoneTransitionKind = ZoneTransitionKind.ORDINARY
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in (
            "object_id",
            "card_ref",
            "owner",
            "origin",
            "destination",
            "previous_controller",
            "current_controller",
            "previous_logical_object_id",
            "current_logical_object_id",
        ):
            _string(getattr(self, field), field=f"zone_occurrence.{field}")
        if type(self.zone_change_counter) is not int or self.zone_change_counter < 0:
            raise ZoneTriggerEventError(
                "zone_occurrence.zone_change_counter must be a nonnegative integer"
            )
        for field in ("token", "card_object", "tapped"):
            if type(getattr(self, field)) is not bool:
                raise ZoneTriggerEventError(
                    f"zone_occurrence.{field} must be a boolean"
                )
        if type(self.cause) is not str:
            raise ZoneTriggerEventError("zone_occurrence.cause must be a string")
        if not isinstance(self.transition_kind, ZoneTransitionKind):
            raise ZoneTriggerEventError(
                "zone_occurrence.transition_kind must be a supported typed value"
            )
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ZoneTriggerEventError(
                "Unsupported zone-trigger occurrence schema version"
            )
        for field in ("previous_characteristics", "current_characteristics"):
            value = getattr(self, field)
            if not isinstance(value, Mapping):
                raise ZoneTriggerEventError(
                    f"zone_occurrence.{field} must be an object"
                )
            if not isinstance(value, FrozenMap):
                try:
                    value = FrozenMap(value)
                except ImmutableValueError as exc:
                    raise ZoneTriggerEventError(
                        f"zone_occurrence.{field} is not canonical"
                    ) from exc
                object.__setattr__(self, field, value)
        if not isinstance(self.previous_attachments, tuple):
            object.__setattr__(
                self,
                "previous_attachments",
                _string_tuple(
                    self.previous_attachments,
                    field="zone_occurrence.previous_attachments",
                ),
            )
        else:
            _string_tuple(
                self.previous_attachments,
                field="zone_occurrence.previous_attachments",
            )
        _optional_string(
            self.previous_attached_to,
            field="zone_occurrence.previous_attached_to",
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "object_id": self.object_id,
            "card_ref": self.card_ref,
            "owner": self.owner,
            "origin": self.origin,
            "destination": self.destination,
            "previous_controller": self.previous_controller,
            "current_controller": self.current_controller,
            "previous_logical_object_id": self.previous_logical_object_id,
            "current_logical_object_id": self.current_logical_object_id,
            "zone_change_counter": self.zone_change_counter,
            "token": self.token,
            "card_object": self.card_object,
            "previous_characteristics": thaw_value(
                self.previous_characteristics
            ),
            "current_characteristics": thaw_value(
                self.current_characteristics
            ),
            "previous_attachments": list(self.previous_attachments),
            "previous_attached_to": self.previous_attached_to,
            "tapped": self.tapped,
            "cause": self.cause,
        }
        # Preserve ordinary occurrence fingerprints while making the corrected
        # counter path explicit and replay-stable.
        if self.transition_kind is not ZoneTransitionKind.ORDINARY:
            result["transition_kind"] = self.transition_kind.value
        return result

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            stable_json(self.to_dict()).encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizedZoneTriggerEvent:
    """One closed event kind derived from a committed zone occurrence."""

    kind: str
    source_timing: ZoneEventSourceTiming
    context: FrozenMap

    def __post_init__(self) -> None:
        _string(self.kind, field="zone_trigger_event.kind")
        if self.source_timing not in {"before", "after"}:
            raise ZoneTriggerEventError(
                "zone_trigger_event.source_timing must be before or after"
            )
        if not isinstance(self.context, FrozenMap):
            object.__setattr__(self, "context", FrozenMap(self.context))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_timing": self.source_timing,
            "context": thaw_value(self.context),
        }


def _type_parts(characteristics: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    type_line = str(characteristics.get("type_line") or "").replace("—", "-")
    left, _, right = type_line.partition("-")
    words = {value.casefold() for value in re.findall(r"[A-Za-z]+", left)}
    types = words.intersection(
        {
            "artifact",
            "battle",
            "creature",
            "enchantment",
            "instant",
            "kindred",
            "land",
            "planeswalker",
            "sorcery",
        }
    )
    subtypes = {
        value.casefold()
        for value in re.findall(r"[A-Za-z]+", right)
    }
    return types, subtypes


def normalized_zone_trigger_events(
    occurrence: ZoneChangeOccurrence,
) -> tuple[NormalizedZoneTriggerEvent, ...]:
    """Derive the represented CR 603.6 event vocabulary without state access."""

    previous_types, _previous_subtypes = _type_parts(
        occurrence.previous_characteristics
    )
    common = {
        "card": occurrence.card_ref,
        "card_object_identity": occurrence.previous_logical_object_id,
        "card_zone_change_counter": occurrence.zone_change_counter,
        "owner": occurrence.owner,
        "controller": occurrence.current_controller,
        "previous_controller": occurrence.previous_controller,
        "from": occurrence.origin,
        "to": occurrence.destination,
        "cause": occurrence.cause,
        "token": occurrence.token,
        "attachments": list(occurrence.previous_attachments),
        "attached_to": occurrence.previous_attached_to,
        "types": sorted(previous_types),
    }
    result: list[NormalizedZoneTriggerEvent] = []
    if occurrence.transition_kind is ZoneTransitionKind.COUNTERED_SPELL:
        result.append(
            NormalizedZoneTriggerEvent(
                "spell.countered", "before", FrozenMap(common)
            )
        )
        if occurrence.card_object and occurrence.destination == "graveyard":
            result.append(
                NormalizedZoneTriggerEvent(
                    "card.graveyard", "after", FrozenMap(common)
                )
            )
    if occurrence.origin == "battlefield" and occurrence.destination != "battlefield":
        departure = {
            **common,
            "controller": occurrence.previous_controller,
            "types": sorted(previous_types),
        }
        result.append(
            NormalizedZoneTriggerEvent(
                "permanent.leave", "before", FrozenMap(departure)
            )
        )
        if occurrence.destination == "graveyard":
            if "creature" in previous_types:
                result.append(
                    NormalizedZoneTriggerEvent(
                        "creature.dies", "before", FrozenMap(departure)
                    )
                )
            if "artifact" in previous_types:
                result.append(
                    NormalizedZoneTriggerEvent(
                        "artifact.graveyard", "before", FrozenMap(departure)
                    )
                )
            result.append(
                NormalizedZoneTriggerEvent(
                    "permanent.graveyard", "before", FrozenMap(departure)
                )
            )
    if occurrence.origin == "graveyard" and occurrence.destination != "graveyard":
        result.append(
            NormalizedZoneTriggerEvent(
                "card.leave_graveyard", "after", FrozenMap(common)
            )
        )
    if occurrence.origin == "hand" and occurrence.destination == "graveyard":
        result.append(
            NormalizedZoneTriggerEvent(
                "card.discarded", "after", FrozenMap(common)
            )
        )
    if occurrence.destination == "battlefield" and occurrence.origin != "battlefield":
        current_types, current_subtypes = _type_parts(
            occurrence.current_characteristics
        )
        entered = {
            **common,
            "controller": occurrence.current_controller,
            "types": sorted(current_types),
            "subtypes": sorted(current_subtypes),
            "mana_value": float(
                occurrence.current_characteristics.get("mana_value", 0) or 0
            ),
            "tapped": occurrence.tapped,
        }
        result.append(
            NormalizedZoneTriggerEvent(
                "permanent.enter", "after", FrozenMap(entered)
            )
        )
        for card_type in ("artifact", "creature", "land", "enchantment"):
            if card_type in current_types:
                result.append(
                    NormalizedZoneTriggerEvent(
                        f"{card_type}.enter", "after", FrozenMap(entered)
                    )
                )
    return tuple(result)


__all__ = [
    "NormalizedZoneTriggerEvent",
    "ZoneChangeOccurrence",
    "ZoneTransitionKind",
    "ZoneTriggerEventError",
    "normalized_zone_trigger_events",
    "validate_zone_transition_request",
]
