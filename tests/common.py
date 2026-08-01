from __future__ import annotations

import os
from pathlib import Path

from mtg_commander_sim import CardDatabase, CommanderSession, DeckLoader, GameConfig
from mtg_commander_sim.model import TurnHistory

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("MTG_CARD_DB", ROOT / "data" / "scryfall-20260728-compact.sqlite3"))


def load_assets():
    db = CardDatabase(DB_PATH)
    loader = DeckLoader(db)
    mishra = loader.load(ROOT / "examples" / "mishra-eminent-one.txt", commander="Mishra, Eminent One", deck_name="Mishra")
    zimone = loader.load(ROOT / "examples" / "zimone-and-dina.txt", commander="Zimone and Dina", deck_name="Zimone")
    return db, mishra, zimone


def make_session(db, mishra, zimone, *, players=4, seed=1, auto_pass_empty=False):
    seats = [chr(ord("A") + i) for i in range(players)]
    decks = {seat: (mishra if i % 2 == 0 else zimone) for i, seat in enumerate(seats)}
    return CommanderSession.create(
        db,
        decks,
        first_player="A",
        seed=seed,
        config=GameConfig(seed=seed, auto_pass_empty_priority=auto_pass_empty),
    )


def keep_all(session):
    while session.state.pending_decision and session.state.pending_decision.kind == "mulligan.declare":
        for principal in list(session.pending_principals()):
            result = session.act(principal, {"a": "keep"})
            assert result.ok, result.summary


def pass_current(session, *, yield_mode=None):
    principals = session.pending_principals()
    assert principals
    principal = principals[0]
    response = {"a": "pass"}
    if yield_mode:
        response["y"] = yield_mode
    result = session.act(principal, response)
    assert result.ok, result.summary
    return principal


def set_fixture_turn(engine, turn_sequence: int) -> None:
    """Move a directly seeded rules fixture to a clean turn boundary."""

    engine.state.turn_sequence = int(turn_sequence)
    if engine.state.turn_history is not None:
        engine.state.turn_history = TurnHistory(
            turn_sequence=engine.state.turn_sequence
        )


def advance_fixture_turn(engine, count: int = 1) -> None:
    set_fixture_turn(engine, engine.state.turn_sequence + int(count))
