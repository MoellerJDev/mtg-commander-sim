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

from .replacement.immutable import FrozenMap, thaw_value
from .fixed_mana_abilities import FixedManaMode
from .util import mana_cost_to_vector, normalize_mana_bundle, parse_mana_symbols

_ACTIVATE_ONLY_SORCERY = re.compile(
    r"(?:activate|craft) only as a sorcery", re.IGNORECASE
)
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
_RETURN_CHOICE = re.compile(
    r"^return\s+(?:a|an|one)\s+"
    r"(?P<kind>creature|artifact|enchantment|land|permanent|"
    r"plains|island|swamp|mountain|forest)"
    r"(?:\s+you\s+control)?\s+to\s+its\s+owner'?s\s+hand$",
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
    loyalty_delta: int | None = None
    choices: tuple[CostChoice, ...] = ()
    uncompiled_costs: tuple[str, ...] = ()
    mana_ability: bool = False
    sorcery_speed: bool = False
    generic_reduction_per_legendary_creature: int = 0
    builtin_semantic_key: str | None = None
    target_schema: FrozenMap | None = None
    crew_threshold: int | None = None
    fixed_mana_outputs: tuple[FixedManaMode, ...] = ()

    def __post_init__(self) -> None:
        if self.target_schema is not None and not isinstance(
            self.target_schema, FrozenMap
        ):
            object.__setattr__(
                self, "target_schema", FrozenMap(self.target_schema)
            )
        if not isinstance(self.fixed_mana_outputs, tuple) or any(
            not isinstance(mode, FixedManaMode)
            for mode in self.fixed_mana_outputs
        ):
            raise ValueError("fixed_mana_outputs must contain typed modes")

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
        if self.loyalty_delta is not None:
            result["loyalty"] = self.loyalty_delta
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
        if self.target_schema is not None:
            result["target_schema"] = thaw_value(self.target_schema)
        if self.crew_threshold is not None:
            result["crew"] = self.crew_threshold
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


def _builtin_effect_descriptor(
    effect_text: str,
) -> tuple[str | None, FrozenMap | None]:
    normalized = " ".join(effect_text.casefold().strip(" .").split())
    normalized = re.sub(
        r"\.?\s*activate only as a sorcery$", "", normalized
    ).strip(" .")
    if normalized == "target creature you control explores":
        return (
            "builtin:explore-target",
            FrozenMap(
                {
                    "zones": ["battlefield"],
                    "categories": ["permanent"],
                    "controller": "you",
                    "creature": True,
                    "count": 1,
                }
            ),
        )
    gain = re.fullmatch(r"you gain (?P<amount>\d+) life", normalized)
    if gain is not None:
        return f"builtin:gain-life:{int(gain.group('amount'))}", None
    return None, None


def _equip_effect_descriptor() -> tuple[str, FrozenMap]:
    """Return the closed CR 702.6 target/effect contract for Equip.

    The keyword normalizer has already proved that this is a printed Equip
    ability with an ordinary mana cost. Keeping the target contract on the
    parsed ability lets proposal validation, projection, and replay use the
    same generic activation path as other activated abilities.
    """

    return (
        "builtin:equip",
        FrozenMap(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "controller": "you",
                "creature": True,
                "count": 1,
            }
        ),
    )


def _crew_keyword_ability(
    line: str,
    line_index: int,
) -> ActivatedAbility | None:
    match = re.fullmatch(r"Crew\s+(?P<power>\d+)", line, re.IGNORECASE)
    if match is None:
        return None
    threshold = int(match.group("power"))
    return ActivatedAbility(
        ability_id="crew",
        line_index=line_index,
        oracle_line=line,
        cost_text=f"Crew {threshold}",
        effect_text=(
            "This Vehicle becomes an artifact creature until end of turn. "
            f"Crew {threshold}."
        ),
        zones=("battlefield",),
        mana=normalize_mana_bundle(None),
        crew_threshold=threshold,
    )


def _craft_keyword_abilities(
    line: str,
    line_index: int,
) -> tuple[ActivatedAbility, ...]:
    match = re.fullmatch(
        r"Craft with (?P<kind>[A-Za-z]+) (?P<mana>(?:\{[^{}]+\})+) "
        r"\((?P<reminder>.+)\)",
        line,
        re.IGNORECASE,
    )
    if match is None or ":" not in match.group("reminder"):
        return ()
    kind = match.group("kind").casefold()
    cost_text, effect_text = match.group("reminder").split(":", 1)
    choice_match = re.search(
        rf"Exile an? {re.escape(kind)} you control or an? {re.escape(kind)} "
        r"card from your graveyard",
        cost_text,
        re.IGNORECASE,
    )
    if (
        choice_match is None
        or "exile this artifact" not in cost_text.casefold()
    ):
        return ()
    requirements, complex_symbols = mana_cost_to_vector(match.group("mana"))
    if complex_symbols:
        return ()
    effect = effect_text.strip()
    return tuple(
        ActivatedAbility(
            ability_id=f"craft_{zone}",
            line_index=line_index * 2 + offset,
            oracle_line=line,
            cost_text=cost_text.strip(),
            effect_text=effect,
            zones=("battlefield",),
            mana=requirements,
            exile_source=True,
            choices=(
                CostChoice(
                    kind="exile",
                    count=1,
                    zone=zone,
                    card_type=kind,
                ),
            ),
            sorcery_speed=bool(_ACTIVATE_ONLY_SORCERY.search(effect)),
        )
        for offset, zone in enumerate(("battlefield", "graveyard"))
    )


@dataclass(frozen=True, slots=True)
class _ParsedCost:
    mana: Mapping[str, int]
    complex_symbols: tuple[str, ...]
    tap_source: bool
    untap_source: bool
    discard_source: bool
    sacrifice_source: bool
    exile_source: bool
    life_payment: int
    energy_payment: int
    loyalty_delta: int | None
    choices: tuple[CostChoice, ...]
    uncompiled: tuple[str, ...]


def _parse_cost(actual_cost: str, card_name: str) -> _ParsedCost:
    requirements, raw_complex = mana_cost_to_vector(actual_cost)
    complex_symbols = [value for value in raw_complex if value not in {"T", "Q"}]
    flags = {"discard": False, "sacrifice": False, "exile": False}
    life_payment = 0
    energy_payment = 0
    loyalty_delta: int | None = None
    loyalty_clauses = 0
    choices: list[CostChoice] = []
    uncompiled: list[str] = []
    source_costs = {
        "discard": {"discard this card", f"discard {card_name.casefold()}"},
        "sacrifice": {
            "sacrifice this permanent", "sacrifice this artifact",
            "sacrifice this creature", "sacrifice this land",
            "sacrifice this token", "sacrifice this card",
            f"sacrifice {card_name.casefold()}",
        },
        "exile": {
            "exile this card from your graveyard", "exile this card",
            f"exile {card_name.casefold()}",
        },
    }
    for clause in _split_cost_clauses(actual_cost):
        symbols = parse_mana_symbols(clause)
        residue = re.sub(r"\{[^{}]+\}", "", clause).strip()
        if not residue:
            continue
        lower = residue.casefold().strip(" .")
        loyalty_match = re.fullmatch(r"(?P<sign>[+\-\u2212])(?P<amount>\d+)", residue)
        if loyalty_match:
            amount = int(loyalty_match.group("amount"))
            loyalty_clauses += 1
            loyalty_delta = amount if loyalty_match.group("sign") == "+" else -amount
            if loyalty_clauses > 1:
                loyalty_delta = None
                if loyalty_clauses == 2:
                    uncompiled.append(
                        "multiple loyalty-symbol costs require combined-cost semantics"
                    )
            continue
        if lower.startswith("channel"):
            continue
        matched_source = next(
            (kind for kind, values in source_costs.items() if lower in values), None
        )
        if matched_source is not None:
            flags[matched_source] = True
            continue
        life_match = _PAY_LIFE.match(lower)
        if life_match:
            life_payment += int(life_match.group(1))
            continue
        energy_match = _PAY_ENERGY.match(lower)
        if energy_match and "E" in symbols:
            energy_payment += _number(energy_match.group("count"))
            complex_symbols = [value for value in complex_symbols if value != "E"]
            continue
        choice = _cost_choice(lower)
        if choice is not None:
            choices.append(choice)
            continue
        uncompiled.append(residue)
    return _ParsedCost(
        mana=requirements,
        complex_symbols=tuple(complex_symbols),
        tap_source="{T}" in actual_cost.upper(),
        untap_source="{Q}" in actual_cost.upper(),
        discard_source=flags["discard"],
        sacrifice_source=flags["sacrifice"],
        exile_source=flags["exile"],
        life_payment=life_payment,
        energy_payment=energy_payment,
        loyalty_delta=loyalty_delta,
        choices=tuple(choices),
        uncompiled=tuple(uncompiled),
    )


def _cost_choice(lower: str) -> CostChoice | None:
    sacrifice = _SACRIFICE_CHOICE.match(lower)
    if sacrifice:
        return CostChoice(
            kind="sacrifice",
            count=_number(sacrifice.group("count") or "one"),
            zone="battlefield",
            card_type=sacrifice.group("kind").casefold(),
            another=bool(sacrifice.group("another")),
        )
    discard = _DISCARD_CHOICE.match(lower)
    if discard:
        return CostChoice(
            kind="discard",
            count=_number(discard.group("count")),
            zone="hand",
            card_type=discard.group("kind") or None,
        )
    returned = _RETURN_CHOICE.match(lower)
    if returned:
        return CostChoice(
            kind="return",
            zone="battlefield",
            card_type=returned.group("kind").casefold(),
        )
    return None


def _normalized_ability_line(raw_line: str) -> tuple[str, str | None]:
    line = raw_line.strip()
    if line.startswith("({T}: Add ") and line.endswith(")"):
        line = line[1:-1].strip()
    else:
        line = _strip_inline_reminder_and_granted_text(line)
    for keyword, effect in (
        ("Cycling", "Draw a card."),
        (
            "Equip",
            "Attach this Equipment to target creature you control. "
            "Activate only as a sorcery.",
        ),
    ):
        match = re.fullmatch(
            rf"{keyword}\s+(?P<cost>(?:\{{[^{{}}]+\}})+)",
            line,
            re.IGNORECASE,
        )
        if match:
            discard = ", Discard this card" if keyword == "Cycling" else ""
            return f"{match.group('cost')}{discard}: {effect}", keyword
    return line, None


def _parse_activated_line(
    raw_line: str,
    line_index: int,
    card_name: str,
    keywords: Sequence[str],
) -> tuple[ActivatedAbility, ...]:
    raw = raw_line.strip()
    crew = _crew_keyword_ability(raw, line_index)
    if crew is not None:
        return (crew,)
    craft = _craft_keyword_abilities(raw, line_index)
    if craft:
        return craft
    line, keyword_override = _normalized_ability_line(raw)
    if not line or ":" not in line:
        return ()
    left, effect_text = line.split(":", 1)
    effect_text = effect_text.strip()
    if not effect_text:
        return ()
    actual_cost, keyword_prefix = _strip_keyword_prefix(left.strip())
    cost = _parse_cost(actual_cost, card_name)
    effect_lower = effect_text.casefold()
    mana_ability = bool(
        cost.loyalty_delta is None
        and "target" not in effect_lower
        and (effect_lower.startswith("add ") or "add one mana" in effect_lower)
    )
    builtin_semantic_key, target_schema = _builtin_effect_descriptor(effect_text)
    if (keyword_override or keyword_prefix or "").casefold() == "equip":
        builtin_semantic_key, target_schema = _equip_effect_descriptor()
    return (
        ActivatedAbility(
            ability_id=f"ab{line_index + 1}",
            line_index=line_index,
            oracle_line=line,
            cost_text=actual_cost,
            effect_text=effect_text,
            zones=_ability_zones(
                line=line,
                cost_text=actual_cost,
                effect_text=effect_text,
                keyword_prefix=keyword_override or keyword_prefix,
                keywords=keywords,
            ),
            mana=cost.mana,
            complex_symbols=cost.complex_symbols,
            tap_source=cost.tap_source,
            untap_source=cost.untap_source,
            discard_source=cost.discard_source,
            sacrifice_source=cost.sacrifice_source,
            exile_source=cost.exile_source,
            life_payment=cost.life_payment,
            energy_payment=cost.energy_payment,
            loyalty_delta=cost.loyalty_delta,
            choices=cost.choices,
            uncompiled_costs=cost.uncompiled,
            mana_ability=mana_ability,
            sorcery_speed=bool(_ACTIVATE_ONLY_SORCERY.search(effect_text)),
            generic_reduction_per_legendary_creature=int(
                bool(
                    re.search(
                        r"this ability costs \{1\} less to activate for each legendary creature you control",
                        effect_text,
                        re.IGNORECASE,
                    )
                )
            ),
            builtin_semantic_key=builtin_semantic_key,
            target_schema=target_schema,
        ),
    )


def parse_activated_abilities(
    *,
    card_name: str,
    oracle_text: str,
    keywords: Sequence[str] = (),
) -> tuple[ActivatedAbility, ...]:
    abilities: list[ActivatedAbility] = []
    for line_index, raw_line in enumerate(oracle_text.splitlines()):
        abilities.extend(
            _parse_activated_line(raw_line, line_index, card_name, keywords)
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
