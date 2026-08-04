from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..continuous_effect_model import (
    ContinuousEffect,
    ContinuousEffectOrigin,
    ContinuousEffectRelation,
    ContinuousOperation,
    Layer,
)
from ..object_predicate import ObjectQuerySpec
from .component_registry import exact_fields
from .context import SemanticNodeError
from .continuous_components import ContinuousEffectSourceContext


ATTACHED_FIXED_CHARACTERISTICS_HANDLER_ID = (
    "continuous.attached.fixed-characteristics.v1"
)
_TYPE_OPERATIONS = frozenset({"set_types", "add_types", "remove_types"})
_TYPE_FIELDS = frozenset({"supertypes", "card_types", "subtypes"})


@dataclass(frozen=True, slots=True)
class AttachedFixedCharacteristicsNode:
    type_operations: tuple[ContinuousOperation, ...]
    add_abilities: tuple[str, ...]
    remove_abilities: tuple[str, ...]
    add_rules_text: tuple[str, ...]
    power: int
    toughness: int


def _ability_values(value: Any, *, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        type(item) is not str or not item.strip() for item in value
    ):
        raise SemanticNodeError(f"{field} must be a string array")
    result = tuple(item.strip().title() for item in value)
    if len({item.casefold() for item in result}) != len(result):
        raise SemanticNodeError(f"{field} values must be unique")
    return result


def _rules_text_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        type(item) is not str or not item.strip() for item in value
    ):
        raise SemanticNodeError(
            "modifier.add_rules_text must be a string array"
        )
    result = tuple(item.strip() for item in value)
    if len(set(result)) != len(result):
        raise SemanticNodeError(
            "modifier.add_rules_text values must be unique"
        )
    return result


def _type_operations(value: Any) -> tuple[ContinuousOperation, ...]:
    if not isinstance(value, list):
        raise SemanticNodeError("modifier.type_operations must be an array")
    result: list[ContinuousOperation] = []
    for index, candidate in enumerate(value):
        if not isinstance(candidate, Mapping):
            raise SemanticNodeError(
                f"modifier.type_operations[{index}] must be an object"
            )
        exact_fields(
            candidate,
            {"op", "field", "values"},
            field=f"modifier.type_operations[{index}]",
        )
        if candidate["op"] not in _TYPE_OPERATIONS:
            raise SemanticNodeError("Unsupported attached type operation")
        if candidate["field"] not in _TYPE_FIELDS:
            raise SemanticNodeError("Unsupported attached type field")
        try:
            result.append(
                ContinuousOperation(
                    op=str(candidate["op"]),
                    field=str(candidate["field"]),
                    value=candidate["values"],
                )
            )
        except ValueError as exc:
            raise SemanticNodeError(str(exc)) from exc
    return tuple(result)


@dataclass(frozen=True, slots=True)
class AttachedFixedCharacteristicsHandler:
    """CR 611.3 live characteristic effect over the attached object."""

    handler_id: str = ATTACHED_FIXED_CHARACTERISTICS_HANDLER_ID
    schema_version: int = 1
    family: str = "continuous.attached.fixed_characteristics"
    event: str = "characteristics.evaluate"
    rule_references: tuple[str, ...] = (
        "301.5",
        "303.4",
        "604.1",
        "611.3a",
        "611.3b",
        "613.1d",
        "613.1f",
        "613.1g",
        "613.6",
        "701.3c",
    )
    capability_dependencies: tuple[str, ...] = (
        "continuous.attached.fixed_characteristics",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> AttachedFixedCharacteristicsNode:
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
            raise SemanticNodeError(f"{self.handler_id} must handle {self.event}")
        condition = descriptor["condition"]
        if not isinstance(condition, Mapping):
            raise SemanticNodeError("runtime handler condition must be an object")
        exact_fields(condition, {"relation"}, field="runtime handler condition")
        if condition["relation"] != "source_attached_object":
            raise SemanticNodeError(
                "attached characteristics require source_attached_object"
            )

        modifier = descriptor["modifier"]
        if not isinstance(modifier, Mapping):
            raise SemanticNodeError("runtime handler modifier must be an object")
        exact_fields(
            modifier,
            {
                "type_operations",
                "add_abilities",
                "remove_abilities",
                "add_rules_text",
                "power",
                "toughness",
            },
            field="runtime handler modifier",
        )
        power = modifier["power"]
        toughness = modifier["toughness"]
        if type(power) is not int or type(toughness) is not int:
            raise SemanticNodeError(
                "attached power/toughness modifiers must be integers"
            )
        node = AttachedFixedCharacteristicsNode(
            type_operations=_type_operations(modifier["type_operations"]),
            add_abilities=_ability_values(
                modifier["add_abilities"], field="modifier.add_abilities"
            ),
            remove_abilities=_ability_values(
                modifier["remove_abilities"], field="modifier.remove_abilities"
            ),
            add_rules_text=_rules_text_values(modifier["add_rules_text"]),
            power=power,
            toughness=toughness,
        )
        if not (
            node.type_operations
            or node.add_abilities
            or node.remove_abilities
            or node.add_rules_text
            or node.power
            or node.toughness
        ):
            raise SemanticNodeError(
                "attached characteristics require at least one modifier"
            )
        return node

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: ContinuousEffectSourceContext,
    ) -> tuple[ContinuousEffect, ...]:
        node = self.validate(descriptor)
        if context.attached_object is None:
            return ()
        common = {
            "source_id": context.source_object_id,
            "timestamp": context.source_timestamp,
            "origin": ContinuousEffectOrigin.STATIC_ABILITY,
            "relation": ContinuousEffectRelation.SOURCE_ATTACHED_TO_OBJECT,
            "related_object": context.attached_object,
            "applies": ObjectQuerySpec(zones=("battlefield",)),
        }
        effects: list[ContinuousEffect] = []
        if node.type_operations:
            effects.append(
                ContinuousEffect(
                    effect_id=f"{context.source_object_id}:{context.component_id}:4",
                    layer=Layer.TYPE,
                    sublayer="4",
                    operations=node.type_operations,
                    **common,
                )
            )
        ability_operations = (
            *(
                ContinuousOperation("add_ability", ability)
                for ability in node.add_abilities
            ),
            *(
                ContinuousOperation("remove_ability", ability)
                for ability in node.remove_abilities
            ),
            *(
                ContinuousOperation("add_rules_text", line)
                for line in node.add_rules_text
            ),
        )
        if ability_operations:
            effects.append(
                ContinuousEffect(
                    effect_id=f"{context.source_object_id}:{context.component_id}:6",
                    layer=Layer.ABILITY,
                    sublayer="6",
                    operations=ability_operations,
                    **common,
                )
            )
        if node.power or node.toughness:
            effects.append(
                ContinuousEffect(
                    effect_id=f"{context.source_object_id}:{context.component_id}:7c",
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer="7c",
                    operations=(
                        ContinuousOperation(
                            "modify_power_toughness",
                            [node.power, node.toughness],
                        ),
                    ),
                    **common,
                )
            )
        return tuple(effects)


__all__ = [
    "ATTACHED_FIXED_CHARACTERISTICS_HANDLER_ID",
    "AttachedFixedCharacteristicsHandler",
    "AttachedFixedCharacteristicsNode",
]
