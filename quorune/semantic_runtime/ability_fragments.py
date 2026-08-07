from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from ..ability_fragments import (
    AbilityFragmentError,
    CombatKeywordTriggerKind,
    CombatKeywordTriggerSpec,
    ProtectionSpec,
    StaticAbilityFragment,
    ability_fragment_from_dict,
)
from ..enchant_spec import SimpleEnchantSpec
from ..enchant_spec import LinkedGraveyardCreatureEnchantSpec
from ..rules.capabilities import load_default_capability_registry
from .component_registry import RuntimeComponentRegistry, exact_fields
from .context import SemanticNodeError


ENCHANT_FRAGMENT_HANDLER_ID = "ability.static.enchant.v1"
LINKED_GRAVEYARD_ENCHANT_HANDLER_ID = (
    "ability.enchant.linked_graveyard_creature.v1"
)
PROTECTION_FRAGMENT_HANDLER_ID = "ability.static.protection.v1"
FLANKING_FRAGMENT_HANDLER_ID = "ability.trigger.flanking.v1"
BUSHIDO_FRAGMENT_HANDLER_ID = "ability.trigger.bushido.v1"
EXALTED_FRAGMENT_HANDLER_ID = "ability.trigger.exalted.v1"
BATTLE_CRY_FRAGMENT_HANDLER_ID = "ability.trigger.battle_cry.v1"
MELEE_FRAGMENT_HANDLER_ID = "ability.trigger.melee.v1"


def _fragment(
    descriptor: Mapping[str, Any],
    *,
    handler_id: str,
    event: str,
    expected_type: type[StaticAbilityFragment],
) -> StaticAbilityFragment:
    exact_fields(
        descriptor,
        {"handler_id", "schema_version", "event", "fragment"},
        field="static ability fragment handler",
    )
    if descriptor["handler_id"] != handler_id:
        raise SemanticNodeError("Static ability fragment handler ID mismatch")
    if descriptor["schema_version"] != 1:
        raise SemanticNodeError(
            f"Unsupported {handler_id} schema version"
        )
    if descriptor["event"] != event:
        raise SemanticNodeError(
            f"{handler_id} must use the {event} event"
        )
    if not isinstance(descriptor["fragment"], Mapping):
        raise SemanticNodeError(
            "Static ability fragment must be an object"
        )
    try:
        fragment = ability_fragment_from_dict(descriptor["fragment"])
    except AbilityFragmentError as exc:
        raise SemanticNodeError(str(exc)) from exc
    if not isinstance(fragment, expected_type):
        raise SemanticNodeError(
            f"{handler_id} carries the wrong typed fragment"
        )
    return fragment


@dataclass(frozen=True, slots=True)
class EnchantAbilityFragmentHandler:
    handler_id: str = ENCHANT_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.static.enchant"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("303.4", "702.5a")
    capability_dependencies: tuple[str, ...] = (
        "attachment.aura.simple_object",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> SimpleEnchantSpec:
        return _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=SimpleEnchantSpec,
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class ProtectionAbilityFragmentHandler:
    handler_id: str = PROTECTION_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.static.protection"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.16", "702.16a")
    capability_dependencies: tuple[str, ...] = (
        "protection.typed.debt",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> ProtectionSpec:
        return _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=ProtectionSpec,
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class LinkedGraveyardEnchantFragmentHandler:
    handler_id: str = LINKED_GRAVEYARD_ENCHANT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.enchant.linked_graveyard_creature"
    event: str = "resolve"
    rule_references: tuple[str, ...] = (
        "303.4",
        "303.4a",
        "303.4f",
        "702.5a",
    )
    capability_dependencies: tuple[str, ...] = ()

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> LinkedGraveyardCreatureEnchantSpec:
        return _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=LinkedGraveyardCreatureEnchantSpec,
        )

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class FlankingAbilityFragmentHandler:
    handler_id: str = FLANKING_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.trigger.flanking"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.25", "702.25a", "702.25b")
    capability_dependencies: tuple[str, ...] = (
        "combat.trigger.flanking",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> CombatKeywordTriggerSpec:
        fragment = _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=CombatKeywordTriggerSpec,
        )
        if fragment.kind is not CombatKeywordTriggerKind.FLANKING:
            raise SemanticNodeError(
                "The Flanking runtime handler requires a Flanking fragment"
            )
        return fragment

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class BushidoAbilityFragmentHandler:
    handler_id: str = BUSHIDO_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.trigger.bushido"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.45", "702.45a", "702.45b")
    capability_dependencies: tuple[str, ...] = (
        "combat.trigger.bushido",
    )

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> CombatKeywordTriggerSpec:
        fragment = _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=CombatKeywordTriggerSpec,
        )
        if fragment.kind is not CombatKeywordTriggerKind.BUSHIDO:
            raise SemanticNodeError(
                "The Bushido runtime handler requires a Bushido fragment"
            )
        return fragment

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class ExaltedAbilityFragmentHandler:
    handler_id: str = EXALTED_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.trigger.exalted"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.83", "702.83a", "702.83b")
    capability_dependencies: tuple[str, ...] = ("combat.trigger.exalted",)

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> CombatKeywordTriggerSpec:
        fragment = _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=CombatKeywordTriggerSpec,
        )
        if fragment.kind is not CombatKeywordTriggerKind.EXALTED:
            raise SemanticNodeError(
                "The Exalted runtime handler requires an Exalted fragment"
            )
        return fragment

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class BattleCryAbilityFragmentHandler:
    handler_id: str = BATTLE_CRY_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.trigger.battle_cry"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.91", "702.91a", "702.91b")
    capability_dependencies: tuple[str, ...] = ("combat.trigger.battle_cry",)

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> CombatKeywordTriggerSpec:
        fragment = _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=CombatKeywordTriggerSpec,
        )
        if fragment.kind is not CombatKeywordTriggerKind.BATTLE_CRY:
            raise SemanticNodeError(
                "The Battle Cry runtime handler requires a Battle Cry fragment"
            )
        return fragment

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


@dataclass(frozen=True, slots=True)
class MeleeAbilityFragmentHandler:
    handler_id: str = MELEE_FRAGMENT_HANDLER_ID
    schema_version: int = 1
    family: str = "ability.trigger.melee"
    event: str = "continuous"
    rule_references: tuple[str, ...] = ("702.121", "702.121a", "702.121b")
    capability_dependencies: tuple[str, ...] = ("combat.trigger.melee",)

    def validate(
        self, descriptor: Mapping[str, Any]
    ) -> CombatKeywordTriggerSpec:
        fragment = _fragment(
            descriptor,
            handler_id=self.handler_id,
            event=self.event,
            expected_type=CombatKeywordTriggerSpec,
        )
        if fragment.kind is not CombatKeywordTriggerKind.MELEE:
            raise SemanticNodeError(
                "The Melee runtime handler requires a Melee fragment"
            )
        return fragment

    def lower(
        self,
        descriptor: Mapping[str, Any],
        context: object,
    ) -> tuple[StaticAbilityFragment, ...]:
        del context
        return (self.validate(descriptor),)


class AbilityFragmentRegistry(
    RuntimeComponentRegistry[object, StaticAbilityFragment]
):
    pass


@lru_cache(maxsize=1)
def default_ability_fragment_registry() -> AbilityFragmentRegistry:
    registry = AbilityFragmentRegistry(
        (
            BattleCryAbilityFragmentHandler(),
            BushidoAbilityFragmentHandler(),
            EnchantAbilityFragmentHandler(),
            ExaltedAbilityFragmentHandler(),
            FlankingAbilityFragmentHandler(),
            LinkedGraveyardEnchantFragmentHandler(),
            MeleeAbilityFragmentHandler(),
            ProtectionAbilityFragmentHandler(),
        )
    )
    registry.require_registered_capabilities(
        load_default_capability_registry()
    )
    return registry.freeze()


def fragments_from_descriptors(
    descriptors: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[StaticAbilityFragment, ...]:
    registry = default_ability_fragment_registry()
    fragments: list[StaticAbilityFragment] = []
    for descriptor in descriptors:
        if registry.describe(str(descriptor.get("handler_id") or "")) is None:
            continue
        fragments.extend(registry.lower(descriptor, None))
    return tuple(fragments)


__all__ = [
    "ENCHANT_FRAGMENT_HANDLER_ID",
    "BUSHIDO_FRAGMENT_HANDLER_ID",
    "BATTLE_CRY_FRAGMENT_HANDLER_ID",
    "EXALTED_FRAGMENT_HANDLER_ID",
    "FLANKING_FRAGMENT_HANDLER_ID",
    "LINKED_GRAVEYARD_ENCHANT_HANDLER_ID",
    "PROTECTION_FRAGMENT_HANDLER_ID",
    "MELEE_FRAGMENT_HANDLER_ID",
    "EnchantAbilityFragmentHandler",
    "BushidoAbilityFragmentHandler",
    "BattleCryAbilityFragmentHandler",
    "ExaltedAbilityFragmentHandler",
    "FlankingAbilityFragmentHandler",
    "LinkedGraveyardEnchantFragmentHandler",
    "MeleeAbilityFragmentHandler",
    "ProtectionAbilityFragmentHandler",
    "AbilityFragmentRegistry",
    "default_ability_fragment_registry",
    "fragments_from_descriptors",
]
