from __future__ import annotations

import asyncio
import unittest

from common import load_assets, make_session
from mtg_commander_sim import (
    CommandEnvelope,
    GameActorClosed,
    GameActorUnavailable,
    GameManager,
    GameService,
    PROTOCOL_VERSION,
)


class GameActorTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_service(self, seed: int):
        session = make_session(
            self.db, self.mishra, self.zimone, seed=seed
        )
        return session, GameService(session)

    @staticmethod
    def envelope(session, command_id: str = "actor-1"):
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

    async def test_actor_serializes_duplicate_concurrent_delivery(self):
        session, service = self.make_service(32001)
        manager = GameManager()
        actor = await manager.add(service)
        envelope = self.envelope(session)
        try:
            first, duplicate = await asyncio.gather(
                actor.command("pilot:A", envelope),
                actor.command("pilot:A", envelope),
            )
            self.assertTrue(first.ok)
            self.assertTrue(duplicate.ok)
            self.assertFalse(first.replayed)
            self.assertTrue(duplicate.replayed)
            self.assertEqual(1, len(session.commands))
            self.assertEqual(2, actor.processed_messages)
            self.assertEqual(0, actor.queue_depth)
        finally:
            await manager.close()

    async def test_only_one_actor_can_own_a_game(self):
        session, service = self.make_service(32002)
        manager = GameManager()
        actor = await manager.add(service)
        self.assertIs(actor, manager.get(session.state.game_id))
        with self.assertRaisesRegex(ValueError, "already has an actor"):
            await manager.add(service)
        await manager.close()

    async def test_observations_use_the_same_mailbox_and_actor_closes(self):
        session, service = self.make_service(32003)
        manager = GameManager()
        actor = await manager.add(service)
        packet = await actor.observe("pilot:A", full=True)
        self.assertEqual(session.state.game_id, packet["state"]["game"]["id"])
        self.assertEqual(1, actor.processed_messages)
        await manager.close()
        with self.assertRaises(GameActorClosed):
            await actor.observe("pilot:A")

    async def test_persistence_failure_sends_no_ack_and_fails_closed(self):
        class BrokenPersistence:
            def save(self, service):
                raise OSError("disk unavailable")

        session, service = self.make_service(32004)
        manager = GameManager()
        actor = await manager.add(service, persistence=BrokenPersistence())
        envelope = self.envelope(session)
        try:
            with self.assertRaisesRegex(
                GameActorUnavailable, "failed durable command commit"
            ):
                await asyncio.wait_for(
                    actor.command("pilot:A", envelope), timeout=5
                )
            self.assertEqual(1, len(session.commands))
            with self.assertRaisesRegex(
                GameActorUnavailable, "requires recovery"
            ):
                await asyncio.wait_for(actor.poll(), timeout=5)
        finally:
            await asyncio.wait_for(manager.close(), timeout=5)

    async def test_network_projection_cursors_are_connection_isolated(self):
        session, service = self.make_service(32005)
        manager = GameManager()
        actor = await manager.add(service)
        first_key = "network:pilot:A:first"
        second_key = "network:pilot:A:second"
        try:
            first = await actor.observe(
                "pilot:A", full=True, cursor_key=first_key
            )
            second = await actor.observe(
                "pilot:A", full=True, cursor_key=second_key
            )
            self.assertEqual(first["view"], second["view"])
            self.assertEqual(1, first["pkt"])
            self.assertEqual(1, second["pkt"])
            receipt = await actor.command("pilot:A", self.envelope(session))
            self.assertTrue(receipt.ok)
            first_delta = await actor.observe(
                "pilot:A", cursor_key=first_key
            )
            second_delta = await actor.observe(
                "pilot:A", cursor_key=second_key
            )
            self.assertEqual("delta", first_delta["mode"])
            self.assertEqual("delta", second_delta["mode"])
            self.assertEqual(first["view"], first_delta["base"])
            self.assertEqual(second["view"], second_delta["base"])
            await actor.drop_projection_cursor(first_key)
            self.assertNotIn(first_key, session.cursors)
            self.assertIn(second_key, session.cursors)
        finally:
            await manager.close()


if __name__ == "__main__":
    unittest.main()
