from __future__ import annotations

"""Conservative extraction of explicit activated abilities from Oracle text.

This module does *not* try to interpret arbitrary Magic prose.  It identifies
colon-form activated abilities, derives ordinary mana and a small set of
objective nonmana costs, and records anything else as uncompiled.  The rules
kernel can therefore expose Channel and other zone-specific abilities without
letting a pilot invent a cheaper cost or mutate state directly.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Mapping, Sequence

from .util import mana_cost_to_vector, normalize_mana_bundle, parse_mana_symbols

_ACTIVATE_ONLY_SORCERY = re.compile(r"activate only as a sorcery", re.IGNORECASE)
_PAY_LIFE = re.compile(r"^pay\s+(\d+)\s+life$", re.IGNORECASE)
_PAY_ENERGY = re.compile(
    r"^pay\s+(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)$",
    re.IGNORECASE,
)
_SACRIFICE_CHOICE = re.compile(
    r"^sacrifice\s+(?:(?P<another>another)\s+|(?P<count>a|an|one|two|three|\d+)\s+)"
    r"(?P<kind>creature|artifact|enchantment|land|permanent)s?(?:\s+you\s+control)?$",
    re.IGNORECASE,
)
_DISCARD_CHOICE = re.compile(
    r"^discard\s+(?P<count>a|an|one|two|three|\d+)\s+"
    r"(?:(?P<kind>creature|land|artifact|enchantment|instant|sorcery|planeswalker)\s+)?card(?:s)?$",
    re.IGNORECASE,
)

_NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3}
_NUMBER_WORDS.update(
    {
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
)


@dataclass(frozen=True, slots=True)
class CostChoice:
    kind: str
    count: int = 1
    zone: str = "battlefield"
    card_type: str | None = None
    another: bool = False

    def compact(self) -> dict[str, Any]:
        result: dict[str, Any] = {"k": self.kind, "n": self.count, "z": self.zone}
        if self.card_type:
            result["t"] = self.card_type
        if self.another:
            result["other"] = 1
        return result


@dataclass(frozen=True, slots=True)
class ActivatedAbility:
    ability_id: str
    line_index: int
    oracle_line: str
    cost_text: str
    effect_text: str
    zones: tuple[str, ...]
    mana: Mapping[str, int]
    complex_symbols: tuple[str, ...] = ()
    tap_source: bool = False
    untap_source: bool = False
    discard_source: bool = False
    sacrifice_source: bool = False
    exile_source: bool = False
    life_payment: int = 0
    energy_payment: int = 0
    choices: tuple[CostChoice, ...] = ()
    uncompiled_costs: tuple[str, ...] = ()
    mana_ability: bool = False
    sorcery_speed: bool = False
    generic_reduction_per_legendary_creature: int = 0

    @property
    def compiled_cost(self) -> bool:
        return not self.complex_symbols and not self.uncompiled_costs

    def compact(self, *, source_ref: str, zone: str) -> dict[str, Any]:
        result: dict[str, Any] = {
            "s": source_ref,
            "z": zone,
            "a": self.ability_id,
            "i": self.line_index,
        }
        mana = {key: value for key, value in self.mana.items() if value}
        if mana:
            result["m"] = mana
        if self.tap_source:
            result["tap"] = 1
        if self.discard_source:
            result["discard_self"] = 1
        if self.sacrifice_source:
            result["sac_self"] = 1
        if self.exile_source:
            result["exile_self"] = 1
        if self.life_payment:
            result["life"] = self.life_payment
        if self.energy_payment:
            result["energy"] = self.energy_payment
        if self.choices:
            result["choose_cost"] = [choice.compact() for choice in self.choices]
        if not self.compiled_cost:
            result["needs_rules"] = 1
        if self.mana_ability:
            result["mana_ability"] = 1
        if self.sorcery_speed:
            result["sorcery"] = 1
        if self.generic_reduction_per_legendary_creature:
            result["legend_discount"] = self.generic_reduction_per_legendary_creature
        return result


def _number(value: str) -> int:
    return _NUMBER_WORDS.get(value.casefold(), int(value) if value.isdigit() else 1)


def _strip_keyword_prefix(cost_text: str) -> tuple[str, str | None]:
    """Return the actual cost text and an optional named ability prefix."""
    if "—" in cost_text:
        prefix, remainder = cost_text.split("—", 1)
        if prefix.strip() and remainder.strip():
            return remainder.strip(), prefix.strip()
    if "-" in cost_text:
        # Oracle uses an em dash, but tolerate normalized text while avoiding
        # subtraction/negative loyalty symbols.
        prefix, remainder = cost_text.split("-", 1)
        if prefix.strip().isalpha() and remainder.strip():
            return remainder.strip(), prefix.strip()
    return cost_text.strip(), None


def _ability_zones(
    *,
    line: str,
    cost_text: str,
    effect_text: str,
    keyword_prefix: str | None,
    keywords: Iterable[str],
) -> tuple[str, ...]:
    lower_line = line.casefold()
    lower_cost = cost_text.casefold()
    keyword_set = {keyword.casefold() for keyword in keywords}
    prefix = (keyword_prefix or "").casefold()

    if prefix == "channel" or ("channel" in keyword_set and lower_line.startswith("channel")):
        return ("hand",)
    if prefix == "cycling":
        return ("hand",)
    if "discard this card" in lower_cost and (prefix or "channel" in keyword_set):
        return ("hand",)
    if "exile this card from your graveyard" in lower_cost:
        return ("graveyard",)
    if re.search(
        r"activate (?:this ability )?only (?:from|if this card is in) "
        r"(?:your|a) graveyard",
        lower_line,
    ):
        return ("graveyard",)
    if any(keyword in keyword_set for keyword in {"unearth", "encore", "scavenge", "embalm", "eternalize"}):
        if any(lower_line.startswith(keyword) for keyword in {"unearth", "encore", "scavenge", "embalm", "eternalize"}):
            return ("graveyard",)
    if "from exile" in lower_line and "activate" in lower_line:
        return ("exile",)
    return ("battlefield",)


def _split_cost_clauses(cost_text: str) -> list[str]:
    # Explicit activated costs conventionally use comma-separated clauses.
    # Oracle card names in self-discard costs are represented as "this card",
    # so a conservative split is preferable to accepting an opaque full cost.
    return [clause.strip() for clause in cost_text.split(",") if clause.strip()]


def _strip_inline_reminder_and_granted_text(line: str) -> str:
    """Keep only activated abilities printed on the source itself.

    Parenthetical token reminder text and quoted abilities granted to other
    objects can contain colons, but neither is an activated ability of this
    card. A fully parenthesized basic-land-type mana reminder remains
    supported below because that reminder represents an intrinsic ability of
    the land itself.
    """

    result: list[str] = []
    parenthetical_depth = 0
    quoted = False
    for character in line:
        if character in {'"', "“", "”"} and parenthetical_depth == 0:
            quoted = not quoted
            continue
        if quoted:
            continue
        if character == "(":
            parenthetical_depth += 1
            continue
        if character == ")" and parenthetical_depth:
            parenthetical_depth -= 1
            continue
        if parenthetical_depth == 0:
            result.append(character)
    return "".join(result).strip()


def parse_activated_abilities(
    *,
    card_name: str,
    oracle_text: str,
    keywords: Sequence[str] = (),
) -> tuple[ActivatedAbility, ...]:
    abilities: list[ActivatedAbility] = []
    for line_index, raw_line in enumerate(oracle_text.splitlines()):
        line = raw_line.strip()
        keyword_override: str | None = None
        # Scryfall preserves reminder text for basic-land-type mana abilities
        # as a fully parenthesized Oracle line, for example
        # "({T}: Add {G} or {U}.)".  The parentheses are not part of the cost.
        intrinsic_basic_mana = (
            line.startswith("({T}: Add ") and line.endswith(")")
        )
        if intrinsic_basic_mana:
            line = line[1:-1].strip()
        else:
            line = _strip_inline_reminder_and_granted_text(line)
        cycling_match = re.match(
            r"^cycling\s+(?P<cost>(?:\{[^{}]+\})+)$",
            line,
            re.IGNORECASE,
        )
        if cycling_match:
            line = (
                f"{cycling_match.group('cost')}, Discard this card: "
                "Draw a card."
            )
            keyword_override = "Cycling"
        if not line or ":" not in line:
            continue
        left, effect_text = line.split(":", 1)
        effect_text = effect_text.strip()
        if not effect_text:
            continue
        actual_cost, keyword_prefix = _strip_keyword_prefix(left.strip())
        keyword_prefix = keyword_override or keyword_prefix
        zones = _ability_zones(
            line=line,
            cost_text=actual_cost,
            effect_text=effect_text,
            keyword_prefix=keyword_prefix,
            keywords=keywords,
        )

        requirements, complex_symbols = mana_cost_to_vector(actual_cost)
        # Tap/untap are objective nonmana costs rather than payment symbols.
        complex_symbols = [symbol for symbol in complex_symbols if symbol not in {"T", "Q"}]
        tap_source = "{T}" in actual_cost.upper()
        untap_source = "{Q}" in actual_cost.upper()
        discard_source = False
        sacrifice_source = False
        exile_source = False
        life_payment = 0
        energy_payment = 0
        choices: list[CostChoice] = []
        uncompiled: list[str] = []

        for clause in _split_cost_clauses(actual_cost):
            symbols = parse_mana_symbols(clause)
            residue = re.sub(r"\{[^{}]+\}", "", clause).strip()
            # A clause can consist solely of mana/tap symbols.
            if not residue:
                continue
            lower = residue.casefold().strip(" .")
            if lower.startswith("channel"):
                continue
            if lower in {"discard this card", f"discard {card_name.casefold()}"}:
                discard_source = True
                continue
            if lower in {
                "sacrifice this permanent",
                "sacrifice this artifact",
                "sacrifice this creature",
                "sacrifice this land",
                "sacrifice this token",
                "sacrifice this card",
                f"sacrifice {card_name.casefold()}",
            }:
                sacrifice_source = True
                continue
            if lower in {
                "exile this card from your graveyard",
                "exile this card",
                f"exile {card_name.casefold()}",
            }:
                exile_source = True
                continue
            life_match = _PAY_LIFE.match(lower)
            if life_match:
                life_payment += int(life_match.group(1))
                continue
            energy_match = _PAY_ENERGY.match(lower)
            if energy_match and "E" in symbols:
                energy_payment += _number(
                    energy_match.group("count")
                )
                complex_symbols = [
                    symbol
                    for symbol in complex_symbols
                    if symbol != "E"
                ]
                continue
            sacrifice_match = _SACRIFICE_CHOICE.match(lower)
            if sacrifice_match:
                choices.append(
                    CostChoice(
                        kind="sacrifice",
                        count=_number(sacrifice_match.group("count") or "one"),
                        zone="battlefield",
                        card_type=sacrifice_match.group("kind").casefold(),
                        another=bool(sacrifice_match.group("another")),
                    )
                )
                continue
            discard_match = _DISCARD_CHOICE.match(lower)
            if discard_match:
                choices.append(
                    CostChoice(
                        kind="discard",
                        count=_number(discard_match.group("count")),
                        zone="hand",
                        card_type=(discard_match.group("kind") or None),
                    )
                )
                continue
            # Loyalty symbols, energy, counter removal, revealing, tapping
            # another permanent, and other costs are intentionally not guessed.
            if symbols and not residue:
                continue
            uncompiled.append(residue)

        effect_lower = effect_text.casefold()
        mana_ability = (
            "target" not in effect_lower
            and (
                effect_lower.startswith("add ")
                or "add one mana" in effect_lower
            )
        )
        generic_discount = 0
        if re.search(
            r"this ability costs \{1\} less to activate for each legendary creature you control",
            effect_text,
            re.IGNORECASE,
        ):
            generic_discount = 1

        abilities.append(
            ActivatedAbility(
                ability_id=f"ab{line_index + 1}",
                line_index=line_index,
                oracle_line=line,
                cost_text=actual_cost,
                effect_text=effect_text,
                zones=zones,
                mana=requirements,
                complex_symbols=tuple(complex_symbols),
                tap_source=tap_source,
                untap_source=untap_source,
                discard_source=discard_source,
                sacrifice_source=sacrifice_source,
                exile_source=exile_source,
                life_payment=life_payment,
                energy_payment=energy_payment,
                choices=tuple(choices),
                uncompiled_costs=tuple(uncompiled),
                mana_ability=mana_ability,
                sorcery_speed=bool(_ACTIVATE_ONLY_SORCERY.search(effect_text)),
                generic_reduction_per_legendary_creature=generic_discount,
            )
        )
    return tuple(abilities)


def choose_ability(
    abilities: Sequence[ActivatedAbility],
    selector: Any,
) -> ActivatedAbility:
    if not abilities:
        raise ValueError("No explicit activated ability was found")
    if selector is None or selector == "":
        if len(abilities) == 1:
            return abilities[0]
        raise ValueError("Select an ability by its ability id or line index")
    text = str(selector).casefold().strip()
    for ability in abilities:
        if text in {
            ability.ability_id.casefold(),
            str(ability.line_index),
            str(ability.line_index + 1),
        }:
            return ability
    raise ValueError(f"Unknown activated ability selector {selector!r}")


def reduced_requirements(
    ability: ActivatedAbility,
    *,
    legendary_creatures: int = 0,
) -> dict[str, int]:
    result = {"GENERIC": int(ability.mana.get("GENERIC", 0))}
    for color in "WUBRGC":
        result[color] = int(ability.mana.get(color, 0))
    if ability.generic_reduction_per_legendary_creature:
        reduction = ability.generic_reduction_per_legendary_creature * max(0, legendary_creatures)
        result["GENERIC"] = max(0, result["GENERIC"] - reduction)
    return result
