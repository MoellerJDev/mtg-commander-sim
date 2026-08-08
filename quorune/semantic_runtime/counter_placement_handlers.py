from __future__ import annotations

"""Strict typed lowering for fixed permanent-counter placement effects."""

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .direct_target_fields import validate_direct_target_effect
from .intents import IntentPlan, PlaceCountersIntent


@dataclass(frozen=True, slots=True)
class FixedCounterPlacementHandler:
    handler_id: str = "generic.fixed-counter-placement.v1"
    schema_version: int = 1
    family: str = "effect.counter-placement"
    operation: str = "place_counters"
    rule_references: tuple[str, ...] = (
        "122.1",
        "122.1a",
        "122.6",
        "608.2c",
    )
    capability_dependencies: tuple[str, ...] = (
        "counter.producer.fixed_effect",
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
            family_label="Counter placement",
            allow_replacement_selections=True,
            additional_allowed_fields=("counter", "amount", "source"),
        )
        counter_name = effect.get("counter")
        if type(counter_name) is not str or not counter_name.strip():
            raise SemanticNodeError(
                "Counter placement requires one nonempty counter name"
            )
        amount = effect.get("amount")
        if type(amount) is not int or amount <= 0:
            raise SemanticNodeError(
                "Counter placement amount must be a positive exact integer"
            )
        source_ref = effect.get("source")
        if type(source_ref) is not str or not source_ref:
            raise SemanticNodeError(
                "Counter placement requires one nonempty source reference"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                PlaceCountersIntent(
                    actor=context.actor,
                    object_refs=(fields.object_ref,),
                    counter_name=" ".join(counter_name.casefold().split()),
                    amount=amount,
                    reason=fields.reason,
                    source_ref=source_ref,
                    replacement_selections=fields.replacement_selections,
                ),
            ),
        )


COUNTER_PLACEMENT_HANDLERS = (FixedCounterPlacementHandler(),)


__all__ = [
    "COUNTER_PLACEMENT_HANDLERS",
    "FixedCounterPlacementHandler",
]
