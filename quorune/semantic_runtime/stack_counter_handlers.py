from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext
from .direct_target_fields import validate_direct_target_effect
from .intents import CounterStackIntent, IntentPlan


@dataclass(frozen=True, slots=True)
class CounterStackTargetHandler:
    handler_id: str = "generic.counter-stack-target.v1"
    schema_version: int = 1
    family: str = "effect.stack-counter"
    operation: str = "counter_stack_target"
    rule_references: tuple[str, ...] = (
        "115.1",
        "608.2b",
        "701.6",
        "701.6a",
        "701.6b",
    )
    capability_dependencies: tuple[str, ...] = (
        "stack.counter.effect",
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
            reference_field="stack",
            family_label="Counter",
            allow_replacement_selections=False,
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                CounterStackIntent(
                    actor=context.actor,
                    stack_ref=fields.object_ref,
                    reason=fields.reason,
                    countered_by=context.actor,
                ),
            ),
        )


STACK_COUNTER_HANDLERS = (CounterStackTargetHandler(),)


__all__ = ["CounterStackTargetHandler", "STACK_COUNTER_HANDLERS"]
