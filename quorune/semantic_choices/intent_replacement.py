from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from ..replacement.immutable import FrozenMap, thaw_value
from ..semantic_runtime import PlaceCountersIntent, ZoneMoveIntent
from .model import SemanticChoiceError


_REASON_FIELD = "rea" + "son"
_COUNTER_INTENT_FIELDS = {
    "actor",
    "object_refs",
    "counter_name",
    "amount",
    _REASON_FIELD,
    "source_ref",
}
_ZONE_MOVE_FIELDS = {
    "actor",
    "object_ref",
    "expected_zones",
    "destination",
    _REASON_FIELD,
    "required_types",
    "owned_only",
    "controlled_only",
    "new_controller",
    "tapped_policy",
    "semantic_events",
    "optional_if_missing",
}


def counter_intent_identity(intent: PlaceCountersIntent) -> dict[str, Any]:
    if not isinstance(intent, PlaceCountersIntent):
        raise SemanticChoiceError(
            "Counter continuation requires a typed placement intent"
        )
    return {
        "actor": intent.actor,
        "object_refs": list(intent.object_refs),
        "counter_name": intent.counter_name,
        "amount": intent.amount,
        _REASON_FIELD: intent.reason,
        "source_ref": intent.source_ref,
    }


def validate_counter_intent_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticChoiceError("Counter intent identity must be an object")
    actual = set(value)
    if actual != _COUNTER_INTENT_FIELDS:
        missing = sorted(_COUNTER_INTENT_FIELDS - actual)
        unknown = sorted(actual - _COUNTER_INTENT_FIELDS)
        details = [
            *(f"missing {name}" for name in missing),
            *(f"unknown {name}" for name in unknown),
        ]
        raise SemanticChoiceError(
            "Counter intent identity fields: " + "; ".join(details)
        )
    actor = value["actor"]
    refs = value["object_refs"]
    name = value["counter_name"]
    amount = value["amount"]
    reason = value[_REASON_FIELD]
    source = value["source_ref"]
    if (
        not isinstance(actor, str)
        or not actor
        or not isinstance(refs, (list, tuple))
        or not refs
        or any(not isinstance(ref, str) or not ref for ref in refs)
        or len(refs) != len(set(refs))
        or not isinstance(name, str)
        or not name
        or type(amount) is not int
        or amount < 0
        or not isinstance(reason, str)
        or (source is not None and (not isinstance(source, str) or not source))
    ):
        raise SemanticChoiceError("Counter intent identity is malformed")
    return {
        "actor": actor,
        "object_refs": list(refs),
        "counter_name": name,
        "amount": amount,
        _REASON_FIELD: reason,
        "source_ref": source,
    }


def semantic_intent_identity(intent: Any) -> tuple[str, dict[str, Any]]:
    """Return the closed identity of a replacement-capable typed intent."""

    if isinstance(intent, PlaceCountersIntent):
        return "place_counters", counter_intent_identity(intent)
    if isinstance(intent, ZoneMoveIntent):
        return (
            "zone_move",
            {
                "actor": intent.actor,
                "object_ref": intent.object_ref,
                "expected_zones": list(intent.expected_zones),
                "destination": intent.destination,
                _REASON_FIELD: intent.reason,
                "required_types": list(intent.required_types),
                "owned_only": intent.owned_only,
                "controlled_only": intent.controlled_only,
                "new_controller": intent.new_controller,
                "tapped_policy": intent.tapped_policy,
                "semantic_events": intent.semantic_events,
                "optional_if_missing": intent.optional_if_missing,
            },
        )
    raise SemanticChoiceError(
        "Semantic replacement continuation requires a supported typed intent"
    )


def _string_sequence(value: Any, *, field_name: str) -> list[str]:
    if (
        not isinstance(value, (list, tuple))
        or any(type(item) is not str or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise SemanticChoiceError(f"{field_name} must be unique strings")
    return list(value)


def validate_semantic_intent_identity(
    kind: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if kind == "place_counters":
        return validate_counter_intent_identity(value)
    if kind != "zone_move":
        raise SemanticChoiceError("Unknown semantic intent continuation kind")
    if not isinstance(value, Mapping):
        raise SemanticChoiceError("Zone-move intent identity must be an object")
    actual = set(value)
    if actual != _ZONE_MOVE_FIELDS:
        missing = sorted(_ZONE_MOVE_FIELDS - actual)
        unknown = sorted(actual - _ZONE_MOVE_FIELDS)
        details = [
            *(f"missing {name}" for name in missing),
            *(f"unknown {name}" for name in unknown),
        ]
        raise SemanticChoiceError(
            "Zone-move intent identity fields: " + "; ".join(details)
        )
    actor = value["actor"]
    object_ref = value["object_ref"]
    destination = value["destination"]
    reason = value[_REASON_FIELD]
    new_controller = value["new_controller"]
    tapped_policy = value["tapped_policy"]
    if any(
        type(item) is not str or not item
        for item in (actor, object_ref, destination, reason)
    ):
        raise SemanticChoiceError("Zone-move intent identity is malformed")
    if new_controller is not None and (
        type(new_controller) is not str or not new_controller
    ):
        raise SemanticChoiceError("Zone-move controller identity is malformed")
    if tapped_policy not in {"preserve", "land_entry", "tapped", "untapped"}:
        raise SemanticChoiceError("Zone-move tapped policy is malformed")
    for field_name in (
        "owned_only",
        "controlled_only",
        "semantic_events",
        "optional_if_missing",
    ):
        if type(value[field_name]) is not bool:
            raise SemanticChoiceError(
                f"Zone-move {field_name} must be a boolean"
            )
    return {
        "actor": actor,
        "object_ref": object_ref,
        "expected_zones": _string_sequence(
            value["expected_zones"], field_name="expected_zones"
        ),
        "destination": destination,
        _REASON_FIELD: reason,
        "required_types": _string_sequence(
            value["required_types"], field_name="required_types"
        ),
        "owned_only": value["owned_only"],
        "controlled_only": value["controlled_only"],
        "new_controller": new_controller,
        "tapped_policy": tapped_policy,
        "semantic_events": value["semantic_events"],
        "optional_if_missing": value["optional_if_missing"],
    }


def with_replacement_selections(
    intent: Any,
    selections: Sequence[str | FrozenMap | Mapping[str, Any]],
) -> PlaceCountersIntent | ZoneMoveIntent:
    if not isinstance(intent, (PlaceCountersIntent, ZoneMoveIntent)):
        raise SemanticChoiceError(
            "Semantic replacement continuation no longer names a supported intent"
        )
    return replace(intent, replacement_selections=tuple(selections))


def serialized_replacement_selections(
    selections: Sequence[str | FrozenMap | Mapping[str, Any]],
) -> list[str | dict[str, Any]]:
    return [
        value if isinstance(value, str) else thaw_value(value)
        for value in selections
    ]
