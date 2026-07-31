from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Any, Iterator
import uuid

from mtg_commander_sim import DeckDefinition
from mtg_commander_sim.persistence import initialize_sqlite


SEATS = ("A", "B", "C", "D")
GAME_STATUSES = {"active", "paused", "complete", "aborted"}


class StoreConflict(ValueError):
    pass


class StoreNotFound(KeyError):
    pass


class StoreForbidden(PermissionError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ServerStore:
    """Small SQLite control-plane store; game state stays in Game Record v3."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()
        initialize_sqlite(self.path)

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    def create_guest(
        self, display_name: str, *, ttl: timedelta = timedelta(days=7)
    ) -> tuple[dict[str, Any], str]:
        guest_id = uuid.uuid4().hex
        token = secrets.token_urlsafe(32)
        created_at = datetime.now(timezone.utc)
        expires_at = created_at + ttl
        with self._connection(write=True) as connection:
            connection.execute(
                """
                INSERT INTO guest_sessions(
                    guest_id, token_hash, display_name, created_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    guest_id,
                    token_hash(token),
                    display_name,
                    created_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
        return {
            "guest_id": guest_id,
            "display_name": display_name,
            "expires_at": expires_at.isoformat(),
        }, token

    def authenticate(self, token: str) -> dict[str, Any]:
        if not token:
            raise StoreForbidden("Missing guest session")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT guest_id, display_name, expires_at, revoked_at
                FROM guest_sessions WHERE token_hash = ?
                """,
                (token_hash(token),),
            ).fetchone()
        if row is None or row["revoked_at"] is not None:
            raise StoreForbidden("Invalid guest session")
        if datetime.fromisoformat(str(row["expires_at"])) <= datetime.now(
            timezone.utc
        ):
            raise StoreForbidden("Guest session expired")
        return {
            "guest_id": str(row["guest_id"]),
            "display_name": str(row["display_name"]),
            "expires_at": str(row["expires_at"]),
        }

    def create_room(
        self, owner_guest_id: str, *, seed: int
    ) -> tuple[dict[str, Any], str]:
        room_id = uuid.uuid4().hex
        invite_code = secrets.token_urlsafe(18)
        now = utc_now()
        with self._connection(write=True) as connection:
            connection.execute(
                """
                INSERT INTO rooms(
                    room_id, owner_guest_id, invite_code_hash, visibility,
                    status, seat_count, format_profile, seed, created_at,
                    updated_at
                ) VALUES (?, ?, ?, 'invite', 'open', 4,
                          'commander_multiplayer', ?, ?, ?)
                """,
                (
                    room_id,
                    owner_guest_id,
                    token_hash(invite_code),
                    seed,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO room_members(room_id, guest_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (room_id, owner_guest_id, now),
            )
            connection.executemany(
                "INSERT INTO room_seats(room_id, seat) VALUES (?, ?)",
                [(room_id, seat) for seat in SEATS],
            )
            connection.execute(
                "UPDATE room_seats SET guest_id = ? WHERE room_id = ? AND seat = 'A'",
                (owner_guest_id, room_id),
            )
        return self.room(room_id, owner_guest_id), invite_code

    def join_room(
        self, guest_id: str, *, invite_code: str, seat: str
    ) -> dict[str, Any]:
        seat = seat.upper()
        if seat not in SEATS:
            raise StoreConflict("Seat must be A, B, C, or D")
        now = utc_now()
        with self._connection(write=True) as connection:
            room = connection.execute(
                "SELECT room_id, status FROM rooms WHERE invite_code_hash = ?",
                (token_hash(invite_code),),
            ).fetchone()
            if room is None:
                raise StoreNotFound("Invite code not found")
            if room["status"] != "open":
                raise StoreConflict("Room is no longer open")
            room_id = str(room["room_id"])
            occupied = connection.execute(
                "SELECT guest_id FROM room_seats WHERE room_id = ? AND seat = ?",
                (room_id, seat),
            ).fetchone()
            if occupied is None:
                raise StoreNotFound("Seat not found")
            if occupied["guest_id"] not in (None, guest_id):
                raise StoreConflict(f"Seat {seat} is occupied")
            existing = connection.execute(
                "SELECT seat FROM room_seats WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            ).fetchone()
            if existing is not None and existing["seat"] != seat:
                raise StoreConflict("Guest already occupies another seat")
            connection.execute(
                """
                INSERT OR IGNORE INTO room_members(room_id, guest_id, joined_at)
                VALUES (?, ?, ?)
                """,
                (room_id, guest_id, now),
            )
            connection.execute(
                "UPDATE room_seats SET guest_id = ? WHERE room_id = ? AND seat = ?",
                (guest_id, room_id, seat),
            )
            connection.execute(
                "UPDATE rooms SET updated_at = ? WHERE room_id = ?",
                (now, room_id),
            )
        return self.room(room_id, guest_id)

    def rotate_invite(self, room_id: str, guest_id: str) -> str:
        invite_code = secrets.token_urlsafe(18)
        with self._connection(write=True) as connection:
            room = connection.execute(
                "SELECT owner_guest_id, status FROM rooms WHERE room_id = ?",
                (room_id,),
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            if room["owner_guest_id"] != guest_id:
                raise StoreForbidden("Only the room owner can replace the invite code")
            if room["status"] != "open":
                raise StoreConflict("Invite codes cannot change after game start")
            connection.execute(
                "UPDATE rooms SET invite_code_hash = ?, updated_at = ? WHERE room_id = ?",
                (token_hash(invite_code), utc_now(), room_id),
            )
        return invite_code

    def room(self, room_id: str, guest_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            member = connection.execute(
                "SELECT 1 FROM room_members WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            ).fetchone()
            if member is None:
                raise StoreForbidden("Guest is not a room member")
            room = connection.execute(
                "SELECT * FROM rooms WHERE room_id = ?", (room_id,)
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            seats = connection.execute(
                """
                SELECT s.seat, s.ready, s.guest_id, g.display_name,
                       d.deck_id, d.name AS deck_name,
                       d.deck_list_fingerprint, d.preflight_json
                FROM room_seats s
                LEFT JOIN guest_sessions g ON g.guest_id = s.guest_id
                LEFT JOIN decks d ON d.deck_id = s.deck_id
                WHERE s.room_id = ? ORDER BY s.seat
                """,
                (room_id,),
            ).fetchall()
        seat_payloads: list[dict[str, Any]] = []
        for row in seats:
            mine = row["guest_id"] == guest_id
            deck_payload = None
            if row["deck_id"] is not None:
                try:
                    preflight = json.loads(str(row["preflight_json"] or "{}"))
                except json.JSONDecodeError:
                    preflight = {}
                format_legality = preflight.get("format_legality") or {}
                legality_issues = format_legality.get("issues") or []
                deck_payload = {
                    "deck_id": row["deck_id"],
                    "name": row["deck_name"],
                    "deck_list_fingerprint": row["deck_list_fingerprint"],
                    "format_legality": {
                        "status": str(format_legality.get("status") or "unknown"),
                        "issue_count": len(legality_issues),
                        # Card names in an unrevealed deck remain visible only
                        # to its owner; other room members receive the public
                        # override state and count.
                        "issues": legality_issues if mine else [],
                    },
                }
            seat_payloads.append(
                {
                    "seat": str(row["seat"]),
                    "guest_id": row["guest_id"],
                    "display_name": row["display_name"],
                    "ready": bool(row["ready"]),
                    "deck": deck_payload,
                    "mine": mine,
                }
            )
        return {
            "room_id": room_id,
            "owner_guest_id": str(room["owner_guest_id"]),
            "status": str(room["status"]),
            "format_profile": str(room["format_profile"]),
            "seat_count": int(room["seat_count"]),
            "game_id": room["game_id"],
            "seats": seat_payloads,
        }

    def guest_seat(self, room_id: str, guest_id: str) -> str:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT seat FROM room_seats WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            ).fetchone()
        if row is None:
            raise StoreForbidden("Guest does not occupy a seat in this room")
        return str(row["seat"])

    def save_deck(
        self,
        guest_id: str,
        room_id: str,
        deck: DeckDefinition,
        *,
        fingerprint: str,
        preflight: dict[str, Any],
    ) -> dict[str, Any]:
        deck_id = uuid.uuid4().hex
        now = utc_now()
        with self._connection(write=True) as connection:
            room = connection.execute(
                "SELECT status FROM rooms WHERE room_id = ?", (room_id,)
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            if room["status"] != "open":
                raise StoreConflict("Decks cannot change after game start")
            seat = connection.execute(
                "SELECT seat FROM room_seats WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            ).fetchone()
            if seat is None:
                raise StoreForbidden("Guest does not occupy a room seat")
            connection.execute(
                """
                INSERT INTO decks(
                    deck_id, owner_guest_id, name, deck_list_fingerprint,
                    definition_json, preflight_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    deck_id,
                    guest_id,
                    deck.name,
                    fingerprint,
                    json.dumps(deck.to_dict(), sort_keys=True),
                    json.dumps(preflight, sort_keys=True),
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE room_seats SET deck_id = ?, ready = 1
                WHERE room_id = ? AND guest_id = ?
                """,
                (deck_id, room_id, guest_id),
            )
            connection.execute(
                "UPDATE rooms SET updated_at = ? WHERE room_id = ?",
                (now, room_id),
            )
        return {
            "deck_id": deck_id,
            "name": deck.name,
            "commanders": list(deck.commanders),
            "deck_list_fingerprint": fingerprint,
            "total_cards": deck.total_cards(),
        }

    def clear_deck(self, guest_id: str, room_id: str) -> dict[str, Any]:
        with self._connection(write=True) as connection:
            room = connection.execute(
                "SELECT status FROM rooms WHERE room_id = ?", (room_id,)
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            if room["status"] != "open":
                raise StoreConflict("Deck readiness cannot change after game start")
            seat = connection.execute(
                "SELECT seat, deck_id FROM room_seats WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            ).fetchone()
            if seat is None:
                raise StoreForbidden("Guest does not occupy a room seat")
            deck_id = seat["deck_id"]
            connection.execute(
                "UPDATE room_seats SET deck_id = NULL, ready = 0 WHERE room_id = ? AND guest_id = ?",
                (room_id, guest_id),
            )
            if deck_id is not None:
                connection.execute("DELETE FROM decks WHERE deck_id = ?", (deck_id,))
            connection.execute(
                "UPDATE rooms SET updated_at = ? WHERE room_id = ?",
                (utc_now(), room_id),
            )
        return self.room(room_id, guest_id)

    def start_spec(
        self, room_id: str, owner_guest_id: str
    ) -> tuple[int, dict[str, DeckDefinition]]:
        with self._connection() as connection:
            room = connection.execute(
                "SELECT * FROM rooms WHERE room_id = ?", (room_id,)
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            if room["owner_guest_id"] != owner_guest_id:
                raise StoreForbidden("Only the room owner can start the game")
            if room["status"] != "open":
                raise StoreConflict("Room has already started")
            rows = connection.execute(
                """
                SELECT s.seat, s.guest_id, s.ready, d.definition_json
                FROM room_seats s
                LEFT JOIN decks d ON d.deck_id = s.deck_id
                WHERE s.room_id = ? ORDER BY s.seat
                """,
                (room_id,),
            ).fetchall()
        if len(rows) != 4 or any(
            row["guest_id"] is None
            or not bool(row["ready"])
            or row["definition_json"] is None
            for row in rows
        ):
            raise StoreConflict("All four seats must be occupied and ready")
        return int(room["seed"]), {
            str(row["seat"]): DeckDefinition.from_dict(
                json.loads(str(row["definition_json"]))
            )
            for row in rows
        }

    def commit_started_game(
        self, room_id: str, game_id: str, record_path: str, revision: int
    ) -> None:
        now = utc_now()
        with self._connection(write=True) as connection:
            room = connection.execute(
                "SELECT status FROM rooms WHERE room_id = ?", (room_id,)
            ).fetchone()
            if room is None:
                raise StoreNotFound("Room not found")
            if room["status"] != "open":
                raise StoreConflict("Room has already started")
            connection.execute(
                """
                INSERT INTO games(
                    game_id, room_id, status, record_path, state_revision,
                    created_at, updated_at
                ) VALUES (?, ?, 'active', ?, ?, ?, ?)
                """,
                (game_id, room_id, record_path, revision, now, now),
            )
            connection.execute(
                """
                UPDATE rooms SET status = 'active', game_id = ?, updated_at = ?
                WHERE room_id = ?
                """,
                (game_id, now, room_id),
            )

    def game_access(self, game_id: str, guest_id: str) -> tuple[str, str]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT g.room_id, s.seat
                FROM games g
                JOIN room_seats s ON s.room_id = g.room_id
                WHERE g.game_id = ? AND s.guest_id = ?
                """,
                (game_id, guest_id),
            ).fetchone()
        if row is None:
            raise StoreForbidden("Guest cannot access this game")
        return str(row["room_id"]), str(row["seat"])

    def game_summary(self, game_id: str, guest_id: str) -> dict[str, Any]:
        """Return control-plane metadata safe for a seated player."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT g.game_id, g.room_id, g.status, g.state_revision,
                       g.created_at, g.updated_at, r.owner_guest_id,
                       r.format_profile, s.seat
                FROM games g
                JOIN rooms r ON r.room_id = g.room_id
                JOIN room_seats s ON s.room_id = g.room_id
                WHERE g.game_id = ? AND s.guest_id = ?
                """,
                (game_id, guest_id),
            ).fetchone()
        if row is None:
            raise StoreForbidden("Guest cannot access this game")
        return {
            "game_id": str(row["game_id"]),
            "room_id": str(row["room_id"]),
            "status": str(row["status"]),
            "state_revision": int(row["state_revision"]),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
            "format_profile": str(row["format_profile"]),
            "seat": str(row["seat"]),
            "owner": row["owner_guest_id"] == guest_id,
        }

    def require_game_owner(self, game_id: str, guest_id: str) -> None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT r.owner_guest_id
                FROM games g JOIN rooms r ON r.room_id = g.room_id
                WHERE g.game_id = ?
                """,
                (game_id,),
            ).fetchone()
        if row is None:
            raise StoreNotFound("Game not found")
        if row["owner_guest_id"] != guest_id:
            raise StoreForbidden(
                "Only the room owner can control the game lifecycle"
            )

    def game_row(self, game_id: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
        if row is None:
            raise StoreNotFound("Game not found")
        return dict(row)

    def update_game_state(
        self, game_id: str, revision: int, status: str
    ) -> None:
        if status not in GAME_STATUSES:
            raise ValueError(f"Unknown server game status {status!r}")
        with self._connection(write=True) as connection:
            updated = connection.execute(
                """
                UPDATE games SET state_revision = ?, status = ?, updated_at = ?
                WHERE game_id = ?
                """,
                (revision, status, utc_now(), game_id),
            )
            if updated.rowcount != 1:
                raise StoreNotFound("Game not found")
            connection.execute(
                """
                UPDATE rooms SET status = ?, updated_at = ?
                WHERE room_id = (
                    SELECT room_id FROM games WHERE game_id = ?
                )
                """,
                (status, utc_now(), game_id),
            )

    def update_game_revision(self, game_id: str, revision: int) -> None:
        """Compatibility wrapper for callers that do not change lifecycle."""

        with self._connection() as connection:
            row = connection.execute(
                "SELECT status FROM games WHERE game_id = ?", (game_id,)
            ).fetchone()
        if row is None:
            raise StoreNotFound("Game not found")
        self.update_game_state(game_id, revision, str(row["status"]))

    def count_rows(self, table: str) -> int:
        if table not in {
            "guest_sessions",
            "rooms",
            "room_members",
            "room_seats",
            "decks",
            "games",
            "idempotency_records",
        }:
            raise ValueError("Unknown table")
        with self._connection() as connection:
            row = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0])
