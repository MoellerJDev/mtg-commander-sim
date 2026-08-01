from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim import GameService
from mtg_commander_sim.record import (
    authoritative_state_hash,
    replay_record,
)


class ConcessionRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_duel(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=1043,
        )
        keep_all(session)
        return session

    def test_priority_catalog_projects_confirmed_concession(self):
        session = self.make_duel()
        packet = GameService(session).observe("pilot:A", full=True)
        concession = next(
            action
            for action in packet["decision"]["legal_actions"]
            if action["id"] == "concede"
        )

        self.assertEqual("concede", concession["action"])
        self.assertEqual("Concede game", concession["label"])
        field = concession["form"]["fields"][0]
        self.assertEqual("confirm_concede", field["name"])
        self.assertEqual([True], field["legal_values"])
        self.assertTrue(field["required"])

    def test_concession_requires_explicit_confirmation_and_replays_normally(self):
        session = self.make_duel()
        before = authoritative_state_hash(session.state)
        decision_id = session.state.pending_decision.decision_id

        missing = session.act("pilot:A", {"action_id": "concede"})

        self.assertFalse(missing.ok)
        self.assertIn("explicit confirmation", missing.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual(decision_id, session.state.pending_decision.decision_id)
        self.assertFalse(session.state.game_over)

        declined = session.act(
            "pilot:A",
            {
                "action_id": "concede",
                "choices": {"confirm_concede": False},
            },
        )
        self.assertFalse(declined.ok)
        self.assertEqual(before, authoritative_state_hash(session.state))

        accepted = session.act(
            "pilot:A",
            {
                "action_id": "concede",
                "choices": {"confirm_concede": True},
            },
        )

        self.assertTrue(accepted.ok, accepted.summary)
        self.assertTrue(session.state.game_over)
        self.assertFalse(session.state.players["A"].in_game)
        self.assertEqual("B", session.state.winner)
        event = next(
            event
            for event in reversed(session.state.events)
            if event.code == "player.eliminated"
        )
        self.assertEqual("conceded", event.details["reason"])

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "concession-record"
            session.save(record)
            replay = replay_record(record, self.db, verify=True)
        self.assertTrue(replay["ok"])

    def test_concession_is_not_a_meaningful_window_for_auto_pass(self):
        session = self.make_duel()
        engine = session.engine
        hints = engine._priority_action_hints("A")
        self.assertIn("concede", [action["id"] for action in hints["actions"]])
        self.assertNotIn(
            "concede",
            engine.state.action_opportunities[-1].get(
                "meaningful_action_ids", []
            ),
        )


if __name__ == "__main__":
    unittest.main()
