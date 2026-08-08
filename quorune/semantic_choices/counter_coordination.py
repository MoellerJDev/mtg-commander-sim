from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Protocol, Sequence

from ..replacement.immutable import FrozenMap, thaw_value
from ..replacement_effects import (
    ReplacementChoiceRequired,
    ReplacementContinuation,
    ReplacementEffectError,
    replacement_choice_payload,
)
from ..semantic_runtime import IntentPlan, PlaceCountersIntent, execute_intent_plan
from .defaults import default_semantic_choice_registry
from .model import (
    SemanticChoiceCompletion,
    SemanticChoiceContinuation,
    SemanticChoiceError,
)


_PILOT_ROLE = "pi" + "lot"
_COUNTER_INTENT_FIELDS = {
    "actor",
    "object_refs",
    "counter_name",
    "amount",
    "reason",
    "source_ref",
}


class SemanticCounterCoordinationHost(Protocol):
    state: Any
    permissions: Any

    def _validate_semantic_frame(
        self, frame: Mapping[str, Any], item: Any
    ) -> None: ...

    def _semantic_choice_query(
        self,
        actor: str,
        *,
        response: Mapping[str, Any] | None = None,
        effect: Mapping[str, Any] | None = None,
        source_ref: str | None = None,
    ) -> Any: ...

    def _continue_resolution(
        self,
        *,
        stack_ref: str,
        effects: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
    ) -> None: ...


def counter_intent_identity(intent: PlaceCountersIntent) -> dict[str, Any]:
    """Serialize the stable, choice-independent identity of one placement."""

    if not isinstance(intent, PlaceCountersIntent):
        raise SemanticChoiceError(
            "Counter continuation requires a typed placement intent"
        )
    return {
        "actor": intent.actor,
        "object_refs": list(intent.object_refs),
        "counter_name": intent.counter_name,
        "amount": intent.amount,
        "reason": intent.reason,
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
    reason = value["reason"]
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
        "reason": reason,
        "source_ref": source,
    }


def _serialized_selections(
    selections: Sequence[str | FrozenMap | Mapping[str, Any]],
) -> list[str | dict[str, Any]]:
    return [
        value if isinstance(value, str) else thaw_value(value)
        for value in selections
    ]


def _issue_counter_replacement_choice(
    host: SemanticCounterCoordinationHost,
    *,
    continuation: SemanticChoiceContinuation,
    actor: str,
    response: Mapping[str, Any],
    intent: PlaceCountersIntent,
    intent_index: int,
    selections: Sequence[str | FrozenMap | Mapping[str, Any]],
    required: ReplacementChoiceRequired,
) -> None:
    pending = required.pending
    seat = pending.choice.chooser
    context = replacement_choice_payload(pending, required.effects)
    host.permissions.issue(
        kind="replacement.order",
        role=_PILOT_ROLE,
        actors=[seat],
        allowed_actions=["choose"],
        payload_by_actor={seat: context},
        continuation={
            "replacement_resume_kind": "semantic_counter_completion",
            "semantic_choice_continuation": continuation.to_dict(),
            "semantic_choice_actor": actor,
            "semantic_choice_response": dict(response),
            "intent_index": intent_index,
            "counter_intent": counter_intent_identity(intent),
            "replacement_selections": _serialized_selections(selections),
            "replacement_batch": required.batch.to_dict(),
            "replacement_effects": [
                effect.to_dict() for effect in required.effects
            ],
        },
    )


def _source_ref(host: SemanticCounterCoordinationHost, item: Any) -> str | None:
    object_id = item.source_object_id or item.card_object_id or ""
    source = host.state.cards.get(object_id)
    return source.ref if source is not None else None


def continue_semantic_completion(
    host: SemanticCounterCoordinationHost,
    *,
    item: Any,
    continuation: SemanticChoiceContinuation,
    actor: str,
    response: Mapping[str, Any],
    completion: SemanticChoiceCompletion,
    start_index: int = 0,
    replacement_selections: Sequence[
        str | FrozenMap | Mapping[str, Any]
    ] = (),
    expected_counter_intent: Mapping[str, Any] | None = None,
) -> bool:
    """Execute a completion, suspending counter placement before mutation."""

    intents = tuple(completion.intents)
    if type(start_index) is not int or start_index < 0 or start_index > len(intents):
        raise SemanticChoiceError("Semantic counter intent index is invalid")
    expected = (
        validate_counter_intent_identity(expected_counter_intent)
        if expected_counter_intent is not None
        else None
    )
    for index in range(start_index, len(intents)):
        intent = intents[index]
        selections = replacement_selections if index == start_index else ()
        if selections or expected is not None:
            if not isinstance(intent, PlaceCountersIntent):
                raise SemanticChoiceError(
                    "Semantic counter continuation no longer names a counter intent"
                )
            identity = counter_intent_identity(intent)
            if expected is not None and identity != expected:
                raise SemanticChoiceError(
                    "Semantic counter intent changed before replacement resume"
                )
            intent = replace(
                intent,
                replacement_selections=tuple(selections),
            )
        try:
            execute_intent_plan(
                host,
                IntentPlan(
                    operation=str(continuation.effect.get("op") or ""),
                    handler_id=continuation.handler_id,
                    intents=(intent,),
                ),
            )
        except ReplacementChoiceRequired as required:
            if not isinstance(intent, PlaceCountersIntent):
                raise
            _issue_counter_replacement_choice(
                host,
                continuation=continuation,
                actor=actor,
                response=response,
                intent=intent,
                intent_index=index,
                selections=intent.replacement_selections,
                required=required,
            )
            return False
        expected = None
        replacement_selections = ()
    if item not in host.state.stack:
        return True
    remaining = [
        *(thaw_value(value) for value in completion.prepend_effects),
        *(thaw_value(value) for value in continuation.remaining),
    ]
    if completion.repeat_effect is not None:
        remaining.insert(0, thaw_value(completion.repeat_effect))
    host._continue_resolution(
        stack_ref=continuation.stack_ref,
        effects=remaining,
        destination=continuation.destination,
        note=continuation.note,
        instruction_pointer=(
            continuation.semantic_frame.instruction_pointer + 1
        ),
    )
    return True


def resume_semantic_counter_completion(
    host: SemanticCounterCoordinationHost,
    restored: ReplacementContinuation,
    selection: str | Mapping[str, Any],
    *,
    error_type: type[Exception],
) -> None:
    try:
        raw_continuation = restored.thaw_semantic_choice_continuation()
        response = restored.thaw_semantic_choice_response()
        expected_intent = validate_counter_intent_identity(
            restored.thaw_counter_intent()
        )
        registry = default_semantic_choice_registry()
        handler, continuation = registry.decode_continuation(raw_continuation)
        item = next(
            (
                candidate
                for candidate in host.state.stack
                if candidate.ref == continuation.stack_ref
            ),
            None,
        )
        if item is None:
            raise SemanticChoiceError(
                "Semantic counter continuation stack object no longer exists"
            )
        host._validate_semantic_frame(
            continuation.semantic_frame.to_dict(), item
        )
        actor = restored.semantic_choice_actor
        completion = handler.complete(
            continuation,
            response,
            host._semantic_choice_query(
                actor,
                response=response,
                effect=continuation.effect,
                source_ref=_source_ref(host, item),
            ),
        )
        continue_semantic_completion(
            host,
            item=item,
            continuation=continuation,
            actor=actor,
            response=response,
            completion=completion,
            start_index=restored.intent_index,
            replacement_selections=(
                *restored.replacement_selections,
                selection,
            ),
            expected_counter_intent=expected_intent,
        )
    except (SemanticChoiceError, ReplacementEffectError) as exc:
        raise error_type(str(exc)) from exc
