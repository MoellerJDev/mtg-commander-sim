from __future__ import annotations

from typing import Any, Mapping

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
