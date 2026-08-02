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


@dataclass(frozen=True, slots=True)
class ReplacementContinuation:
    """Strictly deserialized, replay-pinned replacement suspension data."""

    batch: ReplacementEventBatch
    effects: tuple[ReplacementEffect, ...]
    resume_kind: str
    combat_assignments: tuple[FrozenMap, ...] = ()
    replacement_selections: tuple[str, ...] = ()
    stack_ref: str = ""
    effect: FrozenMap | None = None
    remaining: tuple[FrozenMap, ...] = ()
    destination: str | None = None
    note: str = ""
    instruction_pointer: int = 0
    semantic_frame: FrozenMap | None = None

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "ReplacementContinuation":
        if not isinstance(value, Mapping):
            raise ReplacementEffectError(
                "Replacement continuation must be an object"
            )
        resume_kind = str(
            value.get("replacement_resume_kind") or "semantic"
        )
        if resume_kind == "combat_damage":
            exact_fields(
                value,
                {
                    "replacement_resume_kind",
                    "combat_assignments",
                    "replacement_selections",
                    "replacement_batch",
                    "replacement_effects",
                },
                field_name="combat continuation",
            )
        elif resume_kind == "semantic":
            exact_fields(
                value,
                {
                    "stack_ref",
                    "effect",
                    "remaining",
                    "destination",
                    "note",
                    "instruction_pointer",
                    "semantic_frame",
                    "replacement_batch",
                    "replacement_effects",
                },
                field_name="semantic continuation",
            )
        else:
            raise ReplacementEffectError(
                "Unknown replacement continuation resume kind"
            )
        batch_value = value.get("replacement_batch")
        if not isinstance(batch_value, Mapping):
            raise ReplacementEffectError(
                "Replacement continuation batch must be an object"
            )
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
        if resume_kind == "combat_damage":
            selections = sequence(
                value["replacement_selections"],
                field_name="continuation selections",
            )
            if any(not isinstance(item, str) or not item for item in selections):
                raise ReplacementEffectError(
                    "Replacement continuation selections must be canonical strings"
                )
            return cls(
                batch=ReplacementEventBatch.from_dict(batch_value),
                effects=effects,
                resume_kind=resume_kind,
                combat_assignments=tuple(
                    FrozenMap(item)
                    for item in mapping_sequence(
                        value["combat_assignments"],
                        field_name="combat assignments",
                    )
                ),
                replacement_selections=tuple(selections),
            )
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
        return cls(
            batch=ReplacementEventBatch.from_dict(batch_value),
            effects=effects,
            resume_kind=resume_kind,
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
