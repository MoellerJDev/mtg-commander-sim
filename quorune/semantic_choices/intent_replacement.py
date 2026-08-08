from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from ..affected_permanents import (
    AffectedPermanentSetError,
    AffectedPermanentSetSpec,
)
from ..replacement.immutable import FrozenMap, thaw_value
from ..semantic_runtime import (
    PlaceCountersIntent,
    PlaceCountersOnSetIntent,
    PlacePlayerCountersIntent,
    ProliferateIntent,
    ProliferateSubject,
    ZoneMoveIntent,
)
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
_COUNTER_SET_INTENT_FIELDS = {
    "actor",
    "spec",
    "counter_name",
    "amount",
    _REASON_FIELD,
    "source_ref",
}
_PLAYER_COUNTER_INTENT_FIELDS = {
    "actor",
    "player_ids",
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
_PROLIFERATE_FIELDS = {
    "actor",
    "subjects",
    _REASON_FIELD,
    "source_ref",
}
_PROLIFERATE_SUBJECT_FIELDS = {
    "subject_kind",
    "subject_id",
    "ref",
    "counter_names",
    "logical_object_id",
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
    if isinstance(intent, PlaceCountersOnSetIntent):
        return (
            "place_counters_on_set",
            {
                "actor": intent.actor,
                "spec": intent.spec.to_dict(),
                "counter_name": intent.counter_name,
                "amount": intent.amount,
                _REASON_FIELD: intent.reason,
                "source_ref": intent.source_ref,
            },
        )
    if isinstance(intent, PlacePlayerCountersIntent):
        return (
            "place_player_counters",
            {
                "actor": intent.actor,
                "player_ids": list(intent.player_ids),
                "counter_name": intent.counter_name,
                "amount": intent.amount,
                _REASON_FIELD: intent.reason,
                "source_ref": intent.source_ref,
            },
        )
    if isinstance(intent, ProliferateIntent):
        return (
            "proliferate",
            {
                "actor": intent.actor,
                "subjects": [
                    {
                        "subject_kind": subject.subject_kind,
                        "subject_id": subject.subject_id,
                        "ref": subject.ref,
                        "counter_names": list(subject.counter_names),
                        "logical_object_id": subject.logical_object_id,
                    }
                    for subject in intent.subjects
                ],
                _REASON_FIELD: intent.reason,
                "source_ref": intent.source_ref,
            },
        )
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


def _validate_player_counter_intent_identity(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticChoiceError(
            "Player counter intent identity must be an object"
        )
    actual = set(value)
    if actual != _PLAYER_COUNTER_INTENT_FIELDS:
        missing = sorted(_PLAYER_COUNTER_INTENT_FIELDS - actual)
        unknown = sorted(actual - _PLAYER_COUNTER_INTENT_FIELDS)
        details = [
            *(f"missing {name}" for name in missing),
            *(f"unknown {name}" for name in unknown),
        ]
        raise SemanticChoiceError(
            "Player counter intent identity fields: " + "; ".join(details)
        )
    actor = value["actor"]
    players = value["player_ids"]
    counter_name = value["counter_name"]
    amount = value["amount"]
    reason = value[_REASON_FIELD]
    source = value["source_ref"]
    if (
        type(actor) is not str
        or not actor
        or not isinstance(players, (list, tuple))
        or not players
        or any(type(player) is not str or not player for player in players)
        or len(players) != len(set(players))
        or type(counter_name) is not str
        or not counter_name
        or type(amount) is not int
        or amount <= 0
        or type(reason) is not str
        or not reason
        or (source is not None and (type(source) is not str or not source))
    ):
        raise SemanticChoiceError(
            "Player counter intent identity is malformed"
        )
    return {
        "actor": actor,
        "player_ids": list(players),
        "counter_name": counter_name,
        "amount": amount,
        _REASON_FIELD: reason,
        "source_ref": source,
    }


def _validate_counter_set_intent_identity(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticChoiceError(
            "Counter-set intent identity must be an object"
        )
    actual = set(value)
    if actual != _COUNTER_SET_INTENT_FIELDS:
        missing = sorted(_COUNTER_SET_INTENT_FIELDS - actual)
        unknown = sorted(actual - _COUNTER_SET_INTENT_FIELDS)
        details = [
            *(f"missing {name}" for name in missing),
            *(f"unknown {name}" for name in unknown),
        ]
        raise SemanticChoiceError(
            "Counter-set intent identity fields: " + "; ".join(details)
        )
    try:
        spec = AffectedPermanentSetSpec.from_dict(value["spec"])
    except (AffectedPermanentSetError, TypeError) as exc:
        raise SemanticChoiceError(
            "Counter-set intent specification is malformed"
        ) from exc
    actor = value["actor"]
    counter_name = value["counter_name"]
    amount = value["amount"]
    reason = value[_REASON_FIELD]
    source = value["source_ref"]
    if (
        type(actor) is not str
        or not actor
        or type(counter_name) is not str
        or not counter_name
        or type(amount) is not int
        or amount <= 0
        or type(reason) is not str
        or not reason
        or (source is not None and (type(source) is not str or not source))
        or (spec.exclude_source and source is None)
    ):
        raise SemanticChoiceError("Counter-set intent identity is malformed")
    return {
        "actor": actor,
        "spec": spec.to_dict(),
        "counter_name": counter_name,
        "amount": amount,
        _REASON_FIELD: reason,
        "source_ref": source,
    }


def validate_semantic_intent_identity(
    kind: str,
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if kind == "place_counters":
        return validate_counter_intent_identity(value)
    if kind == "place_counters_on_set":
        return _validate_counter_set_intent_identity(value)
    if kind == "place_player_counters":
        return _validate_player_counter_intent_identity(value)
    if kind == "proliferate":
        return _validate_proliferate_intent_identity(value)
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


def _validate_proliferate_intent_identity(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SemanticChoiceError(
            "Proliferate intent identity must be an object"
        )
    actual = set(value)
    if actual != _PROLIFERATE_FIELDS:
        missing = sorted(_PROLIFERATE_FIELDS - actual)
        unknown = sorted(actual - _PROLIFERATE_FIELDS)
        details = [
            *(f"missing {name}" for name in missing),
            *(f"unknown {name}" for name in unknown),
        ]
        raise SemanticChoiceError(
            "Proliferate intent identity fields: " + "; ".join(details)
        )
    actor = value["actor"]
    reason = value[_REASON_FIELD]
    source = value["source_ref"]
    raw_subjects = value["subjects"]
    if (
        type(actor) is not str
        or not actor
        or type(reason) is not str
        or not reason
        or (source is not None and (type(source) is not str or not source))
        or not isinstance(raw_subjects, (list, tuple))
    ):
        raise SemanticChoiceError("Proliferate intent identity is malformed")
    subjects: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for raw in raw_subjects:
        if not isinstance(raw, Mapping) or set(raw) != _PROLIFERATE_SUBJECT_FIELDS:
            raise SemanticChoiceError(
                "Proliferate subject identity fields are malformed"
            )
        raw_names = raw["counter_names"]
        if not isinstance(raw_names, (list, tuple)):
            raise SemanticChoiceError(
                "Proliferate counter identity must be a sequence"
            )
        try:
            subject = ProliferateSubject(
                subject_kind=raw["subject_kind"],
                subject_id=raw["subject_id"],
                ref=raw["ref"],
                counter_names=tuple(raw_names),
                logical_object_id=raw["logical_object_id"],
            )
        except (TypeError, ValueError) as exc:
            raise SemanticChoiceError(
                "Proliferate subject identity is malformed"
            ) from exc
        identity = (subject.subject_kind, subject.subject_id)
        if identity in identities:
            raise SemanticChoiceError(
                "Proliferate subject identities must be unique"
            )
        identities.add(identity)
        subjects.append(
            {
                "subject_kind": subject.subject_kind,
                "subject_id": subject.subject_id,
                "ref": subject.ref,
                "counter_names": list(subject.counter_names),
                "logical_object_id": subject.logical_object_id,
            }
        )
    return {
        "actor": actor,
        "subjects": subjects,
        _REASON_FIELD: reason,
        "source_ref": source,
    }


def with_replacement_selections(
    intent: Any,
    selections: Sequence[str | FrozenMap | Mapping[str, Any]],
) -> (
    PlaceCountersIntent
    | PlaceCountersOnSetIntent
    | PlacePlayerCountersIntent
    | ProliferateIntent
    | ZoneMoveIntent
):
    if not isinstance(
        intent,
        (
            PlaceCountersIntent,
            PlaceCountersOnSetIntent,
            PlacePlayerCountersIntent,
            ProliferateIntent,
            ZoneMoveIntent,
        ),
    ):
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
