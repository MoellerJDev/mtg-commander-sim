from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from ..fixed_damage_set_model import (
    FixedDamageSetSpec,
    PermanentControllerRelation,
    PermanentDamageGroup,
    PlayerDamageGroup,
    PlayerDamageRelation,
)
from ..object_predicate import ObjectQuerySpec


_ABILITY_WORD = re.compile(
    r"^(?P<word>[A-Za-z][A-Za-z ']+)\s+[—-]\s+(?P<body>.+)$"
)
_DAMAGE_QUANTITY_REPLACEMENT = re.compile(
    r"^If (?P<source>.+?) would deal "
    r"(?:(?P<damage_kind>combat|noncombat) )?damage to (?P<target>.+?), "
    r"(?:it|that source) deals double that damage"
    r"(?: to (?:that permanent or player|that player|that player or permanent))? "
    r"instead\.?$",
    re.IGNORECASE,
)
_FIXED_DAMAGE_PREVENTION = re.compile(
    r"^If (?P<source>.+?) would deal "
    r"(?:(?P<damage_kind>combat|noncombat) )?damage to (?P<target>.+?), "
    r"prevent (?P<amount>[1-9][0-9]*) of that damage\.?$",
    re.IGNORECASE,
)
_REDIRECT_TO_SOURCE = re.compile(
    r"^All damage that would be dealt to you"
    r"(?P<permanents> and other permanents you control)? is dealt to "
    r"this (?:creature|permanent) instead\.?$",
    re.IGNORECASE,
)


class FixedDamageRecipient(str, Enum):
    """Closed recipient vocabulary for fixed direct-damage instructions."""

    ANY_TARGET = "any_target"
    CREATURE = "creature"
    CREATURE_OR_PLANESWALKER = "creature_or_planeswalker"
    PLAYER = "player"
    OPPONENT = "opponent"
    PLAYER_OR_PLANESWALKER = "player_or_planeswalker"
    OPPONENT_OR_PLANESWALKER = "opponent_or_planeswalker"
    EACH_OPPONENT = "each_opponent"


_FIXED_DAMAGE_RECIPIENTS: tuple[tuple[str, FixedDamageRecipient], ...] = (
    ("target creature or planeswalker", FixedDamageRecipient.CREATURE_OR_PLANESWALKER),
    ("target player or planeswalker", FixedDamageRecipient.PLAYER_OR_PLANESWALKER),
    ("target opponent or planeswalker", FixedDamageRecipient.OPPONENT_OR_PLANESWALKER),
    ("target creature", FixedDamageRecipient.CREATURE),
    ("target player", FixedDamageRecipient.PLAYER),
    ("target opponent", FixedDamageRecipient.OPPONENT),
    ("any target", FixedDamageRecipient.ANY_TARGET),
    ("each opponent", FixedDamageRecipient.EACH_OPPONENT),
)
_FIXED_DAMAGE_SOURCE_KINDS = (
    "artifact",
    "battle",
    "creature",
    "enchantment",
    "land",
    "permanent",
    "planeswalker",
    "spell",
)


@dataclass(frozen=True, slots=True)
class FixedDamageEffectTemplate:
    """Typed lowering result for one positive fixed-damage instruction."""

    amount: int
    recipient: FixedDamageRecipient
    source_kind: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise ValueError("Fixed damage amount must be an integer")
        if self.amount <= 0:
            raise ValueError("Fixed damage amount must be positive")
        if not isinstance(self.recipient, FixedDamageRecipient):
            raise ValueError("Fixed damage recipient is unsupported")
        if self.source_kind is not None and self.source_kind not in (
            *_FIXED_DAMAGE_SOURCE_KINDS,
            "named",
        ):
            raise ValueError("Fixed damage source kind is unsupported")

    @property
    def template_id(self) -> str:
        if self.recipient is FixedDamageRecipient.ANY_TARGET:
            if self.source_kind not in {None, "named", "spell"}:
                return f"damage-any-target-self-{self.source_kind}-v1"
            return "damage-any-target-v1"
        return f"damage-{self.recipient.value.replace('_', '-')}-v1"

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        if self.recipient is FixedDamageRecipient.EACH_OPPONENT:
            return (
                {
                    "op": "damage_each_opponent",
                    "source": "$source",
                    "amount": self.amount,
                },
            )
        return (
            {
                "op": "damage",
                "source": "$source",
                "target": "$target.0",
                "amount": self.amount,
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any] | None:
        if self.recipient is FixedDamageRecipient.EACH_OPPONENT:
            return None
        if self.recipient is FixedDamageRecipient.ANY_TARGET:
            return {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            }
        if self.recipient is FixedDamageRecipient.CREATURE:
            return {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_any": ["creature"],
                "count": 1,
            }
        if self.recipient is FixedDamageRecipient.CREATURE_OR_PLANESWALKER:
            return {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_any": ["creature", "planeswalker"],
                "count": 1,
            }
        if self.recipient in {
            FixedDamageRecipient.PLAYER_OR_PLANESWALKER,
            FixedDamageRecipient.OPPONENT_OR_PLANESWALKER,
        }:
            schema: dict[str, Any] = {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "player_or_planeswalker",
                "count": 1,
            }
            if self.recipient is FixedDamageRecipient.OPPONENT_OR_PLANESWALKER:
                schema["player_relation"] = "opponent"
            return schema
        schema = {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
        }
        if self.recipient is FixedDamageRecipient.OPPONENT:
            schema["player_relation"] = "opponent"
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        if self.recipient is FixedDamageRecipient.EACH_OPPONENT:
            return ("cr-120-damage",)
        return ("cr-120-damage", "cr-115-targets")

    def compiled(
        self,
    ) -> tuple[
        str,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any] | None,
        tuple[str, ...],
    ]:
        return (
            self.template_id,
            self.effects,
            self.target_schema,
            self.mechanics,
        )


@dataclass(frozen=True, slots=True)
class FixedMassDamageEffectTemplate:
    """Typed lowering for one fixed simultaneous affected-set instruction."""

    amount: int
    spec: FixedDamageSetSpec
    source_kind: str | None = None
    target_opponent: bool = False

    def __post_init__(self) -> None:
        if type(self.amount) is not int or self.amount <= 0:
            raise ValueError("Fixed mass damage amount must be positive")
        if not isinstance(self.spec, FixedDamageSetSpec):
            raise ValueError("Fixed mass damage requires a typed recipient set")
        if self.source_kind is not None and self.source_kind not in (
            *_FIXED_DAMAGE_SOURCE_KINDS,
            "named",
        ):
            raise ValueError("Fixed mass damage source kind is unsupported")
        if type(self.target_opponent) is not bool:
            raise ValueError("Fixed mass target marker must be boolean")

    @property
    def template_id(self) -> str:
        return (
            "damage-fixed-target-opponent-controlled-set-v1"
            if self.target_opponent
            else "damage-fixed-simultaneous-set-v1"
        )

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "op": "damage_fixed_set",
                "source": "$source",
                "amount": self.amount,
                "groups": self.spec.to_dict()["groups"],
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any] | None:
        if not self.target_opponent:
            return None
        return {
            "zones": ["player"],
            "categories": ["player"],
            "player_relation": "opponent",
            "count": 1,
        }

    @property
    def mechanics(self) -> tuple[str, ...]:
        return (
            ("cr-120-damage", "cr-115-targets")
            if self.target_opponent
            else ("cr-120-damage",)
        )

    def compiled(
        self,
    ) -> tuple[
        str,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any] | None,
        tuple[str, ...],
    ]:
        return (
            self.template_id,
            self.effects,
            self.target_schema,
            self.mechanics,
        )


def _permanent_group(
    *,
    types_all: tuple[str, ...] = (),
    types_any: tuple[str, ...] = (),
    excluded_types: tuple[str, ...] = (),
    colors_any: tuple[str, ...] = (),
    keywords_all: tuple[str, ...] = (),
    token: bool | None = None,
    controller_relation: PermanentControllerRelation = (
        PermanentControllerRelation.ANY
    ),
    target_controller: str | None = None,
) -> PermanentDamageGroup:
    return PermanentDamageGroup(
        query=ObjectQuerySpec(
            zones=("battlefield",),
            types_all=types_all,
            types_any=types_any,
            excluded_types=excluded_types,
            colors_any=colors_any,
            keywords_all=keywords_all,
            token=token,
        ),
        controller_relation=controller_relation,
        target_controller=target_controller,
    )


_COLOR_WORDS = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}


def _fixed_mass_damage_spec(
    recipient_text: str,
) -> tuple[FixedDamageSetSpec, bool] | None:
    normalized = " ".join(recipient_text.casefold().split())
    exact: dict[str, tuple[object, ...]] = {
        "each creature": (_permanent_group(types_all=("creature",)),),
        "each player": (PlayerDamageGroup(PlayerDamageRelation.ALL),),
        "each creature and each player": (
            _permanent_group(types_all=("creature",)),
            PlayerDamageGroup(PlayerDamageRelation.ALL),
        ),
        "each creature and each planeswalker": (
            _permanent_group(types_any=("creature", "planeswalker")),
        ),
        "each opponent and each creature they control": (
            PlayerDamageGroup(PlayerDamageRelation.OPPONENTS),
            _permanent_group(
                types_all=("creature",),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each opponent and each creature and planeswalker they control": (
            PlayerDamageGroup(PlayerDamageRelation.OPPONENTS),
            _permanent_group(
                types_any=("creature", "planeswalker"),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each opponent and each creature and each planeswalker they control": (
            PlayerDamageGroup(PlayerDamageRelation.OPPONENTS),
            _permanent_group(
                types_any=("creature", "planeswalker"),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each creature opponents control": (
            _permanent_group(
                types_all=("creature",),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each creature your opponents control": (
            _permanent_group(
                types_all=("creature",),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each creature and planeswalker your opponents control": (
            _permanent_group(
                types_any=("creature", "planeswalker"),
                controller_relation=PermanentControllerRelation.OPPONENTS,
            ),
        ),
        "each creature with flying": (
            _permanent_group(
                types_all=("creature",), keywords_all=("flying",)
            ),
        ),
        "each nonartifact creature": (
            _permanent_group(
                types_all=("creature",), excluded_types=("artifact",)
            ),
        ),
        "each nontoken creature": (
            _permanent_group(types_all=("creature",), token=False),
        ),
        "each creature with shadow": (
            _permanent_group(
                types_all=("creature",), keywords_all=("shadow",)
            ),
        ),
    }
    if normalized in exact:
        return FixedDamageSetSpec(exact[normalized]), False
    if normalized == "each creature target opponent controls":
        return (
            FixedDamageSetSpec(
                (
                    _permanent_group(
                        types_all=("creature",),
                        controller_relation=(
                            PermanentControllerRelation.TARGET_PLAYER
                        ),
                        target_controller="$target.0",
                    ),
                )
            ),
            True,
        )
    color_match = re.fullmatch(
        r"each (?P<colors>white|blue|black|red|green)"
        r"(?: and/or (?P<second>white|blue|black|red|green))? creature",
        normalized,
    )
    if color_match is not None:
        colors = tuple(
            _COLOR_WORDS[value]
            for value in (
                color_match.group("colors"),
                color_match.group("second"),
            )
            if value is not None
        )
        if len(colors) != len(set(colors)):
            return None
        return (
            FixedDamageSetSpec(
                (
                    _permanent_group(
                        types_all=("creature",), colors_any=colors
                    ),
                )
            ),
            False,
        )
    return None


def fixed_damage_effect_template(
    text: str,
    *,
    card_name: str,
) -> FixedDamageEffectTemplate | FixedMassDamageEffectTemplate | None:
    """Recognize one whole fixed-damage clause without interpreting riders."""

    source = re.fullmatch(
        rf"(?P<source>{re.escape(card_name)}|this "
        rf"(?P<kind>{'|'.join(_FIXED_DAMAGE_SOURCE_KINDS)})) deals "
        r"(?P<amount>[1-9][0-9]*) damage to (?P<recipient>.+?)\.?",
        text.strip(),
        re.IGNORECASE,
    )
    if source is None:
        return None
    recipient_text = source.group("recipient").casefold()
    fixed_set = _fixed_mass_damage_spec(recipient_text)
    if fixed_set is not None:
        spec, target_opponent = fixed_set
        return FixedMassDamageEffectTemplate(
            amount=int(source.group("amount")),
            spec=spec,
            source_kind=(source.group("kind") or "named").casefold(),
            target_opponent=target_opponent,
        )
    recipient = next(
        (
            value
            for phrase, value in _FIXED_DAMAGE_RECIPIENTS
            if recipient_text == phrase
        ),
        None,
    )
    if recipient is None:
        return None
    return FixedDamageEffectTemplate(
        amount=int(source.group("amount")),
        recipient=recipient,
        source_kind=(source.group("kind") or "named").casefold(),
    )


def _source_condition(phrase: str) -> tuple[str, list[str]] | None:
    normalized = " ".join(phrase.casefold().split())
    exact = {
        "a source": ("any", []),
        "a source you control": ("source_controller", []),
        "a source an opponent controls": ("opponent", []),
        "a creature": ("any", ["creature"]),
        "an artifact": ("any", ["artifact"]),
    }
    if normalized in exact:
        return exact[normalized]
    controlled = re.fullmatch(
        r"(?:a|an) (?P<kind>[a-z][a-z0-9-]*)(?: source)? you control",
        normalized,
    )
    if controlled:
        return "source_controller", [controlled.group("kind")]
    return None


def _target_condition(
    phrase: str,
) -> tuple[str, list[str], list[str]] | None:
    normalized = " ".join(phrase.casefold().split())
    exact = {
        "a permanent or player": ("any", [], []),
        "a player or permanent": ("any", [], []),
        "an opponent": ("opponent", ["player"], []),
        "you": ("source_controller", ["player"], []),
        "an opponent or a permanent an opponent controls": (
            "opponent",
            [],
            [],
        ),
        "you or a permanent you control": (
            "source_controller",
            [],
            [],
        ),
        "a permanent an opponent controls": (
            "opponent",
            ["permanent"],
            [],
        ),
    }
    if normalized in exact:
        return exact[normalized]
    controlled = re.fullmatch(
        r"(?:a|an) (?:(?P<qualifier>[a-z][a-z0-9-]*) )?"
        r"(?P<kind>creature|planeswalker|battle|permanent) you control",
        normalized,
    )
    if controlled:
        types = [controlled.group("kind")]
        if controlled.group("qualifier"):
            types.append(controlled.group("qualifier"))
        return "source_controller", ["permanent"], types
    ordinary = re.fullmatch(
        r"(?:a|an) (?P<kind>creature|planeswalker|battle|permanent|"
        r"[a-z][a-z0-9-]*)",
        normalized,
    )
    if ordinary:
        kind = ordinary.group("kind")
        return "any", ["permanent"], [kind]
    return None


def static_damage_handler(
    text: str,
) -> tuple[str, dict[str, Any], str] | None:
    """Lower a closed static damage/prevention wording family."""

    ability_word = _ABILITY_WORD.match(text)
    normalized = ability_word.group("body") if ability_word else text
    redirection = _REDIRECT_TO_SOURCE.fullmatch(normalized)
    if redirection is not None:
        target_kinds = ["player"]
        if redirection.group("permanents"):
            target_kinds.append("permanent")
        return (
            "damage-redirection-static-to-source-v1",
            {
                "handler_id": "replacement.damage.redirect-to-source.v1",
                "schema_version": 1,
                "event": "damage",
                "condition": {
                    "source_controller_relation": "any",
                    "target_controller_relation": "source_controller",
                    "target_kinds": target_kinds,
                    "source_types_all": [],
                    "target_types_all": [],
                    "combat": None,
                },
                "modification": {"destination": "source"},
            },
            "damage.redirection.static_to_source",
        )
    match = _DAMAGE_QUANTITY_REPLACEMENT.fullmatch(normalized)
    handler_id = "replacement.damage.quantity.v1"
    capability = "damage.replacement.static_quantity"
    modification: dict[str, int] = {"multiplier": 2, "additional": 0}
    template_id = "damage-quantity-double-static-v1"
    if match is None:
        match = _FIXED_DAMAGE_PREVENTION.fullmatch(normalized)
        handler_id = "prevention.damage.fixed.v1"
        capability = "damage.prevention.static_fixed"
        template_id = "damage-prevention-fixed-static-v1"
        if match is None:
            return None
        modification = {"amount": int(match.group("amount"))}
    source = _source_condition(match.group("source"))
    target = _target_condition(match.group("target"))
    if source is None or target is None:
        return None
    source_relation, source_types = source
    target_relation, target_kinds, target_types = target
    damage_kind = match.group("damage_kind")
    return (
        template_id,
        {
            "handler_id": handler_id,
            "schema_version": 1,
            "event": "damage",
            "condition": {
                "source_controller_relation": source_relation,
                "target_controller_relation": target_relation,
                "target_kinds": target_kinds,
                "source_types_all": source_types,
                "target_types_all": target_types,
                "combat": (
                    True
                    if damage_kind and damage_kind.casefold() == "combat"
                    else False
                    if damage_kind
                    else None
                ),
            },
            "modification": modification,
        },
        capability,
    )
