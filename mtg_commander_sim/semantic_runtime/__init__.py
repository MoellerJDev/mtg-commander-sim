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
from .counter_replacements import (
    collect_counter_placement_replacement_effects,
    CounterPlacementEventSpec,
    CounterPlacementReplacementRegistry,
    CounterPlacementReplacementResolution,
    CounterQuantityReplacementHandler,
    CounterQuantityReplacementNode,
    CounterReplacementSourceContext,
    default_counter_placement_replacement_registry,
    resolve_counter_placement_replacements,
)
from .damage_replacements import (
    collect_damage_replacement_effects,
    DamageQuantityReplacementHandler,
    DamageQuantityReplacementNode,
    DamageReplacementCondition,
    DamageReplacementRegistry,
    DamageReplacementSourceContext,
    default_damage_replacement_registry,
    FixedDamagePreventionHandler,
    FixedDamagePreventionNode,
)
from .damage_results import (
    collect_damage_result_replacement_effects,
    DamageResultLifeFloorHandler,
    DamageResultLifeFloorNode,
    DamageResultReplacementRegistry,
    DamageResultReplacementSourceContext,
    default_damage_result_replacement_registry,
    LifeGainMultiplierHandler,
    LifeGainMultiplierNode,
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
    TokenCreationReplacementResolution,
    TokenDefinition,
    default_token_creation_replacement_registry,
    resolve_token_creation_replacements,
)
from .tap_state_handlers import TAP_STATE_HANDLERS
from .zone_replacements import (
    collect_zone_change_replacement_effects,
    log_applied_zone_replacements,
    PreparedZoneChange,
    ZoneChangeReplacementContext,
    ZoneChangeReplacementRegistry,
    ZoneChangeReplacementResolution,
    ZoneDestinationIntent,
    ZoneDestinationReplacementHandler,
    ZoneDestinationReplacementNode,
    ZoneReplacementError,
    default_zone_change_replacement_registry,
    resolve_zone_change_replacements,
    prepare_zone_change_replacement,
)


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
    "CounterPlacementEventSpec",
    "CounterPlacementReplacementRegistry",
    "CounterPlacementReplacementResolution",
    "CounterQuantityReplacementHandler",
    "CounterQuantityReplacementNode",
    "CounterReplacementSourceContext",
    "DamageQuantityReplacementHandler",
    "DamageQuantityReplacementNode",
    "DamageReplacementCondition",
    "DamageReplacementRegistry",
    "DamageReplacementSourceContext",
    "DamageResultLifeFloorHandler",
    "DamageResultLifeFloorNode",
    "DamageResultReplacementRegistry",
    "DamageResultReplacementSourceContext",
    "FixedPowerToughnessAnthemHandler",
    "FixedPowerToughnessAnthemNode",
    "FixedDamagePreventionHandler",
    "FixedDamagePreventionNode",
    "LifeGainMultiplierHandler",
    "LifeGainMultiplierNode",
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
    "TokenCreationReplacementResolution",
    "TokenDefinition",
    "UntapAllCreaturesIntent",
    "UntapAllCreaturesNode",
    "ZoneChangeReplacementContext",
    "ZoneChangeReplacementRegistry",
    "ZoneChangeReplacementResolution",
    "ZoneDestinationIntent",
    "ZoneDestinationReplacementHandler",
    "ZoneDestinationReplacementNode",
    "default_token_creation_replacement_registry",
    "default_continuous_effect_component_registry",
    "default_counter_placement_replacement_registry",
    "default_damage_replacement_registry",
    "default_damage_result_replacement_registry",
    "default_semantic_handler_registry",
    "default_semantic_interpreter",
    "default_zone_change_replacement_registry",
    "draw_resolution_batch",
    "execute_intent_plan",
    "prepare_draw_resolution",
    "resolve_token_creation_replacements",
    "resolve_counter_placement_replacements",
    "resolve_zone_change_replacements",
    "collect_zone_change_replacement_effects",
    "collect_counter_placement_replacement_effects",
    "collect_damage_replacement_effects",
    "collect_damage_result_replacement_effects",
    "log_applied_zone_replacements",
    "prepare_zone_change_replacement",
    "PreparedZoneChange",
    "ZoneReplacementError",
    "describe_runtime_handler",
    "runtime_component_inventory",
    "runtime_component_registry_fingerprint",
    "validate_runtime_handler_descriptors",
]
