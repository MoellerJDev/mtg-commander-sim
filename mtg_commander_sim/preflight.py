from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .abilities import parse_activated_abilities
from .carddb import CardDatabase, CardRecord
from .deck import DeckDefinition, DeckLoader
from .mana import ManaPlanError, parsed_cost
from .profiles import deck_profile_fingerprint
from .semantics import SemanticRegistry


def _generic_land_status(record: CardRecord) -> tuple[str, list[str]]:
    oracle = record.oracle_text.casefold()
    unresolved: list[str] = []
    supported = (
        not oracle
        or "add {" in oracle
        or "enters tapped unless you have two or more opponents" in oracle
        or "you may pay 2 life. if you don't, it enters tapped" in oracle
        or "enters tapped unless you control a forest" in oracle
        or (
            "enters tapped" in oracle
            and "unless" not in oracle
            and "when " not in oracle
        )
        or "search your library for a" in oracle
    )
    if "when " in oracle or "whenever " in oracle:
        unresolved.append("triggered_ability")
    if "as " in oracle and "enters" in oracle and not supported:
        unresolved.append("replacement_effect")
    if "return a land you control" in oracle:
        unresolved.append("triggered_ability")
    return ("trusted_builtin" if supported and not unresolved else "partial"), unresolved


def card_semantic_status(
    record: CardRecord,
    registry: SemanticRegistry,
) -> dict[str, Any]:
    programs = registry.programs_for_oracle(record.oracle_id)
    trust = registry.trust_for_oracle(record.oracle_id)
    unresolved: list[str] = []
    try:
        parsed_cost(record.mana_cost)
    except ManaPlanError:
        unresolved.append("cast_cost")
    abilities = parse_activated_abilities(
        card_name=record.name,
        oracle_text=record.oracle_text,
        keywords=record.keywords,
    )
    unresolved.extend(
        "activated_ability"
        for ability in abilities
        if not ability.compiled_cost and not ability.mana_ability
    )
    oracle = record.oracle_text.casefold()
    if record.is_land:
        generic_status, generic_unresolved = _generic_land_status(record)
        unresolved.extend(generic_unresolved)
    else:
        generic_status = "none"
    if any(marker in oracle for marker in ("when ", "whenever ", "at the beginning")):
        if not any(
            "triggered_ability" in program.coverage
            or program.event not in {"resolve", "cast"}
            for program in programs
            if program.trust_level == "trusted"
        ):
            unresolved.append("triggered_ability")
    if "instead" in oracle and not any(
        "replacement_effect" in program.coverage
        for program in programs
        if program.trust_level == "trusted"
    ):
        unresolved.append("replacement_effect")
    trusted_coverage = {
        value
        for program in programs
        if program.trust_level == "trusted"
        for value in program.coverage
    }
    if "triggered_ability" in trusted_coverage:
        unresolved = [
            value for value in unresolved if value != "triggered_ability"
        ]
    if "replacement_effect" in trusted_coverage:
        unresolved = [
            value for value in unresolved if value != "replacement_effect"
        ]
    unresolved = sorted(set(unresolved))
    if trust == "trusted" and not unresolved:
        status = "fully_playable"
    elif record.is_land and generic_status == "trusted_builtin" and not unresolved:
        status = "fully_playable"
        trust = "trusted"
    elif not record.oracle_text.strip() and not unresolved:
        status = "fully_playable"
        trust = "trusted"
    elif (
        record.produced_mana
        and not unresolved
        and not any(
            marker in oracle
            for marker in ("when ", "whenever ", "instead", "sacrifice another")
        )
    ):
        status = "fully_playable"
        trust = "trusted"
    elif trust == "trusted":
        status = "partial" if unresolved else "fully_playable"
    elif trust == "provisional":
        status = "partial"
    else:
        status = "unresolved"
    return {
        "name": record.name,
        "oracle_id": record.oracle_id,
        "status": status,
        "trust_level": trust,
        "unresolved": unresolved,
        "programs": [
            {
                "key": program.key,
                "version": program.version,
                "trust_level": program.trust_level,
            }
            for program in programs
        ],
    }


def semantic_preflight(
    db: CardDatabase,
    deck_or_source: DeckDefinition | str | Path,
    *,
    registry: SemanticRegistry | None = None,
    cache_dir: str | Path | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    registry = registry or SemanticRegistry()
    deck = (
        deck_or_source
        if isinstance(deck_or_source, DeckDefinition)
        else DeckLoader(db, cache_dir=cache_dir).load(
            deck_or_source, force_refresh=force_refresh
        )
    )
    cards = []
    for entry in deck.entries:
        if entry.board not in {"mainboard", "commander"}:
            continue
        row = card_semantic_status(db.lookup(entry.name), registry)
        row["quantity"] = entry.quantity
        cards.append(row)
    quantities = Counter()
    for row in cards:
        quantities[row["status"]] += int(row["quantity"])
    unresolved_costs = [
        row["name"] for row in cards if "cast_cost" in row["unresolved"]
    ]
    unresolved_abilities = [
        row["name"] for row in cards if "activated_ability" in row["unresolved"]
    ]
    unresolved_triggers = [
        row["name"] for row in cards if "triggered_ability" in row["unresolved"]
    ]
    unresolved_replacements = [
        row["name"] for row in cards if "replacement_effect" in row["unresolved"]
    ]
    unresolved_cards = [
        row for row in cards if row["status"] == "unresolved"
    ]
    partial_cards = [row for row in cards if row["status"] == "partial"]
    return {
        "schema_version": 1,
        "deck": deck.name,
        "source": deck.source,
        "commander": list(deck.commanders),
        "deck_fingerprint": deck_profile_fingerprint(deck),
        "total_cards": deck.total_cards(),
        "fully_playable_cards": quantities["fully_playable"],
        "partial_cards": quantities["partial"],
        "unresolved_cards": quantities["unresolved"],
        "unresolved_cast_costs": sorted(set(unresolved_costs)),
        "unresolved_activated_abilities": sorted(set(unresolved_abilities)),
        "unresolved_triggered_abilities": sorted(set(unresolved_triggers)),
        "unresolved_replacement_effects": sorted(set(unresolved_replacements)),
        "expected_arbiter_calls": sum(
            int(row["quantity"]) for row in unresolved_cards + partial_cards
        ),
        "deck_review_eligible_possible": not unresolved_cards
        and not partial_cards,
        "cards": cards,
        "semantic_packs": list(registry.loaded_packs),
    }
