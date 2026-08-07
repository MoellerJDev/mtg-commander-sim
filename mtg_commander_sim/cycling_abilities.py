from __future__ import annotations

"""Typed ordinary Cycling activation descriptors.

The represented grammar is deliberately bounded to fixed generic, colored,
and colorless mana symbols.  Variable, hybrid, Phyrexian, snow, nonmana,
typecycling, trigger, modifier, and prohibition variants remain residuals.
"""

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .fixed_mana_abilities import MANA_COST_KEYS
from .replacement.immutable import FrozenMap, thaw_value
from .util import mana_cost_to_vector


CYCLING_HANDLER_ID = "ability.activated.cycling.v1"
_ABILITY_ID = re.compile(r"^ab[1-9][0-9]*$")
_ORDINARY_COST = r"(?:\{(?:0|[1-9]\d*|[WUBRGC])\})+"
_ORDINARY_CYCLING = re.compile(
    rf"^Cycling\s+(?P<cost>{_ORDINARY_COST})\.?$",
    re.IGNORECASE,
)


class CyclingAbilityError(ValueError):
    """An ordinary Cycling descriptor is malformed or unsupported."""


def _exact_fields(
    value: Mapping[str, Any], expected: set[str], *, field: str
) -> None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing:
        raise CyclingAbilityError(
            f"{field} is missing required fields: {', '.join(missing)}"
        )
    if unknown:
        raise CyclingAbilityError(
            f"{field} has unknown fields: {', '.join(unknown)}"
        )


@dataclass(frozen=True, slots=True)
class OrdinaryCyclingAbilitySpec:
    ability_id: str
    line_index: int
    oracle_line: str
    cost_text: str
    mana_cost: FrozenMap

    def __post_init__(self) -> None:
        if (
            not isinstance(self.ability_id, str)
            or _ABILITY_ID.fullmatch(self.ability_id) is None
        ):
            raise CyclingAbilityError("Cycling ability ID must be abN")
        if type(self.line_index) is not int or self.line_index < 0:
            raise CyclingAbilityError(
                "Cycling ability line_index must be nonnegative"
            )
        if not isinstance(self.oracle_line, str) or not self.oracle_line:
            raise CyclingAbilityError(
                "Cycling ability oracle_line must be nonempty"
            )
        if (
            not isinstance(self.cost_text, str)
            or re.fullmatch(_ORDINARY_COST, self.cost_text, re.IGNORECASE)
            is None
        ):
            raise CyclingAbilityError(
                "Cycling cost must contain only fixed ordinary mana symbols"
            )
        if not isinstance(self.mana_cost, FrozenMap):
            if not isinstance(self.mana_cost, Mapping):
                raise CyclingAbilityError("Cycling mana cost must be an object")
            object.__setattr__(self, "mana_cost", FrozenMap(self.mana_cost))
        mana = thaw_value(self.mana_cost)
        if set(mana) != set(MANA_COST_KEYS) or any(
            type(amount) is not int or amount < 0
            for amount in mana.values()
        ):
            raise CyclingAbilityError(
                "Cycling mana cost must contain canonical nonnegative keys"
            )
        expected, complex_symbols = mana_cost_to_vector(self.cost_text)
        if complex_symbols or mana != expected:
            raise CyclingAbilityError(
                "Cycling mana cost does not match the printed cost"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ability_id": self.ability_id,
            "line_index": self.line_index,
            "oracle_line": self.oracle_line,
            "cost_text": self.cost_text,
            "mana_cost": thaw_value(self.mana_cost),
        }

    @classmethod
    def from_dict(
        cls, value: Mapping[str, Any]
    ) -> "OrdinaryCyclingAbilitySpec":
        _exact_fields(
            value,
            {
                "ability_id",
                "line_index",
                "oracle_line",
                "cost_text",
                "mana_cost",
            },
            field="ordinary Cycling ability",
        )
        if not all(
            isinstance(value[field], str)
            for field in ("ability_id", "oracle_line", "cost_text")
        ):
            raise CyclingAbilityError(
                "Cycling ability text fields must be strings"
            )
        mana_cost = value["mana_cost"]
        if not isinstance(mana_cost, Mapping):
            raise CyclingAbilityError("Cycling mana cost must be an object")
        return cls(
            ability_id=value["ability_id"],
            line_index=value["line_index"],
            oracle_line=value["oracle_line"],
            cost_text=value["cost_text"],
            mana_cost=FrozenMap(mana_cost),
        )

    def to_activated_ability(self) -> Any:
        from .abilities import ActivatedAbility

        return ActivatedAbility(
            ability_id=self.ability_id,
            line_index=self.line_index,
            oracle_line=self.oracle_line,
            cost_text=self.cost_text,
            effect_text="Draw a card.",
            zones=("hand",),
            mana=thaw_value(self.mana_cost),
            discard_source=True,
        )


def compile_ordinary_cycling_ability(
    *,
    material_line: str,
    oracle_line: str,
    line_index: int,
) -> OrdinaryCyclingAbilitySpec | None:
    """Compile one closed fixed-mana Cycling line or return ``None``."""

    match = _ORDINARY_CYCLING.fullmatch(material_line.strip())
    if match is None:
        return None
    cost_text = match.group("cost").upper()
    mana_cost, complex_symbols = mana_cost_to_vector(cost_text)
    if complex_symbols:
        return None
    return OrdinaryCyclingAbilitySpec(
        ability_id=f"ab{line_index + 1}",
        line_index=line_index,
        oracle_line=oracle_line,
        cost_text=cost_text,
        mana_cost=FrozenMap(mana_cost),
    )


def ordinary_cycling_handler_descriptor(
    spec: OrdinaryCyclingAbilitySpec,
) -> dict[str, Any]:
    return {
        "handler_id": CYCLING_HANDLER_ID,
        "schema_version": 1,
        "event": "activate",
        "ability": spec.to_dict(),
    }


__all__ = [
    "CYCLING_HANDLER_ID",
    "CyclingAbilityError",
    "OrdinaryCyclingAbilitySpec",
    "compile_ordinary_cycling_ability",
    "ordinary_cycling_handler_descriptor",
]
