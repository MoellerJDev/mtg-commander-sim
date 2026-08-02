from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Protocol, Sequence

from ..replacement_effects import (
    ReplacementClass,
    ReplacementEffect,
)
from ..rules.capabilities import load_default_capability_registry
from .component_registry import RuntimeComponentRegistry, exact_fields
from .context import SemanticNodeError


_QUANTITY_HANDLER_ID = "replacement.damage.quantity.v1"
_FIXED_PREVENTION_HANDLER_ID = "prevention.damage.fixed.v1"
_RELATIONS = {"any", "source_controller", "opponent"}
_TARGET_KINDS = {"player", "permanent"}


class DamageReplacementHost(Protocol):
    semantics: Any
    active_seats: list[str]

    def _semantic_event_sources(
        self, *, zones: set[str] | None = None
    ) -> list[Any]: ...

    def semantic_program_is_current_trusted(self, program: Any) -> bool: ...


@dataclass(frozen=True, slots=True)
class DamageReplacementCondition:
    source_controller_relation: str
    target_controller_relation: str
    target_kinds: tuple[str, ...]
    source_types_all: tuple[str, ...]
    target_types_all: tuple[str, ...]
    combat: bool | None


@dataclass(frozen=True, slots=True)
class DamageQuantityReplacementNode:
    condition: DamageReplacementCondition
    multiplier: int
    additional: int


@dataclass(frozen=True, slots=True)
class FixedDamagePreventionNode:
    condition: DamageReplacementCondition
    amount: int


@dataclass(frozen=True, slots=True)
class DamageReplacementSourceContext:
    source_ref: str
    source_controller: str
    component_id: str = ""

    def __post_init__(self) -> None:
        if not self.source_ref or not self.source_controller:
            raise SemanticNodeError(
                "Damage replacement sources require a ref and controller"
            )


def _normalized_strings(
    value: Any,
    *,
    field: str,
    allowed: set[str] | None = None,
) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SemanticNodeError(f"{field} must be a list of nonempty strings")
    result = tuple(" ".join(item.casefold().split()) for item in value)
    if len(result) != len(set(result)):
        raise SemanticNodeError(
            f"{field} must remain unique after normalization"
        )
    unknown = sorted(set(result) - allowed) if allowed is not None else []
    if unknown:
        raise SemanticNodeError(
            f"{field} contains unsupported values: {', '.join(unknown)}"
        )
    return result


def _condition(value: Any) -> DamageReplacementCondition:
    if not isinstance(value, Mapping):
        raise SemanticNodeError(
            "Damage replacement condition must be an object"
        )
    exact_fields(
        value,
        {
            "source_controller_relation",
            "target_controller_relation",
            "target_kinds",
            "source_types_all",
            "target_types_all",
            "combat",
        },
        field="damage replacement condition",
    )
    source_relation = str(value["source_controller_relation"])
    target_relation = str(value["target_controller_relation"])
    if source_relation not in _RELATIONS or target_relation not in _RELATIONS:
        raise SemanticNodeError(
            "Damage replacement relations must be any, source_controller, "
            "or opponent"
        )
    combat = value["combat"]
    if combat is not None and type(combat) is not bool:
        raise SemanticNodeError(
            "Damage replacement combat must be a boolean or null"
        )
    return DamageReplacementCondition(
        source_controller_relation=source_relation,
        target_controller_relation=target_relation,
        target_kinds=_normalized_strings(
            value["target_kinds"],
            field="condition.target_kinds",
            allowed=_TARGET_KINDS,
        ),
        source_types_all=_normalized_strings(
            value["source_types_all"],
            field="condition.source_types_all",
        ),
        target_types_all=_normalized_strings(
            value["target_types_all"],
            field="condition.target_types_all",
        ),
        combat=combat,
    )


def _relation_predicate(
    relation: str,
    source_controller: str,
) -> Mapping[str, Any] | None:
    if relation == "any":
        return None
    if relation == "source_controller":
        return {"eq": source_controller}
    return {"not_in": [source_controller, None]}


def _event_conditions(
    condition: DamageReplacementCondition,
    context: DamageReplacementSourceContext,
) -> dict[str, Any]:
    # CR 120.8/614.7a: once prevention reduces the amount to zero, there is no
    # damage event left for another replacement or prevention effect to modify.
    # Unpreventable damage remains positive, so CR 615.12 still applies every
    # applicable prevention effect once without reducing the amount.
    result: dict[str, Any] = {"amount": {"not_in": [0]}}
    source = _relation_predicate(
        condition.source_controller_relation,
        context.source_controller,
    )
    if source is not None:
        result["source_controller"] = source
    target = _relation_predicate(
        condition.target_controller_relation,
        context.source_controller,
    )
    if target is not None:
        result["target_controller"] = target
    if condition.target_kinds:
        result["target_kind"] = {"in": list(condition.target_kinds)}
    if condition.source_types_all:
        result["source_characteristics"] = {
            "contains_all": list(condition.source_types_all)
        }
    if condition.target_types_all:
        result["target_characteristics"] = {
            "contains_all": list(condition.target_types_all)
        }
    if condition.combat is not None:
        result["combat"] = {"eq": condition.combat}
    return result


def _validate_envelope(
    descriptor: Mapping[str, Any],
    *,
    handler_id: str,
) -> None:
    exact_fields(
        descriptor,
        {
            "handler_id",
            "schema_version",
            "event",
            "condition",
            "modification",
        },
        field="runtime handler",
    )
    if descriptor["handler_id"] != handler_id:
        raise SemanticNodeError("Runtime handler ID does not match registry")
    if descriptor["schema_version"] != 1:
        raise SemanticNodeError(f"Unsupported {handler_id} schema version")
    if descriptor["event"] != "damage":
        raise SemanticNodeError(f"{handler_id} must handle damage")


@dataclass(frozen=True, slots=True)
class DamageQuantityReplacementHandler:
    handler_id: str = _QUANTITY_HANDLER_ID
    schema_version: int = 1
    family: str = "replacement.damage.quantity"
    event: str = "damage"
    rule_references: tuple[str, ...] = (
        "120.4b",
        "614.1",
        "614.5",
        "616.1",
        "616.1f",
    )
    capability_dependencies: tuple[str, ...] = (
        "damage.replacement.static_quantity",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> DamageQuantityReplacementNode:
        _validate_envelope(descriptor, handler_id=self.handler_id)
        modification = descriptor["modification"]
        if not isinstance(modification, Mapping):
            raise SemanticNodeError(
                "Damage quantity modification must be an object"
            )
        exact_fields(
            modification,
            {"multiplier", "additional"},
            field="damage quantity modification",
        )
        multiplier = modification["multiplier"]
        additional = modification["additional"]
        if type(multiplier) is not int or multiplier < 1:
            raise SemanticNodeError(
                "Damage multiplier must be a positive integer"
            )
        if type(additional) is not int or additional < 0:
            raise SemanticNodeError(
                "Additional damage must be a nonnegative integer"
            )
        if multiplier == 1 and additional == 0:
            raise SemanticNodeError(
                "A damage replacement must change the amount"
            )
        return DamageQuantityReplacementNode(
            condition=_condition(descriptor["condition"]),
            multiplier=multiplier,
            additional=additional,
        )

    def replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        context: DamageReplacementSourceContext,
    ) -> ReplacementEffect:
        node = self.validate(descriptor)
        operations: list[Mapping[str, Any]] = []
        if node.multiplier != 1:
            operations.append(
                {
                    "op": "multiply",
                    "field": "amount",
                    "factor": node.multiplier,
                }
            )
        if node.additional:
            operations.append(
                {
                    "op": "add",
                    "field": "amount",
                    "amount": node.additional,
                }
            )
        component_id = context.component_id or (
            f"{node.multiplier}x+{node.additional}"
        )
        return ReplacementEffect(
            effect_id=(
                f"{self.handler_id}:{context.source_ref}:{component_id}"
            ),
            source_id=context.source_ref,
            event_kind=self.event,
            replacement_class=ReplacementClass.OTHER,
            conditions=_event_conditions(node.condition, context),
            operations=tuple(operations),
            label=f"{context.source_ref}: change damage amount",
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: DamageReplacementSourceContext,
    ) -> tuple[ReplacementEffect, ...]:
        return (self.replacement_effect(descriptor, context),)


@dataclass(frozen=True, slots=True)
class FixedDamagePreventionHandler:
    handler_id: str = _FIXED_PREVENTION_HANDLER_ID
    schema_version: int = 1
    family: str = "prevention.damage.fixed"
    event: str = "damage"
    rule_references: tuple[str, ...] = (
        "120.4b",
        "615.1",
        "615.6",
        "615.10",
        "615.12",
        "615.12a",
        "616.1",
        "616.1f",
    )
    capability_dependencies: tuple[str, ...] = (
        "damage.prevention.static_fixed",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> FixedDamagePreventionNode:
        _validate_envelope(descriptor, handler_id=self.handler_id)
        modification = descriptor["modification"]
        if not isinstance(modification, Mapping):
            raise SemanticNodeError(
                "Fixed prevention modification must be an object"
            )
        exact_fields(
            modification,
            {"amount"},
            field="fixed prevention modification",
        )
        amount = modification["amount"]
        if type(amount) is not int or amount < 1:
            raise SemanticNodeError(
                "Fixed prevention amount must be a positive integer"
            )
        return FixedDamagePreventionNode(
            condition=_condition(descriptor["condition"]),
            amount=amount,
        )

    def replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        context: DamageReplacementSourceContext,
    ) -> ReplacementEffect:
        node = self.validate(descriptor)
        component_id = context.component_id or str(node.amount)
        return ReplacementEffect(
            effect_id=(
                f"{self.handler_id}:{context.source_ref}:{component_id}"
            ),
            source_id=context.source_ref,
            event_kind=self.event,
            replacement_class=ReplacementClass.OTHER,
            conditions=_event_conditions(node.condition, context),
            operations=({"op": "prevent", "amount": node.amount},),
            label=f"{context.source_ref}: prevent {node.amount} damage",
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: DamageReplacementSourceContext,
    ) -> tuple[ReplacementEffect, ...]:
        return (self.replacement_effect(descriptor, context),)


class DamageReplacementRegistry(
    RuntimeComponentRegistry[
        DamageReplacementSourceContext,
        ReplacementEffect,
    ]
):
    def replacement_effect(
        self,
        descriptor: Mapping[str, Any],
        context: DamageReplacementSourceContext,
    ) -> ReplacementEffect:
        handler = self._handler(descriptor)
        compiler = getattr(handler, "replacement_effect", None)
        if compiler is None:
            raise SemanticNodeError(
                f"Runtime handler {handler.handler_id} cannot compile a "
                "replacement effect"
            )
        return compiler(descriptor, context)


@lru_cache(maxsize=1)
def default_damage_replacement_registry() -> DamageReplacementRegistry:
    registry = DamageReplacementRegistry(
        (
            DamageQuantityReplacementHandler(),
            FixedDamagePreventionHandler(),
        )
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()


def collect_damage_replacement_effects(
    host: DamageReplacementHost,
    *,
    sources: Sequence[Any] | None = None,
    source_zones: Mapping[str, str] | None = None,
) -> tuple[ReplacementEffect, ...]:
    """Compile active source-pinned damage components once per batch."""

    candidates = (
        list(sources)
        if sources is not None
        else host._semantic_event_sources(zones={"battlefield"})
    )
    registry = default_damage_replacement_registry()
    effects: list[ReplacementEffect] = []
    for source in candidates:
        active_zone = (
            source_zones.get(source.object_id, source.zone)
            if source_zones is not None
            else source.zone
        )
        if (
            active_zone != "battlefield"
            or source.phased_out
            or source.controller not in host.active_seats
        ):
            continue
        programs = host.semantics.runtime_handler_programs_for_oracle(
            source.oracle_id,
            active_zone="battlefield",
            event="damage",
        )
        for program in programs:
            if not host.semantic_program_is_current_trusted(program):
                continue
            for descriptor_index, descriptor in enumerate(program.handlers):
                effects.append(
                    registry.replacement_effect(
                        descriptor,
                        DamageReplacementSourceContext(
                            source_ref=source.ref,
                            source_controller=source.controller,
                            component_id=f"{program.key}:{descriptor_index}",
                        ),
                    )
                )
    return tuple(effects)
