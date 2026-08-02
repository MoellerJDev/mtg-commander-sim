from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .context import ReadOnlyHandlerContext, SemanticNodeError
from .intents import (
    BecomeMonarchIntent,
    DrawCardsIntent,
    IntentPlan,
)
from .nodes import (
    BecomeMonarchNode,
    DrawEachPlayerNode,
    DrawNode,
)


def _count(effect: Mapping[str, Any]) -> int:
    value = effect.get("count", 1)
    if type(value) is not int or value < 0:
        raise SemanticNodeError("Draw count must be a nonnegative integer")
    return value


def _reason(
    effect: Mapping[str, Any], context: ReadOnlyHandlerContext
) -> str:
    return str(effect.get("reason") or context.default_reason)


def _private(effect: Mapping[str, Any]) -> bool:
    value = effect.get("private", False)
    if type(value) is not bool:
        raise SemanticNodeError("Draw private flag must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class DrawHandler:
    handler_id: str = "generic.draw.v1"
    schema_version: int = 1
    family: str = "zone.draw"
    operation: str = "draw"
    rule_references: tuple[str, ...] = ("121.1", "121.2")
    capability_dependencies: tuple[str, ...] = (
        "zone.draw.library_to_hand",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        node = DrawNode(
            player=context.query.require_known_seat(
                str(effect.get("player") or context.actor)
            ),
            count=_count(effect),
            reason=_reason(effect, context),
            private=_private(effect),
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                DrawCardsIntent(
                    player=node.player,
                    count=node.count,
                    reason=node.reason,
                    private=node.private,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class DrawEachPlayerHandler:
    handler_id: str = "generic.draw-each-player.v1"
    schema_version: int = 1
    family: str = "zone.draw"
    operation: str = "draw_each_player"
    rule_references: tuple[str, ...] = ("121.1", "121.2")
    capability_dependencies: tuple[str, ...] = (
        "zone.draw.library_to_hand",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        node = DrawEachPlayerNode(
            count=_count(effect),
            reason=_reason(effect, context),
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=tuple(
                DrawCardsIntent(
                    player=seat,
                    count=node.count,
                    reason=node.reason,
                    private=True,
                )
                for seat in context.query.apnap_order
            ),
            result_shape="by_player",
        )


@dataclass(frozen=True, slots=True)
class BecomeMonarchHandler:
    handler_id: str = "generic.become-monarch.v1"
    schema_version: int = 1
    family: str = "variant.monarch"
    operation: str = "become_monarch"
    rule_references: tuple[str, ...] = ("725.1", "725.2")
    capability_dependencies: tuple[str, ...] = (
        "variant.monarch.designate",
    )

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        node = BecomeMonarchNode(
            player=context.query.require_active_seat(
                str(effect.get("player") or context.actor)
            ),
            reason=_reason(effect, context),
        )
        return IntentPlan(
            operation=self.operation,
            handler_id=self.handler_id,
            intents=(
                BecomeMonarchIntent(
                    player=node.player,
                    reason=node.reason,
                ),
            ),
        )


GENERIC_HANDLERS = (
    DrawHandler(),
    DrawEachPlayerHandler(),
    BecomeMonarchHandler(),
)
