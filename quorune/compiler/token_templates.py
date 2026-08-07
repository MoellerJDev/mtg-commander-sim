from __future__ import annotations

import re
from typing import Any, Mapping


_ADDITIONAL_DEFINITION = (
    r"(?P<definition>Treasure token|Food token|Map token|"
    r"1/1 colorless Thopter artifact creature token with flying)"
)
_CREATOR_FRAME = re.compile(
    r"^If you would create one or more "
    r"(?:(?P<quality>Treasure|artifact) )?tokens, instead create those "
    rf"tokens plus an additional {_ADDITIONAL_DEFINITION}\.?$",
    re.IGNORECASE,
)
_CONTROLLED_FRAME = re.compile(
    r"^If one or more (?:(?P<quality>artifact) )?tokens would be created "
    r"under your control, those tokens plus an additional "
    rf"{_ADDITIONAL_DEFINITION} are created instead\.?$",
    re.IGNORECASE,
)

_TOKEN_TREASURE = "Treasure"
_TOKEN_FOOD = "Food"
_TOKEN_MAP = "Map"
_TOKEN_THOPTER = "Thopter"

_TOKEN_DEFINITIONS: dict[str, Mapping[str, Any]] = {
    "treasure token": {
        "name": _TOKEN_TREASURE,
        "type_line": "Token Artifact — Treasure",
        "oracle_text": (
            "{T}, Sacrifice this token: Add one mana of any color."
        ),
    },
    "food token": {
        "name": _TOKEN_FOOD,
        "type_line": "Token Artifact — Food",
        "oracle_text": (
            "{2}, {T}, Sacrifice this token: You gain 3 life."
        ),
    },
    "map token": {
        "name": _TOKEN_MAP,
        "type_line": "Token Artifact — Map",
        "oracle_text": (
            "{1}, {T}, Sacrifice this token: Target creature you control "
            "explores. Activate only as a sorcery."
        ),
    },
    "1/1 colorless thopter artifact creature token with flying": {
        "name": _TOKEN_THOPTER,
        "type_line": "Token Artifact Creature — Thopter",
        "colors": [],
        "power": "1",
        "toughness": "1",
        "keywords": ["Flying"],
    },
}


def static_additional_token_replacement_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower the closed mandatory fixed additional-token wording family."""

    normalized = text.strip()
    match = _CREATOR_FRAME.fullmatch(normalized)
    if match is None:
        match = _CONTROLLED_FRAME.fullmatch(normalized)
    if match is None:
        return None

    quality = str(match.group("quality") or "").casefold()
    definition_key = " ".join(
        match.group("definition").casefold().split()
    )
    definition = _TOKEN_DEFINITIONS.get(definition_key)
    if definition is None:
        return None
    created_types = ["artifact"] if quality == "artifact" else []
    treasure_subtype = _TOKEN_TREASURE.casefold()
    created_subtypes = [treasure_subtype] if quality == treasure_subtype else []
    filter_label = quality or "any"
    token_label = str(definition["name"]).casefold()
    return (
        f"additional-token-fixed-{filter_label}-{token_label}-v1",
        {
            "handler_id": "replacement.token.additional.v2",
            "schema_version": 1,
            "event": "token.create",
            "condition": {
                "event_controller": "source_controller",
                "created_types_all": created_types,
                "created_subtypes_all": created_subtypes,
            },
            "quantity": 1,
            "token": dict(definition),
        },
        "token.creation.additional_replacement",
    )


__all__ = ["static_additional_token_replacement_handler"]
