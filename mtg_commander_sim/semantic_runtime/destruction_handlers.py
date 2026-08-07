from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import DestroyPermanentIntent, IntentPlan


_FIELDS = frozenset(
    {"op", "card", "reason", "_replacement_selections"}
)


@dataclass(frozen=True, slots=True)
class DestroyPermanentHandler:
    handler_id: str = "generic.destroy-permanent.v1"
    schema_version: int = 1
    family: str = "effect.permanent-destruction"
    operation: str = "destroy"
    rule_references: tuple[str, ...] = (
        "122.1c",
        "701.8",
        "701.8a",
        "701.8b",
        "701.8c",
        "702.12b",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.destroy.effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        unknown = sorted(set(effect) - _FIELDS)
        if unknown:
            raise SemanticNodeError(
                "Destroy effect has unknown fields: " + ", ".join(unknown)
            )
        object_ref = effect.get("card")
        if not isinstance(object_ref, str) or not object_ref:
            raise SemanticNodeError(
                "Destroy effects require one nonempty permanent reference"
            )
        raw_reason = effect.get("reason")
        if raw_reason is not None and (
            not isinstance(raw_reason, str) or not raw_reason
        ):
            raise SemanticNodeError(
                "Destroy effect reason must be a nonempty string"
            )
        raw_selections = effect.get("_replacement_selections")
        if raw_selections is None:
            raw_selections = ()
        if not isinstance(raw_selections, (list, tuple)):
            raise SemanticNodeError(
                "Destroy replacement selections must be a list"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                DestroyPermanentIntent(
                    actor=context.actor,
                    object_ref=object_ref,
                    reason=raw_reason or context.default_reason,
                    replacement_selections=tuple(raw_selections),
                ),
            ),
        )


DESTRUCTION_HANDLERS = (DestroyPermanentHandler(),)


__all__ = ["DESTRUCTION_HANDLERS", "DestroyPermanentHandler"]
