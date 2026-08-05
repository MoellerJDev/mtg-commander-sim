from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from common import load_assets, make_session
from mtg_commander_sim import (
    CommandEnvelope,
    DirectoryGamePersistence,
    GameManager,
    GameService,
    PROTOCOL_VERSION,
    SqliteIdempotencyRepository,
)


class ServerPersistenceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int):
        return make_session(
            self.db, self.mishra, self.zimone, seed=seed
        )

    @staticmethod
    def envelope(session, *, command_id: str = "persist-1"):
        capability = session.engine.permissions.capability_for("pilot:A")
        decision = session.state.pending_decision
        return CommandEnvelope(
            protocol_version=PROTOCOL_VERSION,
            game_id=session.state.game_id,
            command_id=command_id,
            decision_id=decision.decision_id,
            action_id="keep",
            capability=capability.token,
            expected_view_revision=session.state.revision,
            choices={},
        )

    async def test_actor_persists_before_ack_and_restores_pending_game(self):
        session = self.make_session(33001)
        envelope = self.envelope(session)
        with tempfile.TemporaryDirectory() as tmp:
            persistence = DirectoryGamePersistence(Path(tmp) / "games")
            manager = GameManager()
            actor = await manager.add(
                GameService(session), persistence=persistence
            )
            receipt = await actor.command("pilot:A", envelope)
            self.assertTrue(receipt.ok)
            self.assertTrue(persistence.exists(session.state.game_id))
            record_dir = persistence.game_directory(session.state.game_id)
            self.assertEqual(
                1,
                len(
                    (record_dir / "commands.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ),
            )
            self.assertFalse((record_dir / "review.json").exists())
            self.assertFalse((record_dir / "review.md").exists())
            await manager.close()

            restored = persistence.load(self.db, session.state.game_id)
            self.assertEqual(1, len(restored.session.commands))
            self.assertEqual(
                "persist-1",
                restored.session.commands[0]["client_command_id"],
            )
            self.assertEqual(
                ["pilot:B"], restored.session.pending_principals()
            )
            replayed = restored.command(envelope, principal="pilot:A")
            self.assertTrue(replayed.ok)
            self.assertTrue(replayed.replayed)
            self.assertEqual(1, len(restored.session.commands))

    async def test_live_save_defers_review_until_terminal_state(self):
        session = self.make_session(33004)
        with tempfile.TemporaryDirectory() as tmp:
            persistence = DirectoryGamePersistence(Path(tmp) / "games")
            service = GameService(session)
            persistence.save(service)
            record_dir = persistence.game_directory(session.state.game_id)

            self.assertTrue((record_dir / "manifest.json").exists())
            self.assertFalse((record_dir / "review.json").exists())
            self.assertFalse((record_dir / "review.md").exists())

            session.pause(
                {
                    "kind": "administrative_stop",
                    "label": "Focused persistence test",
                }
            )
            persistence.save(service)
            self.assertTrue((record_dir / "review.json").exists())
            self.assertTrue((record_dir / "review.md").exists())

            session.resume()
            persistence.save(service)
            self.assertFalse((record_dir / "review.json").exists())
            self.assertFalse((record_dir / "review.md").exists())

            session.state.game_over = True
            session.state.winner = "A"
            session.record_status = "complete"
            persistence.save(service)

            self.assertTrue((record_dir / "review.json").exists())
            self.assertTrue((record_dir / "review.md").exists())

    async def test_sqlite_idempotency_survives_service_restart_without_token(self):
        session = self.make_session(33002)
        envelope = self.envelope(session, command_id="durable-1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "server.sqlite3"
            repository = SqliteIdempotencyRepository(database)
            service = GameService(session, idempotency=repository)
            receipt = service.command(envelope, principal="pilot:A")
            self.assertTrue(receipt.ok)
            self.assertNotIn(envelope.capability.encode("utf-8"), database.read_bytes())

            persistence = DirectoryGamePersistence(root / "games")
            persistence.save(service)
            restarted = persistence.load(
                self.db,
                session.state.game_id,
                idempotency=SqliteIdempotencyRepository(database),
            )
            duplicate = restarted.command(envelope, principal="pilot:A")
            self.assertTrue(duplicate.ok)
            self.assertTrue(duplicate.replayed)

    async def test_persisted_checkpoint_contains_no_raw_capability(self):
        session = self.make_session(33003)
        envelope = self.envelope(session)
        token = envelope.capability
        with tempfile.TemporaryDirectory() as tmp:
            persistence = DirectoryGamePersistence(tmp)
            service = GameService(session)
            self.assertTrue(
                service.command(envelope, principal="pilot:A").ok
            )
            persistence.save(service)
            record_dir = persistence.game_directory(session.state.game_id)
            for name in (
                "checkpoint.json",
                "commands.jsonl",
                "manifest.json",
            ):
                self.assertNotIn(
                    token,
                    (record_dir / name).read_text(encoding="utf-8"),
                    name,
                )

    async def test_game_directory_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            persistence = DirectoryGamePersistence(tmp)
            with self.assertRaisesRegex(ValueError, "Invalid game id"):
                persistence.game_directory("../checkpoint")
            with self.assertRaisesRegex(ValueError, "Invalid game id"):
                persistence.game_directory("C:/outside")


if __name__ == "__main__":
    unittest.main()
