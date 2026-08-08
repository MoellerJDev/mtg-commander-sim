from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence

from .replacement_effects import (
    ReplacementChoiceRequired,
    ReplacementContinuation,
    replacement_choice_payload,
)


_PILOT_ROLE = "pi" + "lot"


class EntryCounterCoordinationHost(Protocol):
    permissions: Any
    state: Any

    def _semantic_frame(
        self,
        item: Any,
        *,
        instruction_pointer: int,
        pending_choice_id: str | None = None,
    ) -> dict[str, Any]: ...

    def _validate_semantic_frame(
        self, frame: Mapping[str, Any], item: Any
    ) -> None: ...

    def _continue_resolution(
        self,
        *,
        stack_ref: str,
        effects: list[dict[str, Any]],
        destination: str | None,
        note: str,
        instruction_pointer: int = 0,
        entry_replacement_selections: Sequence[
            str | Mapping[str, Any]
        ] = (),
    ) -> None: ...


def issue_resolving_entry_replacement_choice(
    host: EntryCounterCoordinationHost,
    *,
    item: Any,
    destination: str | None,
    note: str,
    instruction_pointer: int,
    selections: Sequence[str | Mapping[str, Any]],
    required: ReplacementChoiceRequired,
) -> None:
    """Suspend a permanent's final as-enters transaction before mutation."""

    pending = required.pending
    chooser = pending.choice.chooser
    decision = host.permissions.issue(
        kind="replacement.order",
        role=_PILOT_ROLE,
        actors=[chooser],
        allowed_actions=["choose"],
        payload_by_actor={
            chooser: replacement_choice_payload(
                pending, required.effects
            )
        },
        continuation={
            "replacement_resume_kind": "resolving_entry",
            "stack_ref": item.ref,
            "destination": destination,
            "note": note,
            "instruction_pointer": instruction_pointer,
            "semantic_frame": host._semantic_frame(
                item,
                instruction_pointer=instruction_pointer,
            ),
            "replacement_selections": [
                dict(value) if isinstance(value, Mapping) else value
                for value in selections
            ],
            "replacement_batch": required.batch.to_dict(),
            "replacement_effects": [
                effect.to_dict() for effect in required.effects
            ],
        },
    )
    decision.continuation["semantic_frame"]["pending_choice_id"] = (
        decision.decision_id
    )


def resume_resolving_entry_replacement(
    host: EntryCounterCoordinationHost,
    restored: ReplacementContinuation,
    selection: str | Mapping[str, Any],
    *,
    error_type: type[Exception],
) -> None:
    item = next(
        (
            candidate
            for candidate in host.state.stack
            if candidate.ref == restored.stack_ref
        ),
        None,
    )
    if item is None:
        raise error_type(
            "Entry replacement continuation stack object no longer exists"
        )
    host._validate_semantic_frame(restored.thaw_semantic_frame(), item)
    host._continue_resolution(
        stack_ref=item.ref,
        effects=[],
        destination=restored.destination,
        note=restored.note,
        instruction_pointer=restored.instruction_pointer,
        entry_replacement_selections=(
            *restored.replacement_selections,
            selection,
        ),
    )


__all__ = [
    "issue_resolving_entry_replacement_choice",
    "resume_resolving_entry_replacement",
]
