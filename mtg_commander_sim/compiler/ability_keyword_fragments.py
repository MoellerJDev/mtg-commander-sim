from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from ..ability_fragments import (
    CombatKeywordTriggerKind,
    CombatKeywordTriggerSpec,
    ability_fragment_to_dict,
    parse_protection_line,
)
from ..aura import parse_simple_enchant_line
from ..cast_timing import CastTimingPermission, PRINTED_FLASH_MECHANIC


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
    """Lower closed keyword grammar to typed executable fragments."""

    if mechanics == (PRINTED_FLASH_MECHANIC,):
        return AbilityKeywordFragmentLowering(
            handlers=(
                {
                    "handler_id": "ability.static.flash.v1",
                    "schema_version": 1,
                    "event": "cast.permission",
                    "permission": CastTimingPermission().to_dict(),
                },
            )
        )

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
    handlers: list[Mapping[str, Any]] = []
    parts = tuple(
        part.strip() for part in material_line.rstrip(".").split(",")
    )
    flanking_parts = tuple(
        part for part in parts if part.casefold() == "flanking"
    )
    handlers.extend(
        {
            "handler_id": "ability.trigger.flanking.v1",
            "schema_version": 1,
            "event": "continuous",
            "fragment": ability_fragment_to_dict(
                CombatKeywordTriggerSpec(
                    kind=CombatKeywordTriggerKind.FLANKING,
                    amount=1,
                )
            ),
        }
        for _part in flanking_parts
    )

    bushido_matches = tuple(
        match
        for part in parts
        if (
            match := re.fullmatch(
                r"Bushido (?P<amount>[1-9]\d*)",
                part,
                re.IGNORECASE,
            )
        )
        is not None
    )
    handlers.extend(
        {
            "handler_id": "ability.trigger.bushido.v1",
            "schema_version": 1,
            "event": "continuous",
            "fragment": ability_fragment_to_dict(
                CombatKeywordTriggerSpec(
                    kind=CombatKeywordTriggerKind.BUSHIDO,
                    amount=int(match.group("amount")),
                )
            ),
        }
        for match in bushido_matches
    )
    if mechanics.count("flanking") != len(flanking_parts):
        return AbilityKeywordFragmentLowering(
            handlers=tuple(handlers),
            residual_kind="unsupported_flanking_variant",
            residual_reason=(
                "Flanking wording is outside the closed printed keyword grammar"
            ),
            residual_blockers=("ordinary printed Flanking",),
        )
    if mechanics.count("bushido") != len(bushido_matches):
        return AbilityKeywordFragmentLowering(
            handlers=tuple(handlers),
            residual_kind="unsupported_bushido_value",
            residual_reason=(
                "Bushido requires one printed positive integer value"
            ),
            residual_blockers=("positive integer Bushido value",),
        )

    if "protection" in mechanics:
        protection_parts = tuple(
            part
            for part in parts
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
                handlers=tuple(handlers),
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
        handlers.extend(
            tuple(
                {
                    "handler_id": "ability.static.protection.v1",
                    "schema_version": 1,
                    "event": "continuous",
                    "fragment": ability_fragment_to_dict(spec),
                }
                for spec in specs
            )
        )
    return AbilityKeywordFragmentLowering(handlers=tuple(handlers))


__all__ = [
    "AbilityKeywordFragmentLowering",
    "lower_ability_keyword_fragments",
]
