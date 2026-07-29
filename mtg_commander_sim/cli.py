from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .carddb import CardDatabase
from .arena import (
    CodexThreadRegistry,
    CoordinatorTools,
    PilotInvocationIdentity,
    SeatScopedPilotTools,
    primary_session_prompt,
    run_pilot_mcp_stdio,
)
from .model import GameConfig
from .pilot import (
    ManualJsonPilot,
    PilotMemory,
    ScriptedPilot,
    SequentialPilotRunner,
    SubprocessJsonPilot,
)
from .preflight import semantic_preflight
from .record import inspect_game, migrate_v2_game, replay_record
from .report import review_markdown, write_review_artifacts
from .session import CommanderSession
from .util import stable_json


def _seat_values(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise argparse.ArgumentTypeError("Seat values use SEAT=PATH_OR_MOXFIELD_URL")
        seat, source = value.split("=", 1)
        result[seat.strip()] = source.strip()
    return result


def _load(db_path: str, game_dir: str) -> tuple[CardDatabase, CommanderSession]:
    db = CardDatabase(db_path)
    session = CommanderSession.load(
        db,
        game_dir,
        semantics_path=Path(game_dir) / "semantics.json",
    )
    return db, session


def _scripted_choice(
    observation: dict[str, Any],
    decision: dict[str, Any],
    memory: PilotMemory,
) -> dict[str, Any]:
    """Conservative deterministic pilot for local characterization fixtures."""

    kind = str(decision.get("kind") or "")
    context = dict(decision.get("ctx") or {})
    actions = list(decision.get("legal_actions") or [])
    if kind == "mulligan.declare":
        action_id = "keep"
        plan = "MULLIGAN"
        reason = "Keep a functional hand without chasing an ideal synergy hand."
        return {"action_id": action_id, "plan": plan, "reason": reason}
    if kind == "mulligan.bottom":
        hand = list(context.get("hand") or [])
        count = int(context.get("count", 0))
        return {
            "action_id": "bottom",
            "cards": [item["id"] for item in hand[:count]],
            "plan": "MULLIGAN",
            "reason": "Bottom the least immediately useful cards after the counted redraw.",
        }
    if kind == "search.fetch":
        choices = list(context.get("search_cards") or [])
        selected = choices[0]["id"] if choices else None
        return {
            "action_id": "choose",
            "search_card": selected,
            "entry_pay_life": False,
            "plan": "FIX_COLORS",
            "reason": "Choose a legal typed source and preserve life unless untapped mana is required.",
        }
    if kind in {"semantic.choice", "semantic.target"}:
        options = list(
            context.get("options")
            or context.get("target_schema", {}).get("legal_refs")
            or []
        )
        choices: dict[str, Any] = {}
        if kind == "semantic.target":
            count = int(context.get("target_schema", {}).get("count", 1))
            choices["targets"] = options[:count]
        elif context.get("operation") == "choose_mana":
            choices["choice"] = "G"
        elif options:
            choices["card"] = options[0]
        return {
            "action_id": "choose",
            **choices,
            "plan": "DEVELOP_ENGINE",
            "reason": "Make the advertised semantic choice that advances the current engine line.",
        }
    if kind == "arbiter.resolve":
        return {
            "action_id": "resolve",
            "effects": [],
            "note": "Explicit one-shot provisional resolution; semantic remains unresolved.",
            "plan": "RECOVER",
            "reason": "Resolve once without registering unsupported text or inventing hidden choices.",
        }
    if kind == "combat.attackers":
        return {
            "action_id": "attack",
            "attackers": {},
            "plan": "DEVELOP_ENGINE",
            "reason": "Avoid unsupported combat risk during deterministic characterization.",
        }
    if kind == "combat.blockers":
        return {
            "action_id": "block",
            "blocks": {},
            "plan": "DEVELOP_ENGINE",
            "reason": "No profitable deterministic block is selected.",
        }
    if kind == "cleanup.discard":
        hand = list(context.get("hand") or [])
        count = int(context.get("count", 0))
        return {
            "action_id": "discard",
            "cards": [item["id"] for item in hand[:count]],
            "plan": "RECOVER",
            "reason": "Discard to the authoritative maximum-hand-size requirement.",
        }
    if kind in {"state.legend", "choice.apnap", "trigger.order"}:
        options = (
            context.get("keep_one")
            or context.get("options")
            or [item["id"] for item in context.get("triggers") or []]
        )
        choices = {}
        if kind == "state.legend":
            choices["card"] = options[0]
        elif kind == "trigger.order":
            choices["triggers"] = options
        else:
            choices["cards"] = options[: int(context.get("count", 0))]
        return {
            "action_id": actions[0]["id"] if actions else "choose",
            **choices,
            "plan": "DEVELOP_ENGINE",
            "reason": "Make the deterministic required rules choice.",
        }
    land = next((item for item in actions if item.get("kind") == "play_land"), None)
    if land:
        choices = {}
        if land.get("choice_schema", {}).get("pay_life"):
            choices["pay_life"] = False
        return {
            "action_id": land["id"],
            **choices,
            "plan": "DEVELOP_MANA",
            "reason": "Make the available land drop and preserve life unless tempo requires otherwise.",
        }
    cast = next((item for item in actions if item.get("kind") == "cast"), None)
    if cast:
        target_schema = cast.get("target_schema") or {}
        choices = {}
        if target_schema:
            choices["targets"] = list(target_schema.get("legal_refs") or [])[
                : int(target_schema.get("count", 0))
            ]
        return {
            "action_id": cast["id"],
            **choices,
            "plan": "DEVELOP_ENGINE",
            "reason": "Deploy an affordable engine piece from the complete legal-action catalog.",
        }
    fetch = next(
        (
            item
            for item in actions
            if item.get("kind") == "activate"
            and item.get("choice_schema", {}).get("resolution_time")
        ),
        None,
    )
    if fetch:
        return {
            "action_id": fetch["id"],
            "plan": "FIX_COLORS",
            "reason": "Use the fetchland while its resolution-time typed-land search is available.",
        }
    return {
        "action_id": "pass",
        "yield": "until_public_change",
        "plan": "PASS_WITH_YIELD",
        "reason": "No meaningful development or interaction is currently advertised.",
    }


def _provider_from_spec(spec: str, output: Path, seat: str):
    if spec == "scripted":
        return ScriptedPilot(chooser=_scripted_choice)
    if spec == "manual":
        return ManualJsonPilot(
            task_path=output / "manual" / f"{seat}-task.json",
        )
    if spec.startswith("subprocess:"):
        return SubprocessJsonPilot(spec.split(":", 1)[1])
    raise ValueError(f"Unknown pilot provider {spec!r}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mtg-commander-sim")
    sub = parser.add_subparsers(dest="cmd", required=True)

    new = sub.add_parser("new", help="Create a persistent multiplayer game")
    new.add_argument("--db", required=True)
    new.add_argument("--seat", action="append", required=True, help="SEAT=deck.txt or public Moxfield URL")
    new.add_argument("--commander", action="append", default=[], help="SEAT=Commander Name when a text list lacks a section")
    new.add_argument("--first")
    new.add_argument("--seed", type=int)
    new.add_argument("--out", required=True)
    new.add_argument("--cache-dir")
    new.add_argument("--refresh-decks", action="store_true")
    new.add_argument("--profile", choices=("commander_duel", "commander_multiplayer", "auto"), default="auto")
    new.add_argument("--trace-level", choices=("minimal", "standard", "debug"), default="standard")

    duel = sub.add_parser("duel", help="Create a two-player Commander game from two deck sources")
    duel.add_argument("--db", required=True)
    duel.add_argument("--first", choices=("A", "B"), default="A")
    duel.add_argument("--seed", type=int)
    duel.add_argument("--out", required=True)
    duel.add_argument("--cache-dir")
    duel.add_argument("--refresh-decks", action="store_true")
    duel.add_argument("--profile", choices=("commander_duel", "auto"), default="commander_duel")
    duel.add_argument("--trace-level", choices=("minimal", "standard", "debug"), default="standard")
    duel.add_argument("deck_a", help="Seat A deck file, Moxfield URL, or public deck id")
    duel.add_argument("deck_b", help="Seat B deck file, Moxfield URL, or public deck id")

    task = sub.add_parser("task", help="Emit the next compact permission-scoped packet")
    task.add_argument("--db", required=True)
    task.add_argument("--game", required=True)
    task.add_argument("--principal", help="Observe a specific principal instead of the next pending actor")
    task.add_argument("--full", action="store_true")
    task.add_argument("--pretty", action="store_true")

    act = sub.add_parser("act", help="Submit one compact JSON action")
    act.add_argument("--db", required=True)
    act.add_argument("--game", required=True)
    act.add_argument("--principal", required=True)
    action_group = act.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--json")
    action_group.add_argument("--file")

    rules = sub.add_parser("rules", help="Read local Oracle text and rulings by name or object ref")
    rules.add_argument("--db", required=True)
    rules.add_argument("--game", required=True)
    rules.add_argument("cards", nargs="+")

    report = sub.add_parser("report", help="Produce the derived Game Record review")
    report.add_argument("--db", required=True)
    report.add_argument("--game")
    report.add_argument("record", nargs="?")

    inspect = sub.add_parser("inspect-game", help="Inspect a v2 game.json or v3 record directory")
    inspect.add_argument("path")
    inspect.add_argument("--pretty", action="store_true")

    migrate = sub.add_parser("migrate-record", help="Migrate a legacy game.json to Game Record v3")
    migrate.add_argument("game_json")
    migrate.add_argument("--output", "--out", required=True)
    migrate.add_argument("--db", required=True)
    migrate.add_argument("--trace-level", choices=("minimal", "standard", "debug"), default="standard")

    replay = sub.add_parser("replay", help="Replay and verify a Game Record v3 directory")
    replay.add_argument("record")
    replay.add_argument("--db", required=True)
    replay.add_argument("--verify", action="store_true")

    semantics = sub.add_parser("semantics", help="Inspect semantic coverage")
    semantics_sub = semantics.add_subparsers(dest="semantics_cmd", required=True)
    preflight = semantics_sub.add_parser(
        "preflight", help="Preflight a deck or public Moxfield URL"
    )
    preflight.add_argument("deck")
    preflight.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    preflight.add_argument("--cache-dir")
    preflight.add_argument("--refresh-decks", action="store_true")
    preflight.add_argument("--output")

    pilot_run = sub.add_parser(
        "pilot-run", help="Create or resume a provider-piloted native v3 run"
    )
    pilot_run.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    pilot_run.add_argument("--profile", choices=("commander_duel", "commander_multiplayer", "commander_review", "auto"), default="auto")
    pilot_run.add_argument("--deck", action="append", required=True)
    pilot_run.add_argument("--pilot", action="append", required=True)
    pilot_run.add_argument("--output", required=True)
    pilot_run.add_argument("--cache-dir")
    pilot_run.add_argument("--refresh-decks", action="store_true")
    pilot_run.add_argument("--first")
    pilot_run.add_argument("--seed", type=int)
    pilot_run.add_argument("--through-turn", type=int, default=8)
    pilot_run.add_argument("--max-invocations", type=int, default=200)

    inspect_decisions = sub.add_parser(
        "inspect-decisions", help="Inspect a record's durable decision audit"
    )
    inspect_decisions.add_argument("record")

    inspect_semantics = sub.add_parser(
        "inspect-semantics", help="Inspect semantic programs and review coverage"
    )
    inspect_semantics.add_argument("record")

    pilot_mcp = sub.add_parser(
        "pilot-mcp",
        help="Run a fixed-seat MCP server without exposing authoritative state",
    )
    pilot_mcp.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    pilot_mcp.add_argument(
        "--game-dir", default=os.environ.get("MTG_GAME_DIR")
    )
    pilot_mcp.add_argument("--seat", required=True)
    pilot_mcp.add_argument("--provider", default="codex_subagent")
    pilot_mcp.add_argument("--model")
    pilot_mcp.add_argument("--reasoning-effort")
    pilot_mcp.add_argument("--thread-id")
    pilot_mcp.add_argument("--thread-label")
    pilot_mcp.add_argument("--parent-session-id")
    pilot_mcp.add_argument("--provider-invoked", action="store_true")

    pilot_tool = sub.add_parser(
        "pilot-tool",
        help="Invoke one fixed-seat pilot tool for local Codex orchestration",
    )
    pilot_tool.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    pilot_tool.add_argument("--game-dir", required=True)
    pilot_tool.add_argument("--seat", required=True)
    pilot_tool.add_argument("--provider", default="codex_subagent")
    pilot_tool.add_argument("--model")
    pilot_tool.add_argument("--reasoning-effort")
    pilot_tool.add_argument("--thread-id")
    pilot_tool.add_argument("--thread-label")
    pilot_tool.add_argument("--parent-session-id")
    pilot_tool.add_argument("--provider-invoked", action="store_true")
    pilot_tool.add_argument(
        "operation",
        choices=(
            "get-task",
            "submit-action",
            "get-rules",
            "get-profile",
            "get-memory",
            "update-memory",
        ),
    )
    pilot_tool.add_argument("--json")
    pilot_tool.add_argument("--file")
    pilot_tool.add_argument("--ref", action="append", default=[])
    pilot_tool.add_argument("--text")

    arena_create = sub.add_parser(
        "arena-create",
        help="Create a four-seat commander_review record and primary prompt",
    )
    arena_create.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    arena_create.add_argument("--deck", action="append", required=True)
    arena_create.add_argument("--output", required=True)
    arena_create.add_argument("--cache-dir")
    arena_create.add_argument("--refresh-decks", action="store_true")
    arena_create.add_argument("--first", default="A")
    arena_create.add_argument("--seed", type=int)

    arena_status = sub.add_parser(
        "arena-status",
        help="Inspect public coordinator progress without pilot packets",
    )
    arena_status.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    arena_status.add_argument("--game", required=True)

    coordinator_tool = sub.add_parser(
        "coordinator-tool",
        help="Invoke the public coordinator/arbiter surface (never a seat action)",
    )
    coordinator_tool.add_argument(
        "--db", default="data/scryfall-20260728-compact.sqlite3"
    )
    coordinator_tool.add_argument("--game", required=True)
    coordinator_tool.add_argument(
        "operation",
        choices=("status", "get-arbiter-task", "submit-arbiter"),
    )
    coordinator_tool.add_argument("--json")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "pilot-mcp":
        if not args.game_dir:
            raise SystemExit(
                "pilot-mcp requires --game-dir or MTG_GAME_DIR"
            )
        identity = PilotInvocationIdentity(
            provider=args.provider,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            thread_id=args.thread_id,
            thread_label=args.thread_label,
            parent_session_id=args.parent_session_id,
            provider_invoked=bool(args.provider_invoked),
        )
        tools = SeatScopedPilotTools.open(
            game_dir=args.game_dir,
            db_path=args.db,
            seat=args.seat,
            identity=identity,
        )
        run_pilot_mcp_stdio(tools)
        return 0
    if args.cmd == "pilot-tool":
        identity = PilotInvocationIdentity(
            provider=args.provider,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            thread_id=args.thread_id,
            thread_label=args.thread_label,
            parent_session_id=args.parent_session_id,
            provider_invoked=bool(args.provider_invoked),
        )
        tools = SeatScopedPilotTools.open(
            game_dir=args.game_dir,
            db_path=args.db,
            seat=args.seat,
            identity=identity,
        )
        if args.operation == "get-task":
            value = tools.get_task()
        elif args.operation == "submit-action":
            if bool(args.json) == bool(args.file):
                raise SystemExit(
                    "submit-action requires exactly one of --json or --file"
                )
            response = json.loads(
                args.json
                if args.json
                else Path(args.file).read_text(encoding="utf-8")
            )
            value = tools.submit_action(response)
        elif args.operation == "get-rules":
            value = tools.get_rules(args.ref)
        elif args.operation == "get-profile":
            value = tools.get_profile()
        elif args.operation == "get-memory":
            value = tools.get_memory()
        else:
            if args.text is None:
                raise SystemExit("update-memory requires --text")
            value = tools.update_memory(args.text)
        print(stable_json(value))
        return 0
    if args.cmd == "arena-create":
        sources = _seat_values(args.deck)
        if set(sources) != {"A", "B", "C", "D"}:
            raise SystemExit(
                "arena-create requires exactly A, B, C, and D deck sources"
            )
        output = Path(args.output)
        db = CardDatabase(args.db)
        try:
            session = CommanderSession.from_sources(
                db,
                sources,
                first_player=args.first,
                seed=args.seed,
                cache_dir=args.cache_dir,
                force_refresh=args.refresh_decks,
                semantics_path=output / "semantics.json",
                config=GameConfig(
                    seed=args.seed,
                    profile="commander_multiplayer",
                    auto_pass_empty_priority=True,
                ),
            )
            registry = CodexThreadRegistry()
            for seat in "ABCD":
                registry.register(
                    seat=seat,
                    thread_label=f"mtg-pilot-{seat.lower()}",
                    provider="unavailable",
                    model=None,
                    reasoning_effort=None,
                    thread_id=None,
                )
            session.arena_metadata = registry.metadata()
            session.save(output)
            prompt = primary_session_prompt(output)
            (output / "PRIMARY_CODEX_PROMPT.md").write_text(
                prompt + "\n", encoding="utf-8"
            )
            print(
                stable_json(
                    {
                        "game_id": session.state.game_id,
                        "record": str(output.resolve()),
                        "profile": "commander_review",
                        "pilot_thread_count": 4,
                        "codex_subagent_run": False,
                        "primary_prompt": prompt,
                    }
                )
            )
        finally:
            db.close()
        return 0
    if args.cmd == "arena-status":
        db, session = _load(args.db, args.game)
        try:
            print(stable_json(CoordinatorTools(session).status()))
        finally:
            db.close()
        return 0
    if args.cmd == "coordinator-tool":
        db, session = _load(args.db, args.game)
        try:
            coordinator = CoordinatorTools(session)
            if args.operation == "status":
                if args.json:
                    raise SystemExit("status does not accept --json")
                value = coordinator.status()
            elif args.operation == "get-arbiter-task":
                if args.json:
                    raise SystemExit("get-arbiter-task does not accept --json")
                value = coordinator.get_arbiter_task()
            else:
                if not args.json:
                    raise SystemExit("submit-arbiter requires --json")
                value = coordinator.submit_arbiter(json.loads(args.json))
                if value.get("accepted"):
                    session.save(args.game)
            print(stable_json(value))
        finally:
            db.close()
        return 0
    if args.cmd == "semantics" and args.semantics_cmd == "preflight":
        db = CardDatabase(args.db)
        try:
            result = semantic_preflight(
                db,
                args.deck,
                cache_dir=args.cache_dir,
                force_refresh=args.refresh_decks,
            )
            if args.output:
                Path(args.output).write_text(
                    stable_json(result), encoding="utf-8"
                )
            print(stable_json(result))
        finally:
            db.close()
        return 0

    if args.cmd == "inspect-decisions":
        path = Path(args.record) / "decisions.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        print(stable_json({"record": args.record, "decisions": rows}))
        return 0

    if args.cmd == "inspect-semantics":
        record = Path(args.record)
        registry_path = record / "semantics.json"
        from .semantics import SemanticRegistry

        registry = SemanticRegistry(registry_path)
        review_path = record / "review.json"
        review = (
            json.loads(review_path.read_text(encoding="utf-8"))
            if review_path.exists()
            else {}
        )
        print(
            stable_json(
                {
                    "record": args.record,
                    "programs": [
                        program.to_dict() for program in registry.programs()
                    ],
                    "coverage": review.get("semantic_coverage"),
                }
            )
        )
        return 0

    if args.cmd == "pilot-run":
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        db = CardDatabase(args.db)
        try:
            if (output / "manifest.json").exists():
                session = CommanderSession.load(
                    db, output, semantics_path=output / "semantics.json"
                )
            else:
                sources = _seat_values(args.deck)
                effective_profile = (
                    "commander_multiplayer"
                    if args.profile == "commander_review"
                    else args.profile
                )
                config = GameConfig(
                    seed=args.seed,
                    profile=effective_profile,
                    trace_level="standard",
                )
                session = CommanderSession.from_sources(
                    db,
                    sources,
                    first_player=args.first or next(iter(sources)),
                    seed=args.seed,
                    cache_dir=args.cache_dir,
                    force_refresh=args.refresh_decks,
                    semantics_path=output / "semantics.json",
                    config=config,
                )
            specs = _seat_values(args.pilot)
            providers = {
                f"pilot:{seat}": _provider_from_spec(spec, output, seat)
                for seat, spec in specs.items()
            }
            arbiter = ScriptedPilot(chooser=_scripted_choice, implementation_id="provisional-arbiter-v1")
            memories_path = output / "pilot-memory.json"
            memories = {}
            if memories_path.exists():
                memories = {
                    principal: PilotMemory.from_dict(value)
                    for principal, value in json.loads(
                        memories_path.read_text(encoding="utf-8")
                    ).items()
                }
            runner = SequentialPilotRunner(
                session,
                providers,
                arbiter=arbiter,
                memories=memories,
            )
            invocations = 0
            while (
                not session.state.game_over
                and session.state.turn_sequence < args.through_turn
                and invocations < args.max_invocations
            ):
                if not runner.step():
                    break
                invocations += 1
                memories_path.write_text(
                    stable_json(
                        {
                            principal: memory.to_dict()
                            for principal, memory in runner.memories.items()
                        }
                    ),
                    encoding="utf-8",
                )
                session.save(output)
            memories_path.write_text(
                stable_json(
                    {
                        principal: memory.to_dict()
                        for principal, memory in runner.memories.items()
                    }
                ),
                encoding="utf-8",
            )
            session.save(output)
            benchmark = {
                "schema_version": 1,
                "game_id": session.state.game_id,
                "through_turn_sequence": session.state.turn_sequence,
                "provider_segment": runner.metrics.to_dict(),
                "notes": {
                    "observed_tokens": (
                        "Provider-reported only; null when the adapter supplied no usage."
                    ),
                    "estimated_tokens": (
                        "Compact packet/response character estimates; never labeled observed."
                    ),
                    "resume_scope": (
                        "Provider-segment packet metrics cover this pilot-run invocation; "
                        "review.json derives durable decision/provider totals across the record."
                    ),
                },
            }
            (output / "call-benchmark.json").write_text(
                stable_json(benchmark), encoding="utf-8"
            )
            # Include the benchmark file in the stable record-size review.
            session.save(output)
            print(
                stable_json(
                    {
                        "game_id": session.state.game_id,
                        "record": str(output),
                        "turn_sequence": session.state.turn_sequence,
                        "game_over": session.state.game_over,
                        "pending": session.pending_principals(),
                        "metrics": benchmark["provider_segment"],
                    }
                )
            )
        finally:
            db.close()
        return 0
    if args.cmd == "inspect-game":
        result = inspect_game(args.path)
        print(stable_json(result) if args.pretty else json.dumps(result, separators=(",", ":"), ensure_ascii=False))
        return 0

    if args.cmd == "migrate-record":
        db = CardDatabase(args.db)
        try:
            manifest = migrate_v2_game(
                args.game_json,
                args.output,
                db,
                trace_level=args.trace_level,
                semantics_path=Path(args.output) / "semantics.json",
            )
            session = CommanderSession.load(
                db,
                args.output,
                semantics_path=Path(args.output) / "semantics.json",
            )
            write_review_artifacts(
                args.output,
                session.engine,
                decisions=session.decisions,
                manifest=manifest,
            )
            print(stable_json(inspect_game(args.output)))
        finally:
            db.close()
        return 0

    if args.cmd == "replay":
        db = CardDatabase(args.db)
        try:
            result = replay_record(
                args.record,
                db,
                semantics_path=Path(args.record) / "semantics.json",
                verify=args.verify,
            )
            if args.verify:
                manifest_path = Path(args.record) / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["replay"]["verification"] = "pass" if result["ok"] else "fail"
                manifest_path.write_text(stable_json(manifest), encoding="utf-8")
                session = CommanderSession.load(
                    db,
                    args.record,
                    semantics_path=Path(args.record) / "semantics.json",
                )
                write_review_artifacts(
                    args.record,
                    session.engine,
                    decisions=session.decisions,
                    manifest=manifest,
                )
            print(stable_json(result))
            return 0 if result["ok"] else 2
        finally:
            db.close()

    if args.cmd in {"new", "duel"}:
        if args.cmd == "duel":
            sources = {"A": args.deck_a, "B": args.deck_b}
            commanders: dict[str, str] = {}
        else:
            sources = _seat_values(args.seat)
            commanders = _seat_values(args.commander)
        if not 2 <= len(sources) <= 6:
            raise SystemExit("Supply 2-6 --seat arguments; four is the Commander default")
        db = CardDatabase(args.db)
        try:
            config = GameConfig(
                seed=args.seed,
                profile=args.profile,
                trace_level=args.trace_level,
            )
            session = CommanderSession.from_sources(
                db,
                sources,
                commanders=commanders,
                first_player=args.first or next(iter(sources)),
                seed=args.seed,
                cache_dir=args.cache_dir,
                force_refresh=args.refresh_decks,
                semantics_path=Path(args.out) / "semantics.json",
                config=config,
            )
            session.save(args.out)
            print(
                stable_json(
                    {
                        "game_id": session.state.game_id,
                        "dir": args.out,
                        "decks": session.state.deck_names,
                        "pending": session.pending_principals(),
                    }
                )
            )
        finally:
            db.close()
        return 0

    game_path = (args.game or args.record) if args.cmd == "report" else args.game
    if not game_path:
        raise SystemExit("report requires a record directory (positional or --game)")
    db, session = _load(args.db, game_path)
    try:
        if args.cmd == "task":
            packet = session.packet(args.principal, full=args.full) if args.principal else session.next_task(full=args.full)
            session.save(game_path)
            print(stable_json(packet) if args.pretty else json.dumps(packet, separators=(",", ":"), ensure_ascii=False))
        elif args.cmd == "act":
            raw = Path(args.file).read_text(encoding="utf-8") if args.file else args.json
            response: dict[str, Any] = json.loads(raw)
            result = session.act(args.principal, response)
            session.save(game_path)
            print(stable_json({"ok": result.ok, "summary": result.summary, "events": result.event_ids, "pending": session.pending_principals()}))
            return 0 if result.ok else 2
        elif args.cmd == "rules":
            print(session.rules(args.cards))
        elif args.cmd == "report":
            manifest_path = Path(game_path) / "manifest.json"
            manifest = (
                json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists()
                else None
            )
            review = write_review_artifacts(
                game_path,
                session.engine,
                decisions=session.decisions,
                manifest=manifest,
            )
            print(review_markdown(review), end="")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
