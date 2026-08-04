from __future__ import annotations

import re

from ..characteristic_evaluation import type_parts
from .model import (
    AuraControllerRelation,
    AuraRuleError,
    SimpleEnchantSpec,
)


_REMINDER = re.compile(r"\s*\([^()]*\)\s*$")
_ENCHANT = re.compile(
    r"^enchant (?P<restriction>.+?)\.?$",
    re.IGNORECASE,
)


def is_aura_type_line(type_line: str) -> bool:
    return "aura" in type_parts(str(type_line))[1]


def _material_line(value: str) -> str:
    line = value.strip()
    while True:
        reduced = _REMINDER.sub("", line).strip()
        if reduced == line:
            return reduced
        line = reduced


def parse_simple_enchant_line(line: str) -> SimpleEnchantSpec | None:
    """Parse one bounded battlefield-object Enchant keyword line.

    The grammar deliberately rejects players, cards in other zones, object
    qualities, subtype alternatives, conjunctions, and multiple restrictions.
    Those families need additional legality predicates before they can be
    advertised as executable.
    """

    match = _ENCHANT.fullmatch(_material_line(line))
    if match is None:
        return None
    restriction = " ".join(
        match.group("restriction").casefold().split()
    )
    relation = AuraControllerRelation.ANY
    for suffix, candidate in (
        (" an opponent controls", AuraControllerRelation.OPPONENT),
        (" opponent controls", AuraControllerRelation.OPPONENT),
        (" you control", AuraControllerRelation.YOU),
    ):
        if restriction.endswith(suffix):
            restriction = restriction[: -len(suffix)].strip()
            relation = candidate
            break
    try:
        return SimpleEnchantSpec(
            object_kind=restriction,
            controller_relation=relation,
        )
    except AuraRuleError:
        return None


def simple_enchant_spec_from_oracle(
    oracle_text: str,
) -> SimpleEnchantSpec | None:
    lines = [
        line.strip()
        for line in str(oracle_text).splitlines()
        if line.strip().casefold().startswith("enchant ")
    ]
    if len(lines) != 1:
        return None
    return parse_simple_enchant_line(lines[0])


__all__ = [
    "is_aura_type_line",
    "parse_simple_enchant_line",
    "simple_enchant_spec_from_oracle",
]
