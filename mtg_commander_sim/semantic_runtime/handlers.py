from __future__ import annotations

from typing import Any, Mapping, Protocol

from .context import ReadOnlyHandlerContext
from .intents import IntentPlan


class SemanticNodeHandler(Protocol):
    """One typed semantic-node family registered under a stable operation."""

    handler_id: str
    schema_version: int
    operation: str
    capability_dependencies: tuple[str, ...]

    def lower(
        self,
        effect: Mapping[str, Any],
        context: ReadOnlyHandlerContext,
    ) -> IntentPlan:
        """Validate a serialized node and lower it to typed intents."""
