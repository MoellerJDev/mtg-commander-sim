from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


PUBLIC_TARGET_ZONES = {
    "battlefield",
    "stack",
    "graveyard",
    "exile",
    "command",
    "player",
}


LEGACY_SELECTORS: dict[str, dict[str, Any]] = {
    "opponent": {
        "zones": ["player"],
        "categories": ["player"],
        "player_relation": "opponent",
    },
    "blue_spell_or_permanent": {
        "zones": ["stack", "battlefield"],
        "categories": ["spell", "permanent"],
        "colors_any": ["U"],
    },
}


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else bool(value)


@dataclass(frozen=True, slots=True)
class TargetGroup:
    """A declarative target domain and its structural selection constraints."""

    group_id: str = "target"
    zones: tuple[str, ...] = ("battlefield",)
    categories: tuple[str, ...] = ()
    types_any: tuple[str, ...] = ()
    types_all: tuple[str, ...] = ()
    subtypes_any: tuple[str, ...] = ()
    supertypes_any: tuple[str, ...] = ()
    colors_any: tuple[str, ...] = ()
    colors_all: tuple[str, ...] = ()
    colorless: bool | None = None
    mana_value_min: float | None = None
    mana_value_max: float | None = None
    mana_value_equal: float | None = None
    controller_relation: str = "any"
    owner_relation: str = "any"
    player_relation: str = "any"
    attacking: bool | None = None
    blocking: bool | None = None
    tapped: bool | None = None
    commander: bool | None = None
    token: bool | None = None
    land: bool | None = None
    creature: bool | None = None
    artifact: bool | None = None
    enchantment: bool | None = None
    permanent: bool | None = None
    source_exclusion: bool = False
    another: bool = False
    min_targets: int = 1
    max_targets: int = 1
    distinct: bool = True
    allow_reuse: bool = False
    different_from_groups: tuple[str, ...] = ()
    predicate: str = ""
    resolution_condition: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        value: Mapping[str, Any],
        *,
        default_id: str = "target",
    ) -> "TargetGroup":
        raw = dict(value)
        selector = str(raw.pop("selector", "") or "")
        if selector:
            legacy = LEGACY_SELECTORS.get(selector)
            if legacy is None:
                raise ValueError(f"Unknown legacy target selector {selector!r}")
            raw = {**legacy, **raw}
        count = raw.get("count")
        minimum = raw.get("min", raw.get("minimum", count))
        maximum = raw.get("max", raw.get("maximum", count))
        if raw.get("up_to") is not None:
            minimum = 0
            maximum = raw["up_to"]
        minimum = 1 if minimum is None else int(minimum)
        maximum = minimum if maximum is None else int(maximum)
        if minimum < 0 or maximum < minimum:
            raise ValueError("Target count bounds are invalid")
        zones = _strings(raw.get("zones", raw.get("zone", ("battlefield",))))
        unknown_zones = sorted(set(zones) - PUBLIC_TARGET_ZONES)
        if unknown_zones:
            raise ValueError(
                "Target schemas may not enumerate hidden/nonpublic zones: "
                + ", ".join(unknown_zones)
            )
        relation = str(raw.get("controller", raw.get("controller_relation", "any")))
        owner = str(raw.get("owner", raw.get("owner_relation", "any")))
        player_relation = str(raw.get("player_relation", "any"))
        if relation not in {"any", "you", "opponent"}:
            raise ValueError(f"Unknown controller relation {relation!r}")
        if owner not in {"any", "you", "opponent"}:
            raise ValueError(f"Unknown owner relation {owner!r}")
        if player_relation not in {"any", "you", "opponent"}:
            raise ValueError(f"Unknown player relation {player_relation!r}")
        return cls(
            group_id=str(raw.get("id") or raw.get("group") or default_id),
            zones=zones,
            categories=_strings(raw.get("categories", raw.get("category"))),
            types_any=_strings(
                raw.get("types_any", raw.get("card_types", raw.get("type")))
            ),
            types_all=_strings(raw.get("types_all")),
            subtypes_any=_strings(raw.get("subtypes_any", raw.get("subtype"))),
            supertypes_any=_strings(
                raw.get("supertypes_any", raw.get("supertype"))
            ),
            colors_any=tuple(
                color.upper()
                for color in _strings(raw.get("colors_any", raw.get("colors")))
            ),
            colors_all=tuple(
                color.upper() for color in _strings(raw.get("colors_all"))
            ),
            colorless=_optional_bool(raw.get("colorless")),
            mana_value_min=(
                float(raw["mana_value_min"])
                if raw.get("mana_value_min") is not None
                else None
            ),
            mana_value_max=(
                float(raw["mana_value_max"])
                if raw.get("mana_value_max") is not None
                else None
            ),
            mana_value_equal=(
                float(raw["mana_value"])
                if raw.get("mana_value") is not None
                else None
            ),
            controller_relation=relation,
            owner_relation=owner,
            player_relation=player_relation,
            attacking=_optional_bool(raw.get("attacking")),
            blocking=_optional_bool(raw.get("blocking")),
            tapped=_optional_bool(raw.get("tapped")),
            commander=_optional_bool(raw.get("commander")),
            token=_optional_bool(raw.get("token")),
            land=_optional_bool(raw.get("land")),
            creature=_optional_bool(raw.get("creature")),
            artifact=_optional_bool(raw.get("artifact")),
            enchantment=_optional_bool(raw.get("enchantment")),
            permanent=_optional_bool(raw.get("permanent")),
            source_exclusion=bool(raw.get("source_exclusion", False)),
            another=bool(raw.get("another", False)),
            min_targets=minimum,
            max_targets=maximum,
            distinct=bool(raw.get("distinct", True)),
            allow_reuse=bool(raw.get("allow_reuse", False)),
            different_from_groups=_strings(raw.get("different_from_groups")),
            predicate=str(raw.get("predicate") or ""),
            resolution_condition=dict(raw.get("resolution_condition") or {}),
        )

    def public_dict(self, legal_refs: Sequence[str]) -> dict[str, Any]:
        return {
            "id": self.group_id,
            "zones": list(self.zones),
            "categories": list(self.categories),
            "min": self.min_targets,
            "max": self.max_targets,
            "distinct": self.distinct,
            "allow_reuse": self.allow_reuse,
            "different_from_groups": list(self.different_from_groups),
            "legal_refs": list(legal_refs),
        }


@dataclass(frozen=True, slots=True)
class TargetPlan:
    groups: tuple[TargetGroup, ...]
    modes: tuple[str, ...] = ()
    globally_distinct: bool = False


def available_modes(schema: Mapping[str, Any]) -> tuple[str, ...]:
    modes = schema.get("modes")
    if not isinstance(modes, Mapping):
        return ()
    return tuple(str(name) for name in modes)


def target_plan(
    schema: Mapping[str, Any],
    modes: Sequence[str] = (),
    *,
    require_modes: bool = True,
) -> TargetPlan:
    selected_modes = tuple(str(mode) for mode in modes)
    mode_definitions = schema.get("modes")
    raw_groups: list[Mapping[str, Any]] = []
    if isinstance(mode_definitions, Mapping):
        minimum_modes = int(schema.get("min_modes", schema.get("mode_count", 1)))
        maximum_modes = int(schema.get("max_modes", schema.get("mode_count", 1)))
        if require_modes and not (
            minimum_modes <= len(selected_modes) <= maximum_modes
        ):
            raise ValueError(
                f"Action requires between {minimum_modes} and {maximum_modes} mode(s)"
            )
        if len(set(selected_modes)) != len(selected_modes):
            raise ValueError("The same mode cannot be selected twice")
        for mode in selected_modes:
            definition = mode_definitions.get(mode)
            if not isinstance(definition, Mapping):
                raise ValueError(f"Unknown target mode {mode!r}")
            groups = definition.get("groups")
            if groups is None:
                groups = [definition]
            raw_groups.extend(dict(group) for group in groups)
    else:
        groups = schema.get("groups")
        if groups is None:
            groups = [schema]
        raw_groups.extend(dict(group) for group in groups)
    parsed = tuple(
        TargetGroup.from_mapping(group, default_id=f"target_{index}")
        for index, group in enumerate(raw_groups)
    )
    group_ids = [group.group_id for group in parsed]
    if len(set(group_ids)) != len(group_ids):
        raise ValueError("Target group ids must be unique")
    return TargetPlan(
        groups=parsed,
        modes=selected_modes,
        globally_distinct=bool(schema.get("globally_distinct", False)),
    )


def mode_effects(
    schema: Mapping[str, Any],
    modes: Sequence[str],
) -> list[dict[str, Any]]:
    definitions = schema.get("modes")
    if not isinstance(definitions, Mapping):
        return []
    effects: list[dict[str, Any]] = []
    for mode in modes:
        definition = definitions.get(str(mode))
        if isinstance(definition, Mapping):
            effects.extend(dict(effect) for effect in definition.get("effects", []))
    return effects
