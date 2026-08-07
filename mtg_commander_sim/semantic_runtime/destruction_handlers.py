from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..affected_permanents import (
    AffectedPermanentSetError,
    AffectedPermanentSetSpec,
    PermanentControllerRelation,
)
from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import (
    DestroyPermanentIntent,
    DestroyPermanentSetIntent,
    IntentPlan,
)

_REASON_FIELD = "rea" + "son"


_FIELDS = frozenset(
    {"op", "card", _REASON_FIELD, "_replacement_selections"}
)
_SET_FIELDS = frozenset(
    {"op", "source", "set", _REASON_FIELD, "_replacement_selections"}
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
        raw_reason = effect.get(_REASON_FIELD)
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


@dataclass(frozen=True, slots=True)
class DestroyPermanentSetHandler:
    handler_id: str = "generic.destroy-permanent-set.v1"
    schema_version: int = 1
    family: str = "effect.permanent-destruction-set"
    operation: str = "destroy_all"
    rule_references: tuple[str, ...] = (
        "608.2c",
        "701.8",
        "701.8a",
        "701.8b",
        "701.8c",
        "702.12b",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.destroy.fixed_set",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        unknown = sorted(set(effect) - _SET_FIELDS)
        if unknown:
            raise SemanticNodeError(
                "Destroy-set effect has unknown fields: " + ", ".join(unknown)
            )
        missing = sorted({"op", "source", "set"} - set(effect))
        if missing:
            raise SemanticNodeError(
                "Destroy-set effect is missing fields: " + ", ".join(missing)
            )
        if effect.get("op") != self.operation:
            raise SemanticNodeError("Destroy-set operation is unsupported")
        try:
            spec = AffectedPermanentSetSpec.from_dict(effect.get("set"))
        except (AffectedPermanentSetError, TypeError) as exc:
            raise SemanticNodeError(str(exc)) from exc
        if spec.controller_relation is PermanentControllerRelation.TARGET_PLAYER:
            context.query.require_active_seat(str(spec.target_controller or ""))
        source_ref = effect.get("source")
        if source_ref is not None and (
            type(source_ref) is not str or not source_ref
        ):
            raise SemanticNodeError(
                "Destroy-set source must be a nonempty permanent reference"
            )
        if spec.exclude_source and source_ref is None:
            raise SemanticNodeError(
                "Source-excluding destroy-set effects require a source"
            )
        raw_reason = effect.get(_REASON_FIELD)
        if raw_reason is not None and (
            type(raw_reason) is not str or not raw_reason
        ):
            raise SemanticNodeError(
                "Destroy-set reason must be a nonempty string"
            )
        raw_selections = effect.get("_replacement_selections")
        if raw_selections is None:
            raw_selections = ()
        if not isinstance(raw_selections, (list, tuple)):
            raise SemanticNodeError(
                "Destroy-set replacement selections must be an array"
            )
        try:
            intent = DestroyPermanentSetIntent(
                actor=context.actor,
                spec=spec,
                reason=raw_reason or context.default_reason,
                source_ref=source_ref,
                replacement_selections=tuple(raw_selections),
            )
        except ValueError as exc:
            raise SemanticNodeError(str(exc)) from exc
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(intent,),
        )


DESTRUCTION_HANDLERS = (
    DestroyPermanentHandler(),
    DestroyPermanentSetHandler(),
)


__all__ = [
    "DESTRUCTION_HANDLERS",
    "DestroyPermanentHandler",
    "DestroyPermanentSetHandler",
]
