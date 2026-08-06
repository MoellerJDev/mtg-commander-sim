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
_DRAW_REVEAL_FIRST = re.compile(
    r"^(?P<sentence>"
    r"(?:Reveal the first card you draw each turn|"
    r"Reveal the first card you draw on each of your turns|"
    r"You may reveal the first card you draw each turn as you draw it)"
    r"\.)(?:\s+(?P<remainder>.+))?$",
    re.IGNORECASE,
)
_DRAW_REVEAL_LINKED_DRAW = re.compile(
    r"^Whenever you reveal a (?P<quality>basic land|creature) card "
    r"this way, draw a card\.?$",
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
        "zone.draw.result_generated_ordering",
    )


def draw_reveal_line_parts(text: str) -> tuple[str, str] | None:
    """Split only the closed CR 121.9 first-draw reveal grammar."""

    match = _DRAW_REVEAL_FIRST.fullmatch(text.strip())
    if match is None:
        return None
    return match.group("sentence"), str(match.group("remainder") or "")


def static_draw_reveal_handler(
    text: str,
) -> tuple[str, Mapping[str, Any], str] | None:
    """Lower one first-draw reveal policy without interpreting its rider."""

    parts = draw_reveal_line_parts(text)
    if parts is None or parts[1]:
        return None
    sentence = parts[0].casefold()
    optional = sentence.startswith("you may")
    controller_turn = "on each of your turns" in sentence
    return (
        (
            "draw-reveal-first-controller-turn-static-v1"
            if controller_turn
            else "draw-reveal-first-controller-static-v1"
        ),
        {
            "handler_id": "action.draw.reveal-first.v1",
            "schema_version": 1,
            "event": "draw.reveal_as_drawn",
            "condition": {
                "affected_player_relation": "source_controller",
                "turn_relation": (
                    "source_controller_turn" if controller_turn else "any"
                ),
                "draw_ordinal": 1,
            },
            "reveal": {"optional": optional, "public": True},
        },
        "zone.draw.reveal_as_drawn",
    )


def linked_draw_reveal_condition(
    text: str,
) -> tuple[str, Mapping[str, Any]] | None:
    """Lower the two closed source-linked reveal-and-draw conditions."""

    match = _DRAW_REVEAL_LINKED_DRAW.fullmatch(text.strip())
    if match is None:
        return None
    quality = match.group("quality").casefold()
    conditions: list[Mapping[str, Any]] = [
        {
            "field": "reveal_source_object_id",
            "op": "eq",
            "value": "$source.object_id",
        }
    ]
    if quality == "basic land":
        conditions.extend(
            (
                {
                    "field": "revealed_card_types",
                    "op": "contains_any",
                    "value": ["land"],
                },
                {
                    "field": "revealed_card_supertypes",
                    "op": "contains_any",
                    "value": ["basic"],
                },
            )
        )
    else:
        conditions.append(
            {
                "field": "revealed_card_types",
                "op": "contains_any",
                "value": ["creature"],
            }
        )
    return quality.replace(" ", "-"), {"all": conditions}


__all__ = [
    "draw_reveal_line_parts",
    "fixed_draw_effect_template",
    "linked_draw_reveal_condition",
    "static_draw_instruction_handler",
    "static_draw_reveal_handler",
    "static_draw_result_handler",
    "static_draw_restriction_handler",
]
