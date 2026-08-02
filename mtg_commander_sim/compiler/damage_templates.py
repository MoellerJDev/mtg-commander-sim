from __future__ import annotations

import re
from typing import Any


_ABILITY_WORD = re.compile(
    r"^(?P<word>[A-Za-z][A-Za-z ']+)\s+[—-]\s+(?P<body>.+)$"
)
_DAMAGE_QUANTITY_REPLACEMENT = re.compile(
    r"^If (?P<source>.+?) would deal "
    r"(?:(?P<damage_kind>combat|noncombat) )?damage to (?P<target>.+?), "
    r"(?:it|that source) deals double that damage"
    r"(?: to (?:that permanent or player|that player|that player or permanent))? "
    r"instead\.?$",
    re.IGNORECASE,
)
_FIXED_DAMAGE_PREVENTION = re.compile(
    r"^If (?P<source>.+?) would deal "
    r"(?:(?P<damage_kind>combat|noncombat) )?damage to (?P<target>.+?), "
    r"prevent (?P<amount>[1-9][0-9]*) of that damage\.?$",
    re.IGNORECASE,
)


def _source_condition(phrase: str) -> tuple[str, list[str]] | None:
    normalized = " ".join(phrase.casefold().split())
    exact = {
        "a source": ("any", []),
        "a source you control": ("source_controller", []),
        "a source an opponent controls": ("opponent", []),
        "a creature": ("any", ["creature"]),
        "an artifact": ("any", ["artifact"]),
    }
    if normalized in exact:
        return exact[normalized]
    controlled = re.fullmatch(
        r"(?:a|an) (?P<kind>[a-z][a-z0-9-]*)(?: source)? you control",
        normalized,
    )
    if controlled:
        return "source_controller", [controlled.group("kind")]
    return None


def _target_condition(
    phrase: str,
) -> tuple[str, list[str], list[str]] | None:
    normalized = " ".join(phrase.casefold().split())
    exact = {
        "a permanent or player": ("any", [], []),
        "a player or permanent": ("any", [], []),
        "an opponent": ("opponent", ["player"], []),
        "you": ("source_controller", ["player"], []),
        "an opponent or a permanent an opponent controls": (
            "opponent",
            [],
            [],
        ),
        "you or a permanent you control": (
            "source_controller",
            [],
            [],
        ),
        "a permanent an opponent controls": (
            "opponent",
            ["permanent"],
            [],
        ),
    }
    if normalized in exact:
        return exact[normalized]
    controlled = re.fullmatch(
        r"(?:a|an) (?:(?P<qualifier>[a-z][a-z0-9-]*) )?"
        r"(?P<kind>creature|planeswalker|battle|permanent) you control",
        normalized,
    )
    if controlled:
        types = [controlled.group("kind")]
        if controlled.group("qualifier"):
            types.append(controlled.group("qualifier"))
        return "source_controller", ["permanent"], types
    ordinary = re.fullmatch(
        r"(?:a|an) (?P<kind>creature|planeswalker|battle|permanent|"
        r"[a-z][a-z0-9-]*)",
        normalized,
    )
    if ordinary:
        kind = ordinary.group("kind")
        return "any", ["permanent"], [kind]
    return None


def static_damage_handler(
    text: str,
) -> tuple[str, dict[str, Any], str] | None:
    """Lower a closed static damage/prevention wording family."""

    ability_word = _ABILITY_WORD.match(text)
    normalized = ability_word.group("body") if ability_word else text
    match = _DAMAGE_QUANTITY_REPLACEMENT.fullmatch(normalized)
    handler_id = "replacement.damage.quantity.v1"
    capability = "damage.replacement.static_quantity"
    modification: dict[str, int] = {"multiplier": 2, "additional": 0}
    template_id = "damage-quantity-double-static-v1"
    if match is None:
        match = _FIXED_DAMAGE_PREVENTION.fullmatch(normalized)
        handler_id = "prevention.damage.fixed.v1"
        capability = "damage.prevention.static_fixed"
        template_id = "damage-prevention-fixed-static-v1"
        if match is None:
            return None
        modification = {"amount": int(match.group("amount"))}
    source = _source_condition(match.group("source"))
    target = _target_condition(match.group("target"))
    if source is None or target is None:
        return None
    source_relation, source_types = source
    target_relation, target_kinds, target_types = target
    damage_kind = match.group("damage_kind")
    return (
        template_id,
        {
            "handler_id": handler_id,
            "schema_version": 1,
            "event": "damage",
            "condition": {
                "source_controller_relation": source_relation,
                "target_controller_relation": target_relation,
                "target_kinds": target_kinds,
                "source_types_all": source_types,
                "target_types_all": target_types,
                "combat": (
                    True
                    if damage_kind and damage_kind.casefold() == "combat"
                    else False
                    if damage_kind
                    else None
                ),
            },
            "modification": modification,
        },
        capability,
    )
