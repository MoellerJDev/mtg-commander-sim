from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext
from .direct_target_fields import validate_direct_target_effect
from .intents import ExilePermanentIntent, IntentPlan


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
        fields = validate_direct_target_effect(
            effect,
            context,
            operation=self.operation,
            reference_field="card",
            family_label="Permanent-exile",
            allow_replacement_selections=True,
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                ExilePermanentIntent(
                    actor=context.actor,
                    object_ref=fields.object_ref,
                    reason=fields.reason,
                    replacement_selections=fields.replacement_selections,
                ),
            ),
        )


PERMANENT_EXILE_HANDLERS = (ExilePermanentHandler(),)


__all__ = ["ExilePermanentHandler", "PERMANENT_EXILE_HANDLERS"]
