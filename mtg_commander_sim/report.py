from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .engine import CommanderEngine
from .model import Event
from .util import stable_json

MEANINGFUL_CODES = {
    "mulligan.keep.private",
    "card.draw.private",
    "land.play",
    "stack.cast",
    "stack.activate",
    "stack.trigger",
    "stack.resolve",
    "stack.counter",
    "library.search",
    "cleanup.discard",
    "combat.attack",
    "combat.block",
    "combat.damage",
    "player.eliminated",
    "game.win",
    "game.draw",
    "action.rejected",
}


def _card_by_ref(engine: CommanderEngine) -> dict[str, Any]:
    return {card.ref: card for card in engine.state.cards.values()}


def _name(engine: CommanderEngine, ref: str) -> str:
    card = _card_by_ref(engine).get(ref)
    return card.printed_name if card else ref


def _oracle_name(engine: CommanderEngine, oracle_id: str) -> str:
    try:
        return engine.card_db.by_oracle_id(oracle_id).name
    except KeyError:
        return oracle_id


def _opening_hands(engine: CommanderEngine) -> dict[str, dict[str, Any]]:
    result = {
        seat: {"kept": None, "cards": [], "mulligans": engine.state.players[seat].mulligans_taken}
        for seat in engine.state.turn_order
    }
    for event in engine.state.events:
        if event.code != "mulligan.keep.private" or event.actor not in result:
            continue
        refs = list(event.details.get("objects") or [])
        result[event.actor] = {
            "kept": len(refs),
            "cards": [{"id": ref, "name": _name(engine, ref)} for ref in refs],
            "mulligans": engine.state.players[event.actor].mulligans_taken,
            "visibility": "analyst_only",
        }
    return result


def _land_entry_review(engine: CommanderEngine) -> dict[str, Any]:
    controlled_types: dict[str, list[str]] = defaultdict(list)
    conflicts: list[dict[str, Any]] = []
    plays: list[dict[str, Any]] = []
    by_ref = _card_by_ref(engine)
    opponents = max(0, len(engine.state.turn_order) - 1)
    for event in engine.state.events:
        if event.code != "land.play" or event.actor is None:
            continue
        ref = str(event.details.get("object"))
        card = by_ref.get(ref)
        record = engine.card_record(card) if card else None
        if record is None:
            continue
        oracle = record.oracle_text.casefold()
        if "enters tapped unless you have two or more opponents" in oracle:
            expected: bool | None = opponents < 2
            basis = "bond-land opponent count"
        elif "enters tapped unless you control a forest" in oracle:
            expected = not any("forest" in value for value in controlled_types[event.actor])
            basis = "controlled Forest at entry"
        elif "you may pay 2 life. if you don't, it enters tapped" in oracle:
            expected = None
            basis = "entry choice unavailable in legacy event"
        elif "enters tapped" in oracle and "unless" not in oracle:
            expected = True
            basis = "unconditional Oracle text"
        elif "enters tapped unless" in oracle:
            expected = None
            basis = "uncompiled contextual condition"
        else:
            expected = False
            basis = "no tapped-entry instruction"
        actual = bool(event.details.get("tapped", False))
        row = {
            "turn": event.turn_sequence,
            "seat": event.actor,
            "id": ref,
            "name": record.name,
            "recorded_tapped": actual,
            "expected_tapped": expected,
            "basis": basis,
        }
        plays.append(row)
        if expected is not None and actual != expected:
            conflicts.append(row)
        controlled_types[event.actor].append(record.type_line.casefold())
    return {
        "plays": len(plays),
        "all_recorded_tapped": bool(plays) and all(row["recorded_tapped"] for row in plays),
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


def _semantic_coverage(engine: CommanderEngine) -> dict[str, Any]:
    refs: dict[str, set[str]] = defaultdict(set)
    by_ref = _card_by_ref(engine)
    for event in engine.state.events:
        if event.code in {"land.play", "stack.cast", "stack.activate"}:
            value = event.details.get("object") or event.details.get("source")
            if value:
                refs[str(value)].add(event.code)
    unresolved = []
    partial = []
    cards: list[dict[str, Any]] = []
    for ref in sorted(refs):
        card = by_ref.get(ref)
        record = engine.card_record(card) if card else None
        operations = refs[ref]
        if not record:
            continue
        key_prefix = record.oracle_id
        registered = any(key.startswith(key_prefix) for key in engine.semantics.keys())
        oracle = record.oracle_text.casefold()
        builtin_fetch = bool(engine._fetch_land_types(record.oracle_text))
        if registered or ("stack.activate" in operations and builtin_fetch):
            status = "fully_supported"
            reason = "registered or built-in semantics"
        elif operations == {"land.play"} and not any(
            marker in oracle for marker in ("when ", "whenever ", "as ")
        ):
            status = (
                "intentionally_ignored_as_irrelevant"
                if ":" in oracle
                else "fully_supported"
            )
            reason = (
                "unactivated ability was not relevant to this land play"
                if status.startswith("intentionally")
                else "entry behavior was covered by the land-entry rules"
            )
        elif not oracle.strip():
            status = "fully_supported"
            reason = "no Oracle effect required"
        elif "stack.cast" in operations and ":" in oracle and not any(
            marker in oracle for marker in ("when ", "whenever ", "as ")
        ):
            status = "partially_supported"
            reason = "permanent characteristics resolved; unactivated Oracle abilities were not exercised"
        else:
            status = "unresolved"
            reason = "relevant Oracle semantics were not registered or observed resolving"
        row = {
            "id": ref,
            "name": record.name,
            "operations": sorted(operations),
            "status": status,
            "reason": reason,
        }
        cards.append(row)
        if status == "unresolved":
            unresolved.append(row)
        elif status == "partially_supported":
            partial.append(row)
    return {
        "status": "complete" if not unresolved and not partial else "partial",
        "cards": cards,
        "partially_supported": partial,
        "unresolved_relevant": unresolved,
    }


def _event_description(engine: CommanderEngine, event: Event) -> str:
    details = event.details
    seat = event.actor or event.active_player or "System"
    if event.code == "mulligan.keep":
        return f"{seat} kept their opening hand."
    if event.code == "mulligan.keep.private":
        names = ", ".join(_name(engine, str(ref)) for ref in details.get("objects") or [])
        return f"{seat} kept {len(details.get('objects') or [])}: {names}."
    if event.code == "card.draw.private":
        names = ", ".join(_name(engine, str(ref)) for ref in details.get("objects") or [])
        return f"{seat} drew {names or details.get('count', 1)}."
    if event.code == "land.play":
        ref = str(details.get("object") or "")
        suffix = " tapped" if details.get("tapped") else " untapped"
        return f"{seat} played {_name(engine, ref)}{suffix}."
    if event.code == "stack.cast":
        ref = str(details.get("object") or "")
        return f"{seat} cast {_name(engine, ref)} from {details.get('from', 'an unknown zone')}."
    if event.code == "stack.activate":
        ref = str(details.get("source") or "")
        return f"{seat} activated {_name(engine, ref)} ({details.get('ability')})."
    if event.code == "stack.resolve":
        return f"Resolved {details.get('stack')} ({details.get('note') or 'registered/default semantics'})."
    if event.code == "stack.counter":
        return f"{details.get('stack')} was countered ({details.get('reason')})."
    if event.code == "library.search":
        ref = details.get("object")
        return (
            f"{seat} searched for {_name(engine, str(ref))}."
            if ref
            else f"{seat} searched and did not find a card."
        )
    if event.code == "cleanup.discard":
        refs = list(details.get("objects") or [])
        names = ", ".join(_name(engine, str(ref)) for ref in refs)
        return f"{seat} discarded {names or len(refs)} to maximum hand size."
    if event.code == "combat.attack":
        attackers = details.get("attackers") or {}
        if not attackers:
            return f"{seat} declared no attackers."
        values = ", ".join(
            f"{_name(engine, str(ref))} at {defender}"
            for ref, defender in attackers.items()
        )
        return f"{seat} attacked with {values}."
    if event.code == "combat.block":
        blocks = details.get("blocks") or {}
        return f"{seat} declared {len(blocks)} block(s)."
    if event.code == "combat.damage":
        values = ", ".join(
            f"{_name(engine, str(item.get('source')))} dealt {item.get('amount')} to {item.get('target')}"
            for item in details.get("assignments") or []
        )
        return values + "."
    if event.code == "player.eliminated":
        return f"{seat} was eliminated ({details.get('reason')})."
    if event.code == "game.win":
        return f"{seat} won the game."
    if event.code == "game.draw":
        return "The game ended in a draw."
    if event.code == "action.rejected":
        return f"{seat}'s action was rejected: {details.get('reason') or 'unknown reason'}."
    return event.summary if event.summary != event.code else event.code


def _turn_groups(
    events: Sequence[Event],
    engine: CommanderEngine,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    active: dict[int, str | None] = {}
    for event in events:
        if event.code not in MEANINGFUL_CODES:
            continue
        if (
            event.code == "card.draw.private"
            and event.details.get("reason") == "opening hand"
        ):
            continue
        if event.code == "combat.damage" and not event.details.get("assignments"):
            continue
        if event.code == "combat.attack" and not event.details.get("attackers"):
            continue
        if event.code == "combat.block" and not event.details.get("blocks"):
            continue
        grouped[event.turn_sequence].append(
            {
                "event_id": event.event_id,
                "phase": event.phase,
                "step": event.step,
                "actor": event.actor,
                "code": event.code,
                "summary": _event_description(engine, event),
                "details": event.details,
            }
        )
        active[event.turn_sequence] = event.active_player
    return [
        {"turn": turn, "active_player": active.get(turn), "events": grouped[turn]}
        for turn in sorted(grouped)
    ]


def derive_review(
    engine: CommanderEngine,
    *,
    decisions: Sequence[Mapping[str, Any]] = (),
    manifest: Mapping[str, Any] | None = None,
    record_directory: str | Path | None = None,
) -> dict[str, Any]:
    state = engine.state
    counts = Counter(event.code for event in state.events)
    casts: dict[str, list[dict[str, Any]]] = {seat: [] for seat in state.turn_order}
    land_counts = Counter()
    discards = Counter()
    damage = Counter()
    attacks = Counter()
    draws: dict[str, dict[str, Any]] = {
        seat: {"lands": 0, "spells": 0, "cards": []}
        for seat in state.turn_order
    }
    mana_by_turn: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mana_spent_by_turn: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mana_unused_by_turn: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    commander_casts = Counter()
    tutors: list[dict[str, Any]] = []
    by_ref = _card_by_ref(engine)
    for event in state.events:
        if event.code == "stack.cast" and event.actor in casts:
            ref = str(event.details.get("object"))
            casts[event.actor].append(
                {"turn": event.turn_sequence, "id": ref, "name": _name(engine, ref)}
            )
            for color, amount in (event.details.get("payment") or {}).items():
                mana_spent_by_turn[event.turn_sequence][color] += int(amount)
            if event.details.get("from") == "command":
                commander_casts[event.actor] += 1
        elif event.code == "land.play" and event.actor:
            land_counts[event.actor] += 1
        elif event.code == "cleanup.discard" and event.actor:
            discards[event.actor] += len(event.details.get("objects") or [])
        elif event.code == "combat.attack" and event.actor:
            attacks[event.actor] += len(event.details.get("attackers") or [])
        elif event.code == "combat.damage":
            for assignment in event.details.get("assignments") or []:
                target = assignment.get("target")
                if target in state.players:
                    damage[target] += int(assignment.get("amount", 0))
        elif event.code == "card.draw.private" and event.actor in draws:
            if str(event.details.get("reason") or "") == "opening hand":
                continue
            refs = list(event.details.get("objects") or [])
            for ref in refs:
                card = by_ref.get(str(ref))
                record = engine.card_record(card) if card else None
                kind = "lands" if record and record.is_land else "spells"
                draws[event.actor][kind] += 1
                draws[event.actor]["cards"].append(
                    {
                        "turn": event.turn_sequence,
                        "id": ref,
                        "name": card.printed_name if card else str(ref),
                        "kind": kind[:-1],
                    }
                )
        elif event.code in {"mana.produce", "mana.ability"} and event.actor:
            for color, amount in (event.details.get("bundle") or {}).items():
                mana_by_turn[event.turn_sequence][color] += int(amount)
        elif event.code == "mana.empty" and event.actor:
            for color, amount in (event.details.get("lost") or {}).items():
                mana_unused_by_turn[event.turn_sequence][color] += int(amount)
        elif event.code == "library.search":
            ref = event.details.get("object")
            tutors.append(
                {
                    "turn": event.turn_sequence,
                    "seat": event.actor,
                    "selected": (
                        {"id": ref, "name": _name(engine, str(ref))}
                        if ref
                        else None
                    ),
                    "source": event.details.get("source"),
                }
            )

    land_review = _land_entry_review(engine)
    semantics = _semantic_coverage(engine)
    legacy_decisions = any(bool(row.get("legacy_incomplete")) for row in decisions)
    smoke_marker = any(
        "smoke" in str(event.details.get("note") or "").casefold()
        for event in state.events
        if event.code == "stack.resolve"
    )
    replay_status = (
        str((manifest or {}).get("replay", {}).get("verification") or "not_run")
    )
    fidelity_failures = []
    if land_review["conflict_count"]:
        fidelity_failures.append("land-entry conflicts")
    if semantics["status"] != "complete":
        fidelity_failures.append("incomplete relevant Oracle semantics")
    complete_alternatives = bool(decisions) and not legacy_decisions and all(
        isinstance(row.get("legal_alternatives"), list)
        and bool(row.get("legal_alternatives"))
        for row in decisions
    )
    complete_reasons = bool(decisions) and not legacy_decisions and all(
        row.get("reason") is not None
        for row in decisions
    )
    if not complete_alternatives or not complete_reasons:
        fidelity_failures.append("incomplete pilot decision alternatives/reasons")
    if replay_status not in {"pass", "snapshot_only"}:
        fidelity_failures.append("replay verification not established")
    if smoke_marker:
        fidelity_failures.append("fixture explicitly identifies itself as a smoke baseline")
    if state.config.effective_profile(len(state.turn_order)) not in {
        "commander_duel",
        "commander_multiplayer",
    }:
        fidelity_failures.append("format profile mismatch")
    if not state.game_over:
        classification = "in_progress"
    elif smoke_marker or legacy_decisions or not decisions:
        classification = "smoke_only"
    elif fidelity_failures:
        classification = "pilot_test"
    else:
        classification = "deck_review_eligible"
    eligible = classification == "deck_review_eligible" and not fidelity_failures

    turns_begun = {seat: state.players[seat].turns_begun for seat in state.turn_order}
    accepted = sum(bool(row.get("accepted")) for row in decisions)
    rejected = len(decisions) - accepted
    pass_decisions = sum(row.get("action") == "pass" for row in decisions)
    turn_groups = _turn_groups(state.events, engine)
    first_three: dict[str, list[dict[str, Any]]] = {}
    for seat in state.turn_order:
        seat_turns = [
            group for group in turn_groups
            if group["turn"] and group["active_player"] == seat
        ][:3]
        first_three[seat] = seat_turns
    legal_action_trace_complete = complete_alternatives and complete_reasons
    stranded = {
        seat: [
            {
                "id": state.cards[object_id].ref,
                "name": state.cards[object_id].printed_name,
                "why": "The game ended while the card remained in hand; strategic causality is not inferred.",
            }
            for object_id in state.players[seat].zones["hand"]
        ]
        for seat in state.turn_order
    }
    suspected_pilot: list[dict[str, Any]] = []
    for seat in state.turn_order:
        if not casts[seat] and discards[seat]:
            suspected_pilot.append(
                {
                    "seat": seat,
                    "finding": (
                        f"{seat} cast no spells and discarded {discards[seat]} card(s) "
                        "to maximum hand size."
                    ),
                    "confidence": "suspected",
                    "legal_alternatives_verified": legal_action_trace_complete,
                    "caveat": (
                        None
                        if legal_action_trace_complete
                        else "Historical action catalogs are unavailable, so no specific unchosen play is asserted legal."
                    ),
                }
            )
    replay_pass = replay_status in {"pass", "snapshot_only"}
    dimensions = {
        "format_match": "pass",
        "rules_kernel": "fail" if land_review["conflict_count"] else "partial",
        "card_semantics": "pass" if semantics["status"] == "complete" else "fail",
        "pilot_trace": "pass" if legal_action_trace_complete else "fail",
        "legal_action_exposure": "pass" if legal_action_trace_complete else "fail",
        "hidden_information": "pass",
        "replay_verification": "pass" if replay_pass else "fail",
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "game_id": state.game_id,
        "outcome": {
            "status": "complete" if state.game_over else "in_progress",
            "winner": state.winner,
            "draw": state.draw,
            "eliminations": [
                {
                    "seat": event.actor,
                    "turn": event.turn_sequence,
                    "reason": event.details.get("reason"),
                }
                for event in state.events
                if event.code == "player.eliminated"
            ],
        },
        "format": {
            "name": state.config.format_name,
            "review_profile": state.config.review_profile,
            "profile": state.config.effective_profile(len(state.turn_order)),
            "seed": state.config.seed,
            "warnings": (
                [
                    "This is an explicit Commander duel/1v1 profile and must not be treated as four-player matchup evidence."
                ]
                if state.config.effective_profile(len(state.turn_order)) == "commander_duel"
                else []
            ),
        },
        "opening_hands": _opening_hands(engine),
        "players": {
            seat: {
                "deck": state.deck_names.get(seat, ""),
                "turns_begun": turns_begun[seat],
                "lands_played": land_counts[seat],
                "spells_cast": casts[seat],
                "draws_after_opening": draws[seat],
                "activated_abilities": sum(
                    event.code == "stack.activate" and event.actor == seat
                    for event in state.events
                ),
                "cleanup_discards": discards[seat],
                "attackers_declared": attacks[seat],
                "combat_damage_received": damage[seat],
                "commander_damage_received": dict(state.players[seat].commander_damage_received),
                "commander_damage_sources": [
                    {
                        "oracle_id": oracle_id,
                        "name": _oracle_name(engine, oracle_id),
                        "damage": amount,
                    }
                    for oracle_id, amount in state.players[seat].commander_damage_received.items()
                ],
                "commander_casts": commander_casts[seat],
                "land_drops_made": land_counts[seat],
                "baseline_land_drops_missed": max(0, turns_begun[seat] - land_counts[seat]),
                "stranded_cards": stranded[seat],
                "ending_life": state.players[seat].life,
            }
            for seat in state.turn_order
        },
        "land_entry": land_review,
        "fetchlands": {
            "activations": sum(
                event.code == "stack.activate"
                and (
                    (
                        (source := by_ref.get(str(event.details.get("source") or "")))
                        is not None
                    )
                    and (
                        (record := engine.card_record(source))
                        is not None
                    )
                    and "search your library" in record.oracle_text.casefold()
                )
                for event in state.events
            ),
            "searches_resolved": counts["library.search"],
        },
        "development": {
            "first_three_player_turns": first_three,
            "mana_produced_by_turn": {
                str(turn): dict(values)
                for turn, values in sorted(mana_by_turn.items())
            },
            "mana_spent_by_turn": {
                str(turn): dict(values)
                for turn, values in sorted(mana_spent_by_turn.items())
            },
            "mana_left_unused_by_turn": {
                str(turn): dict(values)
                for turn, values in sorted(mana_unused_by_turn.items())
            },
            "mana_warning": (
                "Unused-mana events are unavailable in this compact or legacy trace."
                if not mana_unused_by_turn
                else None
            ),
        },
        "tutors_and_searches": tutors,
        "interaction_opportunities": {
            "status": "available" if legal_action_trace_complete else "unavailable",
            "note": (
                "Consult decisions.jsonl legal_alternatives for authoritative historical options."
                if legal_action_trace_complete
                else "No specific unchosen interaction is asserted legal from the v2 event log."
            ),
        },
        "pivotal_timeline": [
            {
                "turn": event.turn_sequence,
                "actor": event.actor,
                "code": event.code,
                "summary": event.summary,
            }
            for event in state.events
            if event.code in {
                "stack.cast",
                "stack.activate",
                "stack.counter",
                "library.search",
                "player.eliminated",
                "game.win",
                "game.draw",
            }
        ],
        "suspected_pilot_mistakes": suspected_pilot,
        "suspected_rules_or_semantics_failures": {
            "land_entry_conflicts": land_review["conflicts"],
            "unresolved_relevant_semantics": semantics["unresolved_relevant"],
        },
        "win_route": {
            "winner": state.winner,
            "commander_damage": {
                seat: [
                    {
                        "oracle_id": oracle_id,
                        "name": _oracle_name(engine, oracle_id),
                        "damage": amount,
                    }
                    for oracle_id, amount in state.players[seat].commander_damage_received.items()
                ]
                for seat in state.turn_order
            },
            "description": (
                f"{state.winner} won after commander-damage state-based elimination."
                if state.winner
                and any(
                    sum(player.commander_damage_received.values())
                    >= state.config.commander_damage_to_lose
                    for player in state.players.values()
                )
                else (f"{state.winner} won." if state.winner else "Game incomplete.")
            ),
        },
        "semantic_coverage": semantics,
        "pilot_audit": {
            "attempts": len(decisions),
            "accepted": accepted,
            "rejected": rejected,
            "complete_alternatives": complete_alternatives,
            "complete_reasons": complete_reasons,
            "model_calls_observed": len(decisions),
            "legacy_priority_passes": pass_decisions,
            "potential_calls_avoided_by_empty-priority_auto-pass": pass_decisions,
            "before_after_model_call_estimate": {
                "before_observed": len(decisions),
                "after_if_every_observed_pass_were_proven_safe": max(
                    0, len(decisions) - pass_decisions
                ),
                "caveat": (
                    "This is an upper-bound estimate, not a claim that every historical pass was safely automatable."
                ),
            },
            "warning": (
                "Historical legal alternatives are unavailable; this review does not "
                "assert that a particular unplayed card was legal in a past state."
                if legacy_decisions or not decisions
                else None
            ),
        },
        "trace": {
            "authoritative_events_in_memory": len(state.events),
            "events_by_code": dict(sorted(counts.items())),
        },
        "turns": turn_groups,
        "fidelity": {
            "classification": classification,
            "review_eligible": eligible,
            "matchup_evidence": False,
            "failures": fidelity_failures,
            "dimensions": dimensions,
            "replay_verification": replay_status,
            "statement": (
                "This run is a smoke/protocol artifact, not evidence about deck quality or matchup balance."
                if not eligible
                else "This run passed the single-game deck-review fidelity gate; it is not sufficient matchup evidence."
            ),
        },
    }
    if record_directory:
        directory = Path(record_directory)
        migrated_from = (manifest or {}).get("migrated_from")
        before_bytes = (
            Path(str(migrated_from)).stat().st_size
            if migrated_from and Path(str(migrated_from)).exists()
            else None
        )
        component_bytes = {
            path.name: path.stat().st_size
            for path in directory.glob("*")
            if path.is_file() and path.name not in {"review.json", "review.md"}
        }
        record_total = sum(component_bytes.values())
        report["size_comparison"] = {
            "legacy_game_json_bytes": before_bytes,
            "record_components_bytes": component_bytes,
            "record_total_bytes": record_total,
            "bytes_saved_before_derived_review": (
                before_bytes - record_total
                if before_bytes is not None
                else None
            ),
            "percent_smaller_before_derived_review": (
                round((before_bytes - record_total) * 100 / before_bytes, 1)
                if before_bytes
                else None
            ),
        }
    return report


def review_markdown(review: Mapping[str, Any]) -> str:
    fidelity = review["fidelity"]
    lines = [
        "# Commander game review",
        "",
        f"Game: {review['game_id']}",
        f"Outcome: {review['outcome']['winner'] or review['outcome']['status']}",
        f"Profile: {review['format']['profile']}",
        f"Fidelity: **{fidelity['classification']}** — review eligible: **{str(fidelity['review_eligible']).lower()}**",
        "",
        fidelity["statement"],
        "",
        "## Players",
        "",
    ]
    for seat, player in review["players"].items():
        spells = ", ".join(item["name"] for item in player["spells_cast"]) or "none"
        commander_damage = sum(player["commander_damage_received"].values())
        commander_sources = ", ".join(
            f"{item['damage']} from {item['name']}"
            for item in player["commander_damage_sources"]
        ) or "none"
        lines.append(
            f"- {seat} ({player['deck']}): {player['turns_begun']} turns, "
            f"{player['lands_played']} lands, spells {spells}, "
            f"{player['cleanup_discards']} cleanup discards, "
            f"{commander_damage} commander damage received ({commander_sources})."
        )
    lines.extend(
        [
            "",
            "## Audit findings",
            "",
            f"- Land plays: {review['land_entry']['plays']}; entry-state conflicts: {review['land_entry']['conflict_count']}.",
            f"- Fetchland activations: {review['fetchlands']['activations']}; resolved searches: {review['fetchlands']['searches_resolved']}.",
            f"- Pilot decision attempts: {review['pilot_audit']['attempts']}; accepted: {review['pilot_audit']['accepted']}; rejected: {review['pilot_audit']['rejected']}.",
            f"- Model-call estimate: observed {review['pilot_audit']['before_after_model_call_estimate']['before_observed']}; "
            f"upper-bound after safe pass automation {review['pilot_audit']['before_after_model_call_estimate']['after_if_every_observed_pass_were_proven_safe']}.",
            f"- Semantic coverage: {review['semantic_coverage']['status']}.",
        ]
    )
    lines.extend(["", "### Fidelity dimensions", ""])
    lines.extend(
        f"- {name}: {value}"
        for name, value in fidelity["dimensions"].items()
    )
    if review.get("size_comparison"):
        size = review["size_comparison"]
        lines.extend(
            [
                "",
                "### Record size",
                "",
                f"- Legacy monolith: {size.get('legacy_game_json_bytes')} bytes.",
                f"- V3 record components before derived review: {size.get('record_total_bytes')} bytes.",
                f"- Reduction before derived review: {size.get('percent_smaller_before_derived_review')}%.",
            ]
        )
    if review["land_entry"]["conflicts"]:
        lines.extend(["", "### Land-entry conflicts", ""])
        for conflict in review["land_entry"]["conflicts"]:
            lines.append(
                f"- Turn {conflict['turn']} {conflict['seat']} — {conflict['name']}: "
                f"recorded tapped={conflict['recorded_tapped']}, "
                f"expected={conflict['expected_tapped']} ({conflict['basis']})."
            )
    if fidelity["failures"]:
        lines.extend(["", "### Fidelity gate failures", ""])
        lines.extend(f"- {failure}" for failure in fidelity["failures"])
    lines.extend(["", "## Meaningful turn history", ""])
    for turn in review["turns"]:
        label = "Setup" if turn["turn"] == 0 else f"Turn {turn['turn']} ({turn['active_player']})"
        lines.append(f"### {label}")
        lines.append("")
        for event in turn["events"]:
            lines.append(f"- {event['summary']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_review_artifacts(
    directory: str | Path,
    engine: CommanderEngine,
    *,
    decisions: Sequence[Mapping[str, Any]] = (),
    manifest: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    directory = Path(directory)
    review = derive_review(
        engine,
        decisions=decisions,
        manifest=manifest,
        record_directory=directory,
    )
    (directory / "review.json").write_text(stable_json(review), encoding="utf-8")
    (directory / "review.md").write_text(review_markdown(review), encoding="utf-8")
    if manifest is not None:
        updated = dict(manifest)
        updated["review"] = {
            "classification": review["fidelity"]["classification"],
            "eligible": review["fidelity"]["review_eligible"],
            "matchup_evidence": review["fidelity"]["matchup_evidence"],
        }
        (directory / "manifest.json").write_text(stable_json(updated), encoding="utf-8")
    return review


def concise_report(engine: CommanderEngine) -> str:
    return review_markdown(derive_review(engine))


def load_review(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        path = path / "review.json"
    return json.loads(path.read_text(encoding="utf-8"))
