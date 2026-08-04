from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from .abilities import parse_activated_abilities
from .aura import keyword_target_schema
from .carddb import CardDatabase, CardRecord
from .compiler.corpus_reporting import (
    execute_oracle_operation,
    explain_oracle_ir,
    oracle_corpus_coverage,
)
from .compiler.continuous_templates import (
    controlled_creature_until_end_of_turn_effect,
)
from .compiler.activated_costs import activated_ability_cost
from .compiler.dependency_gate import (
    dependency_gate as _dependency_gate,
    explicit_capability_gate as _explicit_capability_gate,
    keyword_dependency_gate,
)
from .compiler.keyword_templates import keyword_mechanics
from .compiler.prevention_templates import (
    fixed_prevention_effect_template,
    prevention_trigger_effect_template,
)
from .compiler.runtime_templates import static_runtime_template
from .declaration_costs import parse_declaration_cost_line
from .declaration_restrictions import parse_declaration_restriction_line
from .rules.capabilities import CapabilityRegistry
from .semantics import SemanticProgram, SemanticRegistry
from .util import stable_json


ORACLE_IR_SCHEMA_VERSION = 1
ORACLE_COMPILER_VERSION = "oracle-ir-v26"
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
    handlers: tuple[Mapping[str, Any], ...] = ()
    target_schema: Mapping[str, Any] | None = None
    event_condition: Mapping[str, Any] | None = None
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
            "handlers": [dict(handler) for handler in self.handlers],
            "target_schema": (
                dict(self.target_schema)
                if self.target_schema is not None
                else None
            ),
            "event_condition": (
                dict(self.event_condition)
                if self.event_condition is not None
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


def _reviewed_effect_template(
    text: str,
    *,
    card_name: str,
) -> tuple[
    str | None,
    tuple[Mapping[str, Any], ...],
    Mapping[str, Any] | None,
    tuple[str, ...],
]:
    temporary_modifier = controlled_creature_until_end_of_turn_effect(
        text.strip()
    )
    if temporary_modifier is not None:
        template, effects, mechanics = temporary_modifier
        return template, effects, None, mechanics
    prevention = fixed_prevention_effect_template(
        text.strip(),
        card_name=card_name,
    )
    return prevention or _effect_template(text, card_name=card_name)


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


def _keyword_node(
    *,
    node_id: str,
    line: str,
    material_line: str,
    span: SourceSpan,
    keywords: Sequence[str],
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
) -> OracleNode | None:
    mechanics = keyword_mechanics(material_line, keywords)
    if mechanics is None:
        return None
    gate = keyword_dependency_gate(
        material_line=material_line,
        mechanics=mechanics,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    enchant_target_schema = keyword_target_schema(material_line, mechanics)
    residual_ids = (
        (
            _residual(
                residuals,
                kind="dependency_contract",
                text=line,
                span=span,
                reason="recognized keyword lacks a trusted mechanic contract",
                blockers=gate.blockers,
            ),
        )
        if gate.blockers
        else ()
    )
    dredge = re.fullmatch(
        r"Dredge\s+(?P<count>[1-9]\d*)\.?",
        material_line,
        re.IGNORECASE,
    )
    if mechanics == ("dredge",) and dredge is not None:
        return OracleNode(
            node_id=node_id,
            kind="keyword_ability",
            text=line,
            span=span,
            active_zone="graveyard",
            event="draw",
            lowerable=True,
            exact=not gate.blockers,
            template_id="dredge-keyword-replacement-v1",
            mechanics=mechanics,
            handlers=(
                {
                    "handler_id": "replacement.draw.dredge.v1",
                    "schema_version": 1,
                    "event": "draw",
                    "modification": {
                        "mill_count": int(dredge.group("count")),
                    },
                },
            ),
            residual_ids=residual_ids,
            capability_dependencies=gate.capabilities,
            capability_closure=(
                gate.closure.reachable if gate.closure is not None else ()
            ),
            capability_profile=(
                gate.closure.profile if gate.closure is not None else None
            ),
            capability_fingerprint=(
                gate.closure.fingerprint if gate.closure is not None else None
            ),
        )
    return OracleNode(
        node_id=node_id,
        kind="keyword_ability",
        text=line,
        span=span,
        active_zone="battlefield",
        event="continuous",
        lowerable=True,
        exact=not gate.blockers,
        template_id="printed-keyword-list-v1",
        target_schema=enchant_target_schema,
        mechanics=mechanics,
        residual_ids=residual_ids,
        capability_dependencies=gate.capabilities,
        capability_closure=(
            gate.closure.reachable if gate.closure is not None else ()
        ),
        capability_profile=(
            gate.closure.profile if gate.closure is not None else None
        ),
        capability_fingerprint=(
            gate.closure.fingerprint if gate.closure is not None else None
        ),
    )


def _runtime_handler_node(
    *,
    node_id: str,
    line: str,
    span: SourceSpan,
    compiled: tuple[str, Mapping[str, Any], str],
    kind: str,
    event: str,
    dependency_reason: str,
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
) -> OracleNode:
    template_id, handler, capability = compiled
    gate = _explicit_capability_gate(
        capability,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    residual_ids = (
        (
            _residual(
                residuals,
                kind="dependency_contract",
                text=line,
                span=span,
                reason=dependency_reason,
                blockers=gate.blockers,
            ),
        )
        if gate.blockers
        else ()
    )
    return OracleNode(
        node_id=node_id,
        kind=kind,
        text=line,
        span=span,
        active_zone="battlefield",
        event=event,
        lowerable=True,
        exact=not gate.blockers,
        template_id=template_id,
        handlers=(handler,),
        residual_ids=residual_ids,
        capability_dependencies=gate.capabilities,
        capability_closure=(
            gate.closure.reachable if gate.closure is not None else ()
        ),
        capability_profile=(
            gate.closure.profile if gate.closure is not None else None
        ),
        capability_fingerprint=(
            gate.closure.fingerprint if gate.closure is not None else None
        ),
    )


def _trigger_node(
    *,
    node_id: str,
    line: str,
    span: SourceSpan,
    card_name: str,
    trusted_mechanics: frozenset[str],
    capability_registry: CapabilityRegistry | None,
    capability_profile: str,
    residuals: list[OracleResidual],
) -> OracleNode | None:
    """Compile one closed ordinary or CR 615.13 triggered ability."""

    if not _TRIGGER_PREFIX.match(line):
        return None
    source_name = re.escape(card_name)
    trigger = re.fullmatch(
        rf"(?:when|whenever) "
        rf"(?P<subject>this (?:artifact|aura|card|creature|"
        rf"enchantment|equipment|land|permanent)|{source_name}) "
        rf"(?P<event>enters|dies|leaves the battlefield), "
        rf"(?P<body>.+)",
        line,
        re.IGNORECASE,
    )
    prevention_trigger = prevention_trigger_effect_template(
        line,
        card_name=card_name,
    )
    template = None
    effects: tuple[Mapping[str, Any], ...] = ()
    target_schema = None
    mechanics: tuple[str, ...] = ()
    event_condition: Mapping[str, Any] | None = None
    event = "unresolved"
    recognized = False
    if prevention_trigger is not None:
        (
            template,
            effects,
            target_schema,
            mechanics,
            event_condition,
        ) = prevention_trigger
        event = "damage.prevented"
        recognized = True
    elif trigger:
        template, effects, target_schema, mechanics = (
            _reviewed_effect_template(
                trigger.group("body"),
                card_name=card_name,
            )
        )
        event = {
            "enters": "permanent.enter.self",
            "dies": "creature.dies.self",
            "leaves the battlefield": "permanent.leave.self",
        }[trigger.group("event").casefold()]
        recognized = True
    dependencies = (
        "cr-603-handling-triggered-abilities",
        *(
            ("trigger-event-normalized-zone-change",)
            if trigger is not None
            else ()
        ),
        *mechanics,
    )
    gate = _dependency_gate(
        mechanics=dependencies,
        effects=effects,
        target_schema=target_schema,
        trusted_mechanics=trusted_mechanics,
        capability_registry=capability_registry,
        capability_profile=capability_profile,
    )
    if recognized and template is not None:
        residual_ids = (
            (
                _residual(
                    residuals,
                    kind="dependency_contract",
                    text=line,
                    span=span,
                    reason=(
                        "lowerable trigger depends on untrusted mechanic contracts"
                    ),
                    blockers=gate.blockers,
                ),
            )
            if gate.blockers
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
                    if recognized
                    else "trigger condition/event binding is not exact"
                ),
                blockers=(
                    "normalized event binding",
                    "intervening-if and reflexive-trigger grammar",
                ),
            ),
        )
    closure = gate.closure
    return OracleNode(
        node_id=node_id,
        kind="triggered_ability",
        text=line,
        span=span,
        active_zone="battlefield",
        event=event,
        lowerable=recognized and template is not None,
        exact=recognized and template is not None and not gate.blockers,
        template_id=template,
        effects=effects,
        target_schema=target_schema,
        event_condition=event_condition,
        mechanics=dependencies,
        residual_ids=residual_ids,
        capability_dependencies=gate.capabilities,
        capability_closure=closure.reachable if closure is not None else (),
        capability_profile=closure.profile if closure is not None else None,
        capability_fingerprint=(
            closure.fingerprint if closure is not None else None
        ),
    )


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
        keyword_node = _keyword_node(
            node_id=node_id,
            line=line,
            material_line=material_line,
            span=span,
            keywords=keywords,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
            residuals=residuals,
        )
        if keyword_node is not None:
            nodes.append(keyword_node)
            continue

        abilities = parse_activated_abilities(
            card_name=face_name or record.name,
            oracle_text=line,
            keywords=keywords,
        )
        if abilities:
            ability = abilities[0]
            template, effects, target_schema, mechanics = (
                _reviewed_effect_template(
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
                cost=activated_ability_cost(ability),
                    effects=effects,
                    target_schema=target_schema,
                    mechanics=mechanics,
                    residual_ids=tuple(residual_ids),
                )
            )
            continue

        trigger_node = _trigger_node(
            node_id=node_id,
            line=line,
            span=span,
            card_name=face_name or record.name,
            trusted_mechanics=trusted_mechanics,
            capability_registry=capability_registry,
            capability_profile=capability_profile,
            residuals=residuals,
        )
        if trigger_node is not None:
            nodes.append(trigger_node)
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

        runtime_template = static_runtime_template(
            material_line,
            source_damageable=any(
                card_type in type_line.casefold()
                for card_type in ("battle", "creature", "planeswalker")
            ),
        )
        if runtime_template is not None:
            nodes.append(
                _runtime_handler_node(
                    node_id=node_id,
                    line=line,
                    span=span,
                    compiled=runtime_template.compiled,
                    kind=runtime_template.kind,
                    event=runtime_template.event,
                    dependency_reason=runtime_template.dependency_reason,
                    capability_registry=capability_registry,
                    capability_profile=capability_profile,
                    residuals=residuals,
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
        template, effects, target_schema, mechanics = _reviewed_effect_template(
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
    promote_exact_runtime_handlers: bool = False,
    promote_exact_trigger_programs: bool = False,
    promote_exact_capability_declarations: bool = False,
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
        promote_exact_runtime_handlers=promote_exact_runtime_handlers,
        promote_exact_trigger_programs=promote_exact_trigger_programs,
        promote_exact_capability_declarations=(
            promote_exact_capability_declarations
        ),
    )
