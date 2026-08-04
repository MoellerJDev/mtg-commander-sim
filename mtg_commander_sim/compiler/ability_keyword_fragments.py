from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..ability_fragments import (
    ability_fragment_to_dict,
    parse_protection_line,
)
from ..aura import parse_simple_enchant_line


@dataclass(frozen=True, slots=True)
class AbilityKeywordFragmentLowering:
    handlers: tuple[Mapping[str, Any], ...] = ()
    residual_kind: str | None = None
    residual_reason: str | None = None
    residual_blockers: tuple[str, ...] = ()


def lower_ability_keyword_fragments(
    material_line: str,
    mechanics: tuple[str, ...],
) -> AbilityKeywordFragmentLowering:
    """Lower closed Enchant/protection grammar to typed runtime fragments."""

    if mechanics == ("enchant",):
        enchant_spec = parse_simple_enchant_line(material_line)
        if enchant_spec is None:
            return AbilityKeywordFragmentLowering(
                residual_kind="unsupported_enchant_restriction",
                residual_reason=(
                    "Enchant restriction is outside the closed typed "
                    "battlefield-object grammar"
                ),
                residual_blockers=("typed Enchant restriction",),
            )
        return AbilityKeywordFragmentLowering(
            handlers=(
                {
                    "handler_id": "ability.static.enchant.v1",
                    "schema_version": 1,
                    "event": "continuous",
                    "fragment": ability_fragment_to_dict(enchant_spec),
                },
            )
        )
    if "protection" in mechanics:
        protection_parts = tuple(
            part.strip()
            for part in material_line.rstrip(".").split(",")
            if part.strip().casefold().startswith("protection from ")
        )
        parsed = tuple(
            parse_protection_line(part) for part in protection_parts
        )
        if (
            len(protection_parts) != mechanics.count("protection")
            or any(not specs for specs in parsed)
        ):
            return AbilityKeywordFragmentLowering(
                residual_kind="unsupported_protection_quality",
                residual_reason=(
                    "protection quality is outside the closed typed DEBT "
                    "grammar"
                ),
                residual_blockers=("typed protection quality",),
            )
        specs = tuple(
            spec
            for values in parsed
            for spec in (values or ())
        )
        return AbilityKeywordFragmentLowering(
            handlers=tuple(
                {
                    "handler_id": "ability.static.protection.v1",
                    "schema_version": 1,
                    "event": "continuous",
                    "fragment": ability_fragment_to_dict(spec),
                }
                for spec in specs
            )
        )
    return AbilityKeywordFragmentLowering()


__all__ = [
    "AbilityKeywordFragmentLowering",
    "lower_ability_keyword_fragments",
]
