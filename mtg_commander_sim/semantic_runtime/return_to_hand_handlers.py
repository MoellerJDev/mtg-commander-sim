from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext
from .direct_target_fields import validate_direct_target_effect
from .intents import IntentPlan, ReturnPermanentToOwnerHandIntent


@dataclass(frozen=True, slots=True)
class ReturnPermanentToOwnerHandHandler:
    handler_id: str = "generic.return-permanent-to-owner-hand.v1"
    schema_version: int = 1
    family: str = "effect.permanent-return"
    operation: str = "bounce"
    rule_references: tuple[str, ...] = (
        "108.3",
        "110.2",
        "400.2",
        "400.3",
        "400.6",
        "400.7",
        "608.2c",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.return.owner_hand",
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
            family_label="Return-to-hand",
            allow_replacement_selections=True,
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                ReturnPermanentToOwnerHandIntent(
                    actor=context.actor,
                    object_ref=fields.object_ref,
                    reason=fields.reason,
                    replacement_selections=fields.replacement_selections,
                ),
            ),
        )


RETURN_TO_HAND_HANDLERS = (ReturnPermanentToOwnerHandHandler(),)


__all__ = [
    "RETURN_TO_HAND_HANDLERS",
    "ReturnPermanentToOwnerHandHandler",
]
