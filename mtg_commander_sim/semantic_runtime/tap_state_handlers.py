from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import (
    IntentPlan,
    SetPermanentTappedIntent,
    UntapAllCreaturesIntent,
)
from .nodes import SetPermanentTappedNode, UntapAllCreaturesNode


_SINGLE_TAP_STATE_FIELDS = frozenset(
    dict(op=None, card=None, reason=None)
)
_AGGREGATE_TAP_STATE_FIELDS = frozenset(dict(op=None, reason=None))
_REASON_FIELD = next(iter(dict(reason=None)))


def _reason(
    effect: Mapping[str, Any], context: ReadOnlyHandlerContext
) -> str:
    return str(effect.get(_REASON_FIELD) or context.default_reason)


def _object_ref(effect: Mapping[str, Any]) -> str:
    value = effect.get("card")
    if not isinstance(value, str) or not value.strip():
        raise SemanticNodeError(
            "Tap-state effects require a nonempty permanent reference"
        )
    return value


def _source_logical_object_id(
    object_ref: str,
    context: ReadOnlyHandlerContext,
) -> str | None:
    source = context.source
    if source is None or source.card_ref != object_ref:
        return None
    return source.logical_object_id


def _require_fields(
    effect: Mapping[str, Any], allowed: frozenset[str]
) -> None:
    unknown = sorted(set(effect) - allowed)
    if unknown:
        raise SemanticNodeError(
            "Tap-state effect has unknown fields: " + ", ".join(unknown)
        )


@dataclass(frozen=True, slots=True)
class TapPermanentHandler:
    handler_id: str = "generic.tap-permanent.v2"
    schema_version: int = 2
    family: str = "permanent.tap_state"
    operation: str = "tap"
    rule_references: tuple[str, ...] = ("701.26", "701.26a")
    capability_dependencies: tuple[str, ...] = (
        "permanent.tap.effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        _require_fields(effect, _SINGLE_TAP_STATE_FIELDS)
        object_ref = _object_ref(effect)
        node = SetPermanentTappedNode(
            object_ref=object_ref,
            tapped=True,
            reason=_reason(effect, context),
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                SetPermanentTappedIntent(
                    object_ref=node.object_ref,
                    actor=context.actor,
                    tapped=node.tapped,
                    reason=node.reason,
                    logical_object_id=_source_logical_object_id(
                        object_ref,
                        context,
                    ),
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class UntapPermanentHandler:
    handler_id: str = "generic.untap-permanent.v2"
    schema_version: int = 2
    family: str = "permanent.tap_state"
    operation: str = "untap"
    rule_references: tuple[str, ...] = (
        "122.1d",
        "701.26",
        "701.26b",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.untap.effect",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        _require_fields(effect, _SINGLE_TAP_STATE_FIELDS)
        object_ref = _object_ref(effect)
        node = SetPermanentTappedNode(
            object_ref=object_ref,
            tapped=False,
            reason=_reason(effect, context),
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                SetPermanentTappedIntent(
                    object_ref=node.object_ref,
                    actor=context.actor,
                    tapped=node.tapped,
                    reason=node.reason,
                    logical_object_id=_source_logical_object_id(
                        object_ref,
                        context,
                    ),
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class UntapAllCreaturesHandler:
    handler_id: str = "generic.untap-all-creatures.v1"
    schema_version: int = 1
    family: str = "permanent.tap_state"
    operation: str = "untap_all_creatures"
    rule_references: tuple[str, ...] = (
        "110.4",
        "122.1d",
        "701.26",
        "701.26b",
        "702.26b",
    )
    capability_dependencies: tuple[str, ...] = (
        "permanent.untap.all_creatures",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        _require_fields(effect, _AGGREGATE_TAP_STATE_FIELDS)
        node = UntapAllCreaturesNode(reason=_reason(effect, context))
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                UntapAllCreaturesIntent(
                    actor=context.actor,
                    reason=node.reason,
                ),
            ),
        )


TAP_STATE_HANDLERS = (
    TapPermanentHandler(),
    UntapPermanentHandler(),
    UntapAllCreaturesHandler(),
)
