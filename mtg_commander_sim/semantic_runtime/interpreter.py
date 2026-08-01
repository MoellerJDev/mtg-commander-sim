from __future__ import annotations

from typing import Any, Iterable, Mapping

from .context import ReadOnlyHandlerContext
from .intents import IntentPlan
from .registry import SemanticHandlerRegistry


class SemanticInterpreter:
    """Typed front door with an explicit legacy fallback for unmigrated ops."""

    def __init__(self, registry: SemanticHandlerRegistry):
        self.registry = registry

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan | None:
        return self.registry.lower(effect, context)

    def lower_for_seats(
        self,
        effect: Mapping[str, Any],
        *,
        actor: str,
        default_reason: str,
        seats: Iterable[str],
        active_seats: Iterable[str],
        apnap_order: Iterable[str],
    ) -> IntentPlan | None:
        return self.lower(
            effect,
            ReadOnlyHandlerContext.from_sequences(
                actor=actor,
                default_reason=default_reason,
                seats=seats,
                active_seats=active_seats,
                apnap_order=apnap_order,
            ),
        )
