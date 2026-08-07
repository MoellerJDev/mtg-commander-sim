from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session
from quorune.record import authoritative_state_hash


class CastingActivationProposalEquivalenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.db.close()

    def make_session(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.clear()
        engine.state.priority_player = None
        engine.state.priority_passes = []
        return session

    @staticmethod
    def card(session, seat: str, name: str):
        return next(
            card
            for card in session.state.cards.values()
            if card.owner == seat
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def issue_priority(session, seat: str = "A") -> dict:
        session.engine._grant_priority(seat)
        session.engine.pump()
        return session.packet(f"pilot:{seat}", full=True)

    @staticmethod
    def action(packet: dict, action_id: str) -> dict:
        return next(
            action
            for action in packet["decision"]["ctx"]["legal"]["actions"]
            if action["id"] == action_id
        )

    def test_advertised_cast_offer_executes_at_its_exact_revision(self) -> None:
        session = self.make_session(61701)
        engine = session.engine
        ring = self.card(session, "A", "Sol Ring")
        engine.move_card(ring.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["C"] = 1
        packet = self.issue_priority(session)
        offer = self.action(packet, f"cast:{ring.ref}")

        self.assertEqual("cast", offer["kind"])
        self.assertEqual(engine.state.revision, offer["expiry_revision"])
        self.assertRegex(offer["proposal_fingerprint"], r"^[0-9a-f]{64}$")
        result = session.act("pilot:A", {"action_id": offer["id"]})

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("stack", session.state.cards[ring.object_id].zone)
        self.assertEqual(
            ring.object_id,
            session.state.stack[0].card_object_id,
        )

    def test_changed_cast_payability_rejects_stale_offer_without_mutation(self) -> None:
        session = self.make_session(61702)
        engine = session.engine
        ring = self.card(session, "A", "Sol Ring")
        engine.move_card(ring.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["C"] = 1
        packet = self.issue_priority(session)
        offer = self.action(packet, f"cast:{ring.ref}")
        engine.state.players["A"].mana_pool["C"] = 0
        before = authoritative_state_hash(engine.state)

        result = session.act("pilot:A", {"action_id": offer["id"]})

        self.assertFalse(result.ok)
        self.assertIn("stale", result.summary.casefold())
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual("hand", session.state.cards[ring.object_id].zone)

    def test_advertised_activation_uses_the_same_typed_source_query(self) -> None:
        session = self.make_session(61703)
        engine = session.engine
        top = self.card(session, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        packet = self.issue_priority(session)
        offer = self.action(packet, f"activate:{top.ref}:ab2")

        self.assertEqual("activate", offer["kind"])
        result = session.act("pilot:A", {"action_id": offer["id"]})

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(session.state.cards[top.object_id].tapped)
        self.assertEqual(top.object_id, session.state.stack[-1].source_object_id)

    def test_source_leaving_invalidates_activation_offer_without_mutation(self) -> None:
        session = self.make_session(61704)
        engine = session.engine
        top = self.card(session, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        packet = self.issue_priority(session)
        offer = self.action(packet, f"activate:{top.ref}:ab2")
        engine.move_card(top.object_id, "graveyard", log=False)
        before = authoritative_state_hash(engine.state)

        result = session.act("pilot:A", {"action_id": offer["id"]})

        self.assertFalse(result.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual("graveyard", session.state.cards[top.object_id].zone)
        self.assertFalse(session.state.stack)


if __name__ == "__main__":
    unittest.main()
