from __future__ import annotations

import copy
import gzip
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .carddb import CardDatabase
from .engine import CommanderEngine
from .model import Event, GameState
from .semantics import SemanticRegistry
from .util import stable_json

RECORD_SCHEMA_VERSION = 3
ENGINE_VERSION = "0.5.0"
TRACE_LEVELS = {"minimal", "standard", "debug"}

_STANDARD_OMIT = {
    "decision.response",
    "priority.pass",
    "step.begin",
    "turn.cleanup",
    "mana.empty",
    "permanent.untap",
}
_MINIMAL_OMIT = _STANDARD_OMIT | {
    "card.draw",
    "card.draw.private",
    "draw.skip",
    "library.shuffle",
    "mana.produce",
    "mana.ability",
    "zone.move",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def capability_id(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _canonical_hash(value: Any) -> str:
    compact = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def checkpoint_state(state: GameState) -> dict[str, Any]:
    """Return authoritative state without logs or transport credentials."""
    payload = copy.deepcopy(state.to_dict())
    payload["events"] = []
    payload["capabilities"] = {}
    return payload


def authoritative_state_hash(state: GameState | Mapping[str, Any]) -> str:
    payload = checkpoint_state(state) if isinstance(state, GameState) else copy.deepcopy(dict(state))
    payload["events"] = []
    payload["capabilities"] = {}
    return _canonical_hash(payload)


def checkpoint_envelope(state: GameState) -> dict[str, Any]:
    active_caps = []
    decision = state.pending_decision
    if decision:
        for cap in state.capabilities.values():
            if cap.decision_id == decision.decision_id and not cap.consumed:
                active_caps.append(
                    {
                        "id": capability_id(cap.token),
                        "decision_id": cap.decision_id,
                        "principal": cap.principal,
                        "actor": cap.actor,
                    }
                )
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "kind": "authoritative-checkpoint",
        "state_hash": authoritative_state_hash(state),
        "active_capabilities": sorted(active_caps, key=lambda item: (item["principal"], item["id"])),
        "state": checkpoint_state(state),
    }


def semantics_fingerprint(registry: SemanticRegistry) -> str:
    programs = {
        key: registry.get(key).to_dict()
        for key in registry.keys()
        if registry.get(key) is not None
    }
    return _canonical_hash({"schema_version": 1, "programs": programs})


def database_fingerprint(card_db: CardDatabase) -> dict[str, Any]:
    metadata = card_db.metadata()
    stable_metadata = {
        key: metadata[key]
        for key in sorted(metadata)
        if key not in {"database_path"}
    }
    return {
        "algorithm": "sha256",
        "metadata_hash": _canonical_hash(stable_metadata),
        "metadata": stable_metadata,
    }


def deck_list_fingerprints(state: GameState) -> dict[str, str]:
    result: dict[str, str] = {}
    for seat in state.turn_order:
        counts = Counter(
            (
                card.printed_name,
                "commander" if card.is_commander else "mainboard",
            )
            for card in state.cards.values()
            if card.owner == seat and not card.is_token
        )
        payload = {
            "commanders": sorted(
                card.printed_name
                for card in state.cards.values()
                if card.owner == seat
                and not card.is_token
                and card.is_commander
            ),
            "cards": sorted(
                (name, quantity, board)
                for (name, board), quantity in counts.items()
            ),
        }
        result[seat] = _canonical_hash(payload)
    return result


def deck_fingerprints(state: GameState) -> dict[str, str]:
    """Compatibility alias; Game Record v3 now names this exact list hash."""

    return deck_list_fingerprints(state)


def event_for_trace(event: Event, trace_level: str) -> dict[str, Any] | None:
    if trace_level not in TRACE_LEVELS:
        raise ValueError(f"Unknown trace level {trace_level!r}")
    if trace_level == "standard" and event.code in _STANDARD_OMIT:
        return None
    if trace_level == "minimal":
        if event.code in _MINIMAL_OMIT or event.importance <= 0:
            return None
        if event.code in {"combat.attack", "combat.damage"} and not event.details:
            return None
    payload = {
        "id": event.event_id,
        "revision": event.revision,
        "turn": event.turn_sequence,
        "active_player": event.active_player,
        "phase": event.phase,
        "step": event.step,
        "actor": event.actor,
        "code": event.code,
        "details": copy.deepcopy(event.details),
        "visibility": list(event.visibility),
        "importance": event.importance,
        "changed_objects": list(event.changed_objects),
        "changed_players": list(event.changed_players),
    }
    if trace_level == "debug" or not event.details:
        payload["summary"] = event.summary
    return payload


def event_from_record(data: Mapping[str, Any]) -> Event:
    return Event(
        event_id=int(data["id"]),
        revision=int(data.get("revision", 0)),
        turn_sequence=int(data.get("turn", 0)),
        active_player=data.get("active_player"),
        phase=str(data.get("phase") or ""),
        step=str(data.get("step") or ""),
        actor=data.get("actor"),
        code=str(data["code"]),
        summary=str(data.get("summary") or data["code"]),
        details=copy.deepcopy(dict(data.get("details") or {})),
        visibility=list(data.get("visibility") or []),
        importance=int(data.get("importance", 1)),
        changed_objects=list(data.get("changed_objects") or []),
        changed_players=list(data.get("changed_players") or []),
    )


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(stable_json(payload), encoding="utf-8")
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    text = "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        for row in rows
    )
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_initial_checkpoint(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wt", encoding="utf-8") as handle:
        handle.write(stable_json(payload))
    temporary.replace(path)


def read_initial_checkpoint(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def build_manifest(
    *,
    state: GameState,
    card_db: CardDatabase,
    semantics: SemanticRegistry,
    created_at: str,
    updated_at: str,
    replay_mode: str,
    deck_provenance: Mapping[str, Mapping[str, Any]] | None = None,
    profile_validation: Mapping[str, Mapping[str, Any]] | None = None,
    codex_arena: Mapping[str, Any] | None = None,
    migrated_from: str | None = None,
) -> dict[str, Any]:
    list_fingerprints = deck_list_fingerprints(state)
    provenance = dict(deck_provenance or {})
    validations = dict(profile_validation or {})
    match_values = [
        validations.get(f"pilot:{seat}", {}).get(
            "profile_fingerprint_match"
        )
        for seat in state.turn_order
    ]
    overall_profile_match: bool | str = (
        all(value is True for value in match_values)
        if any(value is not None for value in match_values)
        else "unavailable"
    )
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "record_schema_version": RECORD_SCHEMA_VERSION,
        "record_type": "mtg-commander-game",
        "game_id": state.game_id,
        "engine_version": ENGINE_VERSION,
        "state_version": state.state_version,
        "protocol_version": 2,
        "format": {
            "name": state.config.format_name,
            "review_profile": state.config.review_profile,
            "profile": state.config.effective_profile(len(state.turn_order)),
            "starting_life": state.config.starting_life,
            "free_mulligans": state.config.effective_free_mulligans(len(state.turn_order)),
            "first_player_draws": state.config.effective_first_player_draws(len(state.turn_order)),
        },
        "player_count": len(state.turn_order),
        "turn_order": list(state.turn_order),
        "players": [
            {
                "seat": seat,
                "name": state.players[seat].name,
                "deck": state.deck_names.get(seat, ""),
                "deck_fingerprint": list_fingerprints[seat],
                "deck_list_fingerprint": list_fingerprints[seat],
                "deck_source_fingerprint": provenance.get(seat, {}).get(
                    "deck_source_fingerprint"
                ),
                "deck_source": provenance.get(seat, {}).get("source"),
                "profile_validation": validations.get(f"pilot:{seat}"),
            }
            for seat in state.turn_order
        ],
        "fingerprint_algorithm_version": 1,
        "profile_fingerprint_match": overall_profile_match,
        "seed": state.config.seed,
        "trace_level": state.config.trace_level,
        "semantics_fingerprint": semantics_fingerprint(semantics),
        "semantics_registry": {
            "schema_version": 1,
            "hash": semantics_fingerprint(semantics),
        },
        "scryfall": database_fingerprint(card_db),
        "created_at": created_at,
        "started_at": created_at,
        "updated_at": updated_at,
        "ended_at": updated_at if state.game_over else None,
        "status": "complete" if state.game_over else "in_progress",
        "winner": state.winner,
        "draw": state.draw,
        "final_state_hash": authoritative_state_hash(state),
        "replay": {
            "mode": replay_mode,
            "verification": "not_run",
            "engine_version": ENGINE_VERSION,
            "semantics_fingerprint": semantics_fingerprint(semantics),
        },
        "review": {
            "classification": "unreviewed",
            "eligible": False,
        },
        **(
            {"codex_arena": copy.deepcopy(dict(codex_arena))}
            if codex_arena
            else {}
        ),
        **({"migrated_from": migrated_from} if migrated_from else {}),
    }


def write_record(
    directory: str | Path,
    *,
    state: GameState,
    card_db: CardDatabase,
    semantics: SemanticRegistry,
    initial_checkpoint: Mapping[str, Any],
    commands: Sequence[Mapping[str, Any]],
    decisions: Sequence[Mapping[str, Any]],
    created_at: str,
    replay_mode: str = "command_replay",
    deck_provenance: Mapping[str, Mapping[str, Any]] | None = None,
    profile_validation: Mapping[str, Mapping[str, Any]] | None = None,
    codex_arena: Mapping[str, Any] | None = None,
    migrated_from: str | None = None,
) -> dict[str, Any]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    prior_manifest: dict[str, Any] | None = None
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        prior_game_id = prior_manifest.get("game_id")
        if prior_game_id and prior_game_id != state.game_id:
            raise ValueError(
                f"Record directory belongs to game {prior_game_id}, not {state.game_id}"
            )
    updated_at = utc_now()
    manifest = build_manifest(
        state=state,
        card_db=card_db,
        semantics=semantics,
        created_at=created_at,
        updated_at=updated_at,
        replay_mode=replay_mode,
        deck_provenance=deck_provenance,
        profile_validation=profile_validation,
        codex_arena=codex_arena,
        migrated_from=migrated_from,
    )
    if prior_manifest:
        if not migrated_from and prior_manifest.get("migrated_from"):
            manifest["migrated_from"] = prior_manifest["migrated_from"]
        if prior_manifest.get("created_at"):
            manifest["created_at"] = prior_manifest["created_at"]
        prior_replay = prior_manifest.get("replay", {})
        if (
            prior_manifest.get("final_state_hash") == manifest["final_state_hash"]
            and prior_replay.get("engine_version") == manifest["engine_version"]
            and prior_replay.get("semantics_fingerprint") == manifest["semantics_fingerprint"]
        ):
            manifest["replay"]["verification"] = prior_replay.get("verification", "not_run")
    _atomic_json(directory / "manifest.json", manifest)
    _atomic_json(directory / "checkpoint.json", checkpoint_envelope(state))
    _atomic_jsonl(directory / "commands.jsonl", commands)
    _atomic_jsonl(
        directory / "events.jsonl",
        (
            row
            for event in state.events
            if (row := event_for_trace(event, state.config.trace_level)) is not None
        ),
    )
    _atomic_jsonl(directory / "decisions.jsonl", decisions)
    _atomic_jsonl(
        directory / "opportunities.jsonl",
        state.action_opportunities,
    )
    initial_path = directory / "initial-checkpoint.json.gz"
    if not initial_path.exists():
        write_initial_checkpoint(initial_path, initial_checkpoint)
    return manifest


def load_record_state(directory: str | Path) -> GameState:
    directory = Path(directory)
    checkpoint = json.loads((directory / "checkpoint.json").read_text(encoding="utf-8"))
    state = GameState.from_dict(checkpoint["state"])
    state.events = [
        event_from_record(row)
        for row in _read_jsonl(directory / "events.jsonl")
    ]
    return state


def replay_record(
    directory: str | Path,
    card_db: CardDatabase,
    *,
    semantics_path: str | Path | None = None,
    verify: bool = True,
) -> dict[str, Any]:
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if int(manifest.get("schema_version", 0)) != RECORD_SCHEMA_VERSION:
        raise ValueError("Replay requires a Game Record v3 directory")
    semantics = SemanticRegistry(semantics_path or directory / "semantics.json")
    if manifest.get("engine_version") != ENGINE_VERSION:
        raise ValueError(
            f"Engine version mismatch: record={manifest.get('engine_version')} runtime={ENGINE_VERSION}"
        )
    if manifest.get("semantics_fingerprint") != semantics_fingerprint(semantics):
        raise ValueError("Semantic registry fingerprint does not match the record")
    initial = read_initial_checkpoint(directory / "initial-checkpoint.json.gz")
    mode = str(manifest.get("replay", {}).get("mode") or "command_replay")
    if mode == "legacy_snapshot":
        actual = authoritative_state_hash(initial["state"])
        expected = str(manifest["final_state_hash"])
        ok = actual == expected
        if verify and not ok:
            raise ValueError(f"Legacy snapshot hash mismatch: expected {expected}, got {actual}")
        return {
            "ok": ok,
            "mode": mode,
            "commands": 0,
            "final_state_hash": actual,
            "expected_state_hash": expected,
        }

    state = GameState.from_dict(initial["state"])
    engine = CommanderEngine(card_db, state, semantics)
    engine.permissions.reissue_pending()
    applied = 0
    for command in _read_jsonl(directory / "commands.jsonl"):
        command_semantics = command.get("semantics", {})
        recorded_registry = (
            command_semantics.get("registry_hash")
            or command.get("semantics_fingerprint")
        )
        current_registry = semantics_fingerprint(semantics)
        if verify and recorded_registry and recorded_registry != current_registry:
            raise ValueError(
                f"Semantic registry mismatch at command {command.get('sequence')}"
            )
        before = authoritative_state_hash(engine.state)
        if verify and before != command.get("before_state_hash"):
            raise ValueError(
                f"Replay diverged before command {command.get('sequence')}: "
                f"expected {command.get('before_state_hash')}, got {before}"
            )
        principal = str(command["principal"])
        capability = engine.permissions.capability_for(principal)
        if capability is None:
            raise ValueError(f"No replay capability for {principal} at command {command.get('sequence')}")
        result = engine.try_submit(
            token=capability.token,
            principal=principal,
            action=str(command["action"]),
            payload=copy.deepcopy(dict(command.get("payload") or {})),
        )
        if not result.ok:
            raise ValueError(f"Replay command {command.get('sequence')} rejected: {result.summary}")
        after = authoritative_state_hash(engine.state)
        if verify and after != command.get("after_state_hash"):
            raise ValueError(
                f"Replay diverged after command {command.get('sequence')}: "
                f"expected {command.get('after_state_hash')}, got {after}"
            )
        applied += 1
    actual = authoritative_state_hash(engine.state)
    expected = str(manifest["final_state_hash"])
    ok = actual == expected
    if verify and not ok:
        raise ValueError(f"Final state hash mismatch: expected {expected}, got {actual}")
    return {
        "ok": ok,
        "mode": mode,
        "commands": applied,
        "final_state_hash": actual,
        "expected_state_hash": expected,
    }


def migrate_v2_game(
    game_json: str | Path,
    output: str | Path,
    card_db: CardDatabase,
    *,
    trace_level: str = "standard",
    semantics_path: str | Path | None = None,
) -> dict[str, Any]:
    game_json = Path(game_json)
    state = GameState.load(game_json)
    state.config.trace_level = trace_level
    state.config.profile = state.config.effective_profile(len(state.turn_order))
    semantics = SemanticRegistry(semantics_path)
    created_at = utc_now()
    # Older elimination code moved every owned card to the public ``outside``
    # zone and marked it known to every seat. That did not prove the hidden
    # hand or library had actually been revealed. Reconstruct only identities
    # supported by public event evidence and otherwise preserve the restrictive
    # knowledge state.
    public_refs: set[str] = set()
    public_codes = {
        "land.play",
        "stack.cast",
        "stack.activate",
        "combat.attack",
        "combat.block",
        "library.search",
        "cleanup.discard",
        "zone.move",
        "permanent.untap",
        "state.creatures_died",
    }
    for event in state.events:
        if event.code not in public_codes:
            continue
        details = event.details
        for key in ("object", "source", "card", "kept"):
            if details.get(key):
                public_refs.add(str(details[key]))
        for key in ("objects", "moved"):
            public_refs.update(str(value) for value in details.get(key) or [])
    restricted = 0
    for card in state.cards.values():
        if (
            card.owner in state.eliminated_players
            and card.zone == "outside"
            and card.ref not in public_refs
        ):
            card.known_to = [card.owner]
            card.revealed_to = []
            card.annotations["migration_hidden_zone_uncertain"] = True
            card.annotations["hidden_after_owner_left"] = True
            restricted += 1
    if restricted:
        state.annotations.append(
            {
                "kind": "migration_uncertainty",
                "scope": "eliminated-player hidden zones",
                "objects_restricted": restricted,
                "note": (
                    "V2 did not retain enough history to reconstruct exact "
                    "knowledge; identities were kept private unless public "
                    "event evidence supported disclosure."
                ),
            }
        )
    initial = checkpoint_envelope(state)
    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)
    existing_manifest = output_path / "manifest.json"
    if existing_manifest.exists():
        existing_game = json.loads(existing_manifest.read_text(encoding="utf-8")).get("game_id")
        if existing_game and existing_game != state.game_id:
            raise ValueError(
                f"Migration output belongs to game {existing_game}, not {state.game_id}"
            )
    write_initial_checkpoint(output_path / "initial-checkpoint.json.gz", initial)
    decisions = []
    for event in state.events:
        if event.code != "decision.response":
            continue
        decisions.append(
            {
                "sequence": len(decisions) + 1,
                "decision_id": event.details.get("decision"),
                "kind": None,
                "role": "pilot" if event.actor in state.players else event.actor,
                "principal": (
                    f"pilot:{event.actor}" if event.actor in state.players else event.actor
                ),
                "actor": event.actor,
                "seat": event.actor if event.actor in state.players else None,
                "action": event.details.get("action"),
                "accepted": True,
                "legacy_incomplete": True,
                "legal_alternatives": "unavailable",
                "reason": "unavailable in v2 record",
                "plan": "unavailable in v2 record",
                "plan_category": None,
                "provider_invoked": None,
                "retry_count": 0,
                "phase": event.phase,
                "step": event.step,
                "projected_state_hash": None,
                "observation_revision": event.revision,
                "observation_base_hash": None,
                "turn": event.turn_sequence,
            }
        )
    manifest = write_record(
        output,
        state=state,
        card_db=card_db,
        semantics=semantics,
        initial_checkpoint=initial,
        commands=[],
        decisions=decisions,
        created_at=created_at,
        replay_mode="legacy_snapshot",
        migrated_from=str(game_json),
    )
    manifest["replay"]["verification"] = "snapshot_only"
    manifest["started_at"] = None
    manifest["ended_at"] = None
    manifest["migrated_at"] = created_at
    _atomic_json(output_path / "manifest.json", manifest)
    return manifest


def inspect_game(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir() and (path / "manifest.json").exists():
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        checkpoint = json.loads((path / "checkpoint.json").read_text(encoding="utf-8"))
        return {
            "record_version": int(manifest.get("schema_version", 0)),
            "kind": "game-record",
            "path": str(path),
            "game_id": manifest.get("game_id"),
            "status": manifest.get("status"),
            "profile": manifest.get("format", {}).get("profile"),
            "trace_level": manifest.get("trace_level"),
            "commands": len(_read_jsonl(path / "commands.jsonl")),
            "events": len(_read_jsonl(path / "events.jsonl")),
            "decisions": len(_read_jsonl(path / "decisions.jsonl")),
            "state_hash": checkpoint.get("state_hash"),
            "replay": manifest.get("replay"),
        }
    game_json = path / "game.json" if path.is_dir() else path
    state = GameState.load(game_json)
    counts = Counter(event.code for event in state.events)
    by_ref = {card.ref: card for card in state.cards.values()}
    spells: dict[str, list[str]] = {seat: [] for seat in state.turn_order}
    cleanup_discards = Counter()
    for event in state.events:
        if event.code == "stack.cast" and event.actor in spells:
            ref = str(event.details.get("object") or "")
            spells[event.actor].append(
                by_ref[ref].printed_name if ref in by_ref else ref
            )
        elif event.code == "cleanup.discard" and event.actor:
            cleanup_discards[event.actor] += len(event.details.get("objects") or [])
    return {
        "record_version": 2,
        "kind": "legacy-monolith",
        "path": str(game_json),
        "game_id": state.game_id,
        "status": "complete" if state.game_over else "in_progress",
        "profile": state.config.effective_profile(len(state.turn_order)),
        "bytes": game_json.stat().st_size,
        "events": len(state.events),
        "capabilities": len(state.capabilities),
        "event_breakdown": {
            "decisions": counts["decision.response"],
            "priority_passes": counts["priority.pass"],
            "step_boundaries": counts["step.begin"],
            "lands_played": counts["land.play"],
            "spells_cast": counts["stack.cast"],
            "abilities_activated": counts["stack.activate"],
        },
        "players": {
            seat: {
                "deck": state.deck_names.get(seat, ""),
                "turns_begun": state.players[seat].turns_begun,
                "spells_cast": spells[seat],
                "cleanup_discards": cleanup_discards[seat],
            }
            for seat in state.turn_order
        },
        "winner": state.winner,
        "eliminated_players": list(state.eliminated_players),
        "warning": "Legacy game.json has no replayable command payloads or complete decision audit.",
    }
