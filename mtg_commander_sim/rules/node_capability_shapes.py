from __future__ import annotations

"""Strict CardProgram node shapes with reviewed capability ownership."""

from typing import Any, Iterable, Mapping, Sequence


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


__all__ = [
    "fixed_damage_node_capabilities",
    "fixed_draw_node_capabilities",
]
