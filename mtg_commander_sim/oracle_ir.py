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
from .semantics import SemanticProgram, SemanticRegistry
from .util import stable_json


ORACLE_IR_SCHEMA_VERSION = 1
ORACLE_COMPILER_VERSION = "oracle-ir-v1"
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
    r"^(?P<name>ward|equip|cycling|crew|kicker|"
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
    "lifelink",
    "menace",
    "reach",
    "shadow",
    "shroud",
    "trample",
    "vigilance",
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

    def to_dict(self) -> dict[str, Any]:
        return {
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
            ("drawing-a-card",),
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
            ("drawing-a-card", "target"),
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
            ("drawing-a-card", "apnap"),
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
            ("life",),
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
            ("life", "apnap"),
        )
    match = re.fullmatch(
        rf"(?:{name}|this spell) deals (?P<count>\d+) damage to any target\.?",
        normalized,
        re.IGNORECASE,
    )
    if match:
        return (
            "damage-any-target-v1",
            (
                {
                    "op": "damage",
                    "target": "$target.0",
                    "amount": int(match.group("count")),
                },
            ),
            {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            },
            ("damage", "target"),
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
            ("destroy", "target"),
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
            ("exile", "target"),
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
            ("return", "target"),
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
            ("counter", "target"),
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
            ("mill", "target"),
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
            (action, "target"),
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
            ("continuous-effects", "target"),
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
                else ("mana-abilities",)
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
            trigger_body = re.split(r",\s*", line, maxsplit=1)
            template = None
            effects: tuple[Mapping[str, Any], ...] = ()
            target_schema = None
            mechanics: tuple[str, ...] = ()
            if len(trigger_body) == 2:
                template, effects, target_schema, mechanics = (
                    _effect_template(
                        trigger_body[1],
                        card_name=face_name or record.name,
                    )
                )
            residual_id = _residual(
                residuals,
                kind="trigger",
                text=line,
                span=span,
                reason=(
                    "trigger condition/event binding is not exact"
                    if template is not None
                    else "trigger condition and effect are not compiled"
                ),
                blockers=(
                    "normalized event binding",
                    "intervening-if and reflexive-trigger grammar",
                ),
            )
            nodes.append(
                OracleNode(
                    node_id=node_id,
                    kind="triggered_ability",
                    text=line,
                    span=span,
                    active_zone="battlefield" if permanent else "stack",
                    event="unresolved",
                    lowerable=False,
                    exact=False,
                    template_id=template,
                    effects=effects,
                    target_schema=target_schema,
                    mechanics=mechanics,
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
            missing = sorted(set(mechanics) - trusted_mechanics)
            residual_ids = (
                (
                    _residual(
                        residuals,
                        kind="dependency_contract",
                        text=line,
                        span=span,
                        reason=(
                            "lowerable spell depends on untrusted "
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
) -> OracleCardIR:
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


def _rulings_hash(db: CardDatabase, record: CardRecord) -> str:
    rows = sorted(
        (asdict(ruling) for ruling in db.rulings(record)),
        key=lambda row: (
            str(row["published_at"]),
            str(row["source"]),
            str(row["comment"]),
            str(row["oracle_id"]),
        ),
    )
    return hashlib.sha256(stable_json(rows).encode("utf-8")).hexdigest()


def generated_programs(
    db: CardDatabase,
    record: CardRecord,
    *,
    trust_level: str = "provisional",
) -> list[SemanticProgram]:
    """Lower exact IR nodes into the existing generic effect DSL.

    Generated programs remain provisional until every mechanic dependency in
    their contract is trusted. This allows arbitrary new Oracle cards to be
    compiled without pretending that a template match proves global CR
    correctness.
    """

    ir = compile_oracle_card(record)
    programs: list[SemanticProgram] = []
    rulings_hash = _rulings_hash(db, record)
    for face in ir.faces:
        activated_index = 0
        for node in face.nodes:
            if node.kind in {"activated_ability", "mana_ability"}:
                activated_index += 1
            if not node.lowerable or not node.effects:
                continue
            if node.kind == "spell_ability":
                ability_id = f"spell:{face.face_id}"
            elif node.kind == "activated_ability":
                ability_id = f"ability:ab{node.span.line}"
            else:
                continue
            key = f"{record.oracle_id}:{ability_id}"
            programs.append(
                SemanticProgram(
                    key=key,
                    label=(
                        record.name
                        if node.kind == "spell_ability"
                        else f"{record.name} — {node.text}"
                    ),
                    effects=[dict(effect) for effect in node.effects],
                    destination=(
                        "graveyard"
                        if node.kind == "spell_ability"
                        else None
                    ),
                    requires_arbiter=trust_level != "trusted",
                    version=1,
                    oracle_id=record.oracle_id,
                    ability_id=ability_id,
                    active_zone=node.active_zone,
                    event=node.event,
                    trust_level=trust_level,
                    provenance={
                        "source_oracle_hash": ir.oracle_hash,
                        "source_rulings_hash": rulings_hash,
                        "authored_by": ORACLE_COMPILER_VERSION,
                        "review_status": "generated_review_required",
                        "template_id": node.template_id,
                        "source_span": asdict(node.span),
                        "semantic_hash": ir.semantic_hash,
                        "dependency_trust": (
                            "pending_mechanic_contracts"
                            if trust_level != "trusted"
                            else "verified"
                        ),
                    },
                    tests=[
                        f"oracle_template:{node.template_id}",
                    ],
                    target_schema=(
                        dict(node.target_schema)
                        if node.target_schema is not None
                        else None
                    ),
                    coverage=[
                        "generated_oracle_ir",
                        "spell_resolution"
                        if node.kind == "spell_ability"
                        else "activated_ability",
                        *node.mechanics,
                    ],
                )
            )
    return programs


def register_generated_programs(
    db: CardDatabase,
    registry: SemanticRegistry,
    records: Iterable[CardRecord],
    *,
    trust_level: str = "provisional",
) -> dict[str, Any]:
    generated = 0
    skipped_existing = 0
    cards_seen: set[str] = set()
    for record in records:
        if record.oracle_id in cards_seen:
            continue
        cards_seen.add(record.oracle_id)
        for program in generated_programs(
            db,
            record,
            trust_level=trust_level,
        ):
            if registry.get(program.key) is not None:
                skipped_existing += 1
                continue
            registry.put(program)
            generated += 1
    return {
        "cards_considered": len(cards_seen),
        "programs_generated": generated,
        "programs_skipped_existing": skipped_existing,
        "trust_level": trust_level,
        "compiler_version": ORACLE_COMPILER_VERSION,
    }


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
