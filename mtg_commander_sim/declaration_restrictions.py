from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from .declaration_costs import (
    DeclarationKind,
    normalized_oracle_line,
    parse_declaration_cost_line,
)


DeclarationRestrictionScope = Literal[
    "attached",
    "attached_option",
    "global",
    "self",
    "source_opponents",
    "source_option",
]
DeclarationRestrictionMode = Literal[
    "prohibit",
    "minimum_matching_selections",
    "minimum_total_selections",
    "maximum_total_selections",
    "minimum_option_uses",
    "maximum_option_uses",
]
PowerOperand = Literal["fixed", "source"]
PowerOperator = Literal["eq", "lt", "le", "gt", "ge"]
ComparedStat = Literal["power", "toughness"]

_COLORS = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}
_ABILITY_WORD_PREFIX = re.compile(
    r"^[a-z][a-z ']+ [—-] (?P<body>.+)$"
)
_SELF_PROHIBITION = re.compile(
    r"this creature can't (?P<kind>attack|block|attack or block)\."
)
_ATTACHED_PROHIBITION = re.compile(
    r"enchanted (?:creature|permanent) can't "
    r"(?P<kind>attack|block|attack or block)\."
)
_GLOBAL_PROHIBITION = re.compile(
    r"creatures can't (?P<kind>attack|block)\."
)
_SELF_NOT_ALONE = re.compile(
    r"this creature can't (?P<kind>attack|block|attack or block) alone\."
)
_GLOBAL_MAXIMUM = re.compile(
    r"no more than (?P<count>one|two|three|\d+) creatures? can "
    r"(?P<kind>attack|block) each combat\."
)
_GOADED_OPPONENT_BLOCK = re.compile(
    r"goaded creatures your opponents control can't block\."
)
_KEYWORDLESS_GLOBAL_ATTACK = re.compile(
    r"creatures without (?P<keywords>[a-z][a-z -]*"
    r"(?: or [a-z][a-z -]*)*) can't attack\."
)
_SOURCE_POWER_EVASION = re.compile(
    r"creatures with power less than this creature's power can't block it\."
)
_SELF_FIXED_POWER_BLOCK = re.compile(
    r"this creature can't block creatures with power (?P<count>\d+) "
    r"or (?P<direction>greater|less)\."
)
_SELF_COLOR_BLOCK = re.compile(
    r"this creature can't block (?P<color>white|blue|black|red|green) "
    r"creatures\."
)
_SELF_UNBLOCKABLE = re.compile(r"this creature can't be blocked\.")
_SELF_BLOCKED_BY_POWER = re.compile(
    r"this creature can't be blocked by creatures with "
    r"(?P<stat>power|toughness) (?P<count>\d+) or "
    r"(?P<direction>greater|less)\."
)
_SELF_BLOCKED_BY_COLOR = re.compile(
    r"this creature can't be blocked by "
    r"(?P<color>white|blue|black|red|green) creatures\."
)
_SELF_BLOCKED_BY_SUBTYPE = re.compile(
    r"this creature can't be blocked by (?P<subtype>[a-z][a-z'-]*)s\."
)
_SELF_BLOCKED_BY_FILTER = re.compile(
    r"this creature can't be blocked by (?P<filter>[^.]+)\."
)
_ATTACHED_BLOCKED_BY_FILTER = re.compile(
    r"enchanted creature can't be blocked by (?P<filter>[^.]+)\."
)
_SELF_BLOCKED_EXCEPT_FILTER = re.compile(
    r"this creature can't be blocked except by (?P<filter>[^.]+)\."
)
_ATTACHED_BLOCKED_EXCEPT_FILTER = re.compile(
    r"enchanted creature can't be blocked except by (?P<filter>[^.]+)\."
)
_ATTACHED_UNBLOCKABLE = re.compile(
    r"enchanted creature can't be blocked\."
)
_SELF_BLOCK_FILTER = re.compile(
    r"this creature can't block (?P<filter>[^.]+)\."
)
_ATTACHED_CAN_BLOCK_ONLY_FILTER = re.compile(
    r"enchanted creature can block only (?P<filter>[^.]+)\."
)
_GLOBAL_CAN_BLOCK_ONLY_FILTER = re.compile(
    r"(?P<subject>[^.]+) can block only (?P<opposing>[^.]+)\."
)
_SELF_BLOCK_SOURCE_POWER = re.compile(
    r"this creature can't block creatures with power greater than "
    r"this creature's power\."
)
_SELF_BLOCKED_BY_GREATER_POWER = re.compile(
    r"this creature can't be blocked by creatures with greater power\."
)
_SELF_BATTLEFIELD_CONDITION = re.compile(
    r"this creature can't (?P<kind>attack|block|attack or block) "
    r"(?P<link>unless|if) "
    r"(?:(?P<source>you) control|"
    r"(?P<defender>defending player) controls) "
    r"(?P<filter>[^.]+)\."
)
_SELF_CONDITIONAL_UNBLOCKABLE = re.compile(
    r"this creature can't be blocked as long as defending player controls "
    r"(?P<condition>[^.]+)\."
)
_SELF_CONDITIONAL_BLOCKER_FILTER = re.compile(
    r"this creature can't be blocked by (?P<blockers>[^.]+) as long as "
    r"defending player controls (?P<condition>[^.]+)\."
)
_SELF_OTHER_DECLARATIONS = re.compile(
    r"this creature can't (?P<kind>attack|block) unless at least "
    r"(?P<count>one|two|three|\d+) other creatures "
    r"(?P<verb>attack|block)\."
)
_SELF_MATCHING_COMPANION = re.compile(
    r"this creature can't (?P<kind>attack|block) unless "
    r"(?P<filter>a [a-z]+ or [a-z]+ creature|a creature with greater power) "
    r"also (?P<verb>attacks|blocks)\."
)
_SELF_ATTACKING_ALONE_EVASION = re.compile(
    r"this creature can't be blocked as long as it's attacking alone\."
)
_ATTACHED_ATTACKING_ALONE_EVASION = re.compile(
    r"enchanted creature can't be blocked as long as it's attacking alone\."
)
_SELF_NO_OTHER_CREATURE_EVASION = re.compile(
    r"this creature can't be blocked as long as you control no other creatures\."
)
_GLOBAL_SOURCE_CONTROLLER_ATTACK = re.compile(
    r"creatures(?P<filter> with power \d+ or (?:greater|less)| "
    r"with [a-z-]+| without [a-z-]+)? can't attack you"
    r"(?P<planeswalkers> or planeswalkers you control)?\."
)
_GLOBAL_SOURCE_CONTROLLER_ATTACK_BLOCK = re.compile(
    r"creatures with (?P<keyword>[a-z-]+) can't attack you or block "
    r"creatures you control\."
)
_ATTACHED_SOURCE_CONTROLLER_ATTACK = re.compile(
    r"enchanted creature can't attack you"
    r"(?P<planeswalkers> or planeswalkers you control)?\."
)
_SOURCE_CONTROLLER_ATTACK_MAXIMUM = re.compile(
    r"no more than (?P<count>one|two|three|\d+) creatures? can attack "
    r"you each combat\."
)
_SOURCE_ATTACK_MAXIMUM = re.compile(
    r"no more than (?P<count>one|two|three|\d+) creatures? can attack "
    r"this creature each combat\."
)
_SELF_SHARED_SUBTYPE_BLOCK_CONDITION = re.compile(
    r"this creature can't be blocked unless defending player controls "
    r"(?P<count>one|two|three|\d+) or more creatures that share a "
    r"creature type\."
)
_SELF_BLOCKED_BY_MORE_THAN = re.compile(
    r"this creature can't be blocked by more than (?P<count>one|two|three|\d+) "
    r"creatures?\."
)
_SELF_BLOCKED_EXCEPT_COUNT = re.compile(
    r"this creature can't be blocked except by "
    r"(?P<count>one|two|three|\d+) or more creatures\."
)
_SELF_CAN_BLOCK_ONLY_KEYWORD = re.compile(
    r"this creature can block only creatures with "
    r"(?P<keyword>[a-z][a-z -]*)\."
)
_SUBTYPE_BLOCK = re.compile(
    r"(?P<blocker>[a-z][a-z'-]*)s can't block "
    r"(?P<attacker>[a-z][a-z'-]*)s\."
)
_STATIC_RESTRICTION_PREFIX = re.compile(
    r"^(?:(?:"
    r"this creature|enchanted (?:creature|permanent)|"
    r"goaded creatures|creatures|non-[a-z'-]+ creatures"
    r")[^.]*\b(?:(?:can't|cannot) (?:attack|block|be blocked)"
    r"|can (?:attack|block) only)\b"
    r"|no more than [a-z0-9]+ creatures? can (?:attack|block)\b)"
)

_FILTER_KEYWORDS = {
    "defender",
    "flying",
    "horsemanship",
    "reach",
}
_IRREGULAR_SUBTYPE_PLURALS = {
    "elves": "Elf",
    "dwarves": "Dwarf",
    "mice": "Mouse",
    "oxen": "Ox",
}


def _declarations(kind: str) -> tuple[DeclarationKind, ...]:
    return {
        "attack": ("attack",),
        "block": ("block",),
        "attack or block": ("attack", "block"),
    }[kind]


def _number(value: str) -> int:
    return {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }.get(value, int(value) if value.isdigit() else 0)


def _singular_subtype(value: str) -> str:
    normalized = value.strip().casefold()
    if normalized in _IRREGULAR_SUBTYPE_PLURALS:
        return _IRREGULAR_SUBTYPE_PLURALS[normalized]
    words = normalized.split()
    if not words:
        return ""
    last = words[-1]
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    words[-1] = last
    return " ".join(words).title()


@dataclass(frozen=True, slots=True)
class StatComparison:
    stat: ComparedStat
    operator: PowerOperator
    operand: PowerOperand
    value: int | None = None

    def __post_init__(self) -> None:
        if self.operand == "fixed" and self.value is None:
            raise ValueError("A fixed stat comparison requires a value")
        if self.operand == "source" and self.value is not None:
            raise ValueError("A source stat comparison cannot set a value")

    def to_dict(self) -> dict[str, object]:
        return {
            "stat": self.stat,
            "operator": self.operator,
            "operand": self.operand,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class DeclarationObjectPredicate:
    """Declarative battlefield-object filter used by restrictions and conditions."""

    types_any: tuple[str, ...] = ()
    types_none: tuple[str, ...] = ()
    supertypes_any: tuple[str, ...] = ()
    supertypes_none: tuple[str, ...] = ()
    subtypes_any: tuple[str, ...] = ()
    subtypes_none: tuple[str, ...] = ()
    colors_any: tuple[str, ...] = ()
    colors_none: tuple[str, ...] = ()
    keywords_any: tuple[str, ...] = ()
    keywords_none: tuple[str, ...] = ()
    token: bool | None = None
    goaded: bool | None = None
    stat: StatComparison | None = None
    additional_stats: tuple[StatComparison, ...] = ()
    tapped: bool | None = None
    enchanted: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "types_any": list(self.types_any),
            "types_none": list(self.types_none),
            "supertypes_any": list(self.supertypes_any),
            "supertypes_none": list(self.supertypes_none),
            "subtypes_any": list(self.subtypes_any),
            "subtypes_none": list(self.subtypes_none),
            "colors_any": list(self.colors_any),
            "colors_none": list(self.colors_none),
            "keywords_any": list(self.keywords_any),
            "keywords_none": list(self.keywords_none),
            "token": self.token,
            "goaded": self.goaded,
            "stat": self.stat.to_dict() if self.stat else None,
            "additional_stats": [
                comparison.to_dict() for comparison in self.additional_stats
            ],
            "tapped": self.tapped,
            "enchanted": self.enchanted,
        }


DeclarationConditionPlayer = Literal[
    "attacking_player",
    "defending_player",
    "source_controller",
]


@dataclass(frozen=True, slots=True)
class DeclarationBattlefieldCondition:
    """A typed battlefield-state predicate gating a declaration restriction."""

    player: DeclarationConditionPlayer
    predicates_any: tuple[DeclarationObjectPredicate, ...]
    minimum: int = 1
    maximum: int | None = None
    exclude_source: bool = False
    compare_player: DeclarationConditionPlayer | None = None

    def __post_init__(self) -> None:
        if not self.predicates_any:
            raise ValueError("A battlefield condition requires a predicate")
        if self.minimum < 0:
            raise ValueError("A battlefield condition minimum cannot be negative")
        if self.maximum is not None and self.maximum < self.minimum:
            raise ValueError("A battlefield condition maximum is below its minimum")
        if self.compare_player is not None and (
            self.minimum != 1 or self.maximum is not None
        ):
            raise ValueError("A comparative condition cannot set a count range")

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "battlefield_count",
            "player": self.player,
            "predicates_any": [
                predicate.to_dict() for predicate in self.predicates_any
            ],
            "minimum": self.minimum,
            "maximum": self.maximum,
            "exclude_source": self.exclude_source,
            "compare_player": self.compare_player,
        }


@dataclass(frozen=True, slots=True)
class DeclarationCombatCondition:
    """A declaration-history condition available from the current combat."""

    kind: Literal["attacking_alone"]

    def __post_init__(self) -> None:
        if self.kind != "attacking_alone":
            raise ValueError(
                f"Unknown declaration combat condition {self.kind!r}"
            )

    def to_dict(self) -> dict[str, object]:
        return {"kind": self.kind}


@dataclass(frozen=True, slots=True)
class DeclarationSharedSubtypeCondition:
    """Require one public creature subtype to occur on enough permanents."""

    player: DeclarationConditionPlayer
    minimum: int

    def __post_init__(self) -> None:
        if self.minimum < 1:
            raise ValueError(
                "A shared-subtype condition requires a positive minimum"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": "shared_creature_subtype_count",
            "player": self.player,
            "minimum": self.minimum,
        }


DeclarationCondition = (
    DeclarationBattlefieldCondition
    | DeclarationCombatCondition
    | DeclarationSharedSubtypeCondition
)


@dataclass(frozen=True, slots=True)
class DeclarationRestrictionTemplate:
    """A reviewed whole-line static declaration-restriction template."""

    template_id: str
    declarations: tuple[DeclarationKind, ...]
    scope: DeclarationRestrictionScope
    mode: DeclarationRestrictionMode = "prohibit"
    count: int = 0
    subject: DeclarationObjectPredicate = DeclarationObjectPredicate()
    opposing: DeclarationObjectPredicate = DeclarationObjectPredicate()
    matching: DeclarationObjectPredicate = DeclarationObjectPredicate()
    condition: DeclarationCondition | None = None
    applies_when_condition: bool = True
    option_relation: Literal["source_controller"] | None = None
    includes_planeswalkers: bool = False

    @property
    def mechanics(self) -> tuple[str, ...]:
        mechanics: list[str] = []
        if "attack" in self.declarations:
            mechanics.append("cr-508-declare-attackers-step")
        if "block" in self.declarations:
            mechanics.append("cr-509-declare-blockers-step")
        return tuple(mechanics)

    def effect(self) -> dict[str, object]:
        return {
            "op": "declaration_restriction",
            "declarations": list(self.declarations),
            "scope": self.scope,
            "mode": self.mode,
            "count": self.count,
            "subject": self.subject.to_dict(),
            "opposing": self.opposing.to_dict(),
            "matching": self.matching.to_dict(),
            "condition": (
                self.condition.to_dict() if self.condition is not None else None
            ),
            "applies_when_condition": self.applies_when_condition,
            "option_relation": self.option_relation,
            "includes_planeswalkers": self.includes_planeswalkers,
        }


@dataclass(frozen=True, slots=True)
class DeclarationRestrictionParse:
    """Exact, unresolved, or unrelated static restriction text."""

    recognized: bool
    template: DeclarationRestrictionTemplate | None = None
    reason: str | None = None
    declarations: tuple[DeclarationKind, ...] = ()
    scope: DeclarationRestrictionScope | None = None

    @property
    def exact(self) -> bool:
        return self.template is not None and self.reason is None


def _matching_creature_filter(text: str) -> DeclarationObjectPredicate | None:
    """Return the creatures named by one exact public filter phrase."""

    phrase = " ".join(text.casefold().split())
    if phrase == "artifact creatures":
        return DeclarationObjectPredicate(types_any=("Artifact",))
    if phrase == "legendary creatures":
        return DeclarationObjectPredicate(supertypes_any=("Legendary",))
    if phrase == "creature tokens":
        return DeclarationObjectPredicate(token=True)
    match = re.fullmatch(
        r"(?P<colors>white|blue|black|red|green)"
        r"(?: and/or (?P<second>white|blue|black|red|green))? creatures",
        phrase,
    )
    if match:
        colors = [match.group("colors")]
        if match.group("second"):
            colors.append(match.group("second"))
        return DeclarationObjectPredicate(
            colors_any=tuple(_COLORS[color] for color in colors)
        )
    match = re.fullmatch(
        r"creatures with (?P<keywords>[a-z-]+(?: or [a-z-]+)*)",
        phrase,
    )
    if match:
        keywords = tuple(match.group("keywords").split(" or "))
        if all(keyword in _FILTER_KEYWORDS for keyword in keywords):
            return DeclarationObjectPredicate(
                keywords_any=tuple(keyword.title() for keyword in keywords)
            )
        return None
    match = re.fullmatch(r"non-(?P<subtype>[a-z'-]+) creatures", phrase)
    if match:
        return DeclarationObjectPredicate(
            subtypes_none=(match.group("subtype").title(),)
        )
    match = re.fullmatch(
        r"creatures with (?P<stat>power|toughness) (?P<count>\d+) "
        r"or (?P<direction>greater|less)",
        phrase,
    )
    if match:
        operator: PowerOperator = (
            "ge" if match.group("direction") == "greater" else "le"
        )
        return DeclarationObjectPredicate(
            stat=StatComparison(
                match.group("stat"),
                operator,
                "fixed",
                int(match.group("count")),
            )
        )
    # Bare subtype filters use plural subtype nouns ("Humans", "Oxen", or
    # "Eldrazi Scions").  Do not interpret arbitrary prose ending in a word
    # such as "controls" as a subtype phrase.
    if {"creature", "creatures"}.intersection(phrase.split()):
        return None
    atoms = phrase.split(" or ")
    if all(
        re.fullmatch(r"[a-z][a-z'-]*(?: [a-z][a-z'-]*)?", atom)
        and (
            atom.split()[-1].endswith("s")
            or atom.split()[-1] in _IRREGULAR_SUBTYPE_PLURALS
        )
        for atom in atoms
    ):
        subtypes = tuple(_singular_subtype(value) for value in atoms)
        if all(subtypes):
            return DeclarationObjectPredicate(subtypes_any=subtypes)
    return None


def _controlled_object_atom(text: str) -> DeclarationObjectPredicate | None:
    """Parse one exact permanent-description atom after ``controls``."""

    phrase = " ".join(text.casefold().split())
    phrase = re.sub(r"^(?:a|an) ", "", phrase)
    if phrase == "permanent":
        return DeclarationObjectPredicate()
    if phrase == "enchanted permanent":
        return DeclarationObjectPredicate(enchanted=True)

    match = re.fullmatch(r"(?P<power>\d+)/(?P<toughness>\d+) creature", phrase)
    if match:
        return DeclarationObjectPredicate(
            types_any=("Creature",),
            stat=StatComparison(
                "power", "eq", "fixed", int(match.group("power"))
            ),
            additional_stats=(
                StatComparison(
                    "toughness",
                    "eq",
                    "fixed",
                    int(match.group("toughness")),
                ),
            ),
        )

    match = re.fullmatch(
        r"(?P<tapped>untapped )?creature with "
        r"(?P<stat>power|toughness) (?P<count>\d+) or "
        r"(?P<direction>greater|less)",
        phrase,
    )
    if match:
        operator: PowerOperator = (
            "ge" if match.group("direction") == "greater" else "le"
        )
        return DeclarationObjectPredicate(
            types_any=("Creature",),
            stat=StatComparison(
                match.group("stat"),
                operator,
                "fixed",
                int(match.group("count")),
            ),
            tapped=False if match.group("tapped") else None,
        )

    match = re.fullmatch(
        r"creature with (?P<keyword>[a-z][a-z-]*)", phrase
    )
    if match and match.group("keyword") in _FILTER_KEYWORDS:
        return DeclarationObjectPredicate(
            types_any=("Creature",),
            keywords_any=(match.group("keyword").title(),),
        )

    match = re.fullmatch(
        r"(?P<tapped>untapped )?(?P<supertype>snow )?"
        r"(?P<type>artifact|creature|enchantment|land)",
        phrase,
    )
    if match:
        return DeclarationObjectPredicate(
            types_any=(match.group("type").title(),),
            supertypes_any=("Snow",) if match.group("supertype") else (),
            tapped=False if match.group("tapped") else None,
        )

    match = re.fullmatch(
        r"(?P<color>white|blue|black|red|green) permanent", phrase
    )
    if match:
        return DeclarationObjectPredicate(
            colors_any=(_COLORS[match.group("color")],)
        )

    # A remaining one- or two-word noun is a subtype. Longer prose and words
    # belonging to condition grammar are rejected rather than guessed.
    if re.fullmatch(r"[a-z][a-z'-]*(?: [a-z][a-z'-]*)?", phrase) and not {
        "more",
        "most",
        "player",
        "controls",
    }.intersection(phrase.split()):
        return DeclarationObjectPredicate(subtypes_any=(phrase.title(),))
    return None


def _battlefield_condition(
    player: DeclarationConditionPlayer,
    text: str,
) -> DeclarationBattlefieldCondition | None:
    """Compile one exact battlefield-count condition from Oracle prose."""

    phrase = " ".join(text.casefold().split())
    comparison = re.fullmatch(
        r"more (?P<type>creatures|lands) than "
        r"(?P<player>defending|attacking) player",
        phrase,
    )
    if comparison:
        return DeclarationBattlefieldCondition(
            player=player,
            predicates_any=(
                DeclarationObjectPredicate(
                    types_any=(comparison.group("type")[:-1].title(),)
                ),
            ),
            compare_player=(
                "defending_player"
                if comparison.group("player") == "defending"
                else "attacking_player"
            ),
        )

    minimum = re.fullmatch(
        r"(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+) "
        r"or more (?P<type>creatures|lands)",
        phrase,
    )
    if minimum:
        return DeclarationBattlefieldCondition(
            player=player,
            predicates_any=(
                DeclarationObjectPredicate(
                    types_any=(minimum.group("type")[:-1].title(),)
                ),
            ),
            minimum=_number(minimum.group("count")),
        )

    exclude_source = phrase.startswith("another ")
    if exclude_source:
        phrase = phrase.removeprefix("another ")

    # Do not split the "or greater/less" portion of a stat comparison.
    if re.search(r"\b(?:power|toughness) \d+ or (?:greater|less)$", phrase):
        atoms = (phrase,)
    else:
        atoms = tuple(
            re.sub(r"^(?:a|an) ", "", atom.strip())
            for atom in phrase.split(" or ")
        )
    predicates = tuple(
        predicate
        for atom in atoms
        if (predicate := _controlled_object_atom(atom)) is not None
    )
    if len(predicates) != len(atoms):
        return None
    return DeclarationBattlefieldCondition(
        player=player,
        predicates_any=predicates,
        exclude_source=exclude_source,
    )


def _nonmatching_creature_filter(text: str) -> DeclarationObjectPredicate | None:
    """Return creatures outside an exact allowed-blocker union."""

    phrase = " ".join(text.casefold().split())
    parts = phrase.split(" and/or ")
    predicates: list[DeclarationObjectPredicate] = []
    if len(parts) > 1:
        for part in parts:
            predicate = _matching_creature_filter(part)
            if predicate is None:
                return None
            predicates.append(predicate)
    else:
        predicate = _matching_creature_filter(phrase)
        if predicate is None:
            return None
        predicates.append(predicate)

    types_any: list[str] = []
    types_none: list[str] = []
    supertypes_any: list[str] = []
    supertypes_none: list[str] = []
    subtypes_any: list[str] = []
    subtypes_none: list[str] = []
    colors_any: list[str] = []
    colors_none: list[str] = []
    keywords_any: list[str] = []
    keywords_none: list[str] = []
    token: bool | None = None
    for predicate in predicates:
        if predicate.types_any:
            types_none.extend(predicate.types_any)
        elif predicate.types_none:
            types_any.extend(predicate.types_none)
        elif predicate.supertypes_any:
            supertypes_none.extend(predicate.supertypes_any)
        elif predicate.supertypes_none:
            supertypes_any.extend(predicate.supertypes_none)
        elif predicate.subtypes_any:
            subtypes_none.extend(predicate.subtypes_any)
        elif predicate.subtypes_none:
            subtypes_any.extend(predicate.subtypes_none)
        elif predicate.colors_any:
            colors_none.extend(predicate.colors_any)
        elif predicate.colors_none:
            colors_any.extend(predicate.colors_none)
        elif predicate.keywords_any:
            keywords_none.extend(predicate.keywords_any)
        elif predicate.keywords_none:
            keywords_any.extend(predicate.keywords_none)
        elif predicate.token is True and len(predicates) == 1:
            token = False
        else:
            return None
    return DeclarationObjectPredicate(
        types_any=tuple(types_any),
        types_none=tuple(types_none),
        supertypes_any=tuple(supertypes_any),
        supertypes_none=tuple(supertypes_none),
        subtypes_any=tuple(subtypes_any),
        subtypes_none=tuple(subtypes_none),
        colors_any=tuple(colors_any),
        colors_none=tuple(colors_none),
        keywords_any=tuple(keywords_any),
        keywords_none=tuple(keywords_none),
        token=token,
    )


def _matching_companion_filter(text: str) -> DeclarationObjectPredicate | None:
    phrase = " ".join(text.casefold().split())
    if phrase == "a creature with greater power":
        return DeclarationObjectPredicate(
            stat=StatComparison("power", "gt", "source")
        )
    match = re.fullmatch(
        r"a (?P<first>white|blue|black|red|green) or "
        r"(?P<second>white|blue|black|red|green) creature",
        phrase,
    )
    if match:
        return DeclarationObjectPredicate(
            colors_any=(
                _COLORS[match.group("first")],
                _COLORS[match.group("second")],
            )
        )
    return None


def _global_attacker_filter(
    text: str | None,
) -> DeclarationObjectPredicate | None:
    if not text:
        return DeclarationObjectPredicate()
    phrase = " ".join(text.casefold().split())
    if phrase.startswith("without "):
        keyword = phrase.removeprefix("without ")
        if keyword in _FILTER_KEYWORDS:
            return DeclarationObjectPredicate(keywords_none=(keyword.title(),))
        return None
    if phrase.startswith("with "):
        return _matching_creature_filter(f"creatures {phrase}")
    return None


def parse_declaration_restriction_line(
    text: str,
    *,
    card_name: str = "",
) -> DeclarationRestrictionParse:
    """Parse reviewed static CR 508.1c/509.1b Oracle sentence families.

    The parser is deliberately whole-line and shared by runtime and Oracle IR.
    Static-looking mutations in a recognized family become material residuals;
    triggered, activated, and resolving one-shot text is left to its own
    semantic compiler instead of being mistaken for a battlefield restriction.
    Declaration costs are owned by ``declaration_costs`` and are not duplicated.
    """

    line = normalized_oracle_line(text, card_name=card_name)
    ability_word = _ABILITY_WORD_PREFIX.fullmatch(line)
    if ability_word:
        line = ability_word.group("body")

    if parse_declaration_cost_line(line).recognized:
        return DeclarationRestrictionParse(False)

    match = _SELF_OTHER_DECLARATIONS.fullmatch(line)
    if match and match.group("kind") == match.group("verb"):
        declarations = _declarations(match.group("kind"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-other-declarations-minimum-v1",
                declarations=declarations,
                scope="self",
                mode="minimum_total_selections",
                count=_number(match.group("count")) + 1,
            ),
            declarations=declarations,
            scope="self",
        )

    match = _SELF_MATCHING_COMPANION.fullmatch(line)
    expected_verb = (
        "attacks"
        if match is not None and match.group("kind") == "attack"
        else "blocks"
    )
    if match and match.group("verb") == expected_verb:
        matching = _matching_companion_filter(match.group("filter"))
        if matching is not None:
            declarations = _declarations(match.group("kind"))
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="intrinsic-matching-companion-minimum-v1",
                    declarations=declarations,
                    scope="self",
                    mode="minimum_matching_selections",
                    count=1,
                    matching=matching,
                ),
                declarations=declarations,
                scope="self",
            )

    if _SELF_ATTACKING_ALONE_EVASION.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-attacking-alone-evasion-v1",
                declarations=("block",),
                scope="source_option",
                condition=DeclarationCombatCondition("attacking_alone"),
            ),
            declarations=("block",),
            scope="source_option",
        )

    if _ATTACHED_ATTACKING_ALONE_EVASION.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="attached-attacking-alone-evasion-v1",
                declarations=("block",),
                scope="attached_option",
                condition=DeclarationCombatCondition("attacking_alone"),
            ),
            declarations=("block",),
            scope="attached_option",
        )

    if _SELF_NO_OTHER_CREATURE_EVASION.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-no-other-creature-evasion-v1",
                declarations=("block",),
                scope="source_option",
                condition=DeclarationBattlefieldCondition(
                    player="source_controller",
                    predicates_any=(
                        DeclarationObjectPredicate(types_any=("Creature",)),
                    ),
                    minimum=0,
                    maximum=0,
                    exclude_source=True,
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SOURCE_CONTROLLER_ATTACK_MAXIMUM.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="source-controller-attack-maximum-v1",
                declarations=("attack",),
                scope="global",
                mode="maximum_option_uses",
                count=_number(match.group("count")),
                option_relation="source_controller",
            ),
            declarations=("attack",),
            scope="global",
        )

    match = _SOURCE_ATTACK_MAXIMUM.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="source-attack-maximum-v1",
                declarations=("attack",),
                scope="source_option",
                mode="maximum_option_uses",
                count=_number(match.group("count")),
            ),
            declarations=("attack",),
            scope="source_option",
        )

    match = _SELF_SHARED_SUBTYPE_BLOCK_CONDITION.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    "intrinsic-defending-player-shared-subtype-"
                    "block-unless-v1"
                ),
                declarations=("block",),
                scope="source_option",
                condition=DeclarationSharedSubtypeCondition(
                    player="defending_player",
                    minimum=_number(match.group("count")),
                ),
                applies_when_condition=False,
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _GLOBAL_SOURCE_CONTROLLER_ATTACK_BLOCK.fullmatch(line)
    if match and match.group("keyword") in _FILTER_KEYWORDS:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="global-source-controller-attack-block-v1",
                declarations=("attack", "block"),
                scope="global",
                subject=DeclarationObjectPredicate(
                    keywords_any=(match.group("keyword").title(),)
                ),
                option_relation="source_controller",
            ),
            declarations=("attack", "block"),
            scope="global",
        )

    match = _GLOBAL_SOURCE_CONTROLLER_ATTACK.fullmatch(line)
    if match:
        subject = _global_attacker_filter(match.group("filter"))
        if subject is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="global-source-controller-attack-v1",
                    declarations=("attack",),
                    scope="global",
                    subject=subject,
                    option_relation="source_controller",
                    includes_planeswalkers=bool(match.group("planeswalkers")),
                ),
                declarations=("attack",),
                scope="global",
            )

    match = _ATTACHED_SOURCE_CONTROLLER_ATTACK.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="attached-source-controller-attack-v1",
                declarations=("attack",),
                scope="attached",
                option_relation="source_controller",
                includes_planeswalkers=bool(match.group("planeswalkers")),
            ),
            declarations=("attack",),
            scope="attached",
        )

    match = _SELF_BATTLEFIELD_CONDITION.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        player: DeclarationConditionPlayer = (
            "source_controller"
            if match.group("source")
            else "defending_player"
        )
        condition = _battlefield_condition(player, match.group("filter"))
        if condition is not None:
            role = (
                "controller"
                if player == "source_controller"
                else "defending-player"
            )
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id=(
                        f"intrinsic-{role}-battlefield-"
                        f"{'-'.join(declarations)}-{match.group('link')}-v1"
                    ),
                    declarations=declarations,
                    scope="self",
                    condition=condition,
                    applies_when_condition=(match.group("link") == "if"),
                ),
                declarations=declarations,
                scope="self",
            )

    match = _SELF_CONDITIONAL_BLOCKER_FILTER.fullmatch(line)
    if match:
        subject = _matching_creature_filter(match.group("blockers"))
        condition = _battlefield_condition(
            "defending_player", match.group("condition")
        )
        if subject is not None and condition is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id=(
                        "intrinsic-defending-player-conditional-"
                        "blocker-filter-v1"
                    ),
                    declarations=("block",),
                    scope="source_option",
                    subject=subject,
                    condition=condition,
                ),
                declarations=("block",),
                scope="source_option",
            )

    match = _SELF_CONDITIONAL_UNBLOCKABLE.fullmatch(line)
    if match:
        condition = _battlefield_condition(
            "defending_player", match.group("condition")
        )
        if condition is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id=(
                        "intrinsic-defending-player-conditional-"
                        "unblockable-v1"
                    ),
                    declarations=("block",),
                    scope="source_option",
                    condition=condition,
                ),
                declarations=("block",),
                scope="source_option",
            )

    match = _SELF_PROHIBITION.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    "intrinsic-" + "-".join(declarations) + "-prohibition-v1"
                ),
                declarations=declarations,
                scope="self",
            ),
            declarations=declarations,
            scope="self",
        )

    match = _ATTACHED_PROHIBITION.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    "attached-" + "-".join(declarations) + "-prohibition-v1"
                ),
                declarations=declarations,
                scope="attached",
            ),
            declarations=declarations,
            scope="attached",
        )

    match = _GLOBAL_PROHIBITION.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    "global-" + "-".join(declarations) + "-prohibition-v1"
                ),
                declarations=declarations,
                scope="global",
            ),
            declarations=declarations,
            scope="global",
        )

    match = _SELF_NOT_ALONE.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    "intrinsic-" + "-".join(declarations) + "-not-alone-v1"
                ),
                declarations=declarations,
                scope="self",
                mode="minimum_total_selections",
                count=2,
            ),
            declarations=declarations,
            scope="self",
        )

    match = _GLOBAL_MAXIMUM.fullmatch(line)
    if match:
        declarations = _declarations(match.group("kind"))
        count = _number(match.group("count"))
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id=(
                    f"global-maximum-{count}-{declarations[0]}-v1"
                ),
                declarations=declarations,
                scope="global",
                mode="maximum_total_selections",
                count=count,
            ),
            declarations=declarations,
            scope="global",
        )

    if _GOADED_OPPONENT_BLOCK.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="opponent-goaded-creature-block-prohibition-v1",
                declarations=("block",),
                scope="source_opponents",
                subject=DeclarationObjectPredicate(goaded=True),
            ),
            declarations=("block",),
            scope="source_opponents",
        )

    match = _KEYWORDLESS_GLOBAL_ATTACK.fullmatch(line)
    if match:
        keywords = tuple(
            word.strip().title()
            for word in match.group("keywords").split(" or ")
        )
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="global-keywordless-attack-prohibition-v1",
                declarations=("attack",),
                scope="global",
                subject=DeclarationObjectPredicate(keywords_none=keywords),
            ),
            declarations=("attack",),
            scope="global",
        )

    if _SOURCE_POWER_EVASION.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="source-power-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=DeclarationObjectPredicate(
                    stat=StatComparison("power", "lt", "source")
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_FIXED_POWER_BLOCK.fullmatch(line)
    if match:
        operator: PowerOperator = (
            "ge" if match.group("direction") == "greater" else "le"
        )
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-fixed-power-block-prohibition-v1",
                declarations=("block",),
                scope="self",
                opposing=DeclarationObjectPredicate(
                    stat=StatComparison(
                        "power",
                        operator,
                        "fixed",
                        int(match.group("count")),
                    )
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    if _SELF_BLOCK_SOURCE_POWER.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-source-power-block-prohibition-v1",
                declarations=("block",),
                scope="self",
                opposing=DeclarationObjectPredicate(
                    stat=StatComparison("power", "gt", "source")
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    if _SELF_UNBLOCKABLE.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-unblockable-v1",
                declarations=("block",),
                scope="source_option",
            ),
            declarations=("block",),
            scope="source_option",
        )

    if _ATTACHED_UNBLOCKABLE.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="attached-unblockable-v1",
                declarations=("block",),
                scope="attached_option",
            ),
            declarations=("block",),
            scope="attached_option",
        )

    if _SELF_BLOCKED_BY_GREATER_POWER.fullmatch(line):
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-source-stat-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=DeclarationObjectPredicate(
                    stat=StatComparison("power", "gt", "source")
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_BY_POWER.fullmatch(line)
    if match:
        operator = "ge" if match.group("direction") == "greater" else "le"
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-blocker-stat-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=DeclarationObjectPredicate(
                    stat=StatComparison(
                        match.group("stat"),
                        operator,
                        "fixed",
                        int(match.group("count")),
                    )
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_BY_COLOR.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-blocker-color-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=DeclarationObjectPredicate(
                    colors_any=(_COLORS[match.group("color")],)
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_BY_SUBTYPE.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-blocker-subtype-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=DeclarationObjectPredicate(
                    subtypes_any=(match.group("subtype").title(),)
                ),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_BY_MORE_THAN.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-maximum-blockers-v1",
                declarations=("block",),
                scope="source_option",
                mode="maximum_option_uses",
                count=_number(match.group("count")),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_EXCEPT_COUNT.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-minimum-blockers-v1",
                declarations=("block",),
                scope="source_option",
                mode="minimum_option_uses",
                count=_number(match.group("count")),
            ),
            declarations=("block",),
            scope="source_option",
        )

    match = _SELF_BLOCKED_BY_FILTER.fullmatch(line)
    if match:
        predicate = _matching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="intrinsic-blocker-filter-evasion-v1",
                    declarations=("block",),
                    scope="source_option",
                    subject=predicate,
                ),
                declarations=("block",),
                scope="source_option",
            )

    match = _ATTACHED_BLOCKED_BY_FILTER.fullmatch(line)
    if match:
        predicate = _matching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="attached-blocker-filter-evasion-v1",
                    declarations=("block",),
                    scope="attached_option",
                    subject=predicate,
                ),
                declarations=("block",),
                scope="attached_option",
            )

    match = _SELF_BLOCKED_EXCEPT_FILTER.fullmatch(line)
    if match:
        predicate = _nonmatching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="intrinsic-allowed-blocker-filter-v1",
                    declarations=("block",),
                    scope="source_option",
                    subject=predicate,
                ),
                declarations=("block",),
                scope="source_option",
            )

    match = _ATTACHED_BLOCKED_EXCEPT_FILTER.fullmatch(line)
    if match:
        predicate = _nonmatching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="attached-allowed-blocker-filter-v1",
                    declarations=("block",),
                    scope="attached_option",
                    subject=predicate,
                ),
                declarations=("block",),
                scope="attached_option",
            )

    match = _SELF_CAN_BLOCK_ONLY_KEYWORD.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-block-only-keyword-v1",
                declarations=("block",),
                scope="self",
                opposing=DeclarationObjectPredicate(
                    keywords_none=(match.group("keyword").title(),)
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    match = _ATTACHED_CAN_BLOCK_ONLY_FILTER.fullmatch(line)
    if match:
        predicate = _nonmatching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="attached-block-only-filter-v1",
                    declarations=("block",),
                    scope="attached",
                    opposing=predicate,
                ),
                declarations=("block",),
                scope="attached",
            )

    match = _SELF_COLOR_BLOCK.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-color-block-prohibition-v1",
                declarations=("block",),
                scope="self",
                opposing=DeclarationObjectPredicate(
                    colors_any=(_COLORS[match.group("color")],)
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    match = _SELF_BLOCK_FILTER.fullmatch(line)
    if match:
        predicate = _matching_creature_filter(match.group("filter"))
        if predicate is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="intrinsic-block-filter-prohibition-v1",
                    declarations=("block",),
                    scope="self",
                    opposing=predicate,
                ),
                declarations=("block",),
                scope="self",
            )

    match = _GLOBAL_CAN_BLOCK_ONLY_FILTER.fullmatch(line)
    if match and not match.group("subject").startswith(
        ("this creature", "enchanted creature")
    ):
        subject = _matching_creature_filter(match.group("subject"))
        opposing = _nonmatching_creature_filter(match.group("opposing"))
        if subject is not None and opposing is not None:
            return DeclarationRestrictionParse(
                True,
                DeclarationRestrictionTemplate(
                    template_id="global-block-only-filter-v1",
                    declarations=("block",),
                    scope="global",
                    subject=subject,
                    opposing=opposing,
                ),
                declarations=("block",),
                scope="global",
            )

    match = _SUBTYPE_BLOCK.fullmatch(line)
    if match and match.group("blocker") != "creature":
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="subtype-pair-block-prohibition-v1",
                declarations=("block",),
                scope="global",
                subject=DeclarationObjectPredicate(
                    subtypes_any=(match.group("blocker").title(),)
                ),
                opposing=DeclarationObjectPredicate(
                    subtypes_any=(match.group("attacker").title(),)
                ),
            ),
            declarations=("block",),
            scope="global",
        )

    if _STATIC_RESTRICTION_PREFIX.match(line):
        declarations: list[DeclarationKind] = []
        if "attack" in line:
            declarations.append("attack")
        if "block" in line or "be blocked" in line:
            declarations.append("block")
        scope: DeclarationRestrictionScope = (
            "attached_option"
            if line.startswith("enchanted ") and "be blocked" in line
            else "source_option"
            if "be blocked" in line or line.endswith("block it.")
            else "self"
            if line.startswith("this creature")
            else "attached"
            if line.startswith("enchanted ")
            else "source_opponents"
            if line.startswith("goaded creatures your opponents")
            else "global"
        )
        return DeclarationRestrictionParse(
            True,
            reason="static declaration restriction grammar is unresolved",
            declarations=tuple(dict.fromkeys(declarations)),
            scope=scope,
        )

    return DeclarationRestrictionParse(False)
