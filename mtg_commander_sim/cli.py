from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .carddb import CardDatabase
from .model import GameConfig
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

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
