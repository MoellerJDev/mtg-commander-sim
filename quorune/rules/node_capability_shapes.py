from __future__ import annotations

"""Strict CardProgram node shapes with reviewed capability ownership."""

from typing import Any, Iterable, Mapping, Sequence

from ..compiler.creature_subtypes import canonical_creature_subtype
from ..affected_permanents import (
    AffectedPermanentSetError,
    AffectedPermanentSetSpec,
    PermanentControllerRelation as AffectedControllerRelation,
)
from ..fixed_damage_set_model import (
    FixedDamageSetError,
    FixedDamageSetSpec,
    PermanentControllerRelation,
    PermanentDamageGroup,
    PlayerDamageGroup,
)

_EXILE_MECHANIC = "exile"


_FIXED_DAMAGE_TARGET_SCHEMAS: dict[str, Mapping[str, Any]] = {
    "any_target": {
        "zones": ["player", "battlefield"],
        "categories": ["player", "permanent"],
        "predicate": "damageable",
        "count": 1,
    },
    "creature": {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        "types_any": ["creature"],
        "count": 1,
    },
    "creature_or_planeswalker": {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        "types_any": ["creature", "planeswalker"],
        "count": 1,
    },
    "player_or_planeswalker": {
        "zones": ["player", "battlefield"],
        "categories": ["player", "permanent"],
        "predicate": "player_or_planeswalker",
        "count": 1,
    },
    "opponent_or_planeswalker": {
        "zones": ["player", "battlefield"],
        "categories": ["player", "permanent"],
        "predicate": "player_or_planeswalker",
        "count": 1,
        "player_relation": "opponent",
    },
    "player": {
        "zones": ["player"],
        "categories": ["player"],
        "count": 1,
    },
    "opponent": {
        "zones": ["player"],
        "categories": ["player"],
        "count": 1,
        "player_relation": "opponent",
    },
}
_PLAYER_DAMAGE_DOMAINS = frozenset(
    {
        "any_target",
        "player_or_planeswalker",
        "opponent_or_planeswalker",
        "player",
        "opponent",
    }
)
_PERMANENT_DAMAGE_DOMAINS = frozenset(
    {
        "any_target",
        "creature",
        "creature_or_planeswalker",
        "player_or_planeswalker",
        "opponent_or_planeswalker",
    }
)

_DRAW_TARGET_SCHEMAS: tuple[Mapping[str, Any], ...] = (
    {
        "zones": ["player"],
        "categories": ["player"],
        "player_relation": "any",
        "count": 1,
    },
    {
        "zones": ["player"],
        "categories": ["player"],
        "player_relation": "opponent",
        "count": 1,
    },
)

_TARGETED_TAP_STATE_SCHEMAS: tuple[Mapping[str, Any], ...] = tuple(
    {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        **({"types_any": [kind]} if kind != "permanent" else {}),
        "count": 1,
    }
    for kind in ("artifact", "creature", "land", "permanent")
)
_TARGETED_DESTRUCTION_SCHEMAS: tuple[Mapping[str, Any], ...] = tuple(
    {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        **({"types_any": list(kinds)} if kinds else {}),
        "count": 1,
    }
    for kinds in (
        ("artifact",),
        ("creature",),
        ("enchantment",),
        ("land",),
        (),
        ("artifact", "enchantment"),
        ("creature", "planeswalker"),
    )
)
_TARGETED_RETURN_TO_HAND_SCHEMAS: tuple[Mapping[str, Any], ...] = (
    *tuple(
        {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            **({"types_any": list(kinds)} if kinds else {}),
            "count": 1,
        }
        for kinds in (
            ("artifact",),
            ("creature",),
            ("enchantment",),
            ("land",),
            (),
            ("artifact", "enchantment"),
            ("creature", "planeswalker"),
        )
    ),
    {
        "zones": ["battlefield"],
        "categories": ["permanent"],
        "types_none": ["land"],
        "count": 1,
    },
)
_TARGETED_EXILE_SCHEMAS: tuple[Mapping[str, Any], ...] = tuple(
    dict(schema) for schema in _TARGETED_RETURN_TO_HAND_SCHEMAS
)
_COUNTER_STACK_BASE = {
    "zones": ["stack"],
    "categories": ["spell"],
    "source_exclusion": True,
    "count": 1,
}
_TARGETED_EXPLORE_SCHEMA = {
    "zones": ["battlefield"],
    "categories": ["permanent"],
    "types_any": ["creature"],
    "controller_relation": "you",
    "count": 1,
}
_TARGETED_COUNTER_SCHEMAS: tuple[Mapping[str, Any], ...] = (
    _COUNTER_STACK_BASE,
    {**_COUNTER_STACK_BASE, "types_none": ["creature"]},
    *tuple(
        {**_COUNTER_STACK_BASE, "types_any": list(types)}
        for types in (
            ("creature",),
            ("creature", "planeswalker"),
            ("instant", "sorcery"),
            ("sorcery",),
            ("instant",),
            ("artifact", "enchantment"),
            ("artifact",),
            ("creature", "enchantment"),
            ("artifact", "creature"),
        )
    ),
    *tuple(
        {**_COUNTER_STACK_BASE, "colors_any": list(colors)}
        for colors in (("U",), ("R",), ("G",), ("R", "G"))
    ),
    {**_COUNTER_STACK_BASE, "predicate": "nonblue_spell"},
    {**_COUNTER_STACK_BASE, "colorless": True},
    {
        "zones": ["stack"],
        "categories": ["ability"],
        "source_exclusion": True,
        "predicate": "activated_ability",
        "count": 1,
    },
    {
        "zones": ["stack"],
        "categories": ["ability"],
        "source_exclusion": True,
        "predicate": "triggered_ability",
        "count": 1,
    },
    {
        "zones": ["stack"],
        "categories": ["ability"],
        "source_exclusion": True,
        "count": 1,
    },
    {
        "zones": ["stack"],
        "categories": ["spell", "ability"],
        "source_exclusion": True,
        "count": 1,
    },
)


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def fixed_damage_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed fixed-damage node vocabulary."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if "cr-120-damage" not in mechanics or len(effects) != 1:
        return ()
    effect = effects[0]
    if (
        set(effect) == {"op", "source", "amount", "groups"}
        and effect.get("op") == "damage_fixed_set"
        and effect.get("source") == "$source"
        and _positive_int(effect.get("amount"))
    ):
        try:
            spec = FixedDamageSetSpec.from_dict(
                {"groups": effect.get("groups")}
            )
        except FixedDamageSetError:
            return ()
        targeted = any(
            isinstance(group, PermanentDamageGroup)
            and group.controller_relation
            is PermanentControllerRelation.TARGET_PLAYER
            for group in spec.groups
        )
        expected_target = (
            {
                "zones": ["player"],
                "categories": ["player"],
                "player_relation": "opponent",
                "count": 1,
            }
            if targeted
            else None
        )
        if target_schema != expected_target or (
            targeted and "cr-115-targets" not in mechanics
        ):
            return ()
        dependencies = {
            "damage.amount.positive",
            "damage.batch.fixed_set",
        }
        if any(isinstance(group, PlayerDamageGroup) for group in spec.groups):
            dependencies.add("damage.result.player_life")
        if any(
            isinstance(group, PermanentDamageGroup) for group in spec.groups
        ):
            dependencies.add("damage.result.multitype_permanent")
        if targeted:
            dependencies.add("target.revalidate_resolution")
        return tuple(sorted(dependencies))
    if (
        target_schema is None
        and set(effect) == {"op", "source", "amount"}
        and effect.get("op") == "damage_each_opponent"
        and effect.get("source") == "$source"
        and _positive_int(effect.get("amount"))
    ):
        return (
            "damage.amount.positive",
            "damage.result.player_life",
        )
    if (
        "cr-115-targets" not in mechanics
        or set(effect) != {"op", "source", "target", "amount"}
        or effect.get("op") != "damage"
        or effect.get("source") != "$source"
        or effect.get("target") != "$target.0"
        or not _positive_int(effect.get("amount"))
    ):
        return ()
    schema = dict(target_schema or {})
    domain = next(
        (
            name
            for name, expected in _FIXED_DAMAGE_TARGET_SCHEMAS.items()
            if schema == expected
        ),
        None,
    )
    if domain is None:
        return ()
    dependencies = {"damage.amount.positive"}
    if domain in _PLAYER_DAMAGE_DOMAINS:
        dependencies.add("damage.result.player_life")
    if domain in _PERMANENT_DAMAGE_DOMAINS:
        dependencies.add("damage.result.multitype_permanent")
    dependencies.add(
        "target.public.player_or_damageable_permanent"
        if domain == "any_target"
        else "target.revalidate_resolution"
    )
    return tuple(sorted(dependencies))


def fixed_draw_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return the draw capability only for the closed fixed-count grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if "cr-121-drawing-a-card" not in mechanics or len(effects) != 1:
        return ()
    effect = effects[0]
    operation = effect.get("op")
    if operation == "draw_with_actions":
        expected_actions = [
            {"action": "reveal", "public": True},
            {
                "action": "discard_unless_type",
                "card_type": "land",
            },
        ]
        if (
            target_schema is None
            and set(effect)
            == {
                "op",
                "player",
                "count",
                "private",
                "post_draw_actions",
            }
            and effect.get("player") == "$controller"
            and effect.get("count") == 1
            and type(effect.get("count")) is int
            and effect.get("private") is True
            and effect.get("post_draw_actions") == expected_actions
        ):
            return ("zone.draw.specifically_drawn_card_actions",)
        return ()
    if (
        target_schema is None
        and operation == "draw_each_player"
        and set(effect) == {"op", "count"}
        and _positive_int(effect.get("count"))
    ):
        return ("zone.draw.library_to_hand",)
    if operation not in {"draw", "offer_draw"}:
        return ()
    expected_fields = (
        {"op", "player", "count", "private"}
        if operation == "draw"
        else {"op", "player", "drawer", "count", "private"}
    )
    if (
        set(effect) != expected_fields
        or not _positive_int(effect.get("count"))
        or effect.get("private") is not True
    ):
        return ()
    player = effect.get("player")
    drawer = effect.get("drawer", player)
    if player == "$controller" and drawer == "$controller":
        return (
            ("zone.draw.library_to_hand",)
            if target_schema is None
            else ()
        )
    if (
        (
            (operation == "draw" and player == "$target.0")
            or (operation == "offer_draw" and player == "$controller")
        )
        and drawer == "$target.0"
        and dict(target_schema or {}) in _DRAW_TARGET_SCHEMAS
        and "cr-115-targets" in mechanics
    ):
        return (
            "target.revalidate_resolution",
            "zone.draw.library_to_hand",
        )
    return ()


def single_explore_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for one permanent exploring once."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if "ex" + "plore" not in mechanics or len(effects) != 1:
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "player", "card"}
        or effect.get("op") != "ex" + "plore"
    ):
        return ()
    if (
        target_schema is None
        and effect.get("player") == "$source.controller"
        and effect.get("card") == "$source"
    ):
        return ("keyword_action.explore.single",)
    if (
        "cr-115-targets" in mechanics
        and dict(target_schema or {}) == _TARGETED_EXPLORE_SCHEMA
        and effect.get("player") == "$target.controller.0"
        and effect.get("card") == "$target.0"
    ):
        return (
            "keyword_action.explore.single",
            "target.revalidate_resolution",
        )
    return ()


def single_proliferate_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return the capability for one unmodified Proliferate instruction."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        "proliferate" not in mechanics
        or target_schema is not None
        or len(effects) != 1
        or dict(effects[0]) != {"op": "proliferate"}
    ):
        return ()
    return ("counter.producer.proliferate",)


def targeted_tap_state_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the direct targeted tap-state grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        not {"tap-and-untap", "cr-115-targets"}.issubset(mechanics)
        or len(effects) != 1
        or dict(target_schema or {}) not in _TARGETED_TAP_STATE_SCHEMAS
    ):
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "card"}
        or effect.get("op") not in {"tap", "untap"}
        or effect.get("card") != "$target.0"
    ):
        return ()
    return (
        (
            "permanent.tap.effect"
            if effect["op"] == "tap"
            else "permanent.untap.effect"
        ),
        "target.revalidate_resolution",
    )


def targeted_destruction_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed direct destruction grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        not {"destroy", "cr-115-targets"}.issubset(mechanics)
        or len(effects) != 1
        or dict(target_schema or {}) not in _TARGETED_DESTRUCTION_SCHEMAS
    ):
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "card"}
        or effect.get("op") != "destroy"
        or effect.get("card") != "$target.0"
    ):
        return ()
    return (
        "permanent.destroy.effect",
        "target.revalidate_resolution",
    )


def mass_destruction_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed fixed-set destruction grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if not {"destroy", "destroy-fixed-set"}.issubset(mechanics) or len(effects) != 1:
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "source", "set"}
        or effect.get("op") != "destroy_all"
        or effect.get("source") != "$source"
    ):
        return ()
    try:
        spec = AffectedPermanentSetSpec.from_dict(effect["set"])
    except (AffectedPermanentSetError, KeyError, TypeError):
        return ()
    targeted = spec.controller_relation is AffectedControllerRelation.TARGET_PLAYER
    schema = dict(target_schema or {})
    valid_player_schemas = (
        {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
            "player_relation": "any",
        },
        {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
            "player_relation": "opponent",
        },
    )
    if targeted:
        if "cr-115-targets" not in mechanics or schema not in valid_player_schemas:
            return ()
        if spec.target_controller != "$target.0":
            return ()
        return (
            "permanent.destroy.fixed_set",
            "target.revalidate_resolution",
        )
    if target_schema is not None or "cr-115-targets" in mechanics:
        return ()
    return ("permanent.destroy.fixed_set",)


def targeted_return_to_hand_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed direct battlefield grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        not {"return-to-owner-hand", "cr-115-targets"}.issubset(mechanics)
        or len(effects) != 1
        or dict(target_schema or {}) not in _TARGETED_RETURN_TO_HAND_SCHEMAS
    ):
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "card"}
        or effect.get("op") != "bounce"
        or effect.get("card") != "$target.0"
    ):
        return ()
    return (
        "permanent.return.owner_hand",
        "target.revalidate_resolution",
    )


def targeted_exile_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed direct permanent exile."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        not {_EXILE_MECHANIC, "cr-115-targets"}.issubset(mechanics)
        or len(effects) != 1
        or dict(target_schema or {}) not in _TARGETED_EXILE_SCHEMAS
    ):
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "card"}
        or effect.get("op") != "exile_permanent"
        or effect.get("card") != "$target.0"
    ):
        return ()
    return (
        "permanent.exile.effect",
        "target.revalidate_resolution",
    )


def targeted_counter_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for the closed direct stack-counter grammar."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if (
        not {"counter", "cr-115-targets"}.issubset(mechanics)
        or len(effects) != 1
        or dict(target_schema or {}) not in _TARGETED_COUNTER_SCHEMAS
    ):
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "stack"}
        or effect.get("op") != "counter_stack_target"
        or effect.get("stack") != "$target.0"
    ):
        return ()
    return (
        "stack.counter.effect",
        "target.revalidate_resolution",
    )


def _fixed_counter_target_schema_is_closed(
    target_schema: Mapping[str, Any] | None,
) -> bool:
    if target_schema is None:
        return False
    schema = dict(target_schema)
    allowed = {
        "zones",
        "categories",
        "count",
        "types_any",
        "subtypes_any",
        "controller_relation",
        "source_exclusion",
    }
    if set(schema) - allowed or (
        schema.get("zones") != ["battlefield"]
        or schema.get("categories") != ["permanent"]
        or type(schema.get("count")) is not int
        or schema.get("count") != 1
    ):
        return False
    types = schema.get("types_any", ())
    subtypes = schema.get("subtypes_any", ())
    if types and subtypes:
        return False
    if types:
        if not isinstance(types, (list, tuple)) or tuple(types) not in {
            ("artifact",),
            ("battle",),
            ("creature",),
            ("enchantment",),
            ("land",),
            ("planeswalker",),
        }:
            return False
    if subtypes:
        if (
            not isinstance(subtypes, (list, tuple))
            or len(subtypes) != 1
            or canonical_creature_subtype(subtypes[0]) != subtypes[0]
        ):
            return False
    relation = schema.get("controller_relation", "any")
    if relation not in {"any", "you", "opponent"}:
        return False
    if "source_exclusion" in schema and schema["source_exclusion"] is not True:
        return False
    return True


def fixed_counter_placement_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for one closed fixed counter placement."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if "cr-122-counters" not in mechanics or len(effects) != 1:
        return ()
    effect = effects[0]
    if (
        set(effect) != {"op", "card", "counter", "amount", "source"}
        or effect.get("op") != "place_counters"
        or type(effect.get("counter")) is not str
        or not effect.get("counter")
        or type(effect.get("amount")) is not int
        or effect.get("amount", 0) <= 0
        or effect.get("source") != "$source"
    ):
        return ()
    if target_schema is None and effect.get("card") == "$source":
        return ("counter.producer.fixed_effect",)
    if (
        "cr-115-targets" in mechanics
        and effect.get("card") == "$target.0"
        and _fixed_counter_target_schema_is_closed(target_schema)
    ):
        return (
            "counter.producer.fixed_effect",
            "target.revalidate_resolution",
        )
    return ()


def fixed_player_counter_placement_node_capabilities(
    *,
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    mechanic_ids: Iterable[str],
) -> tuple[str, ...]:
    """Return capabilities only for one closed player-counter placement."""

    mechanics = {str(value).casefold() for value in mechanic_ids}
    if "cr-122-counters" not in mechanics or len(effects) != 1:
        return ()
    effect = effects[0]
    subject = effect.get("subjects")
    base_fields = {"op", "subjects", "counter", "amount", "source"}
    expected_fields = (
        base_fields | {"target"} if subject == "target" else base_fields
    )
    if (
        set(effect) != expected_fields
        or effect.get("op") != "place_player_counters"
        or subject
        not in {"controller", "target", "each-player", "each-opponent"}
        or type(effect.get("counter")) is not str
        or not str(effect.get("counter") or "").strip()
        or type(effect.get("amount")) is not int
        or effect.get("amount", 0) <= 0
        or effect.get("source") != "$source"
    ):
        return ()
    if subject != "target":
        return (
            ("counter.producer.fixed_player_effect",)
            if target_schema is None
            else ()
        )
    valid_schemas = (
        {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
        },
        {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
            "player_relation": "opponent",
        },
    )
    if (
        effect.get("target") != "$target.0"
        or "cr-115-targets" not in mechanics
        or dict(target_schema or {}) not in valid_schemas
    ):
        return ()
    return (
        "counter.producer.fixed_player_effect",
        "target.revalidate_resolution",
    )


__all__ = [
    "fixed_damage_node_capabilities",
    "mass_destruction_node_capabilities",
    "fixed_draw_node_capabilities",
    "fixed_counter_placement_node_capabilities",
    "fixed_player_counter_placement_node_capabilities",
    "single_explore_node_capabilities",
    "single_proliferate_node_capabilities",
    "targeted_destruction_node_capabilities",
    "targeted_exile_node_capabilities",
    "targeted_return_to_hand_node_capabilities",
    "targeted_tap_state_node_capabilities",
    "targeted_counter_node_capabilities",
]
