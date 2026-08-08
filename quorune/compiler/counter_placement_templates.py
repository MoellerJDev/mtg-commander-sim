from __future__ import annotations

"""Closed Oracle lowering for fixed counter-placement effects."""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Mapping

from ..affected_permanents import (
    AffectedPermanentSetSpec,
    PermanentControllerRelation,
)
from ..object_predicate import ObjectQuerySpec
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
class FixedCounterPlacementTargetSetTemplate:
    """One fixed placement on each member of an optional target set."""

    count: int
    counter_name: str
    maximum_targets: int
    permanent_type: str
    controller_relation: str = "any"
    exclude_creature: bool = False

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise ValueError("Counter-target placement count must be positive")
        if type(self.counter_name) is not str:
            raise ValueError("Counter-target placement name must be nonempty")
        normalized = " ".join(self.counter_name.casefold().split())
        if not normalized:
            raise ValueError("Counter-target placement name must be nonempty")
        object.__setattr__(self, "counter_name", normalized)
        if type(self.maximum_targets) is not int or self.maximum_targets <= 0:
            raise ValueError("Counter-target maximum must be positive")
        if self.permanent_type not in _PERMANENT_TYPES:
            raise ValueError("Counter-target permanent type is unsupported")
        if self.controller_relation not in {"any", "you", "opponent"}:
            raise ValueError("Counter-target controller relation is unsupported")
        if type(self.exclude_creature) is not bool or (
            self.exclude_creature and self.permanent_type != "artifact"
        ):
            raise ValueError("Counter-target negative type predicate is unsupported")

    @property
    def template_id(self) -> str:
        negative = "noncreature-" if self.exclude_creature else ""
        relation = (
            f"-{self.controller_relation}"
            if self.controller_relation != "any"
            else ""
        )
        return (
            f"place-fixed-counter-target-set-{self.maximum_targets}-"
            f"{negative}{self.permanent_type}{relation}-v1"
        )

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "op": "place_counters_on_targets",
                "cards": "$targets",
                "maximum_targets": self.maximum_targets,
                "counter": self.counter_name,
                "amount": self.count,
                "source": "$source",
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any]:
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "up_to": self.maximum_targets,
        }
        if self.permanent_type != "permanent":
            schema["types_any"] = [self.permanent_type]
        if self.exclude_creature:
            schema["types_none"] = ["creature"]
        if self.controller_relation != "any":
            schema["controller_relation"] = self.controller_relation
        return schema

    @property
    def mechanics(self) -> tuple[str, ...]:
        return ("cr-122-counters", "cr-115-targets")

    def compiled(
        self,
    ) -> tuple[
        str,
        tuple[Mapping[str, Any], ...],
        Mapping[str, Any],
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


@dataclass(frozen=True, slots=True)
class FixedCounterPlacementSetTemplate:
    """One mandatory fixed placement on one closed battlefield set."""

    count: int
    counter_name: str
    spec: AffectedPermanentSetSpec
    target_relation: str | None = None

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count <= 0:
            raise ValueError("Counter-set placement count must be positive")
        if type(self.counter_name) is not str:
            raise ValueError("Counter-set placement name must be nonempty")
        normalized = " ".join(self.counter_name.casefold().split())
        if not normalized:
            raise ValueError("Counter-set placement name must be nonempty")
        object.__setattr__(self, "counter_name", normalized)
        if not isinstance(self.spec, AffectedPermanentSetSpec):
            raise ValueError("Counter-set placement requires a typed set")
        if not fixed_counter_set_spec_is_closed(self.spec):
            raise ValueError("Counter-set placement predicate is unsupported")
        if self.target_relation not in {None, "any", "opponent"}:
            raise ValueError("Counter-set player target relation is unsupported")
        needs_target = (
            self.spec.controller_relation
            is PermanentControllerRelation.TARGET_PLAYER
        )
        if needs_target is not (self.target_relation is not None):
            raise ValueError(
                "Counter-set target relation contradicts its affected set"
            )

    @property
    def template_id(self) -> str:
        return (
            f"place-fixed-counter-set-{self.spec.fingerprint[:16]}-"
            f"{self.target_relation or 'untargeted'}-v1"
        )

    @property
    def effects(self) -> tuple[Mapping[str, Any], ...]:
        return (
            {
                "op": "place_counters_on_set",
                "source": "$source",
                "set": self.spec.to_dict(),
                "counter": self.counter_name,
                "amount": self.count,
            },
        )

    @property
    def target_schema(self) -> Mapping[str, Any] | None:
        if self.target_relation is None:
            return None
        return {
            "zones": ["player"],
            "categories": ["player"],
            "count": 1,
            "player_relation": self.target_relation,
        }

    @property
    def mechanics(self) -> tuple[str, ...]:
        return (
            ("cr-122-counters", "cr-115-targets")
            if self.target_relation is not None
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


_TARGET_SET_PERMANENT_TYPES = {
    "artifact": "artifact",
    "artifacts": "artifact",
    "battle": "battle",
    "battles": "battle",
    "creature": "creature",
    "creatures": "creature",
    "enchantment": "enchantment",
    "enchantments": "enchantment",
    "land": "land",
    "lands": "land",
    "permanent": "permanent",
    "permanents": "permanent",
    "planeswalker": "planeswalker",
    "planeswalkers": "planeswalker",
}


def fixed_counter_placement_target_set_effect_template(
    text: str,
) -> FixedCounterPlacementTargetSetTemplate | None:
    """Parse one fixed placement on each of up to N direct targets."""

    match = _PLACEMENT.fullmatch(text.strip())
    if match is None:
        return None
    count = fixed_number(match.group("count"))
    if count <= 0 or (match.group("plural").casefold() == "counter") != (
        count == 1
    ):
        return None
    subject = " ".join(match.group("subject").casefold().split())
    target = re.fullmatch(
        rf"each of up to (?P<maximum>{_COUNT}) target "
        r"(?P<noncreature>noncreature )?"
        r"(?P<kind>artifact|artifacts|battle|battles|creature|creatures|"
        r"enchantment|enchantments|land|lands|permanent|permanents|"
        r"planeswalker|planeswalkers)"
        r"(?P<relation> you control| an opponent controls| you don't control)?",
        subject,
        re.IGNORECASE,
    )
    if target is None:
        return None
    maximum = fixed_number(target.group("maximum"))
    kind_word = target.group("kind").casefold()
    singular = not kind_word.endswith("s")
    if maximum <= 0 or singular is not (maximum == 1):
        return None
    permanent_type = _TARGET_SET_PERMANENT_TYPES[kind_word]
    exclude_creature = bool(target.group("noncreature"))
    if exclude_creature and permanent_type != "artifact":
        return None
    relation = (target.group("relation") or "").casefold()
    return FixedCounterPlacementTargetSetTemplate(
        count=count,
        counter_name=match.group("counter"),
        maximum_targets=maximum,
        permanent_type=permanent_type,
        controller_relation=(
            "you"
            if relation == " you control"
            else "opponent"
            if relation
            else "any"
        ),
        exclude_creature=exclude_creature,
    )


_SET_COLOR_WORDS = {
    "white": "W",
    "blue": "U",
    "black": "B",
    "red": "R",
    "green": "G",
}
FIXED_COUNTER_SET_KEYWORDS = frozenset(
    {"flying", "lifelink", "menace", "trample", "vigilance"}
)
_FIXED_COUNTER_SET_TYPE_SHAPES = frozenset(
    {
        (),
        ("artifact",),
        ("battle",),
        ("creature",),
        ("enchantment",),
        ("land",),
        ("planeswalker",),
        ("artifact", "creature"),
        ("creature", "land"),
    }
)
_SET_NONCREATURE_SUBTYPES = {
    "equipment": "equipment",
    "saga": "saga",
}


def fixed_counter_set_spec_is_closed(
    spec: AffectedPermanentSetSpec,
) -> bool:
    """Return whether a set uses only the reviewed compiler grammar."""

    if not isinstance(spec, AffectedPermanentSetSpec):
        return False
    query = spec.query
    type_shape = tuple(query.types_all)
    if type_shape not in _FIXED_COUNTER_SET_TYPE_SHAPES:
        return False
    if query.types_any or query.excluded_types or query.colors_all:
        return False
    subtypes = tuple(query.subtypes_all)
    if len(subtypes) > 1:
        return False
    if subtypes:
        subtype = subtypes[0]
        creature_subtype = canonical_creature_subtype(subtype)
        if creature_subtype is not None:
            if type_shape not in {(), ("creature",)}:
                return False
        elif subtype not in {"equipment", "saga"} or type_shape:
            return False
    if tuple(query.supertypes_all) not in {(), ("legendary",)}:
        return False
    if query.supertypes_all and type_shape not in {
        ("creature",),
        ("planeswalker",),
    }:
        return False
    if len(query.colors_any) > 1 or not set(query.colors_any).issubset(
        {"W", "U", "B", "R", "G"}
    ):
        return False
    if query.colors_any and type_shape not in {
        ("creature",),
        ("planeswalker",),
    }:
        return False
    if len(query.keywords_all) > 1 or not set(query.keywords_all).issubset(
        FIXED_COUNTER_SET_KEYWORDS
    ):
        return False
    if query.keywords_all and type_shape != ("creature",):
        return False
    if (query.token is not None or query.tapped is not None) and (
        type_shape != ("creature",)
    ):
        return False
    qualifier_count = sum(
        (
            bool(query.supertypes_all),
            bool(query.colors_any),
            bool(query.keywords_all),
            query.token is not None,
            query.tapped is not None,
        )
    )
    return qualifier_count <= 1


def _fixed_counter_set_query(
    subject: str,
) -> tuple[AffectedPermanentSetSpec, str | None] | None:
    phrase = " ".join(subject.casefold().split())
    if not phrase.startswith("each "):
        return None
    phrase = phrase[5:]

    keyword: str | None = None
    keyword_match = re.fullmatch(
        r"(?P<body>.+) with (?P<keyword>"
        + "|".join(sorted(FIXED_COUNTER_SET_KEYWORDS))
        + r")",
        phrase,
    )
    if keyword_match is not None:
        phrase = keyword_match.group("body")
        keyword = keyword_match.group("keyword")

    relation = PermanentControllerRelation.ANY
    target_controller: str | None = None
    target_relation: str | None = None
    controller_suffixes = (
        (
            " target opponent controls",
            PermanentControllerRelation.TARGET_PLAYER,
            "$target.0",
            "opponent",
        ),
        (
            " target player controls",
            PermanentControllerRelation.TARGET_PLAYER,
            "$target.0",
            "any",
        ),
        (
            " each opponent controls",
            PermanentControllerRelation.OPPONENTS,
            None,
            None,
        ),
        (
            " your opponents control",
            PermanentControllerRelation.OPPONENTS,
            None,
            None,
        ),
        (
            " opponents control",
            PermanentControllerRelation.OPPONENTS,
            None,
            None,
        ),
        (
            " you don't control",
            PermanentControllerRelation.OPPONENTS,
            None,
            None,
        ),
        (
            " you control",
            PermanentControllerRelation.ACTOR,
            None,
            None,
        ),
    )
    for suffix, candidate, target, target_kind in controller_suffixes:
        if phrase.endswith(suffix):
            phrase = phrase[: -len(suffix)]
            relation = candidate
            target_controller = target
            target_relation = target_kind
            break

    exclude_source = phrase.startswith("other ")
    if exclude_source:
        phrase = phrase[6:]
    kwargs: dict[str, Any] = {"zones": ("battlefield",)}

    exact_types: dict[str, tuple[str, ...]] = {
        "permanent": (),
        "artifact": ("artifact",),
        "battle": ("battle",),
        "creature": ("creature",),
        "enchantment": ("enchantment",),
        "land": ("land",),
        "planeswalker": ("planeswalker",),
        "artifact creature": ("artifact", "creature"),
        "land creature": ("creature", "land"),
    }
    if phrase in exact_types:
        kwargs["types_all"] = exact_types[phrase]
    elif phrase in {"token creature", "creature token"}:
        kwargs["types_all"] = ("creature",)
        kwargs["token"] = True
    elif phrase == "nontoken creature":
        kwargs["types_all"] = ("creature",)
        kwargs["token"] = False
    else:
        quality = re.fullmatch(
            r"(?P<quality>legendary|tapped|untapped|white|blue|black|red|green) "
            r"(?P<kind>creature|planeswalker)",
            phrase,
        )
        if quality is not None:
            kwargs["types_all"] = (quality.group("kind"),)
            value = quality.group("quality")
            if value == "legendary":
                kwargs["supertypes_all"] = ("legendary",)
            elif value in {"tapped", "untapped"}:
                kwargs["tapped"] = value == "tapped"
            else:
                kwargs["colors_any"] = (_SET_COLOR_WORDS[value],)
        elif phrase in _SET_NONCREATURE_SUBTYPES:
            kwargs["subtypes_all"] = (_SET_NONCREATURE_SUBTYPES[phrase],)
        else:
            creature_match = re.fullmatch(
                r"(?P<subtype>[a-z][a-z' -]*?)(?P<creature> creature)?",
                phrase,
            )
            if creature_match is None:
                return None
            subtype = canonical_creature_subtype(
                creature_match.group("subtype")
            )
            if subtype is None:
                return None
            kwargs["subtypes_all"] = (subtype,)
            if creature_match.group("creature"):
                kwargs["types_all"] = ("creature",)

    if keyword is not None:
        if keyword not in FIXED_COUNTER_SET_KEYWORDS or kwargs.get("types_all") != (
            "creature",
        ):
            return None
        kwargs["keywords_all"] = (keyword,)
    try:
        return (
            AffectedPermanentSetSpec(
                query=ObjectQuerySpec(**kwargs),
                controller_relation=relation,
                target_controller=target_controller,
                exclude_source=exclude_source,
            ),
            target_relation,
        )
    except ValueError:
        return None


def fixed_counter_placement_set_effect_template(
    text: str,
) -> FixedCounterPlacementSetTemplate | None:
    """Parse one mandatory fixed placement on a closed permanent set."""

    match = _PLACEMENT.fullmatch(text.strip())
    if match is None:
        return None
    count = fixed_number(match.group("count"))
    if count <= 0 or (match.group("plural").casefold() == "counter") != (
        count == 1
    ):
        return None
    parsed = _fixed_counter_set_query(match.group("subject"))
    if parsed is None:
        return None
    spec, target_relation = parsed
    return FixedCounterPlacementSetTemplate(
        count=count,
        counter_name=match.group("counter"),
        spec=spec,
        target_relation=target_relation,
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
    "FIXED_COUNTER_SET_KEYWORDS",
    "FixedCounterPlacementTemplate",
    "FixedCounterPlacementSetTemplate",
    "FixedCounterPlacementTargetSetTemplate",
    "FixedPlayerCounterPlacementTemplate",
    "PlayerCounterPlacementSubject",
    "fixed_counter_placement_effect_template",
    "fixed_counter_placement_set_effect_template",
    "fixed_counter_placement_target_set_effect_template",
    "fixed_counter_set_spec_is_closed",
    "fixed_player_counter_placement_effect_template",
]
