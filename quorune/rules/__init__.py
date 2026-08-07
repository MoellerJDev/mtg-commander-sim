"""Pure rules metadata and dependency-closure components."""

from .capabilities import (
    CAPABILITY_REGISTRY_SCHEMA_VERSION,
    CapabilityClosure,
    CapabilityRegistry,
    CapabilityRegistryError,
    capability_covered_mechanics,
    capability_dependencies_for_node,
    load_default_capability_registry,
)

__all__ = [
    "CAPABILITY_REGISTRY_SCHEMA_VERSION",
    "CapabilityClosure",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "capability_covered_mechanics",
    "capability_dependencies_for_node",
    "load_default_capability_registry",
]
