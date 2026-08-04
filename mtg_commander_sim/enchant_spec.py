from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Any, Mapping, TypeAlias

from .util import stable_json


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

    def target_schema(self, source: Any | None = None) -> dict[str, Any]:
        del source
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

    def linked_target_object_id(self, source: Any) -> str | None:
        del source
        return None

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
        if not isinstance(value, Mapping) or set(value) != expected:
            missing = (
                sorted(expected - set(value))
                if isinstance(value, Mapping)
                else sorted(expected)
            )
            unknown = (
                sorted(set(value) - expected)
                if isinstance(value, Mapping)
                else []
            )
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


@dataclass(frozen=True, slots=True)
class LinkedGraveyardCreatureEnchantSpec:
    """Closed linked Enchant restriction used by reanimating Auras.

    The initial restriction selects a creature card in a graveyard. Once the
    reviewed semantic instruction records the linked physical object, the
    restriction follows only that object on the battlefield. This models the
    rules-bearing transition without reparsing Oracle text or storing a raw
    target-schema override on the Aura.
    """

    link_annotation: str
    controller_relation: AuraControllerRelation = AuraControllerRelation.ANY
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AuraRuleError(
                "Unsupported linked Enchant schema version"
            )
        if (
            not isinstance(self.link_annotation, str)
            or not self.link_annotation.strip()
        ):
            raise AuraRuleError(
                "Linked Enchant requires a nonempty annotation key"
            )
        object.__setattr__(
            self,
            "link_annotation",
            self.link_annotation.strip(),
        )
        if not isinstance(self.controller_relation, AuraControllerRelation):
            raise AuraRuleError("Unsupported Enchant controller relation")

    def linked_target_object_id(self, source: Any) -> str | None:
        annotations = getattr(source, "annotations", None)
        if not isinstance(annotations, Mapping):
            return None
        value = annotations.get(self.link_annotation)
        return str(value) if isinstance(value, str) and value else None

    def target_schema(self, source: Any | None = None) -> dict[str, Any]:
        linked_id = self.linked_target_object_id(source)
        if linked_id is not None:
            return {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "controller": self.controller_relation.value,
                "creature": True,
                "count": 1,
                "source_exclusion": True,
            }
        return {
            "zones": ["graveyard"],
            "categories": ["card"],
            "controller": self.controller_relation.value,
            "creature": True,
            "count": 1,
            "source_exclusion": True,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "link_annotation": self.link_annotation,
            "controller_relation": self.controller_relation.value,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "LinkedGraveyardCreatureEnchantSpec":
        expected = {
            "schema_version",
            "link_annotation",
            "controller_relation",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AuraRuleError(
                "Linked Enchant values require schema_version, "
                "link_annotation, and controller_relation"
            )
        if type(value["schema_version"]) is not int:
            raise AuraRuleError(
                "Linked Enchant schema version must be an integer"
            )
        if not isinstance(value["link_annotation"], str):
            raise AuraRuleError(
                "Linked Enchant annotation key must be a string"
            )
        if not isinstance(value["controller_relation"], str):
            raise AuraRuleError(
                "Linked Enchant controller relation must be a string"
            )
        try:
            relation = AuraControllerRelation(value["controller_relation"])
        except ValueError as exc:
            raise AuraRuleError(
                "Unsupported Enchant controller relation"
            ) from exc
        return cls(
            schema_version=value["schema_version"],
            link_annotation=value["link_annotation"],
            controller_relation=relation,
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            stable_json(self.to_dict()).encode("utf-8")
        ).hexdigest()


EnchantSpec: TypeAlias = (
    SimpleEnchantSpec | LinkedGraveyardCreatureEnchantSpec
)


def enchant_spec_to_dict(spec: EnchantSpec) -> dict[str, Any]:
    if isinstance(spec, SimpleEnchantSpec):
        kind = "simple_object"
    elif isinstance(spec, LinkedGraveyardCreatureEnchantSpec):
        kind = "linked_graveyard_creature"
    else:
        raise AuraRuleError(
            f"Unsupported Enchant spec {type(spec).__name__}"
        )
    return {"kind": kind, "value": spec.to_dict()}


def enchant_spec_from_dict(value: Mapping[str, Any]) -> EnchantSpec:
    if not isinstance(value, Mapping) or set(value) != {"kind", "value"}:
        raise AuraRuleError("Enchant specs require exactly kind and value")
    kind = value["kind"]
    raw = value["value"]
    if not isinstance(kind, str) or not isinstance(raw, Mapping):
        raise AuraRuleError(
            "Enchant spec kind must be a string and value an object"
        )
    if kind == "simple_object":
        return SimpleEnchantSpec.from_dict(raw)
    if kind == "linked_graveyard_creature":
        return LinkedGraveyardCreatureEnchantSpec.from_dict(raw)
    raise AuraRuleError(f"Unsupported Enchant spec kind {kind!r}")


__all__ = [
    "AuraControllerRelation",
    "AuraRuleError",
    "EnchantSpec",
    "LinkedGraveyardCreatureEnchantSpec",
    "SimpleEnchantSpec",
    "enchant_spec_from_dict",
    "enchant_spec_to_dict",
]
