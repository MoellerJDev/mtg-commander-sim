from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import re
from typing import Any, Iterable, Mapping, TypeAlias

from .enchant_spec import (
    EnchantSpec,
    LinkedGraveyardCreatureEnchantSpec,
    SimpleEnchantSpec,
)
from .util import stable_json


class AbilityFragmentError(ValueError):
    """A typed executable ability fragment is malformed or unsupported."""


class ProtectionQualityKind(str, Enum):
    EVERYTHING = "everything"
    COLOR = "color"
    CARD_TYPE = "card_type"
    SUBTYPE = "subtype"


class CombatKeywordTriggerKind(str, Enum):
    """Closed printed combat keywords whose abilities trigger on blocking."""

    FLANKING = "flanking"
    BUSHIDO = "bushido"


_COLOR_NAMES = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}
_CARD_TYPES = frozenset(
    {
        "artifact",
        "battle",
        "creature",
        "enchantment",
        "instant",
        "kindred",
        "land",
        "planeswalker",
        "sorcery",
    }
)
_CARD_TYPE_QUALITIES = {
    **{value: value for value in _CARD_TYPES},
    **{f"{value}s": value for value in _CARD_TYPES},
}
_SUBTYPE_QUALITIES = {"aura": "aura", "auras": "aura"}


@dataclass(frozen=True, slots=True)
class ProtectionSpec:
    """One closed CR 702.16 protection quality.

    Broader qualities remain unrepresented rather than being inferred from
    display text at runtime.
    """

    quality_kind: ProtectionQualityKind
    quality: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AbilityFragmentError(
                "Unsupported protection fragment schema version"
            )
        if not isinstance(self.quality_kind, ProtectionQualityKind):
            raise AbilityFragmentError("Unsupported protection quality kind")
        if self.quality_kind is ProtectionQualityKind.EVERYTHING:
            if self.quality is not None:
                raise AbilityFragmentError(
                    "Protection from everything cannot carry a quality value"
                )
            return
        if not isinstance(self.quality, str) or not self.quality.strip():
            raise AbilityFragmentError(
                "A protection quality requires a nonempty value"
            )
        normalized = " ".join(self.quality.split())
        if self.quality_kind is ProtectionQualityKind.COLOR:
            normalized = normalized.upper()
            if normalized not in set("WUBRG"):
                raise AbilityFragmentError(
                    "Protection color qualities use Magic color symbols"
                )
        else:
            normalized = normalized.casefold()
            allowed = (
                _CARD_TYPES
                if self.quality_kind is ProtectionQualityKind.CARD_TYPE
                else frozenset(_SUBTYPE_QUALITIES.values())
            )
            if normalized not in allowed:
                raise AbilityFragmentError(
                    f"Unsupported protection quality {self.quality!r}"
                )
        object.__setattr__(self, "quality", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "quality_kind": self.quality_kind.value,
            "quality": self.quality,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ProtectionSpec":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "quality_kind",
            "quality",
        }:
            raise AbilityFragmentError(
                "Protection fragments require schema_version, quality_kind, "
                "and quality"
            )
        if type(value["schema_version"]) is not int:
            raise AbilityFragmentError(
                "Protection fragment schema_version must be an integer"
            )
        if not isinstance(value["quality_kind"], str):
            raise AbilityFragmentError(
                "Protection fragment quality_kind must be a string"
            )
        if value["quality"] is not None and not isinstance(
            value["quality"], str
        ):
            raise AbilityFragmentError(
                "Protection fragment quality must be a string or null"
            )
        try:
            quality_kind = ProtectionQualityKind(value["quality_kind"])
        except ValueError as exc:
            raise AbilityFragmentError(
                "Unsupported protection quality kind"
            ) from exc
        return cls(
            schema_version=value["schema_version"],
            quality_kind=quality_kind,
            quality=value["quality"],
        )

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(
            stable_json(self.to_dict()).encode("utf-8")
        ).hexdigest()


_MANA_KEYS = frozenset({"W", "U", "B", "R", "G", "C", "GENERIC"})


def _mana_pairs(
    value: Mapping[str, Any] | Iterable[tuple[str, int]],
) -> tuple[tuple[str, int], ...]:
    items = value.items() if isinstance(value, Mapping) else value
    normalized: dict[str, int] = {}
    for raw_key, raw_amount in items:
        key = str(raw_key).upper()
        if key not in _MANA_KEYS:
            raise AbilityFragmentError(
                f"Unsupported granted-ability mana key {raw_key!r}"
            )
        if type(raw_amount) is not int or raw_amount < 0:
            raise AbilityFragmentError(
                "Granted-ability mana amounts must be nonnegative integers"
            )
        if raw_amount:
            normalized[key] = raw_amount
    return tuple(sorted(normalized.items()))


def _nonempty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AbilityFragmentError(f"{field} must be a nonempty string")
    return value.strip()


@dataclass(frozen=True, slots=True)
class GrantedActivatedAbilitySpec:
    """A closed executable activated ability granted in layer 6."""

    ability_id: str
    semantic_key: str
    cost_text: str
    effect_text: str
    mana: tuple[tuple[str, int], ...] = ()
    tap_source: bool = False
    sorcery_speed: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AbilityFragmentError(
                "Unsupported granted activated-ability schema version"
            )
        for field in ("ability_id", "semantic_key", "cost_text", "effect_text"):
            object.__setattr__(
                self,
                field,
                _nonempty_string(getattr(self, field), field=field),
            )
        for field in ("tap_source", "sorcery_speed"):
            if type(getattr(self, field)) is not bool:
                raise AbilityFragmentError(f"{field} must be a boolean")
        object.__setattr__(self, "mana", _mana_pairs(self.mana))

    @property
    def mana_bundle(self) -> dict[str, int]:
        return dict(self.mana)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ability_id": self.ability_id,
            "semantic_key": self.semantic_key,
            "cost_text": self.cost_text,
            "effect_text": self.effect_text,
            "mana": self.mana_bundle,
            "tap_source": self.tap_source,
            "sorcery_speed": self.sorcery_speed,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "GrantedActivatedAbilitySpec":
        expected = {
            "schema_version",
            "ability_id",
            "semantic_key",
            "cost_text",
            "effect_text",
            "mana",
            "tap_source",
            "sorcery_speed",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AbilityFragmentError(
                "Granted activated-ability fragments have a closed schema"
            )
        if not isinstance(value["mana"], Mapping):
            raise AbilityFragmentError(
                "Granted activated-ability mana must be an object"
            )
        return cls(
            schema_version=value["schema_version"],
            ability_id=value["ability_id"],
            semantic_key=value["semantic_key"],
            cost_text=value["cost_text"],
            effect_text=value["effect_text"],
            mana=value["mana"],
            tap_source=value["tap_source"],
            sorcery_speed=value["sorcery_speed"],
        )


@dataclass(frozen=True, slots=True)
class GrantedTriggeredAbilitySpec:
    """A closed executable triggered ability granted in layer 6."""

    ability_id: str
    semantic_key: str
    event: str
    label: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AbilityFragmentError(
                "Unsupported granted triggered-ability schema version"
            )
        for field in ("ability_id", "semantic_key", "event", "label"):
            object.__setattr__(
                self,
                field,
                _nonempty_string(getattr(self, field), field=field),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ability_id": self.ability_id,
            "semantic_key": self.semantic_key,
            "event": self.event,
            "label": self.label,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "GrantedTriggeredAbilitySpec":
        expected = {
            "schema_version",
            "ability_id",
            "semantic_key",
            "event",
            "label",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AbilityFragmentError(
                "Granted triggered-ability fragments have a closed schema"
            )
        return cls(**dict(value))


@dataclass(frozen=True, slots=True)
class CombatKeywordTriggerSpec:
    """One executable printed Flanking or Bushido ability instance.

    Multiplicity is intentionally preserved by ``canonical_ability_fragments``:
    each printed or independently granted instance triggers separately.
    """

    kind: CombatKeywordTriggerKind
    amount: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise AbilityFragmentError(
                "Unsupported combat keyword-trigger fragment schema version"
            )
        if not isinstance(self.kind, CombatKeywordTriggerKind):
            raise AbilityFragmentError(
                "Unsupported combat keyword-trigger kind"
            )
        if type(self.amount) is not int or self.amount <= 0:
            raise AbilityFragmentError(
                "Combat keyword-trigger amounts must be positive integers"
            )
        if self.kind is CombatKeywordTriggerKind.FLANKING and self.amount != 1:
            raise AbilityFragmentError("Each Flanking instance has amount 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "amount": self.amount,
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "CombatKeywordTriggerSpec":
        expected = {"schema_version", "kind", "amount"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise AbilityFragmentError(
                "Combat keyword-trigger fragments have a closed schema"
            )
        if not isinstance(value["kind"], str):
            raise AbilityFragmentError(
                "Combat keyword-trigger kind must be a string"
            )
        try:
            kind = CombatKeywordTriggerKind(value["kind"])
        except ValueError as exc:
            raise AbilityFragmentError(
                "Unsupported combat keyword-trigger kind"
            ) from exc
        return cls(
            schema_version=value["schema_version"],
            kind=kind,
            amount=value["amount"],
        )


StaticAbilityFragment: TypeAlias = (
    SimpleEnchantSpec
    | LinkedGraveyardCreatureEnchantSpec
    | ProtectionSpec
    | GrantedActivatedAbilitySpec
    | GrantedTriggeredAbilitySpec
    | CombatKeywordTriggerSpec
)


def ability_fragment_to_dict(
    fragment: StaticAbilityFragment,
) -> dict[str, Any]:
    if isinstance(fragment, SimpleEnchantSpec):
        kind = "enchant"
    elif isinstance(fragment, LinkedGraveyardCreatureEnchantSpec):
        kind = "enchant_linked_graveyard_creature"
    elif isinstance(fragment, ProtectionSpec):
        kind = "protection"
    elif isinstance(fragment, GrantedActivatedAbilitySpec):
        kind = "granted_activated"
    elif isinstance(fragment, GrantedTriggeredAbilitySpec):
        kind = "granted_triggered"
    elif isinstance(fragment, CombatKeywordTriggerSpec):
        kind = "combat_keyword_trigger"
    else:
        raise AbilityFragmentError(
            f"Unsupported ability fragment {type(fragment).__name__}"
        )
    return {"kind": kind, "value": fragment.to_dict()}


def ability_fragment_from_dict(
    value: Mapping[str, Any],
) -> StaticAbilityFragment:
    if not isinstance(value, Mapping) or set(value) != {"kind", "value"}:
        raise AbilityFragmentError(
            "Ability fragments require exactly kind and value"
        )
    if not isinstance(value["kind"], str) or not isinstance(
        value["value"], Mapping
    ):
        raise AbilityFragmentError(
            "Ability fragment kind must be a string and value an object"
        )
    if value["kind"] == "enchant":
        return SimpleEnchantSpec.from_dict(value["value"])
    if value["kind"] == "enchant_linked_graveyard_creature":
        return LinkedGraveyardCreatureEnchantSpec.from_dict(value["value"])
    if value["kind"] == "protection":
        return ProtectionSpec.from_dict(value["value"])
    if value["kind"] == "granted_activated":
        return GrantedActivatedAbilitySpec.from_dict(value["value"])
    if value["kind"] == "granted_triggered":
        return GrantedTriggeredAbilitySpec.from_dict(value["value"])
    if value["kind"] == "combat_keyword_trigger":
        return CombatKeywordTriggerSpec.from_dict(value["value"])
    raise AbilityFragmentError(
        f"Unsupported ability fragment kind {value['kind']!r}"
    )


def canonical_ability_fragments(
    values: Iterable[StaticAbilityFragment | Mapping[str, Any]],
) -> tuple[StaticAbilityFragment, ...]:
    fragments = [
        value
        if isinstance(
            value,
            (
                SimpleEnchantSpec,
                LinkedGraveyardCreatureEnchantSpec,
                ProtectionSpec,
                GrantedActivatedAbilitySpec,
                GrantedTriggeredAbilitySpec,
                CombatKeywordTriggerSpec,
            ),
        )
        else ability_fragment_from_dict(value)
        for value in values
    ]
    keyed = [
        (stable_json(ability_fragment_to_dict(fragment)), fragment)
        for fragment in fragments
    ]
    # Multiplicity is rules-significant for separately granted triggered
    # abilities. Sorting makes construction order canonical without merging
    # two physical grants into one ability.
    return tuple(fragment for _, fragment in sorted(keyed, key=lambda row: row[0]))


def parse_protection_line(line: str) -> tuple[ProtectionSpec, ...] | None:
    """Compile one closed printed protection keyword line.

    Compound qualities are deliberately residual until their Oracle grammar is
    represented explicitly; runtime code never reparses the printed line.
    """

    match = re.fullmatch(
        r"protection from (?P<quality>[^.,]+)\.?",
        " ".join(str(line).strip().split()),
        re.IGNORECASE,
    )
    if match is None:
        return None
    quality = match.group("quality").casefold().strip()
    if " and " in quality or "," in quality:
        return None
    if quality == "everything":
        return (
            ProtectionSpec(ProtectionQualityKind.EVERYTHING),
        )
    if quality in _COLOR_NAMES:
        return (
            ProtectionSpec(
                ProtectionQualityKind.COLOR,
                _COLOR_NAMES[quality],
            ),
        )
    if quality in _CARD_TYPE_QUALITIES:
        return (
            ProtectionSpec(
                ProtectionQualityKind.CARD_TYPE,
                _CARD_TYPE_QUALITIES[quality],
            ),
        )
    if quality in _SUBTYPE_QUALITIES:
        return (
            ProtectionSpec(
                ProtectionQualityKind.SUBTYPE,
                _SUBTYPE_QUALITIES[quality],
            ),
        )
    return None


def enchant_specs(
    fragments: Iterable[StaticAbilityFragment],
) -> tuple[EnchantSpec, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if isinstance(
            fragment,
            (SimpleEnchantSpec, LinkedGraveyardCreatureEnchantSpec),
        )
    )


def protection_specs(
    fragments: Iterable[StaticAbilityFragment],
) -> tuple[ProtectionSpec, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if isinstance(fragment, ProtectionSpec)
    )


def granted_activated_specs(
    fragments: Iterable[StaticAbilityFragment],
) -> tuple[GrantedActivatedAbilitySpec, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if isinstance(fragment, GrantedActivatedAbilitySpec)
    )


def granted_triggered_specs(
    fragments: Iterable[StaticAbilityFragment],
) -> tuple[GrantedTriggeredAbilitySpec, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if isinstance(fragment, GrantedTriggeredAbilitySpec)
    )


def combat_keyword_trigger_specs(
    fragments: Iterable[StaticAbilityFragment],
) -> tuple[CombatKeywordTriggerSpec, ...]:
    return tuple(
        fragment
        for fragment in fragments
        if isinstance(fragment, CombatKeywordTriggerSpec)
    )


__all__ = [
    "AbilityFragmentError",
    "CombatKeywordTriggerKind",
    "CombatKeywordTriggerSpec",
    "GrantedActivatedAbilitySpec",
    "GrantedTriggeredAbilitySpec",
    "ProtectionQualityKind",
    "ProtectionSpec",
    "StaticAbilityFragment",
    "ability_fragment_from_dict",
    "ability_fragment_to_dict",
    "canonical_ability_fragments",
    "combat_keyword_trigger_specs",
    "enchant_specs",
    "granted_activated_specs",
    "granted_triggered_specs",
    "parse_protection_line",
    "protection_specs",
]
