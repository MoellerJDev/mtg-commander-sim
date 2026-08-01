from __future__ import annotations

from functools import lru_cache

from ..rules.capabilities import load_default_capability_registry
from .context import (
    ReadOnlyHandlerContext,
    ReadOnlyRulesQuery,
    SemanticNodeError,
)
from .executor import (
    DrawResolutionBatch,
    DrawResolutionRequest,
    SemanticIntentSink,
    draw_resolution_batch,
    execute_intent_plan,
    prepare_draw_resolution,
)
from .generic import GENERIC_HANDLERS
from .handlers import SemanticNodeHandler
from .intents import (
    BecomeMonarchIntent,
    DrawCardsIntent,
    IntentPlan,
)
from .interpreter import SemanticInterpreter
from .nodes import BecomeMonarchNode, DrawEachPlayerNode, DrawNode
from .registry import (
    SemanticHandlerRegistry,
    SemanticHandlerRegistryError,
)


@lru_cache(maxsize=1)
def default_semantic_handler_registry() -> SemanticHandlerRegistry:
    registry = SemanticHandlerRegistry(GENERIC_HANDLERS)
    capabilities = load_default_capability_registry()
    missing = sorted(
        dependency
        for handler in registry.inventory()
        for dependency in handler["capability_dependencies"]
        if capabilities.capability(dependency) is None
    )
    if missing:
        raise SemanticHandlerRegistryError(
            "Semantic handlers reference unknown capabilities: "
            + ", ".join(missing)
        )
    return registry.freeze()


@lru_cache(maxsize=1)
def default_semantic_interpreter() -> SemanticInterpreter:
    return SemanticInterpreter(default_semantic_handler_registry())


__all__ = [
    "BecomeMonarchIntent",
    "BecomeMonarchNode",
    "DrawCardsIntent",
    "DrawEachPlayerNode",
    "DrawNode",
    "DrawResolutionBatch",
    "DrawResolutionRequest",
    "IntentPlan",
    "ReadOnlyHandlerContext",
    "ReadOnlyRulesQuery",
    "SemanticHandlerRegistry",
    "SemanticHandlerRegistryError",
    "SemanticIntentSink",
    "SemanticInterpreter",
    "SemanticNodeHandler",
    "SemanticNodeError",
    "default_semantic_handler_registry",
    "default_semantic_interpreter",
    "draw_resolution_batch",
    "execute_intent_plan",
    "prepare_draw_resolution",
]
