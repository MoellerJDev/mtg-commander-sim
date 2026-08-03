from __future__ import annotations

import re
from typing import Any, Mapping


PreventionTemplate = tuple[
    str,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]


_DYNAMIC_AMOUNT_TOKEN = chr(120)
_LIFE_CAPTURE = "".join(("li", "fe"))
_SUBJECT_PATTERN = (
    r"any target|target creature(?: you control)?|"
    r"target artifact creature|target legendary creature|you"
)


def _target_schema(phrase: str) -> Mapping[str, Any] | None:
    normalized = phrase.casefold()
    if normalized == "you":
        return None
    if normalized == "any target":
        return {
            "zones": ["player", "battlefield"],
            "categories": ["player", "permanent"],
            "predicate": "damageable",
            "count": 1,
        }
    if normalized in {
        "target creature",
        "target creature you control",
        "target artifact creature",
        "target legendary creature",
    }:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "types_all": ["creature"],
            "count": 1,
        }
        if normalized == "target artifact creature":
            schema["types_all"] = ["artifact", "creature"]
        if normalized == "target creature you control":
            schema["controller"] = "you"
        if normalized == "target legendary creature":
            schema["supertypes_any"] = ["legendary"]
        return schema
    return None


def _amount_value(raw: str) -> int | str:
    return "$x" if raw.casefold() == _DYNAMIC_AMOUNT_TOKEN else int(raw)


def _shield(
    *,
    amount: int | str,
    subject: str,
    aftermath: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {
        "op": "create_damage_prevention_shield",
        "source": "$source",
        "subject": "$controller" if subject == "you" else "$target.0",
        "mode": "amount",
        "amount": amount,
        "duration": "until_end_of_turn",
    }
    if aftermath:
        value["aftermath"] = aftermath
    return value


def _rules(
    target_schema: Mapping[str, Any] | None,
    *extra: str,
) -> tuple[str, ...]:
    return (
        "cr-615-prevention-effects",
        *extra,
        *(("cr-115-targets",) if target_schema is not None else ()),
    )


def _chosen_source_fixed_life(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        rf"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        rf"(?P<subject>{_SUBJECT_PATTERN}) this turn by a source of your choice\. "
        r"you gain (?P<life>\d+) life\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        subject = match.group("subject").casefold()
        target_schema = _target_schema(subject)
        nested = _shield(
            amount=_amount_value(match.group("amount")),
            subject=subject,
            aftermath=[
                {
                    "kind": "gain_life",
                    "player": "$controller",
                    "per_prevented": 0,
                    "fixed_amount": int(match.group(_LIFE_CAPTURE)),
                }
            ],
        )
        return (
            "damage-prevention-chosen-source-fixed-life-v1",
            (
                {
                    "op": "choose_damage_source",
                    "prompt": "Choose the source whose damage will be prevented.",
                    "required_colors": [],
                    "required_types": [],
                    "shield": nested,
                },
            ),
            target_schema,
            _rules(target_schema, "cr-119-life"),
        )
    return None


def _scaled_life_aftermath(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        rf"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        rf"(?P<subject>{_SUBJECT_PATTERN}) this turn\. you gain life equal to "
        r"the damage prevented this way\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        subject = match.group("subject").casefold()
        target_schema = _target_schema(subject)
        return (
            "damage-prevention-life-aftermath-v1",
            (
                _shield(
                    amount=_amount_value(match.group("amount")),
                    subject=subject,
                    aftermath=[
                        {
                            "kind": "gain_life",
                            "player": "$controller",
                            "per_prevented": 1,
                            "fixed_amount": 0,
                        }
                    ],
                ),
            ),
            target_schema,
            _rules(target_schema, "cr-119-life"),
        )
    return None


def _counter_aftermath(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        rf"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        rf"(?P<subject>target creature(?: you control)?) this turn\. for each "
        r"1 damage prevented this way, put a (?P<counter>\+\d+/\+\d+) counter "
        r"on that creature\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        subject = match.group("subject").casefold()
        return (
            "damage-prevention-counter-aftermath-v1",
            (
                _shield(
                    amount=_amount_value(match.group("amount")),
                    subject=subject,
                    aftermath=[
                        {
                            "kind": "place_counters",
                            "subject": "$target.0",
                            "counter_name": match.group("counter"),
                            "placing_player": "$controller",
                            "per_prevented": 1,
                            "fixed_amount": 0,
                        }
                    ],
                ),
            ),
            _target_schema(subject),
            _rules(_target_schema(subject), "cr-122-counters"),
        )
    return None


def _shared_color_creatures(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        r"target creature and each other creature that shares a color with it "
        r"this turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "damage-prevention-shared-color-creatures-v1",
            (
                {
                    "op": "create_damage_prevention_shield",
                    "source": "$source",
                    "selector": {
                        "kind": "shares_color_with",
                        "anchor": "$target.0",
                        "types_all": ["creature"],
                    },
                    "mode": "amount",
                    "amount": _amount_value(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            _target_schema("target creature"),
            ("cr-615-prevention-effects", "cr-115-targets"),
        )
    return None


def _ordinary_shield(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        rf"(?P<subject>{_SUBJECT_PATTERN}) "
        r"this turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        subject = match.group("subject").casefold()
        target_schema = _target_schema(subject)
        return (
            "damage-prevention-fixed-shield-v1",
            (
                {
                    "op": "create_damage_prevention_shield",
                    "source": "$source",
                    "subject": (
                        "$controller" if subject == "you" else "$target.0"
                    ),
                    "mode": "amount",
                    "amount": _amount_value(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            target_schema,
            _rules(target_schema),
        )
    return None


def _self_shield(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+|x) damage that would be dealt to "
        r"(?:it|this (?:artifact|creature|permanent)) this turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "damage-prevention-fixed-shield-self-v1",
            (
                {
                    "op": "create_damage_prevention_shield",
                    "source": "$source",
                    "subject": "$source",
                    "mode": "amount",
                    "amount": _amount_value(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            None,
            ("cr-615-prevention-effects",),
        )
    return None


def _source_shield(normalized: str) -> PreventionTemplate | None:
    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+|x) damage that would be dealt by "
        r"this (?:artifact|creature|permanent) this turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "damage-prevention-fixed-shield-source-v1",
            (
                {
                    "op": "create_damage_prevention_shield",
                    "source": "$source",
                    "subject": "*",
                    "chosen_source": "$source",
                    "mode": "amount",
                    "amount": _amount_value(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            None,
            ("cr-615-prevention-effects",),
        )
    return None


_PREVENTION_PRODUCTIONS = (
    _chosen_source_fixed_life,
    _scaled_life_aftermath,
    _counter_aftermath,
    _shared_color_creatures,
    _ordinary_shield,
    _self_shield,
    _source_shield,
)


def fixed_prevention_effect_template(
    text: str,
) -> PreventionTemplate | None:
    """Lower one closed finite CR 615 sentence through ordered productions."""

    normalized = " ".join(text.strip().split())
    for production in _PREVENTION_PRODUCTIONS:
        result = production(normalized)
        if result is not None:
            return result
    return None
