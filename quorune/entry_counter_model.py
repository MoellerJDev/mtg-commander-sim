from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence


class EntryCounterError(ValueError):
    """An intrinsic as-enters counter instruction is not representable."""


@dataclass(frozen=True, slots=True)
class IntrinsicEntryCounter:
    counter_name: str
    amount: int
    required_type: str
    rule_id: str

    def __post_init__(self) -> None:
        counter_name = " ".join(self.counter_name.casefold().split())
        required_type = " ".join(self.required_type.casefold().split())
        rule_id = str(self.rule_id or "")
        if not counter_name or not required_type or not rule_id:
            raise EntryCounterError(
                "Intrinsic entry counters require a counter, type, and rule"
            )
        if type(self.amount) is not int or self.amount < 0:
            raise EntryCounterError(
                "Intrinsic entry counter amounts must be nonnegative integers"
            )
        object.__setattr__(self, "counter_name", counter_name)
        object.__setattr__(self, "required_type", required_type)
        object.__setattr__(self, "rule_id", rule_id)


def _printed_nonnegative_integer(
    value: Any,
    *,
    characteristic: str,
) -> int:
    if type(value) is int:
        amount = value
    elif type(value) is str and re.fullmatch(r"-?\d+", value.strip()):
        amount = int(value.strip())
    else:
        raise EntryCounterError(
            f"{characteristic} must be a represented nonnegative integer"
        )
    if amount < 0:
        raise EntryCounterError(f"{characteristic} cannot be negative")
    return amount


def intrinsic_entry_counters(
    characteristics: Mapping[str, Any],
    *,
    card_types: Sequence[str],
) -> tuple[IntrinsicEntryCounter, ...]:
    """Return the closed CR 306.5b/310.4b entry-counter instructions."""

    if not isinstance(characteristics, Mapping):
        raise EntryCounterError(
            "Entry counter characteristics must be a mapping"
        )
    types = {" ".join(str(value).casefold().split()) for value in card_types}
    counters: list[IntrinsicEntryCounter] = []
    if "planeswalker" in types:
        counters.append(
            IntrinsicEntryCounter(
                counter_name="loyalty",
                amount=_printed_nonnegative_integer(
                    characteristics.get("loyalty"),
                    characteristic="Starting loyalty",
                ),
                required_type="planeswalker",
                rule_id="306.5b",
            )
        )
    if "battle" in types:
        counters.append(
            IntrinsicEntryCounter(
                counter_name="defense",
                amount=_printed_nonnegative_integer(
                    characteristics.get("defense"),
                    characteristic="Battle defense",
                ),
                required_type="battle",
                rule_id="310.4b",
            )
        )
    return tuple(counters)


__all__ = [
    "EntryCounterError",
    "IntrinsicEntryCounter",
    "intrinsic_entry_counters",
]
