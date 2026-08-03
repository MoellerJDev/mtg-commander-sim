from __future__ import annotations

import re
from typing import Any, Mapping


PreventionTemplate = tuple[
    str,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]


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
    if normalized in {"target creature", "target artifact creature"}:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "types_all": ["creature"],
            "count": 1,
        }
        if normalized == "target artifact creature":
            schema["types_all"] = ["artifact", "creature"]
        return schema
    return None


def fixed_prevention_effect_template(
    text: str,
) -> PreventionTemplate | None:
    """Lower closed, finite CR 615 shield sentences.

    Compound aftermath text, variable quantities, divided multi-target shields,
    source-choice grammar, and combat-only filters intentionally remain
    unresolved until their own typed contracts are available.
    """

    normalized = " ".join(text.strip().split())
    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+) damage that would be dealt to "
        r"(?P<subject>any target|target creature|target artifact creature|you) "
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
                    "amount": int(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            target_schema,
            (
                "cr-615-prevention-effects",
                *(("cr-115-targets",) if target_schema is not None else ()),
            ),
        )

    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+) damage that would be dealt to "
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
                    "amount": int(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            None,
            ("cr-615-prevention-effects",),
        )

    match = re.fullmatch(
        r"prevent the next (?P<amount>\d+) damage that would be dealt by "
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
                    "amount": int(match.group("amount")),
                    "duration": "until_end_of_turn",
                },
            ),
            None,
            ("cr-615-prevention-effects",),
        )
    return None
