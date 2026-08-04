from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any, Mapping

from ..util import stable_json


class AuraRuleError(ValueError):
    """A represented Aura rule value is malformed or unsupported."""


class AuraControllerRelation(str, Enum):
    ANY = "any"
    YOU = "you"
    OPPONENT = "opponent"


_OBJECT_KINDS = frozenset(
    {
        "artifact",
        "battle",
        "creature",
        "enchantment",
        "land",
        "planeswalker",
        "permanent",
        "nonland permanent",
    }
)


@dataclass(frozen=True, slots=True)
class SimpleEnchantSpec:
    """Closed CR 702.5 object grammar supported by the Aura subsystem."""

    object_kind: str
    controller_relation: AuraControllerRelation = AuraControllerRelation.ANY
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AuraRuleError("Unsupported simple Enchant schema version")
        if not isinstance(self.object_kind, str) or not self.object_kind.strip():
            raise AuraRuleError(
                "Simple Enchant object kind must be a nonempty string"
            )
        normalized = " ".join(self.object_kind.casefold().split())
        if normalized not in _OBJECT_KINDS:
            raise AuraRuleError(
                f"Unsupported simple Enchant object kind: {self.object_kind!r}"
            )
        object.__setattr__(self, "object_kind", normalized)
        if not isinstance(self.controller_relation, AuraControllerRelation):
            raise AuraRuleError("Unsupported Enchant controller relation")

    def target_schema(self) -> dict[str, Any]:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "controller": self.controller_relation.value,
            "count": 1,
            "source_exclusion": True,
        }
        if self.object_kind == "permanent":
            schema["permanent"] = True
        elif self.object_kind == "nonland permanent":
            schema.update({"permanent": True, "land": False})
        else:
            schema["types_all"] = [self.object_kind]
        return schema

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "object_kind": self.object_kind,
            "controller_relation": self.controller_relation.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SimpleEnchantSpec":
        expected = {
            "schema_version",
            "object_kind",
            "controller_relation",
        }
        if set(value) != expected:
            missing = sorted(expected - set(value))
            unknown = sorted(set(value) - expected)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if unknown:
                details.append("unknown " + ", ".join(unknown))
            raise AuraRuleError(
                "Malformed simple Enchant value: " + "; ".join(details)
            )
        if type(value["schema_version"]) is not int:
            raise AuraRuleError("Simple Enchant schema version must be an integer")
        if not isinstance(value["object_kind"], str):
            raise AuraRuleError("Simple Enchant object kind must be a string")
        if not isinstance(value["controller_relation"], str):
            raise AuraRuleError(
                "Simple Enchant controller relation must be a string"
            )
        try:
            relation = AuraControllerRelation(value["controller_relation"])
        except ValueError as exc:
            raise AuraRuleError(
                "Unsupported Enchant controller relation"
            ) from exc
        return cls(
            schema_version=value["schema_version"],
            object_kind=value["object_kind"],
            controller_relation=relation,
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            stable_json(self.to_dict()).encode("utf-8")
        ).hexdigest()


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
    spec: SimpleEnchantSpec
    outcome: AuraEntryOutcome
    target_ref: str | None = None
    legal_target_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.spec, SimpleEnchantSpec):
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
    "SimpleEnchantSpec",
]
