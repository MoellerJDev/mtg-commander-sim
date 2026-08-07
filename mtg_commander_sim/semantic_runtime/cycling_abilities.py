from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from ..cycling_abilities import (
    CYCLING_HANDLER_ID,
    CyclingAbilityError,
    OrdinaryCyclingAbilitySpec,
)
from ..rules.capabilities import load_default_capability_registry
from .component_registry import RuntimeComponentRegistry, exact_fields
from .context import SemanticNodeError


@dataclass(frozen=True, slots=True)
class OrdinaryCyclingAbilityHandler:
    handler_id: str = CYCLING_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.activated.cycling"
    event: str = "activate"
    rule_references: tuple[str, ...] = (
        "602.1",
        "602.2",
        "702.29",
        "702.29a",
        "702.29b",
    )
    capability_dependencies: tuple[str, ...] = (
        "activation.cycling.hand",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> OrdinaryCyclingAbilitySpec:
        exact_fields(
            descriptor,
            {"handler_id", "schema_version", "event", "ability"},
            field="ordinary Cycling handler",
        )
        if descriptor["handler_id"] != self.handler_id:
            raise SemanticNodeError("Cycling handler ID mismatch")
        if descriptor["schema_version"] != self.schema_version:
            raise SemanticNodeError(
                "Unsupported ordinary Cycling handler schema version"
            )
        if descriptor["event"] != self.event:
            raise SemanticNodeError(
                "Ordinary Cycling handler must use the activate event"
            )
        ability = descriptor["ability"]
        if not isinstance(ability, Mapping):
            raise SemanticNodeError("Cycling ability must be an object")
        try:
            return OrdinaryCyclingAbilitySpec.from_dict(ability)
        except CyclingAbilityError as exc:
            raise SemanticNodeError(str(exc)) from exc

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[OrdinaryCyclingAbilitySpec, ...]:
        del context
        return (self.validate(descriptor),)


class OrdinaryCyclingAbilityRegistry(
    RuntimeComponentRegistry[object, OrdinaryCyclingAbilitySpec]
):
    pass


@lru_cache(maxsize=1)
def default_ordinary_cycling_ability_registry(
) -> OrdinaryCyclingAbilityRegistry:
    registry = OrdinaryCyclingAbilityRegistry(
        (OrdinaryCyclingAbilityHandler(),)
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()


def ordinary_cycling_specs_from_descriptors(
    descriptors: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[OrdinaryCyclingAbilitySpec, ...]:
    registry = default_ordinary_cycling_ability_registry()
    result: list[OrdinaryCyclingAbilitySpec] = []
    for descriptor in descriptors:
        if registry.describe(str(descriptor.get("handler_id") or "")) is None:
            continue
        result.extend(registry.lower(descriptor, None))
    return tuple(result)


__all__ = [
    "OrdinaryCyclingAbilityHandler",
    "OrdinaryCyclingAbilityRegistry",
    "default_ordinary_cycling_ability_registry",
    "ordinary_cycling_specs_from_descriptors",
]
