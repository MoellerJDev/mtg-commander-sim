from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .immutable import FrozenMap, thaw_value
from .model import (
    ReplacementEffect,
    ReplacementEffectError,
    ReplacementEventBatch,
    exact_fields,
    mapping_sequence,
    sequence,
)


_COMBAT_FIELDS = {
    "replacement_resume_kind",
    "combat_assignments",
    "replacement_selections",
    "replacement_batch",
    "replacement_effects",
}
_SEMANTIC_FIELDS = {
    "stack_ref",
    "effect",
    "remaining",
    "destination",
    "note",
    "instruction_pointer",
    "semantic_frame",
    "replacement_batch",
    "replacement_effects",
}
_MANA_FIELDS = {
    "replacement_resume_kind",
    "priority_seat",
    "priority_action",
    "priority_response",
    "priority_frame",
    "replacement_batch",
    "replacement_effects",
}
_SEMANTIC_COUNTER_COMPLETION_FIELDS = {
    "replacement_resume_kind",
    "semantic_choice_continuation",
    "semantic_choice_actor",
    "semantic_choice_response",
    "intent_index",
    "counter_intent",
    "replacement_selections",
    "replacement_batch",
    "replacement_effects",
}
_SEMANTIC_INTENT_COMPLETION_FIELDS = {
    "replacement_resume_kind",
    "semantic_choice_continuation",
    "semantic_choice_actor",
    "semantic_choice_response",
    "intent_index",
    "semantic_intent_kind",
    "semantic_intent",
    "replacement_selections",
    "replacement_batch",
    "replacement_effects",
}
_SEMANTIC_PREPARATION_FIELDS = (
    _SEMANTIC_INTENT_COMPLETION_FIELDS - {"semantic_choice_response"}
)
_RESOLVING_ENTRY_FIELDS = {
    "replacement_resume_kind",
    "stack_ref",
    "destination",
    "note",
    "instruction_pointer",
    "semantic_frame",
    "replacement_selections",
    "replacement_batch",
    "replacement_effects",
}
_MANA_FRAME_FIELDS = {
    "active_player",
    "phase",
    "step",
    "turn_sequence",
    "priority_player",
    "priority_epoch",
    "stack_refs",
}


@dataclass(frozen=True, slots=True)
class ReplacementContinuation:
    """Strictly deserialized, replay-pinned replacement suspension data."""

    batch: ReplacementEventBatch
    effects: tuple[ReplacementEffect, ...]
    resume_kind: str
    combat_assignments: tuple[FrozenMap, ...] = ()
    replacement_selections: tuple[str | FrozenMap, ...] = ()
    stack_ref: str = ""
    effect: FrozenMap | None = None
    remaining: tuple[FrozenMap, ...] = ()
    destination: str | None = None
    note: str = ""
    instruction_pointer: int = 0
    semantic_frame: FrozenMap | None = None
    priority_seat: str = ""
    priority_action: str = ""
    priority_response: FrozenMap | None = None
    priority_frame: FrozenMap | None = None
    semantic_choice_continuation: FrozenMap | None = None
    semantic_choice_actor: str = ""
    semantic_choice_response: FrozenMap | None = None
    intent_index: int = 0
    counter_intent: FrozenMap | None = None
    semantic_intent_kind: str = ""
    semantic_intent: FrozenMap | None = None

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "ReplacementContinuation":
        if not isinstance(value, Mapping):
            raise ReplacementEffectError(
                "Replacement continuation must be an object"
            )
        resume_kind = _validate_continuation_shape(value)
        batch, effects = _decode_batch_and_effects(value)
        if resume_kind == "combat_damage":
            return _decode_combat_continuation(cls, value, batch, effects)
        if resume_kind == "mana_payment":
            return _decode_mana_continuation(cls, value, batch, effects)
        if resume_kind == "semantic_counter_completion":
            return _decode_semantic_counter_completion(
                cls, value, batch, effects
            )
        if resume_kind in {
            "semantic_intent_completion",
            "semantic_preparation",
        }:
            return _decode_semantic_intent_continuation(
                cls, value, batch, effects, resume_kind=resume_kind
            )
        if resume_kind == "resolving_entry":
            return _decode_resolving_entry_continuation(
                cls, value, batch, effects
            )
        return _decode_semantic_continuation(cls, value, batch, effects)

    def thaw_combat_assignments(self) -> list[dict[str, Any]]:
        return [thaw_value(value) for value in self.combat_assignments]

    def thaw_effect(self) -> dict[str, Any]:
        if self.effect is None:
            raise ReplacementEffectError(
                "Combat continuation has no semantic effect"
            )
        return thaw_value(self.effect)

    def thaw_remaining(self) -> list[dict[str, Any]]:
        return [thaw_value(value) for value in self.remaining]

    def thaw_semantic_frame(self) -> dict[str, Any]:
        if self.semantic_frame is None:
            raise ReplacementEffectError(
                "Combat continuation has no semantic frame"
            )
        return thaw_value(self.semantic_frame)

    def thaw_priority_response(self) -> dict[str, Any]:
        if self.priority_response is None:
            raise ReplacementEffectError(
                "This continuation has no priority response"
            )
        return thaw_value(self.priority_response)

    def thaw_priority_frame(self) -> dict[str, Any]:
        if self.priority_frame is None:
            raise ReplacementEffectError(
                "This continuation has no priority frame"
            )
        return thaw_value(self.priority_frame)

    def thaw_semantic_choice_continuation(self) -> dict[str, Any]:
        if self.semantic_choice_continuation is None:
            raise ReplacementEffectError(
                "This continuation has no semantic-choice continuation"
            )
        return thaw_value(self.semantic_choice_continuation)

    def thaw_semantic_choice_response(self) -> dict[str, Any]:
        if self.semantic_choice_response is None:
            raise ReplacementEffectError(
                "This continuation has no semantic-choice response"
            )
        return thaw_value(self.semantic_choice_response)

    def thaw_counter_intent(self) -> dict[str, Any]:
        if self.counter_intent is None:
            raise ReplacementEffectError(
                "This continuation has no counter intent"
            )
        return thaw_value(self.counter_intent)

    def thaw_semantic_intent(self) -> dict[str, Any]:
        if self.semantic_intent is None:
            raise ReplacementEffectError(
                "This continuation has no semantic intent"
            )
        return thaw_value(self.semantic_intent)


def _validate_continuation_shape(value: Mapping[str, Any]) -> str:
    resume_kind = str(value.get("replacement_resume_kind") or "semantic")
    shapes = {
        "combat_damage": (_COMBAT_FIELDS, "combat continuation"),
        "semantic": (_SEMANTIC_FIELDS, "semantic continuation"),
        "mana_payment": (_MANA_FIELDS, "mana-payment continuation"),
        "semantic_counter_completion": (
            _SEMANTIC_COUNTER_COMPLETION_FIELDS,
            "semantic counter-completion continuation",
        ),
        "semantic_intent_completion": (
            _SEMANTIC_INTENT_COMPLETION_FIELDS,
            "semantic intent-completion continuation",
        ),
        "semantic_preparation": (
            _SEMANTIC_PREPARATION_FIELDS,
            "semantic preparation continuation",
        ),
        "resolving_entry": (
            _RESOLVING_ENTRY_FIELDS,
            "resolving entry continuation",
        ),
    }
    shape = shapes.get(resume_kind)
    if shape is None:
        raise ReplacementEffectError(
            "Unknown replacement continuation resume kind"
        )
    fields, field_name = shape
    exact_fields(value, fields, field_name=field_name)
    return resume_kind


def _decode_batch_and_effects(
    value: Mapping[str, Any],
) -> tuple[ReplacementEventBatch, tuple[ReplacementEffect, ...]]:
    batch_value = value.get("replacement_batch")
    if not isinstance(batch_value, Mapping):
        raise ReplacementEffectError(
            "Replacement continuation batch must be an object"
        )
    batch = ReplacementEventBatch.from_dict(batch_value)
    effects = tuple(
        ReplacementEffect.from_dict(effect)
        for effect in mapping_sequence(
            value.get("replacement_effects"),
            field_name="continuation effects",
        )
    )
    if not effects:
        raise ReplacementEffectError(
            "Replacement continuation requires effects"
        )
    return batch, effects


def _decode_typed_selection(item: Mapping[str, Any]) -> FrozenMap:
    expected = {"effect_id"}
    if "allocation" in item:
        expected.add("allocation")
    if "event_id" in item:
        expected.add("event_id")
    if expected == {"effect_id"}:
        raise ReplacementEffectError(
            "Typed continuation selection has no typed payload"
        )
    exact_fields(
        item,
        expected,
        field_name="typed continuation selection",
    )
    if not isinstance(item["effect_id"], str) or not item["effect_id"]:
        raise ReplacementEffectError(
            "Typed continuation selection is malformed"
        )
    if "allocation" in item and not isinstance(item["allocation"], Mapping):
        raise ReplacementEffectError(
            "Typed continuation selection is malformed"
        )
    if "event_id" in item and (
        not isinstance(item["event_id"], str) or not item["event_id"]
    ):
        raise ReplacementEffectError(
            "Typed continuation event identity is malformed"
        )
    return FrozenMap(item)


def _decode_combat_selections(
    value: Mapping[str, Any],
) -> tuple[str | FrozenMap, ...]:
    parsed: list[str | FrozenMap] = []
    for item in sequence(
        value["replacement_selections"],
        field_name="continuation selections",
    ):
        if isinstance(item, str) and item:
            parsed.append(item)
        elif isinstance(item, Mapping):
            parsed.append(_decode_typed_selection(item))
        else:
            raise ReplacementEffectError(
                "Replacement continuation selections must be canonical strings"
            )
    return tuple(parsed)


def _decode_combat_continuation(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
) -> ReplacementContinuation:
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind="combat_damage",
        combat_assignments=tuple(
            FrozenMap(item)
            for item in mapping_sequence(
                value["combat_assignments"],
                field_name="combat assignments",
            )
        ),
        replacement_selections=_decode_combat_selections(value),
    )


def _validate_mana_frame(frame: Mapping[str, Any], seat: str) -> None:
    exact_fields(frame, _MANA_FRAME_FIELDS, field_name="mana-payment frame")
    stack_refs = frame["stack_refs"]
    if not isinstance(stack_refs, (list, tuple)) or any(
        not isinstance(item, str) or not item for item in stack_refs
    ):
        raise ReplacementEffectError(
            "Mana-payment stack frame is malformed"
        )
    if len(stack_refs) != len(set(stack_refs)):
        raise ReplacementEffectError(
            "Mana-payment stack frame repeats an object"
        )
    if (
        not isinstance(frame["active_player"], str)
        or not frame["active_player"]
        or not isinstance(frame["phase"], str)
        or not frame["phase"]
        or not isinstance(frame["step"], str)
        or not frame["step"]
        or type(frame["turn_sequence"]) is not int
        or frame["turn_sequence"] < 0
        or frame["priority_player"] != seat
        or type(frame["priority_epoch"]) is not int
        or frame["priority_epoch"] < 0
    ):
        raise ReplacementEffectError(
            "Mana-payment continuation frame values are malformed"
        )


def _validate_priority_response(
    action: str, response: Mapping[str, Any]
) -> None:
    payment_id = response.get("_mana_payment_id")
    if not isinstance(payment_id, str) or not payment_id:
        raise ReplacementEffectError(
            "Mana-payment continuation requires a stable payment identity"
        )
    if action == "activate" and (
        not isinstance(response.get("source"), str)
        or not response.get("source")
        or not isinstance(response.get("ability"), str)
        or not response.get("ability")
    ):
        raise ReplacementEffectError(
            "Mana-payment activation response is malformed"
        )
    if action == "cast" and (
        not isinstance(response.get("card"), str) or not response.get("card")
    ):
        raise ReplacementEffectError(
            "Mana-payment cast response is malformed"
        )


def _decode_mana_continuation(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
) -> ReplacementContinuation:
    seat = value["priority_seat"]
    action = value["priority_action"]
    response = value["priority_response"]
    frame = value["priority_frame"]
    if (
        not isinstance(seat, str)
        or not seat
        or action not in {"cast", "activate"}
        or not isinstance(response, Mapping)
        or not isinstance(frame, Mapping)
    ):
        raise ReplacementEffectError(
            "Mana-payment continuation fields are malformed"
        )
    if seat not in batch.apnap_order:
        raise ReplacementEffectError(
            "Mana-payment continuation seat is not in APNAP order"
        )
    _validate_mana_frame(frame, seat)
    _validate_priority_response(action, response)
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind="mana_payment",
        priority_seat=seat,
        priority_action=action,
        priority_response=FrozenMap(response),
        priority_frame=FrozenMap(frame),
    )


def _decode_semantic_counter_completion(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
) -> ReplacementContinuation:
    semantic = value["semantic_choice_continuation"]
    actor = value["semantic_choice_actor"]
    response = value["semantic_choice_response"]
    counter_intent = value["counter_intent"]
    intent_index = value["intent_index"]
    if (
        not isinstance(semantic, Mapping)
        or not isinstance(actor, str)
        or not actor
        or not isinstance(response, Mapping)
        or not isinstance(counter_intent, Mapping)
        or type(intent_index) is not int
        or intent_index < 0
    ):
        raise ReplacementEffectError(
            "Semantic counter-completion continuation fields are malformed"
        )
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind="semantic_counter_completion",
        semantic_choice_continuation=FrozenMap(semantic),
        semantic_choice_actor=actor,
        semantic_choice_response=FrozenMap(response),
        intent_index=intent_index,
        counter_intent=FrozenMap(counter_intent),
        replacement_selections=_decode_combat_selections(value),
    )


def _decode_semantic_intent_continuation(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
    *,
    resume_kind: str,
) -> ReplacementContinuation:
    semantic = value["semantic_choice_continuation"]
    actor = value["semantic_choice_actor"]
    response = value.get("semantic_choice_response")
    semantic_intent = value["semantic_intent"]
    intent_kind = value["semantic_intent_kind"]
    intent_index = value["intent_index"]
    if (
        not isinstance(semantic, Mapping)
        or type(actor) is not str
        or not actor
        or actor not in batch.apnap_order
        or (resume_kind == "semantic_intent_completion" and not isinstance(response, Mapping))
        or not isinstance(semantic_intent, Mapping)
        or intent_kind not in {
            "place_counters",
            "place_counters_on_set",
            "place_counters_on_targets",
            "place_player_counters",
            "proliferate",
            "zone_move",
        }
        or type(intent_index) is not int
        or intent_index < 0
    ):
        raise ReplacementEffectError(
            "Semantic intent continuation fields are malformed"
        )
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind=resume_kind,
        semantic_choice_continuation=FrozenMap(semantic),
        semantic_choice_actor=actor,
        semantic_choice_response=(
            FrozenMap(response) if isinstance(response, Mapping) else None
        ),
        intent_index=intent_index,
        semantic_intent_kind=intent_kind,
        semantic_intent=FrozenMap(semantic_intent),
        replacement_selections=_decode_combat_selections(value),
    )


def _decode_semantic_continuation(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
) -> ReplacementContinuation:
    effect = value["effect"]
    semantic_frame = value["semantic_frame"]
    if not isinstance(effect, Mapping) or not isinstance(
        semantic_frame, Mapping
    ):
        raise ReplacementEffectError(
            "Semantic replacement continuation mappings are malformed"
        )
    instruction_pointer = value["instruction_pointer"]
    if type(instruction_pointer) is not int or instruction_pointer < 0:
        raise ReplacementEffectError(
            "Replacement continuation instruction pointer is invalid"
        )
    destination = value["destination"]
    if destination is not None and not isinstance(destination, str):
        raise ReplacementEffectError(
            "Replacement continuation destination is malformed"
        )
    if not isinstance(value["note"], str):
        raise ReplacementEffectError(
            "Replacement continuation note is malformed"
        )
    stack_ref = value["stack_ref"]
    if not isinstance(stack_ref, str) or not stack_ref:
        raise ReplacementEffectError(
            "Replacement continuation stack reference is required"
        )
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind="semantic",
        stack_ref=stack_ref,
        effect=FrozenMap(effect),
        remaining=tuple(
            FrozenMap(item)
            for item in mapping_sequence(
                value["remaining"], field_name="remaining effects"
            )
        ),
        destination=destination,
        note=value["note"],
        instruction_pointer=instruction_pointer,
        semantic_frame=FrozenMap(semantic_frame),
    )


def _decode_resolving_entry_continuation(
    continuation_type: type[ReplacementContinuation],
    value: Mapping[str, Any],
    batch: ReplacementEventBatch,
    effects: tuple[ReplacementEffect, ...],
) -> ReplacementContinuation:
    stack_ref = value["stack_ref"]
    destination = value["destination"]
    note = value["note"]
    instruction_pointer = value["instruction_pointer"]
    semantic_frame = value["semantic_frame"]
    if (
        not isinstance(stack_ref, str)
        or not stack_ref
        or (
            destination is not None
            and not isinstance(destination, str)
        )
        or not isinstance(note, str)
        or type(instruction_pointer) is not int
        or instruction_pointer < 0
        or not isinstance(semantic_frame, Mapping)
    ):
        raise ReplacementEffectError(
            "Resolving entry continuation fields are malformed"
        )
    return continuation_type(
        batch=batch,
        effects=effects,
        resume_kind="resolving_entry",
        replacement_selections=_decode_combat_selections(value),
        stack_ref=stack_ref,
        destination=destination,
        note=note,
        instruction_pointer=instruction_pointer,
        semantic_frame=FrozenMap(semantic_frame),
    )
