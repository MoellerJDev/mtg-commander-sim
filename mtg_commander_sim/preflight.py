from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Any

from .abilities import parse_activated_abilities
from .carddb import CardDatabase, CardRecord
from .deck import DeckDefinition, DeckLoader
from .mana import ManaPlanError, parsed_cost
from .profiles import (
    deck_list_fingerprint,
    deck_source_fingerprint,
)
from .semantics import SemanticRegistry
from .util import mana_cost_to_vector, stable_json

PREFLIGHT_SCHEMA_VERSION = 2


def _kernel_compiles_cast_cost(record: CardRecord) -> bool:
    _, complex_symbols = mana_cost_to_vector(record.mana_cost)
    for symbol in complex_symbols:
        if symbol == "X":
            continue
        parts = symbol.split("/")
        if len(parts) == 2 and (
            all(part in "WUBRGC" and len(part) == 1 for part in parts)
            or (
                "2" in parts
                and any(
                    part in "WUBRGC" and len(part) == 1
                    for part in parts
                )
            )
        ):
            continue
        return False
    return True


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


def _card_source_hashes(
    db: CardDatabase,
    record: CardRecord,
) -> tuple[str, str]:
    oracle_hash = hashlib.sha256(
        record.oracle_text.encode("utf-8")
    ).hexdigest()
    # Scryfall does not define an ordering among rulings that share a
    # publication date. SQLite's insertion-order tie break therefore differs
    # between a full bulk-data database and the compact CI fixture even when
    # both contain the exact same ruling set. Provenance must describe content,
    # not import order, so canonicalize every field before hashing.
    ruling_rows = sorted(
        (asdict(ruling) for ruling in db.rulings(record)),
        key=lambda row: (
            str(row["published_at"]),
            str(row["source"]),
            str(row["comment"]),
            str(row["oracle_id"]),
        ),
    )
    rulings_hash = hashlib.sha256(
        stable_json(ruling_rows).encode("utf-8")
    ).hexdigest()
    return oracle_hash, rulings_hash


def _material_effect_categories(record: CardRecord) -> list[str]:
    oracle = record.oracle_text.casefold()
    categories: set[str] = set()
    abilities = parse_activated_abilities(
        card_name=record.name,
        oracle_text=record.oracle_text,
        keywords=record.keywords,
    )
    if record.is_instant or record.is_sorcery:
        categories.add("spell_effect")
    if any(ability.mana_ability for ability in abilities):
        categories.add("mana_ability")
    if any(not ability.mana_ability for ability in abilities):
        categories.add("activated_ability")
    if any(
        marker in oracle
        for marker in ("when ", "whenever ", "at the beginning")
    ) or "storm" in {keyword.casefold() for keyword in record.keywords}:
        categories.add("triggered_ability")
    if "instead" in oracle:
        categories.add("replacement_effect")
    if any(
        marker in oracle
        for marker in (
            "additional cost",
            "rather than pay",
            "without paying",
            "kicker",
            "overload",
            "convoke",
            "improvise",
            "affinity",
            "{x}",
        )
    ):
        categories.add("cost_option")
    if (
        record.is_permanent_spell
        and oracle
        and not categories.intersection(
            {
                "activated_ability",
                "mana_ability",
                "triggered_ability",
                "replacement_effect",
            }
        )
    ):
        categories.add("static_ability")
    return sorted(categories)


def card_semantic_status(
    record: CardRecord,
    registry: SemanticRegistry,
    *,
    db: CardDatabase | None = None,
) -> dict[str, Any]:
    programs = registry.programs_for_oracle(record.oracle_id)
    oracle_hash, rulings_hash = (
        _card_source_hashes(db, record)
        if db is not None
        else (None, None)
    )
    program_rows: list[dict[str, Any]] = []
    trusted_programs = []
    drifted_programs = []
    for program in programs:
        source_oracle_hash = program.provenance.get(
            "source_oracle_hash"
        )
        source_rulings_hash = program.provenance.get(
            "source_rulings_hash"
        )
        hash_match = (
            True
            if db is None
            else source_oracle_hash == oracle_hash
            and source_rulings_hash == rulings_hash
        )
        if program.trust_level == "trusted" and hash_match:
            trusted_programs.append(program)
        if program.trust_level == "trusted" and not hash_match:
            drifted_programs.append(program)
        program_rows.append(
            {
                "key": program.key,
                "version": program.version,
                "ability_id": program.ability_id,
                "active_zone": program.active_zone,
                "semantic_family": sorted(set(program.coverage)),
                "trust_level": program.trust_level,
                "source_hash_match": hash_match,
                "scenario_tests": list(program.tests),
            }
        )
    trust = registry.trust_for_oracle(record.oracle_id)
    if drifted_programs:
        trust = "unresolved"
    unresolved: list[str] = []
    try:
        parsed_cost(record.mana_cost)
    except ManaPlanError:
        if _kernel_compiles_cast_cost(record):
            pass
        else:
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
            if program in trusted_programs
        ):
            unresolved.append("triggered_ability")
    if "instead" in oracle and not any(
        "replacement_effect" in program.coverage
        for program in trusted_programs
    ):
        unresolved.append("replacement_effect")
    trusted_coverage = {
        value
        for program in trusted_programs
        for value in program.coverage
    }
    trusted_spell_program = any(
        program.ability_id.startswith("spell:")
        and "spell_resolution" in program.coverage
        for program in trusted_programs
    )
    if (
        "triggered_ability" in trusted_coverage
        or "delayed_trigger" in trusted_coverage
        or "storm" in trusted_coverage
        or (
            trusted_spell_program
            and (record.is_instant or record.is_sorcery)
        )
    ):
        unresolved = [
            value for value in unresolved if value != "triggered_ability"
        ]
    if (
        "replacement_effect" in trusted_coverage
        or "replacement_destination" in trusted_coverage
        or (
            trusted_spell_program
            and (record.is_instant or record.is_sorcery)
        )
    ):
        unresolved = [
            value for value in unresolved if value != "replacement_effect"
        ]
    if any(program.cost_schema for program in trusted_programs):
        unresolved = [
            value for value in unresolved if value != "cast_cost"
        ]
    if drifted_programs:
        unresolved.append("semantic_source_hash_drift")
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
    scenario_tests = sorted(
        {
            test
            for program in programs
            for test in program.tests
        }
    )
    ignored_reasons = sorted(
        {
            str(
                program.provenance.get("intentionally_ignored_reason")
                or program.notes
            )
            for program in programs
            if program.trust_level == "intentionally_ignored"
            and (
                program.provenance.get("intentionally_ignored_reason")
                or program.notes
            )
        }
    )
    if status == "fully_playable":
        support_kind = (
            "trusted_card"
            if trusted_programs
            else "trusted_generic"
        )
    else:
        support_kind = trust
    return {
        "name": record.name,
        "oracle_id": record.oracle_id,
        "active_face": "front",
        "zones": sorted(
            {program.active_zone for program in programs}
            or (
                {"stack"}
                if record.is_instant or record.is_sorcery
                else {"battlefield", "stack"}
            )
        ),
        "semantic_family": sorted(
            {
                coverage
                for program in programs
                for coverage in program.coverage
            }
        ),
        "material_effect_categories": _material_effect_categories(
            record
        ),
        "status": status,
        "trust_level": trust,
        "support_kind": support_kind,
        "oracle_hash": oracle_hash,
        "rulings_hash": rulings_hash,
        "source_hash_match": not drifted_programs,
        "scenario_tests": scenario_tests,
        "intentionally_ignored_reasons": ignored_reasons,
        "unresolved": unresolved,
        "programs": program_rows,
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
        row = card_semantic_status(
            db.lookup(entry.name),
            registry,
            db=db,
        )
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
    drifted_cards = [
        row["name"]
        for row in cards
        if not row["source_hash_match"]
    ]
    ignored_without_reason = [
        row["name"]
        for row in cards
        if row["trust_level"] == "intentionally_ignored"
        and not row["intentionally_ignored_reasons"]
    ]
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "deck": deck.name,
        "source": deck.source,
        "commander": list(deck.commanders),
        "deck_fingerprint": deck_list_fingerprint(deck),
        "deck_list_fingerprint": deck_list_fingerprint(deck),
        "deck_source_fingerprint": deck_source_fingerprint(deck),
        "card_data_metadata": db.metadata(),
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
        and not partial_cards
        and not drifted_cards
        and not ignored_without_reason,
        "trusted_only_ready": not unresolved_cards
        and not partial_cards
        and not drifted_cards
        and not ignored_without_reason,
        "source_hash_drift_cards": sorted(set(drifted_cards)),
        "intentionally_ignored_without_reason": sorted(
            set(ignored_without_reason)
        ),
        "cards": cards,
        "semantic_packs": list(registry.loaded_packs),
    }
