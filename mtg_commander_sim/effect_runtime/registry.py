from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..errors import GameRuleError
from . import (
    damage_modifiers,
    damage_life_and_turns,
    life_effects,
    objects_stack_and_tokens,
    state_and_permissions,
    zones_and_attachments,
)


EffectFunction = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class EffectFamily:
    family_id: str
    operations: frozenset[str]
    apply: EffectFunction


FAMILIES = (
    EffectFamily(
        "state-and-permissions.v1",
        state_and_permissions.OPERATIONS,
        state_and_permissions.apply_effect,
    ),
    EffectFamily(
        "zones-and-attachments.v1",
        zones_and_attachments.OPERATIONS,
        zones_and_attachments.apply_effect,
    ),
    EffectFamily(
        "damage-modifiers.v1",
        damage_modifiers.OPERATIONS,
        damage_modifiers.apply_effect,
    ),
    EffectFamily(
        "damage-life-and-turns.v1",
        damage_life_and_turns.OPERATIONS,
        damage_life_and_turns.apply_effect,
    ),
    EffectFamily(
        "life-effects.v1",
        life_effects.OPERATIONS,
        life_effects.apply_effect,
    ),
    EffectFamily(
        "objects-stack-and-tokens.v1",
        objects_stack_and_tokens.OPERATIONS,
        objects_stack_and_tokens.apply_effect,
    ),
)


_BY_OPERATION: dict[str, EffectFamily] = {}
_FAMILY_MODULES = (
    state_and_permissions,
    zones_and_attachments,
    damage_modifiers,
    damage_life_and_turns,
    life_effects,
    objects_stack_and_tokens,
)
for family, module in zip(FAMILIES, _FAMILY_MODULES, strict=True):
    handler_operations = frozenset(module.HANDLERS)
    if handler_operations != family.operations:
        missing = sorted(family.operations - handler_operations)
        undeclared = sorted(handler_operations - family.operations)
        raise RuntimeError(
            f"Effect family {family.family_id!r} inventory drifted: "
            f"missing handlers={missing!r}; undeclared handlers={undeclared!r}"
        )
    for operation in family.operations:
        if operation in _BY_OPERATION:
            raise RuntimeError(
                f"Effect operation {operation!r} has multiple owners"
            )
        _BY_OPERATION[operation] = family


def dispatch_effect(
    host: Any,
    effect: Mapping[str, Any],
    *,
    actor: str,
    operation: str,
    reason: str,
) -> Any:
    family = _BY_OPERATION.get(operation)
    if family is None:
        raise GameRuleError(f"Unsupported effect operation {operation!r}")
    return family.apply(
        host,
        effect,
        actor=actor,
        operation=operation,
        reason=reason,
    )


def effect_family_inventory() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "family_id": family.family_id,
            "operations": tuple(sorted(family.operations)),
        }
        for family in FAMILIES
    )
