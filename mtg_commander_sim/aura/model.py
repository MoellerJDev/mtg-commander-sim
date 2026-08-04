from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ..enchant_spec import (
    AuraControllerRelation,
    AuraRuleError,
    EnchantSpec,
    LinkedGraveyardCreatureEnchantSpec,
    SimpleEnchantSpec,
    enchant_spec_from_dict,
    enchant_spec_to_dict,
)


class AuraEntryOutcome(str, Enum):
    ENTER_ATTACHED = "enter_attached"
    REMAIN_IN_ZONE = "remain_in_zone"
    MOVE_TO_GRAVEYARD = "move_to_graveyard"


@dataclass(frozen=True, slots=True)
class AuraEntryPlan:
    source_object_id: str
    source_logical_object_id: str
    source_zone: str
    controller: str
    spec: EnchantSpec
    outcome: AuraEntryOutcome
    target_ref: str | None = None
    legal_target_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(
            self.spec,
            (SimpleEnchantSpec, LinkedGraveyardCreatureEnchantSpec),
        ):
            raise AuraRuleError("Aura entry plan requires an Enchant spec")
        if not isinstance(self.outcome, AuraEntryOutcome):
            raise AuraRuleError("Aura entry plan requires a typed outcome")
        for field_name in (
            "source_object_id",
            "source_logical_object_id",
            "source_zone",
            "controller",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise AuraRuleError(
                    f"Aura entry plan requires {field_name}"
                )
        if len(self.legal_target_refs) != len(
            set(self.legal_target_refs)
        ):
            raise AuraRuleError("Aura entry candidates must be unique")
        if any(
            not isinstance(ref, str) or not ref
            for ref in self.legal_target_refs
        ):
            raise AuraRuleError(
                "Aura entry candidates must be nonempty object refs"
            )
        if self.outcome is AuraEntryOutcome.ENTER_ATTACHED:
            if not self.target_ref:
                raise AuraRuleError(
                    "An attached Aura entry requires a target"
                )
            if self.target_ref not in self.legal_target_refs:
                raise AuraRuleError(
                    "Aura entry target is not a legal candidate"
                )
        elif self.target_ref is not None:
            raise AuraRuleError(
                "A nonentering Aura plan cannot retain a target"
            )


@dataclass(frozen=True, slots=True)
class AuraZoneMovePreflight:
    destination: str
    entry_plan: AuraEntryPlan | None = None
    remain_in_origin: bool = False


class AuraEntryChoiceRequired(AuraRuleError):
    """A nonspell Aura entry needs its controller's legal choice."""

    def __init__(self, plan: AuraEntryPlan):
        if plan.outcome is not AuraEntryOutcome.REMAIN_IN_ZONE:
            raise AuraRuleError(
                "Aura entry choices require a pending remain-in-zone plan"
            )
        if not plan.legal_target_refs:
            raise AuraRuleError(
                "Aura entry choices require at least one legal target"
            )
        self.plan = plan
        super().__init__("Aura entry requires a legal attachment choice")


__all__ = [
    "AuraControllerRelation",
    "AuraEntryChoiceRequired",
    "AuraEntryOutcome",
    "AuraEntryPlan",
    "AuraRuleError",
    "AuraZoneMovePreflight",
    "EnchantSpec",
    "LinkedGraveyardCreatureEnchantSpec",
    "SimpleEnchantSpec",
    "enchant_spec_from_dict",
    "enchant_spec_to_dict",
]
