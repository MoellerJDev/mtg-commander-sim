from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import CounterStackIntent, IntentPlan


_FIELDS = frozenset({"op", "stack", "reason"})


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
        unknown = sorted(set(effect) - _FIELDS)
        if unknown:
            raise SemanticNodeError(
                "Counter effect has unknown fields: " + ", ".join(unknown)
            )
        stack_ref = effect.get("stack")
        if not isinstance(stack_ref, str) or not stack_ref:
            raise SemanticNodeError(
                "Counter effects require one nonempty stack reference"
            )
        raw_reason = effect.get("reason")
        if raw_reason is not None and (
            not isinstance(raw_reason, str) or not raw_reason
        ):
            raise SemanticNodeError(
                "Counter effect reason must be a nonempty string"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                CounterStackIntent(
                    actor=context.actor,
                    stack_ref=stack_ref,
                    reason=raw_reason or context.default_reason,
                    countered_by=context.actor,
                ),
            ),
        )


STACK_COUNTER_HANDLERS = (CounterStackTargetHandler(),)


__all__ = ["CounterStackTargetHandler", "STACK_COUNTER_HANDLERS"]
