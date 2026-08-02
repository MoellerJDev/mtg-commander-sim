from __future__ import annotations

import copy
from typing import Any, Mapping, Protocol, Sequence

from .replacement_effects import (
    ReplacementChoiceRequired,
    ReplacementEffect,
    ReplacementEventBatch,
    next_batch_replacement_choice,
    replacement_choice_payload,
)


_PILOT_ROLE = "pi" + "lot"


class ReplacementDecisionHost(Protocol):
    state: Any
    permissions: Any

    def _semantic_frame(
        self, item: Any, *, instruction_pointer: int
    ) -> dict[str, Any]: ...

    def _validate_semantic_frame(
        self, frame: Mapping[str, Any], item: Any
    ) -> None: ...

    def _continue_resolution(
        self,
        *,
        stack_ref: str,
        effects: Sequence[Mapping[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
    ) -> None: ...

    def apply_effect(
        self,
        effect: Mapping[str, Any],
        *,
        actor: str,
        as_cost: bool = False,
    ) -> Any: ...


def issue_replacement_order_choice(
    host: ReplacementDecisionHost,
    *,
    item: Any,
    effect: Mapping[str, Any],
    remaining: Sequence[Mapping[str, Any]],
    destination: str | None,
    note: str,
    instruction_pointer: int,
    required: ReplacementChoiceRequired,
) -> None:
    """Suspend one semantic instruction at a seat-scoped CR 616 choice."""

    pending = required.pending
    seat = pending.choice.chooser
    context = replacement_choice_payload(pending, required.effects)
    decision = host.permissions.issue(
        kind="replacement.order",
        role=_PILOT_ROLE,
        actors=[seat],
        allowed_actions=["choose"],
        payload_by_actor={seat: context},
        continuation={
            "stack_ref": item.ref,
            "effect": copy.deepcopy(dict(effect)),
            "remaining": [copy.deepcopy(dict(value)) for value in remaining],
            "destination": destination,
            "note": note,
            "instruction_pointer": instruction_pointer,
            "semantic_frame": host._semantic_frame(
                item,
                instruction_pointer=instruction_pointer,
            ),
            "replacement_batch": required.batch.to_dict(),
            "replacement_effects": [
                replacement.to_dict() for replacement in required.effects
            ],
        },
    )
    decision.continuation["semantic_frame"]["pending_choice_id"] = (
        decision.decision_id
    )


def apply_effect_with_replacement_choice(
    host: ReplacementDecisionHost,
    item: Any,
    effect: Mapping[str, Any],
    continuation: tuple[
        Sequence[Mapping[str, Any]], str | None, str, int
    ],
) -> bool:
    """Apply one effect or suspend it before any replacement choice."""

    remaining, destination, note, instruction_pointer = continuation
    try:
        host.apply_effect(effect, actor=item.controller, as_cost=False)
    except ReplacementChoiceRequired as required:
        issue_replacement_order_choice(
            host,
            item=item,
            effect=effect,
            remaining=remaining,
            destination=destination,
            note=note,
            instruction_pointer=instruction_pointer,
            required=required,
        )
        return False
    return item in host.state.stack


def complete_replacement_order_choice(
    host: ReplacementDecisionHost,
    decision: Any,
    *,
    error_type: type[Exception],
) -> None:
    """Validate and append one exact replacement choice before resuming."""

    seat = decision.actors[0]
    response = decision.responses[seat]
    selected = response.get("replacement")
    if not isinstance(selected, str) or not selected:
        raise error_type("A replacement effect selection is required")
    continuation = decision.continuation
    stack_ref = str(continuation.get("stack_ref") or "")
    item = next(
        (
            candidate
            for candidate in host.state.stack
            if candidate.ref == stack_ref
        ),
        None,
    )
    if item is None:
        raise error_type(
            "Replacement continuation stack object no longer exists"
        )
    host._validate_semantic_frame(
        dict(continuation.get("semantic_frame") or {}),
        item,
    )
    batch = ReplacementEventBatch.from_dict(
        dict(continuation.get("replacement_batch") or {})
    )
    effects = tuple(
        ReplacementEffect.from_dict(value)
        for value in continuation.get("replacement_effects", ())
        if isinstance(value, Mapping)
    )
    pending = next_batch_replacement_choice(batch, effects)
    if pending is None or pending.choice.chooser != seat:
        raise error_type(
            "Replacement continuation no longer requires this chooser"
        )
    if selected not in pending.choice.legal_selections:
        raise error_type("Selected replacement is not currently available")
    current_effect = copy.deepcopy(
        dict(continuation.get("effect") or {})
    )
    current_effect["_replacement_selections"] = [
        *list(current_effect.get("_replacement_selections") or []),
        selected,
    ]
    host._continue_resolution(
        stack_ref=stack_ref,
        effects=[
            current_effect,
            *[
                copy.deepcopy(dict(value))
                for value in continuation.get("remaining", ())
            ],
        ],
        destination=continuation.get("destination"),
        note=str(continuation.get("note") or ""),
        instruction_pointer=int(
            continuation.get("instruction_pointer", 0)
        ),
    )
