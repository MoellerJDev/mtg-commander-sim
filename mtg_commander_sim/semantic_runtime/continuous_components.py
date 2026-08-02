from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Protocol

from ..continuous_effects import (
    ContinuousEffect,
    ContinuousOperation,
    Layer,
)
from ..rules.capabilities import load_default_capability_registry
from .component_registry import (
    RuntimeComponentRegistry,
    exact_fields,
    nonempty_strings,
)
from .context import SemanticNodeError


_FIXED_ANTHEM_HANDLER_ID = "continuous.anthem.power_toughness.v1"


@dataclass(frozen=True, slots=True)
class FixedPowerToughnessAnthemNode:
    target_controller: str
    target_subtypes_all: tuple[str, ...]
    power: int
    toughness: int


@dataclass(frozen=True, slots=True)
class ContinuousEffectSourceContext:
    source_object_id: str
    source_ref: str
    source_controller: str
    source_timestamp: int
    component_id: str

    def __post_init__(self) -> None:
        if not self.source_object_id or not self.source_ref:
            raise SemanticNodeError(
                "A continuous component source identity is required"
            )
        if not self.component_id:
            raise SemanticNodeError(
                "A continuous component identity is required"
            )
        if not self.source_controller:
            raise SemanticNodeError(
                "A continuous component source controller is required"
            )
        if self.source_timestamp < 0:
            raise SemanticNodeError(
                "A continuous component source timestamp cannot be negative"
            )


class ContinuousEffectComponentHandler(Protocol):
    handler_id: str
    schema_version: int
    family: str
    event: str
    rule_references: tuple[str, ...]
    capability_dependencies: tuple[str, ...]

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> FixedPowerToughnessAnthemNode: ...

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: ContinuousEffectSourceContext,
    ) -> tuple[ContinuousEffect, ...]: ...


@dataclass(frozen=True, slots=True)
class FixedPowerToughnessAnthemHandler:
    handler_id: str = _FIXED_ANTHEM_HANDLER_ID
    schema_version: int = 1
    family: str = "continuous.fixed_power_toughness_anthem"
    event: str = "characteristics.evaluate"
    rule_references: tuple[str, ...] = (
        "604.1",
        "611.3a",
        "613.1g",
        "613.4c",
    )
    capability_dependencies: tuple[str, ...] = (
        "continuous.power_toughness.fixed_anthem",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> FixedPowerToughnessAnthemNode:
        exact_fields(
            descriptor,
            {
                "handler_id",
                "schema_version",
                "event",
                "condition",
                "modifier",
            },
            field="runtime handler",
        )
        if descriptor["handler_id"] != self.handler_id:
            raise SemanticNodeError("Runtime handler ID does not match registry")
        if descriptor["schema_version"] != self.schema_version:
            raise SemanticNodeError(
                f"Unsupported {self.handler_id} schema version"
            )
        if descriptor["event"] != self.event:
            raise SemanticNodeError(
                f"{self.handler_id} must handle {self.event}"
            )
        condition = descriptor["condition"]
        if not isinstance(condition, Mapping):
            raise SemanticNodeError(
                "runtime handler condition must be an object"
            )
        exact_fields(
            condition,
            {"target_controller", "target_subtypes_all"},
            field="runtime handler condition",
        )
        target_controller = str(condition["target_controller"])
        if target_controller != "source_controller":
            raise SemanticNodeError(
                "fixed anthem currently requires "
                "target_controller=source_controller"
            )
        target_subtypes = tuple(
            subtype.casefold()
            for subtype in nonempty_strings(
                condition["target_subtypes_all"],
                field="condition.target_subtypes_all",
            )
        )
        if not target_subtypes:
            raise SemanticNodeError(
                "fixed anthem requires at least one target subtype"
            )
        modifier = descriptor["modifier"]
        if not isinstance(modifier, Mapping):
            raise SemanticNodeError(
                "runtime handler modifier must be an object"
            )
        exact_fields(
            modifier,
            {"power", "toughness"},
            field="runtime handler modifier",
        )
        power = modifier["power"]
        toughness = modifier["toughness"]
        if type(power) is not int or type(toughness) is not int:
            raise SemanticNodeError(
                "fixed anthem modifiers must be integers"
            )
        if power == 0 and toughness == 0:
            raise SemanticNodeError(
                "fixed anthem must modify power or toughness"
            )
        return FixedPowerToughnessAnthemNode(
            target_controller=target_controller,
            target_subtypes_all=target_subtypes,
            power=power,
            toughness=toughness,
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: ContinuousEffectSourceContext,
    ) -> tuple[ContinuousEffect, ...]:
        node = self.validate(descriptor)
        return (
            ContinuousEffect(
                effect_id=(
                    f"{context.source_object_id}:{context.component_id}"
                ),
                source_id=context.source_object_id,
                layer=Layer.POWER_TOUGHNESS,
                sublayer="7c",
                timestamp=context.source_timestamp,
                operations=(
                    ContinuousOperation(
                        "modify_power_toughness",
                        [node.power, node.toughness],
                    ),
                ),
                applies={
                    "controller": context.source_controller,
                    "subtypes": {
                        "contains_all": list(node.target_subtypes_all)
                    },
                },
            ),
        )


class ContinuousEffectComponentRegistry(
    RuntimeComponentRegistry[
        ContinuousEffectSourceContext,
        ContinuousEffect,
    ]
):
    pass


@lru_cache(maxsize=1)
def default_continuous_effect_component_registry(
) -> ContinuousEffectComponentRegistry:
    registry = ContinuousEffectComponentRegistry(
        (FixedPowerToughnessAnthemHandler(),)
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()
