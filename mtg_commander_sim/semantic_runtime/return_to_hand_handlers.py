from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import IntentPlan, ReturnPermanentToOwnerHandIntent


_FIELDS = frozenset({"op", "card", "reason", "_replacement_selections"})


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
        unknown = sorted(set(effect) - _FIELDS)
        if unknown:
            raise SemanticNodeError(
                "Return-to-hand effect has unknown fields: "
                + ", ".join(unknown)
            )
        object_ref = effect.get("card")
        if not isinstance(object_ref, str) or not object_ref:
            raise SemanticNodeError(
                "Return-to-hand effects require one permanent reference"
            )
        raw_reason = effect.get("reason")
        if raw_reason is not None and (
            not isinstance(raw_reason, str) or not raw_reason
        ):
            raise SemanticNodeError(
                "Return-to-hand effect reason must be a nonempty string"
            )
        raw_selections = effect.get("_replacement_selections")
        if raw_selections is None:
            raw_selections = ()
        if not isinstance(raw_selections, (list, tuple)):
            raise SemanticNodeError(
                "Return replacement selections must be a list"
            )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                ReturnPermanentToOwnerHandIntent(
                    actor=context.actor,
                    object_ref=object_ref,
                    reason=raw_reason or context.default_reason,
                    replacement_selections=tuple(raw_selections),
                ),
            ),
        )


RETURN_TO_HAND_HANDLERS = (ReturnPermanentToOwnerHandHandler(),)


__all__ = [
    "RETURN_TO_HAND_HANDLERS",
    "ReturnPermanentToOwnerHandHandler",
]
