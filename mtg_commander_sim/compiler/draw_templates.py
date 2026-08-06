from __future__ import annotations

import re
from typing import Any, Mapping

from .fixed_numbers import FIXED_COUNT_PATTERN, fixed_number


DrawEffectTemplate = tuple[
    str,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]



_DRAW_LIMIT = re.compile(
    r"^(?P<subject>players|each player|each opponent|your opponents|you) "
    r"can['’]t draw(?P<limit> more than one card each turn| cards?)\.?$",
    re.IGNORECASE,
)
_DRAW_DOUBLE = re.compile(
    r"^If you would draw a card, draw two cards instead\.?$",
    re.IGNORECASE,
)


def fixed_draw_effect_template(text: str) -> DrawEffectTemplate | None:
    """Lower closed mandatory and optional fixed-count draw instructions."""

    normalized = text.strip()
    if re.fullmatch(
        r"draw a card and reveal it\. if it isn['’]t a land card, "
        r"discard it\.?",
        normalized,
        re.IGNORECASE,
    ):
        return (
            "draw-reveal-discard-unless-land-controller-v1",
            (
                {
                    "op": "draw_with_actions",
                    "player": "$controller",
                    "count": 1,
                    "private": True,
                    "post_draw_actions": [
                        {"action": "reveal", "public": True},
                        {
                            "action": "discard_unless_type",
                            "card_type": "land",
                        },
                    ],
                },
            ),
            None,
            ("cr-121-drawing-a-card",),
        )
    match = re.fullmatch(
        rf"you may draw (?P<count>{FIXED_COUNT_PATTERN}) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "optional-draw-controller-v1",
            (
                {
                    "op": "offer_draw",
                    "player": "$controller",
                    "drawer": "$controller",
                    "count": fixed_number(match.group("count")),
                    "private": True,
                },
            ),
            None,
            ("cr-121-drawing-a-card",),
        )
    match = re.fullmatch(
        rf"you may have target player draw (?P<count>{FIXED_COUNT_PATTERN}) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "optional-draw-target-player-by-controller-v1",
            (
                {
                    "op": "offer_draw",
                    "player": "$controller",
                    "drawer": "$target.0",
                    "count": fixed_number(match.group("count")),
                    "private": True,
                },
            ),
            {
                "zones": ["player"],
                "categories": ["player"],
                "player_relation": "any",
                "count": 1,
            },
            ("cr-121-drawing-a-card", "cr-115-targets"),
        )
    match = re.fullmatch(
        rf"(?:you )?draw (?P<count>{FIXED_COUNT_PATTERN}) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "draw-controller-v1",
            (
                {
                    "op": "draw",
                    "player": "$controller",
                    "count": fixed_number(match.group("count")),
                    "private": True,
                },
            ),
            None,
            ("cr-121-drawing-a-card",),
        )
    match = re.fullmatch(
        rf"target (?P<relation>player|opponent) draws "
        rf"(?P<count>{FIXED_COUNT_PATTERN}) "
        r"cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        relation = match.group("relation").casefold()
        return (
            f"draw-target-{relation}-v1",
            (
                {
                    "op": "draw",
                    "player": "$target.0",
                    "count": fixed_number(match.group("count")),
                    "private": True,
                },
            ),
            {
                "zones": ["player"],
                "categories": ["player"],
                "player_relation": (
                    "opponent" if relation == "opponent" else "any"
                ),
                "count": 1,
            },
            ("cr-121-drawing-a-card", "cr-115-targets"),
        )
    match = re.fullmatch(
        rf"each player draws (?P<count>{FIXED_COUNT_PATTERN}) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "draw-each-player-v1",
            (
                {
                    "op": "draw_each_player",
                    "count": fixed_number(match.group("count")),
                },
            ),
            None,
            (
                "cr-121-drawing-a-card",
            ),
        )
    return None


def static_draw_restriction_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower the closed fixed draw-prohibition and max-one wording family."""

    match = _DRAW_LIMIT.fullmatch(text)
    if match is None:
        return None
    subject = match.group("subject").casefold()
    relation = {
        "players": "any",
        "each player": "any",
        "each opponent": "opponent",
        "your opponents": "opponent",
        "you": "source_controller",
    }[subject]
    maximum = 1 if "more than one" in match.group("limit").casefold() else 0
    return (
        f"draw-maximum-{maximum}-{relation.replace('_', '-')}-static-v1",
        {
            "handler_id": "restriction.draw.maximum-per-turn.v1",
            "schema_version": 1,
            "event": "draw.permission",
            "condition": {"affected_player_relation": relation},
            "restriction": {"maximum_per_turn": maximum},
        },
        "zone.draw.library_to_hand",
    )


def static_draw_instruction_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower unconditional controller draw doubling at instruction scope."""

    if _DRAW_DOUBLE.fullmatch(text) is None:
        return None
    return (
        "draw-instruction-double-controller-static-v1",
        {
            "handler_id": "replacement.draw.instruction.multiply.v1",
            "schema_version": 1,
            "event": "draw.instruction",
            "condition": {
                "affected_player_relation": "source_controller",
            },
            "modification": {"factor": 2},
        },
        "zone.draw.library_to_hand",
    )


def static_draw_result_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower draw-doubling wording to an individual result replacement."""

    if _DRAW_DOUBLE.fullmatch(text) is None:
        return None
    return (
        "draw-result-double-controller-static-v1",
        {
            "handler_id": "replacement.draw.result.multiply.v1",
            "schema_version": 1,
            "event": "draw",
            "condition": {
                "affected_player_relation": "source_controller",
            },
            "modification": {"factor": 2},
        },
        "zone.draw.library_to_hand",
    )


__all__ = [
    "fixed_draw_effect_template",
    "static_draw_instruction_handler",
    "static_draw_result_handler",
    "static_draw_restriction_handler",
]
