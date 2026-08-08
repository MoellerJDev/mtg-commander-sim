from __future__ import annotations

"""Closed Oracle lowering for fixed counter-placement effects."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping

from .creature_subtypes import canonical_creature_subtype
from .fixed_numbers import fixed_number


_COUNT = r"a|an|one|two|three|four|five|six|seven|eight|nine|ten|\d+"
_COUNTER_PLURAL = "counter" + "s"
_COUNTER_NAME = (
    r"[+-]\d+/[+-]\d+|"
    r"[A-Za-z][A-Za-z'-]*(?: [A-Za-z][A-Za-z'-]*){0,2}"
)
_PLACEMENT = re.compile(
    rf"put (?P<count>{_COUNT}) (?P<counter>{_COUNTER_NAME}) "
    r"(?P<plural>counter|counters) on (?P<subject>.+?)\.?",
    re.IGNORECASE,
)
_PERMANENT_TYPES = frozenset(
    {
        "artifact",
        "battle",
        "creature",
        "enchantment",
        "land",
        "permanent",
        "planeswalker",
    }
)


class CounterPlacementSubject(str, Enum):
    SOURCE = "source"
    TARGET = "target"


class PlayerCounterPlacementSubject(str, Enum):
    CONTROLLER = "controller"
    TARGET = "target"
    EACH_PLAYER = "each-player"
    EACH_OPPONENT = "each-opponent"


@dataclass(frozen=True, slots=True)
class FixedCounterPlacementTemplate:
    """One mandatory fixed placement on the source or one direct target."""

    count: int
    counter_name: str
    subject: CounterPlacementSubject
    permanent_type: str | None = None
    creature_subtype: str | None = None
    controller_relation: str = "any"
    exclude_source: bool = False

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise ValueError("Counter placement count must be positive")
        if type(self.counter_name) is not str or not self.counter_name:
            raise ValueError("Counter placement name must be nonempty")
        if not isinstance(self.subject, CounterPlacementSubject):
            raise ValueError("Counter placement subject is unsupported")
        if self.permanent_type not in {*_PERMANENT_TYPES, None}:
            raise ValueError("Counter placement permanent type is unsupported")
        if self.creature_subtype is not None and (
            canonical_creature_subtype(self.creature_subtype)
            != self.creature_subtype
        ):
            raise ValueError("Counter placement creature subtype is unsupported")
        if self.permanent_type is not None and self.creature_subtype is not None:
            raise ValueError("Counter placement requires one subject predicate")
        if self.controller_relation not in {"any", "you", "opponent"}:
            raise ValueError("Counter placement controller relation is unsupported")
        if self.subject is CounterPlacementSubject.SOURCE and (
            self.controller_relation != "any" or self.exclude_source
        ):
            raise ValueError("Source counter placement cannot add target predicates")

    @property
    def template_id(self) -> str:
        subject = self.subject.value
        predicate = self.permanent_type or self.creature_subtype or "permanent"
        relation = (
            f"-{self.controller_relation}"
            if self.controller_relation != "any"
            else ""
        )
        another = "-another" if self.exclude_source else ""
        return f"place-fixed-counter-{subject}-{predicate}{relation}{another}-v1"

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "op": "place_counters",
                "card": (
                    "$source"
                    if self.subject is CounterPlacementSubject.SOURCE
                    else "$target.0"
                ),
                "counter": self.counter_name,
                "amount": self.count,
                "source": "$source",
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any] | None:
        if self.subject is CounterPlacementSubject.SOURCE:
            return None
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if self.permanent_type not in {None, "permanent"}:
            schema["types_any"] = [self.permanent_type]
        elif self.creature_subtype is not None:
            schema["subtypes_any"] = [self.creature_subtype]
        if self.controller_relation != "any":
            schema["controller_relation"] = self.controller_relation
        if self.exclude_source:
            schema["source_exclusion"] = True
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return (
            ("cr-122-counters",)
            if self.subject is CounterPlacementSubject.SOURCE
            else ("cr-122-counters", "cr-115-targets")
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


@dataclass(frozen=True, slots=True)
class FixedPlayerCounterPlacementTemplate:
    """One mandatory fixed placement on a closed player relation."""

    count: int
    counter_name: str
    subject: PlayerCounterPlacementSubject
    player_relation: str = "any"

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise ValueError("Player counter placement count must be positive")
        if type(self.counter_name) is not str:
            raise ValueError(
                "Player counter placement name must be nonempty"
            )
        normalized = " ".join(self.counter_name.casefold().split())
        if not normalized:
            raise ValueError(
                "Player counter placement name must be nonempty"
            )
        object.__setattr__(self, "counter_name", normalized)
        if not isinstance(self.subject, PlayerCounterPlacementSubject):
            raise ValueError("Player counter placement subject is unsupported")
        if self.player_relation not in {"any", "opponent"}:
            raise ValueError("Player counter relation is unsupported")
        if self.subject is not PlayerCounterPlacementSubject.TARGET and (
            self.player_relation != "any"
        ):
            raise ValueError(
                "Only targeted player counters accept a player relation"
            )

    @property
    def template_id(self) -> str:
        relation = (
            f"-{self.player_relation}"
            if self.subject is PlayerCounterPlacementSubject.TARGET
            else ""
        )
        return (
            f"place-fixed-player-counter-{self.subject.value}{relation}-v1"
        )

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        effect: dict[str, Any] = {
            "op": "place_player_counters",
            "subjects": self.subject.value,
            "counter": self.counter_name,
            "amount": self.count,
            "source": "$source",
        }
        if self.subject is PlayerCounterPlacementSubject.TARGET:
            effect["target"] = "$target.0"
        return (effect,)

    @property
    def target_schema(self) -> Mapping[str, Any] | None:
        if self.subject is not PlayerCounterPlacementSubject.TARGET:
            return None
        schema: dict[str, Any] = {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
        }
        if self.player_relation != "any":
            schema["player_relation"] = self.player_relation
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return (
            ("cr-122-counters", "cr-115-targets")
            if self.subject is PlayerCounterPlacementSubject.TARGET
            else ("cr-122-counters",)
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


def _target_subject(subject: str) -> tuple[str | None, str | None, str, bool] | None:
    match = re.fullmatch(
        r"(?P<another>another )?target (?P<kind>artifact|battle|creature|"
        r"enchantment|land|permanent|planeswalker)"
        r"(?P<relation> you control| an opponent controls| you don't control)?",
        subject,
        re.IGNORECASE,
    )
    if match is not None:
        relation = (match.group("relation") or "").casefold()
        return (
            match.group("kind").casefold(),
            None,
            (
                "you"
                if relation == " you control"
                else "opponent"
                if relation
                else "any"
            ),
            bool(match.group("another")),
        )
    match = re.fullmatch(
        r"(?P<another>another )?target (?P<subtype>[A-Za-z][A-Za-z' -]*)"
        r"(?: creature)?"
        r"(?P<relation> you control| an opponent controls| you don't control)?",
        subject,
        re.IGNORECASE,
    )
    if match is None:
        return None
    subtype = canonical_creature_subtype(match.group("subtype"))
    if subtype is None:
        return None
    relation = (match.group("relation") or "").casefold()
    return (
        None,
        subtype,
        (
            "you"
            if relation == " you control"
            else "opponent"
            if relation
            else "any"
        ),
        bool(match.group("another")),
    )


def fixed_counter_placement_effect_template(
    text: str,
    *,
    card_name: str,
) -> FixedCounterPlacementTemplate | None:
    """Parse only one closed, mandatory, positive fixed placement clause."""

    match = _PLACEMENT.fullmatch(text.strip())
    if match is None:
        return None
    count = fixed_number(match.group("count"))
    if count <= 0 or (match.group("plural").casefold() == "counter") != (
        count == 1
    ):
        return None
    counter_name = " ".join(match.group("counter").casefold().split())
    subject = " ".join(match.group("subject").split())
    source = re.fullmatch(
        r"this (artifact|battle|creature|enchantment|land|permanent|planeswalker)",
        subject,
        re.IGNORECASE,
    )
    if source is not None:
        return FixedCounterPlacementTemplate(
            count=count,
            counter_name=counter_name,
            subject=CounterPlacementSubject.SOURCE,
            permanent_type=source.group(1).casefold(),
        )
    if subject.casefold() == " ".join(card_name.casefold().split()):
        return FixedCounterPlacementTemplate(
            count=count,
            counter_name=counter_name,
            subject=CounterPlacementSubject.SOURCE,
        )
    target = _target_subject(subject)
    if target is None:
        return None
    permanent_type, creature_subtype, relation, exclude_source = target
    return FixedCounterPlacementTemplate(
        count=count,
        counter_name=counter_name,
        subject=CounterPlacementSubject.TARGET,
        permanent_type=permanent_type,
        creature_subtype=creature_subtype,
        controller_relation=relation,
        exclude_source=exclude_source,
    )


_PLAYER_COUNTER_WORDING = re.compile(
    rf"(?P<subject>you|target player|target opponent|each player|each opponent) "
    rf"(?P<verb>get|gets) (?P<count>{_COUNT}) "
    rf"(?P<counter>{_COUNTER_NAME}) (?P<plural>counter|counters)\.?",
    re.IGNORECASE,
)
_PLAYER_COUNTER_SYMBOLS = re.compile(
    rf"(?P<subject>you|target player|target opponent|each player|each opponent) "
    rf"(?P<verb>get|gets) (?:(?P<count>{_COUNT}) )?"
    r"(?P<symbols>(?:\{E\})+|(?:\{TK\})+)"
    r"(?: \((?P<explanation>[^()]*)\))?\.?",
    re.IGNORECASE,
)


def _player_counter_subject(
    subject: str,
    verb: str,
) -> tuple[PlayerCounterPlacementSubject, str] | None:
    normalized = " ".join(subject.casefold().split())
    expected_verb = "get" if normalized == "you" else "gets"
    if verb.casefold() != expected_verb:
        return None
    return {
        "you": (PlayerCounterPlacementSubject.CONTROLLER, "any"),
        "target player": (PlayerCounterPlacementSubject.TARGET, "any"),
        "target opponent": (
            PlayerCounterPlacementSubject.TARGET,
            "opponent",
        ),
        "each player": (PlayerCounterPlacementSubject.EACH_PLAYER, "any"),
        "each opponent": (
            PlayerCounterPlacementSubject.EACH_OPPONENT,
            "any",
        ),
    }.get(normalized)


def _validated_symbol_explanation(
    explanation: str | None,
    *,
    count: int,
    counter_name: str,
    explicit_count: bool,
) -> bool:
    if explanation is None:
        return True
    match = re.fullmatch(
        rf"(?:(?P<count>{_COUNT}) )?(?P<counter>energy|ticket) "
        r"(?P<plural>counter|counters)",
        explanation.strip(),
        re.IGNORECASE,
    )
    if match is None:
        return False
    raw_count = match.group("count")
    if raw_count is None:
        return (
            explicit_count
            and count > 1
            and match.group("counter").casefold() == counter_name
            and match.group("plural").casefold() == _COUNTER_PLURAL
        )
    explained_count = fixed_number(raw_count)
    return (
        explained_count == count
        and match.group("counter").casefold() == counter_name
        and (match.group("plural").casefold() == "counter") == (count == 1)
    )


def fixed_player_counter_placement_effect_template(
    text: str,
) -> FixedPlayerCounterPlacementTemplate | None:
    """Parse one mandatory fixed player-counter placement instruction."""

    normalized = re.sub(r"\s+([.,])", r"\1", text.strip())
    symbol_match = _PLAYER_COUNTER_SYMBOLS.fullmatch(normalized)
    if symbol_match is not None:
        subject = _player_counter_subject(
            symbol_match.group("subject"), symbol_match.group("verb")
        )
        if subject is None:
            return None
        symbols = symbol_match.group("symbols").upper()
        symbol = "{TK}" if symbols.startswith("{TK}") else "{E}"
        if symbols != symbol * (symbols.count(symbol)):
            return None
        explicit = symbol_match.group("count")
        count = (
            fixed_number(explicit)
            if explicit is not None
            else symbols.count(symbol)
        )
        if count <= 0 or (explicit is not None and symbols.count(symbol) != 1):
            return None
        counter_name = "ticket" if symbol == "{TK}" else "energy"
        if not _validated_symbol_explanation(
            symbol_match.group("explanation"),
            count=count,
            counter_name=counter_name,
            explicit_count=explicit is not None,
        ):
            return None
        return FixedPlayerCounterPlacementTemplate(
            count=count,
            counter_name=counter_name,
            subject=subject[0],
            player_relation=subject[1],
        )

    word_match = _PLAYER_COUNTER_WORDING.fullmatch(normalized)
    if word_match is None:
        return None
    subject = _player_counter_subject(
        word_match.group("subject"), word_match.group("verb")
    )
    count = fixed_number(word_match.group("count"))
    if (
        subject is None
        or count <= 0
        or (word_match.group("plural").casefold() == "counter") != (count == 1)
    ):
        return None
    return FixedPlayerCounterPlacementTemplate(
        count=count,
        counter_name=word_match.group("counter"),
        subject=subject[0],
        player_relation=subject[1],
    )


__all__ = [
    "CounterPlacementSubject",
    "FixedCounterPlacementTemplate",
    "FixedPlayerCounterPlacementTemplate",
    "PlayerCounterPlacementSubject",
    "fixed_counter_placement_effect_template",
    "fixed_player_counter_placement_effect_template",
]
