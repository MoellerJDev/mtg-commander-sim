from __future__ import annotations

from functools import lru_cache

from ..rules.capabilities import load_default_capability_registry
from .context import (
    ReadOnlyHandlerContext,
    ReadOnlyRulesQuery,
    SemanticNodeError,
)
from .components import (
    describe_runtime_handler,
    runtime_component_inventory,
    runtime_component_registry_fingerprint,
    validate_runtime_handler_descriptors,
)
from .continuous_components import (
    ContinuousEffectComponentRegistry,
    ContinuousEffectSourceContext,
    FixedPowerToughnessAnthemHandler,
    FixedPowerToughnessAnthemNode,
    default_continuous_effect_component_registry,
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
    SetPermanentTappedIntent,
    UntapAllCreaturesIntent,
)
from .interpreter import SemanticInterpreter
from .nodes import (
    BecomeMonarchNode,
    DrawEachPlayerNode,
    DrawNode,
    SetPermanentTappedNode,
    UntapAllCreaturesNode,
)
from .registry import (
    SemanticHandlerRegistry,
    SemanticHandlerRegistryError,
)
from .token_replacements import (
    AdditionalTokenIntent,
    AdditionalTokenReplacementHandler,
    AdditionalTokenReplacementNode,
    TokenCreationReplacementRegistry,
    TokenCreationReplacementContext,
    TokenDefinition,
    default_token_creation_replacement_registry,
)
from .tap_state_handlers import TAP_STATE_HANDLERS


@lru_cache(maxsize=1)
def default_semantic_handler_registry() -> SemanticHandlerRegistry:
    registry = SemanticHandlerRegistry(
        (*GENERIC_HANDLERS, *TAP_STATE_HANDLERS)
    )
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
    "AdditionalTokenIntent",
    "AdditionalTokenReplacementHandler",
    "AdditionalTokenReplacementNode",
    "DrawCardsIntent",
    "DrawEachPlayerNode",
    "DrawNode",
    "DrawResolutionBatch",
    "DrawResolutionRequest",
    "ContinuousEffectComponentRegistry",
    "ContinuousEffectSourceContext",
    "FixedPowerToughnessAnthemHandler",
    "FixedPowerToughnessAnthemNode",
    "IntentPlan",
    "ReadOnlyHandlerContext",
    "ReadOnlyRulesQuery",
    "SetPermanentTappedIntent",
    "SetPermanentTappedNode",
    "SemanticHandlerRegistry",
    "SemanticHandlerRegistryError",
    "SemanticIntentSink",
    "SemanticInterpreter",
    "SemanticNodeHandler",
    "SemanticNodeError",
    "TokenCreationReplacementContext",
    "TokenCreationReplacementRegistry",
    "TokenDefinition",
    "UntapAllCreaturesIntent",
    "UntapAllCreaturesNode",
    "default_token_creation_replacement_registry",
    "default_continuous_effect_component_registry",
    "default_semantic_handler_registry",
    "default_semantic_interpreter",
    "draw_resolution_batch",
    "execute_intent_plan",
    "prepare_draw_resolution",
    "describe_runtime_handler",
    "runtime_component_inventory",
    "runtime_component_registry_fingerprint",
    "validate_runtime_handler_descriptors",
]
