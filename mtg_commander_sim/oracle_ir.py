from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .abilities import ActivatedAbility, parse_activated_abilities
from .carddb import CardDatabase, CardRecord
from .declaration_costs import parse_declaration_cost_line
from .declaration_restrictions import parse_declaration_restriction_line
from .rules.capabilities import (
    CapabilityClosure,
    CapabilityRegistry,
    capability_dependencies_for_node,
)
from .semantics import SemanticProgram, SemanticRegistry
from .util import stable_json


ORACLE_IR_SCHEMA_VERSION = 1
ORACLE_COMPILER_VERSION = "oracle-ir-v12"
ORACLE_OPERATIONS = {"parse", "explain", "residuals", "coverage"}

_NUMBER_WORDS = {
    "a": 1,
    "an": 1,
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
}
_TRIGGER_PREFIX = re.compile(
    r"^(when|whenever|at the beginning of)\b",
    re.IGNORECASE,
)
_REPLACEMENT_MARKERS = re.compile(
    r"\b(instead|as .+ enters|enters .+ with|skip)\b",
    re.IGNORECASE,
)
_ABILITY_WORD = re.compile(
    r"^(?P<word>[A-Za-z][A-Za-z ']+)\s+[—-]\s+(?P<body>.+)$"
)
_KEYWORD_WITH_VALUE = re.compile(
    r"^(?P<name>ward|equip|enchant|cycling|crew|kicker|toxic|"
    r"cumulative upkeep|echo|morph|bestow|evoke|unearth)"
    r"(?:\s+(?P<value>.+))?$",
    re.IGNORECASE,
)
_KNOWN_BARE_KEYWORDS = {
    "deathtouch",
    "defender",
    "double strike",
    "first strike",
    "flash",
    "flying",
    "haste",
    "hexproof",
    "indestructible",
    "infect",
    "lifelink",
    "menace",
    "reach",
    "shadow",
    "shroud",
    "trample",
    "vigilance",
    "wither",
}


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int
    line: int


@dataclass(frozen=True, slots=True)
class OracleResidual:
    residual_id: str
    kind: str
    text: str
    span: SourceSpan
    material: bool
    reason: str
    blockers: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["span"] = asdict(self.span)
        value["blockers"] = list(self.blockers)
        return value


@dataclass(frozen=True, slots=True)
class OracleNode:
    node_id: str
    kind: str
    text: str
    span: SourceSpan
    active_zone: str
    event: str
    lowerable: bool
    exact: bool
    template_id: str | None = None
    cost: Mapping[str, Any] | None = None
    effects: tuple[Mapping[str, Any], ...] = ()
    target_schema: Mapping[str, Any] | None = None
    mechanics: tuple[str, ...] = ()
    residual_ids: tuple[str, ...] = ()
    capability_dependencies: tuple[str, ...] = ()
    capability_closure: tuple[str, ...] = ()
    capability_profile: str | None = None
    capability_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = {
            "node_id": self.node_id,
            "kind": self.kind,
            "text": self.text,
            "span": asdict(self.span),
            "active_zone": self.active_zone,
            "event": self.event,
            "lowerable": self.lowerable,
            "exact": self.exact,
            "template_id": self.template_id,
            "cost": dict(self.cost) if self.cost is not None else None,
            "effects": [dict(effect) for effect in self.effects],
            "target_schema": (
                dict(self.target_schema)
                if self.target_schema is not None
                else None
            ),
            "mechanics": list(self.mechanics),
            "residual_ids": list(self.residual_ids),
        }
        if self.capability_dependencies:
            value["capability_dependencies"] = list(
                self.capability_dependencies
            )
            value["capability_closure"] = list(self.capability_closure)
            value["capability_profile"] = self.capability_profile
            value["capability_fingerprint"] = self.capability_fingerprint
        return value


@dataclass(frozen=True, slots=True)
class OracleFaceIR:
    face_id: str
    face_name: str
    oracle_text: str
    nodes: tuple[OracleNode, ...]
    residuals: tuple[OracleResidual, ...]

    @property
    def exact(self) -> bool:
        return not any(value.material for value in self.residuals) and all(
            node.exact for node in self.nodes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "face_id": self.face_id,
            "face_name": self.face_name,
            "oracle_text": self.oracle_text,
            "exact": self.exact,
            "nodes": [node.to_dict() for node in self.nodes],
            "residuals": [
                residual.to_dict() for residual in self.residuals
            ],
        }


@dataclass(frozen=True, slots=True)
class OracleCardIR:
    oracle_id: str
    card_name: str
    schema_version: int
    compiler_version: str
    oracle_hash: str
    faces: tuple[OracleFaceIR, ...]
    semantic_hash: str

    @property
    def material_residuals(self) -> tuple[OracleResidual, ...]:
        return tuple(
            residual
            for face in self.faces
            for residual in face.residuals
            if residual.material
        )

    @property
    def status(self) -> str:
        if not self.material_residuals and all(
            face.exact for face in self.faces
        ):
            return "exact"
        if any(
            node.lowerable for face in self.faces for node in face.nodes
        ):
            return "partial"
        return "unresolved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "oracle_id": self.oracle_id,
            "card_name": self.card_name,
            "schema_version": self.schema_version,
            "compiler_version": self.compiler_version,
            "oracle_hash": self.oracle_hash,
            "semantic_hash": self.semantic_hash,
            "status": self.status,
            "material_residual_count": len(self.material_residuals),
            "faces": [face.to_dict() for face in self.faces],
        }


def _number(value: str) -> int:
    normalized = value.casefold()
    return (
        int(normalized)
        if normalized.isdigit()
        else _NUMBER_WORDS[normalized]
    )


@dataclass(frozen=True, slots=True)
class _DependencyGate:
    blockers: tuple[str, ...]
    capabilities: tuple[str, ...] = ()
    closure: CapabilityClosure | None = None


def _dependency_gate(
    *,
    mechanics: Iterable[str],
    effects: Sequence[Mapping[str, Any]],
    target_schema: Mapping[str, Any] | None,
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> _DependencyGate:
    mechanic_ids = tuple(str(value).casefold() for value in mechanics)
    capabilities = capability_dependencies_for_node(
        effects=effects,
        target_schema=target_schema,
        mechanic_ids=mechanic_ids,
    )
    if capability_registry is not None and capabilities:
        closure = capability_registry.closure(
            capabilities,
            profile=capability_profile,
        )
        return _DependencyGate(
            blockers=tuple(
                f"capability:{blocker}" for blocker in closure.blockers
            ),
            capabilities=capabilities,
            closure=closure,
        )
    return _DependencyGate(
        blockers=tuple(
            f"mechanic:{mechanic}"
            for mechanic in sorted(set(mechanic_ids) - trusted_mechanics)
        )
    )


def _source_lines(text: str) -> Iterable[tuple[str, SourceSpan]]:
    offset = 0
    for line_number, raw in enumerate(text.splitlines(keepends=True), 1):
        line = raw.rstrip("\r\n")
        stripped = line.strip()
        if stripped:
            left = len(line) - len(line.lstrip())
            yield stripped, SourceSpan(
                start=offset + left,
                end=offset + left + len(stripped),
                line=line_number,
            )
        offset += len(raw)
    if text and not text.splitlines(keepends=True):
        yield text, SourceSpan(0, len(text), 1)


def _without_parenthetical_reminder(text: str) -> str:
    result: list[str] = []
    depth = 0
    for character in text:
        if character == "(":
            depth += 1
            continue
        if character == ")" and depth:
            depth -= 1
            continue
        if depth == 0:
            result.append(character)
    return "".join(result).strip()


def _damage_to_target_effect(amount: int) -> dict[str, Any]:
    return {
        "op": "damage",
        "source": "$source",
        "target": "$target.0",
        "amount": amount,
    }


def _effect_template(
    text: str,
    *,
    card_name: str,
) -> tuple[
    str | None,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]:
    """Compile only whole, reviewed Oracle sentence templates."""

    normalized = text.strip()
    name = re.escape(card_name)
    if re.fullmatch(
        r"you become the monarch\.?",
        normalized,
        re.IGNORECASE,
    ):
        return (
            "become-monarch-controller-v1",
            (
                {
                    "op": "become_monarch",
                    "player": "$controller",
                },
            ),
            None,
            ("cr-725-the-monarch",),
        )
    match = re.fullmatch(
        r"(?:you )?draw (?P<count>a|one|two|three|four|five|six|seven|"
        r"eight|nine|ten|\d+) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "draw-controller-v1",
            (
                {
                    "op": "draw",
                    "player": "$controller",
                    "count": _number(match.group("count")),
                    "private": True,
                },
            ),
            None,
            ("cr-121-drawing-a-card",),
        )
    match = re.fullmatch(
        r"target (?P<relation>player|opponent) draws "
        r"(?P<count>a|one|two|three|four|five|six|seven|eight|nine|"
        r"ten|\d+) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        relation = match.group("relation").casefold()
        return (
            f"draw-target-{relation}-v1",
            (
                {
                    "op": "draw",
                    "player": "$target.0",
                    "count": _number(match.group("count")),
                    "private": True,
                },
            ),
            {
                "zones": ["player"],
                "categories": ["player"],
                "player_relation": (
                    "opponent" if relation == "opponent" else "any"
                ),
                "count": 1,
            },
            ("cr-121-drawing-a-card", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"each player draws (?P<count>a|one|two|three|four|five|six|"
        r"seven|eight|nine|ten|\d+) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "draw-each-player-v1",
            (
                {
                    "op": "draw_each_player",
                    "count": _number(match.group("count")),
                },
            ),
            None,
            (
                "cr-121-drawing-a-card",
                "cr-101-the-magic-golden-rules",
            ),
        )
    match = re.fullmatch(
        r"you gain (?P<count>\d+) life\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "gain-life-controller-v1",
            (
                {
                    "op": "life",
                    "player": "$controller",
                    "delta": int(match.group("count")),
                },
            ),
            None,
            ("cr-119-life",),
        )
    match = re.fullmatch(
        r"each opponent loses (?P<count>\d+) life\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "lose-life-each-opponent-v1",
            (
                {
                    "op": "lose_life_each_opponent",
                    "amount": int(match.group("count")),
                },
            ),
            None,
            (
                "cr-119-life",
                "cr-101-the-magic-golden-rules",
            ),
        )
    match = re.fullmatch(
        rf"(?:{name}|this spell) deals (?P<count>\d+) damage to any target\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "damage-any-target-v1",
            (_damage_to_target_effect(int(match.group("count"))),),
            {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            },
            ("cr-120-damage", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"this (?P<kind>artifact|creature|enchantment|permanent) deals "
        r"(?P<count>\d+) damage to any target\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            f"damage-any-target-self-{match.group('kind').casefold()}-v1",
            (_damage_to_target_effect(int(match.group("count"))),),
            {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            },
            ("cr-120-damage", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"destroy target (?P<kinds>artifact|creature|enchantment|land|"
        r"permanent|artifact or enchantment|creature or planeswalker)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        kinds = match.group("kinds").casefold().split(" or ")
        kind = "-or-".join(kinds)
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if kinds != ["permanent"]:
            schema["types_any"] = kinds
        return (
            f"destroy-target-{kind}-v1",
            ({"op": "destroy", "card": "$target.0"},),
            schema,
            ("destroy", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"exile target (?P<kinds>artifact|creature|enchantment|land|"
        r"permanent|artifact or enchantment|creature or planeswalker)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        kinds = match.group("kinds").casefold().split(" or ")
        kind = "-or-".join(kinds)
        schema = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if kinds != ["permanent"]:
            schema["types_any"] = kinds
        return (
            f"exile-target-{kind}-v1",
            ({"op": "exile", "card": "$target.0"},),
            schema,
            ("exile", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"return target (?P<kind>creature|artifact|enchantment|land|"
        r"permanent) to its owner'?s hand\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        kind = match.group("kind").casefold()
        schema = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if kind != "permanent":
            schema[kind] = True
        return (
            f"bounce-target-{kind}-v1",
            ({"op": "bounce", "card": "$target.0"},),
            schema,
            ("cr-400-general", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"counter target spell\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "counter-target-spell-v1",
            ({"op": "counter_stack", "stack": "$target.0"},),
            {
                "zones": ["stack"],
                "categories": ["spell"],
                "count": 1,
            },
            ("counter", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"target player mills (?P<count>\d+) cards?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "mill-target-player-v1",
            (
                {
                    "op": "mill",
                    "player": "$target.0",
                    "count": int(match.group("count")),
                },
            ),
            {
                "zones": ["player"],
                "categories": ["player"],
                "count": 1,
            },
            ("mill", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"(?P<action>tap|untap) target (?P<kind>artifact|creature|land|"
        r"permanent)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        action = match.group("action").casefold()
        kind = match.group("kind").casefold()
        schema = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if kind != "permanent":
            schema["types_any"] = [kind]
        return (
            f"{action}-target-{kind}-v1",
            ({"op": action, "card": "$target.0"},),
            schema,
            (
                "cr-701-keyword-actions",
                "cr-115-targets",
            ),
        )
    match = re.fullmatch(
        r"goad target creature"
        r"(?P<relation> an opponent controls| you don't control)?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        opponent = bool(match.group("relation"))
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "types_any": ["creature"],
            "count": 1,
        }
        if opponent:
            schema["controller_relation"] = "opponent"
        return (
            (
                "goad-target-opponent-creature-v1"
                if opponent
                else "goad-target-creature-v1"
            ),
            ({"op": "goad", "card": "$target.0"},),
            schema,
            ("goad", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"target creature gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) "
        r"until end of turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "modify-target-creature-stats-eot-v1",
            (
                {
                    "op": "modify_stats_until_end_of_turn",
                    "card": "$target.0",
                    "power": int(match.group("power")),
                    "toughness": int(match.group("toughness")),
                },
            ),
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "types_any": ["creature"],
                "count": 1,
            },
            (
                "cr-611-continuous-effects",
                "cr-115-targets",
            ),
        )
    match = re.fullmatch(
        r"this (?P<kind>artifact|creature|enchantment|permanent) gets "
        r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) until end of turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            f"modify-self-{match.group('kind').casefold()}-stats-eot-v1",
            (
                {
                    "op": "modify_stats_until_end_of_turn",
                    "card": "$source",
                    "power": int(match.group("power")),
                    "toughness": int(match.group("toughness")),
                },
            ),
            None,
            ("cr-611-continuous-effects",),
        )
    match = re.fullmatch(
        r"this (?P<kind>artifact|creature|enchantment|permanent) gains "
        r"(?P<keyword>deathtouch|double strike|first strike|flying|haste|"
        r"hexproof|indestructible|lifelink|menace|reach|trample|vigilance) "
        r"until end of turn\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        keyword = match.group("keyword").casefold()
        return (
            f"grant-self-{keyword.replace(' ', '-')}-eot-v1",
            (
                {
                    "op": "grant_keyword_until_end_of_turn",
                    "card": "$source",
                    "keyword": keyword.title(),
                },
            ),
            None,
            ("cr-611-continuous-effects", keyword),
        )
    counter_pattern = (
        r"(?P<counter>[+-]\d+/[+-]\d+|[A-Za-z][A-Za-z-]*)"
    )
    match = re.fullmatch(
        rf"put (?:a|an|one) {counter_pattern} counter on this "
        r"(?P<kind>artifact|creature|enchantment|permanent)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        counter = match.group("counter")
        return (
            f"counter-self-{match.group('kind').casefold()}-v1",
            (
                {
                    "op": "add_counter_selected",
                    "cards": ["$source"],
                    "counter": counter,
                    "amount": 1,
                },
            ),
            None,
            ("cr-122-counters",),
        )
    match = re.fullmatch(
        rf"put (?:a|an|one) {counter_pattern} counter on target "
        r"(?P<kind>artifact|creature|enchantment|land|permanent)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        kind = match.group("kind").casefold()
        schema: dict[str, Any] = {
            "zones": ["battlefield"],
            "categories": ["permanent"],
            "count": 1,
        }
        if kind != "permanent":
            schema["types_any"] = [kind]
        return (
            f"counter-target-{kind}-v1",
            (
                {
                    "op": "add_counter_selected",
                    "cards": ["$target.0"],
                    "counter": match.group("counter"),
                    "amount": 1,
                },
            ),
            schema,
            ("cr-122-counters", "cr-115-targets"),
        )
    match = re.fullmatch(
        r"return this (?P<kind>artifact|creature|enchantment|permanent) "
        r"to its owner'?s hand\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            f"bounce-self-{match.group('kind').casefold()}-v1",
            ({"op": "bounce", "card": "$source"},),
            None,
            ("cr-400-general",),
        )
    match = re.fullmatch(
        r"create (?P<count>a|one|two|three|four|five|six|seven|eight|"
        r"nine|ten|\d+) (?P<power>\d+)/(?P<toughness>\d+) "
        r"(?P<color>white|blue|black|red|green|colorless) "
        r"(?P<subtypes>[A-Za-z][A-Za-z -]*?) "
        r"(?P<artifact>artifact )?creature tokens?\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        colors = {
            "white": ["W"],
            "blue": ["U"],
            "black": ["B"],
            "red": ["R"],
            "green": ["G"],
            "colorless": [],
        }[match.group("color").casefold()]
        subtypes = " ".join(
            word.capitalize()
            for word in match.group("subtypes").split()
        )
        artifact = bool(match.group("artifact"))
        return (
            "create-basic-creature-token-v1",
            (
                {
                    "op": "create_token",
                    "controller": "$controller",
                    "name": subtypes,
                    "quantity": _number(match.group("count")),
                    "characteristics": {
                        "type_line": (
                            "Token "
                            + ("Artifact " if artifact else "")
                            + f"Creature — {subtypes}"
                        ),
                        "colors": colors,
                        "power": match.group("power"),
                        "toughness": match.group("toughness"),
                    },
                },
            ),
            None,
            ("cr-111-tokens",),
        )
    match = re.fullmatch(
        r"scry (?P<count>\d+)\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "scry-controller-v1",
            (
                {
                    "op": "scry",
                    "player": "$controller",
                    "count": int(match.group("count")),
                },
            ),
            None,
            ("scry",),
        )
    return None, (), None, ()


def _cost_dict(ability: ActivatedAbility) -> dict[str, Any]:
    return {
        "text": ability.cost_text,
        "mana": dict(ability.mana),
        "complex_symbols": list(ability.complex_symbols),
        "tap_source": ability.tap_source,
        "untap_source": ability.untap_source,
        "discard_source": ability.discard_source,
        "sacrifice_source": ability.sacrifice_source,
        "exile_source": ability.exile_source,
        "life_payment": ability.life_payment,
        "energy_payment": ability.energy_payment,
        "loyalty_delta": ability.loyalty_delta,
        "choices": [choice.compact() for choice in ability.choices],
        "uncompiled_costs": list(ability.uncompiled_costs),
    }


def _keyword_mechanics(
    text: str,
    card_keywords: Sequence[str],
) -> tuple[str, ...] | None:
    parts = [part.strip() for part in text.rstrip(".").split(",")]
    if not parts:
        return None
    known = {keyword.casefold() for keyword in card_keywords}
    mechanics: list[str] = []
    for part in parts:
        lower = part.casefold()
        if lower in _KNOWN_BARE_KEYWORDS or lower in known:
            mechanics.append(lower)
            continue
        match = _KEYWORD_WITH_VALUE.fullmatch(part)
        if match and match.group("name").casefold() in known:
            mechanics.append(match.group("name").casefold())
            continue
        if lower.startswith("protection from ") and "protection" in known:
            mechanics.append("protection")
            continue
        return None
    return tuple(mechanics)


def _residual(
    residuals: list[OracleResidual],
    *,
    kind: str,
    text: str,
    span: SourceSpan,
    reason: str,
    blockers: Sequence[str] = (),
) -> str:
    residual_id = f"r{len(residuals) + 1}"
    residuals.append(
        OracleResidual(
            residual_id=residual_id,
            kind=kind,
            text=text,
            span=span,
            material=True,
            reason=reason,
            blockers=tuple(blockers),
        )
    )
    return residual_id


def _compile_face(
    record: CardRecord,
    *,
    face_id: str,
    face_name: str,
    type_line: str,
    oracle_text: str,
    keywords: Sequence[str],
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
) -> OracleFaceIR:
    nodes: list[OracleNode] = []
    residuals: list[OracleResidual] = []
    permanent = any(
        card_type in type_line.casefold()
        for card_type in (
            "artifact",
            "battle",
            "creature",
            "enchantment",
            "land",
            "planeswalker",
        )
    )
    spell = any(
        card_type in type_line.casefold()
        for card_type in ("instant", "sorcery")
    )
    for index, (line, span) in enumerate(_source_lines(oracle_text), 1):
        node_id = f"{face_id}:n{index}"
        material_line = _without_parenthetical_reminder(line)
        keyword_mechanics = _keyword_mechanics(
            material_line, keywords
        )
        if keyword_mechanics is not None:
            missing = sorted(
                set(keyword_mechanics) - trusted_mechanics
            )
            residual_ids = (
                (
                    _residual(
                        residuals,
                        kind="dependency_contract",
                        text=line,
                        span=span,
                        reason=(
                            "recognized keyword lacks a trusted "
                            "mechanic contract"
                        ),
                        blockers=tuple(
                            f"mechanic:{mechanic}"
                            for mechanic in missing
                        ),
                    ),
                )
                if missing
                else ()
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="keyword_ability",
                    text=line,
                    span=span,
                    active_zone="battlefield",
                    event="continuous",
                    lowerable=True,
                    exact=not missing,
                    template_id="printed-keyword-list-v1",
                    mechanics=keyword_mechanics,
                    residual_ids=residual_ids,
                )
            )
            continue

        abilities = parse_activated_abilities(
            card_name=face_name or record.name,
            oracle_text=line,
            keywords=keywords,
        )
        if abilities:
            ability = abilities[0]
            template, effects, target_schema, mechanics = (
                _effect_template(
                    ability.effect_text,
                    card_name=face_name or record.name,
                )
            )
            residual_ids: list[str] = []
            if not ability.compiled_cost:
                residual_ids.append(
                    _residual(
                        residuals,
                        kind="cost",
                        text=ability.cost_text,
                        span=span,
                        reason="mandatory activated cost is not compiled",
                        blockers=(
                            "complete alternate/additional-cost grammar",
                            "restricted payment predicates",
                        ),
                    )
                )
            if template is None and not ability.mana_ability:
                residual_ids.append(
                    _residual(
                        residuals,
                        kind="effect",
                        text=ability.effect_text,
                        span=span,
                        reason="activated effect has no exact generic template",
                    )
                )
            lowerable = not residual_ids and (
                template is not None or ability.mana_ability
            )
            dependencies = (
                mechanics
                if template is not None
                else ("cr-605-mana-abilities",)
            )
            missing = sorted(
                set(dependencies) - trusted_mechanics
            )
            if lowerable and missing:
                residual_ids.append(
                    _residual(
                        residuals,
                        kind="dependency_contract",
                        text=line,
                        span=span,
                        reason=(
                            "lowerable ability depends on untrusted "
                            "mechanic contracts"
                        ),
                        blockers=tuple(
                            f"mechanic:{mechanic}"
                            for mechanic in missing
                        ),
                    )
                )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind=(
                        "mana_ability"
                        if ability.mana_ability
                        else "activated_ability"
                    ),
                    text=line,
                    span=span,
                    active_zone=ability.zones[0],
                    event="activate",
                    lowerable=lowerable,
                    exact=lowerable and not missing,
                    template_id=(
                        "intrinsic-mana-ability-v1"
                        if ability.mana_ability and template is None
                        else template
                    ),
                    cost=_cost_dict(ability),
                    effects=effects,
                    target_schema=target_schema,
                    mechanics=mechanics,
                    residual_ids=tuple(residual_ids),
                )
            )
            continue

        if _TRIGGER_PREFIX.match(line):
            source_name = re.escape(face_name or record.name)
            trigger = re.fullmatch(
                rf"(?:when|whenever) "
                rf"(?P<subject>this (?:artifact|aura|card|creature|"
                rf"enchantment|equipment|land|permanent)|{source_name}) "
                rf"(?P<event>enters|dies|leaves the battlefield), "
                rf"(?P<body>.+)",
                line,
                re.IGNORECASE,
            )
            template = None
            effects: tuple[Mapping[str, Any], ...] = ()
            target_schema = None
            mechanics: tuple[str, ...] = ()
            event = "unresolved"
            if trigger:
                template, effects, target_schema, mechanics = (
                    _effect_template(
                        trigger.group("body"),
                        card_name=face_name or record.name,
                    )
                )
                event = {
                    "enters": "permanent.enter.self",
                    "dies": "creature.dies.self",
                    "leaves the battlefield": "permanent.leave.self",
                }[trigger.group("event").casefold()]
            dependencies = (
                "cr-603-handling-triggered-abilities",
                *mechanics,
            )
            missing = sorted(set(dependencies) - trusted_mechanics)
            residual_ids: tuple[str, ...]
            if trigger is not None and template is not None:
                residual_ids = (
                    (
                        _residual(
                            residuals,
                            kind="dependency_contract",
                            text=line,
                            span=span,
                            reason=(
                                "lowerable trigger depends on untrusted "
                                "mechanic contracts"
                            ),
                            blockers=tuple(
                                f"mechanic:{mechanic}"
                                for mechanic in missing
                            ),
                        ),
                    )
                    if missing
                    else ()
                )
            else:
                residual_ids = (
                    _residual(
                        residuals,
                        kind="trigger",
                        text=line,
                        span=span,
                        reason=(
                            "trigger effect has no exact generic template"
                            if trigger is not None
                            else "trigger condition/event binding is not exact"
                        ),
                        blockers=(
                            "normalized event binding",
                            "intervening-if and reflexive-trigger grammar",
                        ),
                    ),
                )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="triggered_ability",
                    text=line,
                    span=span,
                    active_zone="battlefield",
                    event=event,
                    lowerable=trigger is not None and template is not None,
                    exact=(
                        trigger is not None
                        and template is not None
                        and not missing
                    ),
                    template_id=template,
                    effects=effects,
                    target_schema=target_schema,
                    mechanics=dependencies,
                    residual_ids=residual_ids,
                )
            )
            continue

        enters_tapped = re.fullmatch(
            rf"(?:this (?:artifact|creature|enchantment|land|permanent)"
            rf"|{re.escape(face_name or record.name)}) enters tapped\.?",
            line,
            re.IGNORECASE,
        )
        if enters_tapped:
            dependencies = ("cr-614-replacement-effects",)
            missing = sorted(set(dependencies) - trusted_mechanics)
            residual_ids = (
                (
                    _residual(
                        residuals,
                        kind="dependency_contract",
                        text=line,
                        span=span,
                        reason=(
                            "lowerable entry replacement depends on an "
                            "untrusted mechanic contract"
                        ),
                        blockers=tuple(
                            f"mechanic:{mechanic}"
                            for mechanic in missing
                        ),
                    ),
                )
                if missing
                else ()
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="replacement_effect",
                    text=line,
                    span=span,
                    active_zone="all",
                    event="permanent.enter.self",
                    lowerable=True,
                    exact=not missing,
                    template_id="enters-tapped-self-v1",
                    mechanics=dependencies,
                    residual_ids=residual_ids,
                )
            )
            continue

        declaration_cost = parse_declaration_cost_line(
            line,
            card_name=face_name or record.name,
        )
        if declaration_cost.recognized:
            template = declaration_cost.template
            if declaration_cost.exact and template is not None:
                dependencies = template.mechanics
                missing = sorted(
                    set(dependencies) - trusted_mechanics
                )
                residual_ids = (
                    (
                        _residual(
                            residuals,
                            kind="dependency_contract",
                            text=line,
                            span=span,
                            reason=(
                                "declaration cost depends on untrusted "
                                "mechanic contracts"
                            ),
                            blockers=tuple(
                                f"mechanic:{mechanic}"
                                for mechanic in missing
                            ),
                        ),
                    )
                    if missing
                    else ()
                )
                nodes.append(
                    OracleNode(
                        node_id=node_id,
                        kind="static_ability",
                        text=line,
                        span=span,
                        active_zone="battlefield",
                        event="continuous",
                        lowerable=True,
                        exact=not missing,
                        template_id=template.template_id,
                        cost={
                            "kind": "declaration_mana",
                            "declarations": list(
                                template.declarations
                            ),
                            "scope": template.scope,
                            "mana": dict(template.mana),
                            "printed": template.printed_cost,
                            "source_condition": (
                                template.source_condition
                            ),
                        },
                        mechanics=dependencies,
                        residual_ids=residual_ids,
                    )
                )
                continue
            residual_id = _residual(
                residuals,
                kind="declaration_cost",
                text=line,
                span=span,
                reason=(
                    declaration_cost.reason
                    or "declaration cost grammar is unresolved"
                ),
                blockers=(
                    "nonmana declaration costs",
                    "variable and alternative mana declaration costs",
                    "conditional declaration-cost grammar",
                ),
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="static_ability",
                    text=line,
                    span=span,
                    active_zone="battlefield",
                    event="continuous",
                    lowerable=False,
                    exact=False,
                    mechanics=declaration_cost.declarations,
                    residual_ids=(residual_id,),
                )
            )
            continue

        declaration_restriction = parse_declaration_restriction_line(
            line,
            card_name=face_name or record.name,
        )
        if declaration_restriction.recognized:
            template = declaration_restriction.template
            if declaration_restriction.exact and template is not None:
                dependencies = template.mechanics
                missing = sorted(
                    set(dependencies) - trusted_mechanics
                )
                residual_ids = (
                    (
                        _residual(
                            residuals,
                            kind="dependency_contract",
                            text=line,
                            span=span,
                            reason=(
                                "declaration restriction depends on "
                                "untrusted mechanic contracts"
                            ),
                            blockers=tuple(
                                f"mechanic:{mechanic}"
                                for mechanic in missing
                            ),
                        ),
                    )
                    if missing
                    else ()
                )
                nodes.append(
                    OracleNode(
                        node_id=node_id,
                        kind="static_ability",
                        text=line,
                        span=span,
                        active_zone="battlefield",
                        event="continuous",
                        lowerable=True,
                        exact=not missing,
                        template_id=template.template_id,
                        effects=(template.effect(),),
                        mechanics=dependencies,
                        residual_ids=residual_ids,
                    )
                )
                continue
            dependencies = tuple(
                mechanic
                for declaration, mechanic in (
                    ("attack", "cr-508-declare-attackers-step"),
                    ("block", "cr-509-declare-blockers-step"),
                )
                if declaration in declaration_restriction.declarations
            )
            residual_id = _residual(
                residuals,
                kind="declaration_restriction",
                text=line,
                span=span,
                reason=(
                    declaration_restriction.reason
                    or "declaration restriction grammar is unresolved"
                ),
                blockers=(
                    "conditional declaration predicates",
                    "temporary declaration restrictions",
                    "broader evasion and group constraints",
                ),
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="static_ability",
                    text=line,
                    span=span,
                    active_zone="battlefield",
                    event="continuous",
                    lowerable=False,
                    exact=False,
                    mechanics=dependencies,
                    residual_ids=(residual_id,),
                )
            )
            continue

        if _REPLACEMENT_MARKERS.search(line):
            residual_id = _residual(
                residuals,
                kind="replacement_effect",
                text=line,
                span=span,
                reason="replacement/prevention ordering is not compiled",
                blockers=(
                    "replacement applicability",
                    "affected-player ordering",
                    "self-replacement and prevention ordering",
                ),
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="replacement_effect",
                    text=line,
                    span=span,
                    active_zone="battlefield" if permanent else "stack",
                    event="replace",
                    lowerable=False,
                    exact=False,
                    residual_ids=(residual_id,),
                )
            )
            continue

        ability_word = _ABILITY_WORD.match(line)
        body = ability_word.group("body") if ability_word else line
        template, effects, target_schema, mechanics = _effect_template(
            body,
            card_name=face_name or record.name,
        )
        if spell and template is not None:
            dependency_gate = _dependency_gate(
                mechanics=mechanics,
                effects=effects,
                target_schema=target_schema,
                trusted_mechanics=trusted_mechanics,
                capability_registry=capability_registry,
                capability_profile=capability_profile,
            )
            missing = dependency_gate.blockers
            residual_ids = (
                (
                    _residual(
                        residuals,
                        kind="dependency_contract",
                        text=line,
                        span=span,
                        reason=(
                            "lowerable spell depends on untrusted "
                            "rules dependencies"
                        ),
                        blockers=missing,
                    ),
                )
                if missing
                else ()
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="spell_ability",
                    text=line,
                    span=span,
                    active_zone="stack",
                    event="resolve",
                    lowerable=True,
                    exact=not missing,
                    template_id=template,
                    effects=effects,
                    target_schema=target_schema,
                    mechanics=mechanics,
                    residual_ids=residual_ids,
                    capability_dependencies=(
                        dependency_gate.capabilities
                    ),
                    capability_closure=(
                        dependency_gate.closure.reachable
                        if dependency_gate.closure is not None
                        else ()
                    ),
                    capability_profile=(
                        dependency_gate.closure.profile
                        if dependency_gate.closure is not None
                        else None
                    ),
                    capability_fingerprint=(
                        dependency_gate.closure.fingerprint
                        if dependency_gate.closure is not None
                        else None
                    ),
                )
            )
            continue

        residual_id = _residual(
            residuals,
            kind="static_ability" if permanent else "spell_effect",
            text=line,
            span=span,
            reason=(
                "static/continuous text has no exact typed contract"
                if permanent
                else "spell effect has no exact generic template"
            ),
            blockers=(
                ("continuous-effect layers and dependencies",)
                if permanent
                else ()
            ),
        )
        nodes.append(
            OracleNode(
                node_id=node_id,
                kind="static_ability" if permanent else "spell_ability",
                text=line,
                span=span,
                active_zone="battlefield" if permanent else "stack",
                event="continuous" if permanent else "resolve",
                lowerable=False,
                exact=False,
                residual_ids=(residual_id,),
            )
        )
    return OracleFaceIR(
        face_id=face_id,
        face_name=face_name,
        oracle_text=oracle_text,
        nodes=tuple(nodes),
        residuals=tuple(residuals),
    )


def compile_oracle_card(
    record: CardRecord,
    *,
    trusted_mechanics: Iterable[str] = (),
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
) -> OracleCardIR:
    if (
        capability_registry is not None
        and capability_profile not in capability_registry.profiles
    ):
        raise ValueError(
            f"Unknown capability profile: {capability_profile}"
        )
    trusted = frozenset(
        str(mechanic).casefold() for mechanic in trusted_mechanics
    )
    face_values: list[tuple[str, str, str, str, Sequence[str]]] = []
    if record.faces:
        for index, face in enumerate(record.faces):
            face_values.append(
                (
                    str(face.get("name") or f"face-{index + 1}"),
                    str(face.get("name") or record.name),
                    str(face.get("type_line") or record.type_line),
                    str(face.get("oracle_text") or ""),
                    tuple(face.get("keywords") or record.keywords),
                )
            )
    else:
        face_values.append(
            (
                "front",
                record.name,
                record.type_line,
                record.oracle_text,
                record.keywords,
            )
        )
    faces = tuple(
        _compile_face(
            record,
            face_id=face_id,
            face_name=face_name,
            type_line=type_line,
            oracle_text=oracle_text,
            keywords=keywords,
            trusted_mechanics=trusted,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
        )
        for face_id, face_name, type_line, oracle_text, keywords in face_values
    )
    oracle_hash = hashlib.sha256(
        record.oracle_text.encode("utf-8")
    ).hexdigest()
    semantic_payload = {
        "oracle_id": record.oracle_id,
        "oracle_hash": oracle_hash,
        "schema_version": ORACLE_IR_SCHEMA_VERSION,
        "compiler_version": ORACLE_COMPILER_VERSION,
        "faces": [face.to_dict() for face in faces],
    }
    return OracleCardIR(
        oracle_id=record.oracle_id,
        card_name=record.name,
        schema_version=ORACLE_IR_SCHEMA_VERSION,
        compiler_version=ORACLE_COMPILER_VERSION,
        oracle_hash=oracle_hash,
        faces=faces,
        semantic_hash=hashlib.sha256(
            stable_json(semantic_payload).encode("utf-8")
        ).hexdigest(),
    )


def generated_programs(
    db: CardDatabase,
    record: CardRecord,
    *,
    trust_level: str = "provisional",
    trusted_mechanics: Iterable[str] = (),
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
) -> list[SemanticProgram]:
    """Compatibility API for the extracted generated-program stage."""

    from .compiler.program_generation import generated_programs as generate

    return generate(
        db,
        record,
        trust_level=trust_level,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )


def register_generated_programs(
    db: CardDatabase,
    registry: SemanticRegistry,
    records: Iterable[CardRecord],
    *,
    trust_level: str = "provisional",
    trusted_mechanics: Iterable[str] = (),
    capability_registry: CapabilityRegistry | None = None,
    capability_profile: str = "traditional",
) -> dict[str, Any]:
    """Compatibility API for extracted generated-program registration."""

    from .compiler.program_generation import register_generated_programs as register

    return register(
        db,
        registry,
        records,
        trust_level=trust_level,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )


def oracle_corpus_coverage(
    db: CardDatabase,
    *,
    commander_legal_only: bool = False,
    limit: int | None = None,
    residual_limit: int = 100,
    include_residual_text: bool = False,
) -> dict[str, Any]:
    statuses: Counter[str] = Counter()
    templates: Counter[str] = Counter()
    residual_kinds: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    total_faces = 0
    total_residuals = 0
    for record in db.iter_cards(
        commander_legal_only=commander_legal_only,
        limit=limit,
    ):
        ir = compile_oracle_card(record)
        statuses[ir.status] += 1
        total_faces += len(ir.faces)
        for face in ir.faces:
            for node in face.nodes:
                if node.template_id:
                    templates[node.template_id] += 1
            for residual in face.residuals:
                if not residual.material:
                    continue
                total_residuals += 1
                residual_kinds[residual.kind] += 1
                if len(examples) < residual_limit:
                    example = {
                        "oracle_id": record.oracle_id,
                        "card_name": record.name,
                        "face": face.face_name,
                        "residual_id": residual.residual_id,
                        "kind": residual.kind,
                        "span": asdict(residual.span),
                        "reason": residual.reason,
                        "blockers": list(residual.blockers),
                        "text_sha256": hashlib.sha256(
                            residual.text.encode("utf-8")
                        ).hexdigest(),
                    }
                    if include_residual_text:
                        example["text"] = residual.text
                    examples.append(example)
    total_cards = sum(statuses.values())
    metadata = db.metadata()
    return {
        "schema_version": ORACLE_IR_SCHEMA_VERSION,
        "compiler_version": ORACLE_COMPILER_VERSION,
        "card_data_snapshot": {
            key: metadata.get(key)
            for key in (
                "schema_version",
                "card_count",
                "ruling_count",
                "oracle_source_sha256",
                "rulings_source_sha256",
                "scryfall_oracle_updated_at",
                "scryfall_rulings_updated_at",
            )
            if metadata.get(key) is not None
        },
        "commander_legal_only": commander_legal_only,
        "limited": limit is not None,
        "total_oracle_ids": total_cards,
        "total_faces": total_faces,
        "status_counts": dict(sorted(statuses.items())),
        "exact_fraction": (
            round(statuses["exact"] / total_cards, 6)
            if total_cards
            else 0.0
        ),
        "material_residuals": total_residuals,
        "residual_kinds": dict(residual_kinds.most_common()),
        "templates": dict(templates.most_common()),
        "residual_examples": examples,
        "current_snapshot_complete": bool(total_cards)
        and statuses["exact"] == total_cards
        and total_residuals == 0,
    }


def explain_oracle_ir(ir: OracleCardIR) -> dict[str, Any]:
    return {
        "card_name": ir.card_name,
        "oracle_id": ir.oracle_id,
        "status": ir.status,
        "compiler_version": ir.compiler_version,
        "semantic_hash": ir.semantic_hash,
        "summary": [
            {
                "face": face.face_name,
                "exact": face.exact,
                "nodes": [
                    {
                        "kind": node.kind,
                        "template_id": node.template_id,
                        "exact": node.exact,
                        "lowerable": node.lowerable,
                        "source_line": node.span.line,
                        "mechanics": list(node.mechanics),
                    }
                    for node in face.nodes
                ],
                "material_residuals": [
                    {
                        "kind": residual.kind,
                        "reason": residual.reason,
                        "source_line": residual.span.line,
                        "blockers": list(residual.blockers),
                    }
                    for residual in face.residuals
                    if residual.material
                ],
            }
            for face in ir.faces
        ],
        "fail_closed": bool(ir.material_residuals),
    }


def execute_oracle_operation(
    operation: str,
    *,
    db_path: str | Path,
    card: str | None = None,
    commander_legal_only: bool = False,
    limit: int | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    if operation not in ORACLE_OPERATIONS:
        raise ValueError(f"Unknown Oracle operation {operation!r}")
    with CardDatabase(db_path) as db:
        if operation in {"parse", "explain"}:
            if not card:
                raise ValueError(f"oracle {operation} requires a card name")
            ir = compile_oracle_card(db.lookup(card))
            value = (
                ir.to_dict()
                if operation == "parse"
                else explain_oracle_ir(ir)
            )
        else:
            value = oracle_corpus_coverage(
                db,
                commander_legal_only=commander_legal_only,
                limit=limit,
                residual_limit=(100 if operation == "residuals" else 20),
                include_residual_text=operation == "residuals",
            )
            if operation == "residuals":
                value = {
                    "schema_version": value["schema_version"],
                    "compiler_version": value["compiler_version"],
                    "total_oracle_ids": value["total_oracle_ids"],
                    "material_residuals": value["material_residuals"],
                    "residual_kinds": value["residual_kinds"],
                    "residual_examples": value["residual_examples"],
                }
    if output is not None:
        Path(output).write_text(stable_json(value), encoding="utf-8")
    return value
