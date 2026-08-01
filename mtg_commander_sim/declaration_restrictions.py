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
    "global",
    "self",
    "source_opponents",
    "source_option",
]
DeclarationRestrictionMode = Literal[
    "prohibit",
    "minimum_total_selections",
    "maximum_total_selections",
    "minimum_option_uses",
    "maximum_option_uses",
]
PowerOperand = Literal["fixed", "source"]
PowerOperator = Literal["lt", "le", "gt", "ge"]
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
    }.get(value, int(value) if value.isdigit() else 0)


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
class CreaturePredicate:
    """Declarative creature filter used by declaration-domain restrictions."""

    types_any: tuple[str, ...] = ()
    types_none: tuple[str, ...] = ()
    subtypes_any: tuple[str, ...] = ()
    subtypes_none: tuple[str, ...] = ()
    colors_any: tuple[str, ...] = ()
    keywords_any: tuple[str, ...] = ()
    keywords_none: tuple[str, ...] = ()
    token: bool | None = None
    goaded: bool | None = None
    stat: StatComparison | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "types_any": list(self.types_any),
            "types_none": list(self.types_none),
            "subtypes_any": list(self.subtypes_any),
            "subtypes_none": list(self.subtypes_none),
            "colors_any": list(self.colors_any),
            "keywords_any": list(self.keywords_any),
            "keywords_none": list(self.keywords_none),
            "token": self.token,
            "goaded": self.goaded,
            "stat": self.stat.to_dict() if self.stat else None,
        }


@dataclass(frozen=True, slots=True)
class DeclarationRestrictionTemplate:
    """A reviewed whole-line static declaration-restriction template."""

    template_id: str
    declarations: tuple[DeclarationKind, ...]
    scope: DeclarationRestrictionScope
    mode: DeclarationRestrictionMode = "prohibit"
    count: int = 0
    subject: CreaturePredicate = CreaturePredicate()
    opposing: CreaturePredicate = CreaturePredicate()

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
                subject=CreaturePredicate(goaded=True),
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
                subject=CreaturePredicate(keywords_none=keywords),
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
                subject=CreaturePredicate(
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
                opposing=CreaturePredicate(
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

    match = _SELF_BLOCKED_BY_POWER.fullmatch(line)
    if match:
        operator = "ge" if match.group("direction") == "greater" else "le"
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-blocker-stat-evasion-v1",
                declarations=("block",),
                scope="source_option",
                subject=CreaturePredicate(
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
                subject=CreaturePredicate(
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
                subject=CreaturePredicate(
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

    match = _SELF_CAN_BLOCK_ONLY_KEYWORD.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-block-only-keyword-v1",
                declarations=("block",),
                scope="self",
                opposing=CreaturePredicate(
                    keywords_none=(match.group("keyword").title(),)
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    match = _SELF_COLOR_BLOCK.fullmatch(line)
    if match:
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="intrinsic-color-block-prohibition-v1",
                declarations=("block",),
                scope="self",
                opposing=CreaturePredicate(
                    colors_any=(_COLORS[match.group("color")],)
                ),
            ),
            declarations=("block",),
            scope="self",
        )

    match = _SUBTYPE_BLOCK.fullmatch(line)
    if match and match.group("blocker") != "creature":
        return DeclarationRestrictionParse(
            True,
            DeclarationRestrictionTemplate(
                template_id="subtype-pair-block-prohibition-v1",
                declarations=("block",),
                scope="global",
                subject=CreaturePredicate(
                    subtypes_any=(match.group("blocker").title(),)
                ),
                opposing=CreaturePredicate(
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
            "source_option"
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
