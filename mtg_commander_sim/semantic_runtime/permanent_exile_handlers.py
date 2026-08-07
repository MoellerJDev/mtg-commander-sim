from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import ExilePermanentIntent, IntentPlan


_REASON_FIELD = "rea" + "son"
_FIELDS = frozenset(
    {"op", "card", _REASON_FIELD, "_replacement_selections"}
)


@dataclass(frozen=True, slots=True)
class ExilePermanentHandler:
    handler_id: str = "generic.exile-permanent.v1"
    schema_version: int = 1
    family: str = "effect.permanent-exile"
    operation: str = "exile_permanent"
    rule_references: tuple[str, ...] = (
        "400.2",
        "400.7",
        "406.1",
        "406.2",
        "608.2c",
        "701.13a",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.exile.effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        unknown = sorted(set(effect) - _FIELDS)
        if unknown:
            raise SemanticNodeError(
                "Permanent-exile effect has unknown fields: "
                + ", ".join(unknown)
            )
        object_ref = effect.get("card")
        if not isinstance(object_ref, str) or not object_ref:
            raise SemanticNodeError(
                "Permanent-exile effects require one permanent reference"
            )
        raw_reason = effect.get(_REASON_FIELD)
        if raw_reason is not None and (
            not isinstance(raw_reason, str) or not raw_reason
        ):
            raise SemanticNodeError(
                "Permanent-exile effect reason must be a nonempty string"
            )
        raw_selections = effect.get("_replacement_selections")
        if raw_selections is None:
            raw_selections = ()
        if not isinstance(raw_selections, (list, tuple)):
            raise SemanticNodeError(
                "Permanent-exile replacement selections must be a list"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                ExilePermanentIntent(
                    actor=context.actor,
                    object_ref=object_ref,
                    reason=raw_reason or context.default_reason,
                    replacement_selections=tuple(raw_selections),
                ),
            ),
        )


PERMANENT_EXILE_HANDLERS = (ExilePermanentHandler(),)


__all__ = ["ExilePermanentHandler", "PERMANENT_EXILE_HANDLERS"]
