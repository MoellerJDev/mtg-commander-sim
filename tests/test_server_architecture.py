from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import tempfile
import unittest

from common import ROOT
from quorune.persistence import initialize_sqlite


class ServerArchitectureTests(unittest.TestCase):
    def test_engine_package_does_not_depend_on_transport_framework(self):
        forbidden = {"fastapi", "starlette", "uvicorn", "server"}
        violations: list[str] = []
        for path in (ROOT / "quorune").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.split(".")[0]]
                for name in names:
                    if name in forbidden:
                        violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{name}")
        self.assertEqual([], violations)

    def test_initial_sqlite_schema_contains_control_plane_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / "server.sqlite3"
            initialize_sqlite(database)
            connection = sqlite3.connect(database)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
                version = connection.execute(
                    "SELECT version FROM server_schema_migrations"
                ).fetchone()
            finally:
                connection.close()
        self.assertTrue(
            {
                "guest_sessions",
                "rooms",
                "room_members",
                "room_seats",
                "decks",
                "games",
                "idempotency_records",
            }.issubset(tables)
        )
        self.assertEqual((1,), version)

    def test_migration_never_persists_raw_session_or_invite_tokens(self):
        text = (ROOT / "migrations" / "0001_server.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("token_hash", text)
        self.assertIn("invite_code_hash", text)
        self.assertNotIn(" access_token ", text)
        self.assertNotIn(" capability ", text)


if __name__ == "__main__":
    unittest.main()
