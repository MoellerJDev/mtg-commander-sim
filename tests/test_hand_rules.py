from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune import CommanderSession, GameConfig
from quorune.engine import TURN_STEPS


class HandRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 2):
        return make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )

    def test_contract_traces_every_cr_402_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "hand.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"402", "402.1", "402.2", "402.3"},
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("402")
            },
        )

    def test_starting_hand_size_and_effect_moves_are_generic(self):
        session = CommanderSession.create(
            self.db,
            {"A": self.mishra, "B": self.zimone},
            first_player="A",
            seed=40201,
            config=GameConfig(
                seed=40201,
                opening_hand_size=5,
                auto_pass_empty_priority=False,
            ),
        )
        engine = session.engine

        for seat in engine.seats:
            self.assertEqual(
                5,
                len(engine.state.players[seat].zones["hand"]),
            )
            self.assertEqual(
                7,
                engine.state.players[seat].max_hand_size,
            )

        player = engine.state.players["B"]
        moved = engine.state.cards[player.zones["library"][-1]]
        before = len(player.zones["hand"])
        engine.move_card(
            moved.object_id,
            "hand",
            reason="CR 402.1 represented effect",
            log=False,
        )

        self.assertEqual("hand", moved.zone)
        self.assertIn(moved.object_id, player.zones["hand"])
        self.assertEqual(before + 1, len(player.zones["hand"]))

    def test_hand_may_exceed_maximum_until_cleanup(self):
        session = self.make_session(40202)
        keep_all(session)
        engine = session.engine
        player = engine.state.players["A"]
        self.assertEqual(7, player.max_hand_size)

        engine.draw(
            "A",
            3,
            reason="CR 402.2 excess-hand witness",
            private=True,
        )
        self.assertEqual(10, len(player.zones["hand"]))
        self.assertNotEqual(
            "cleanup.discard",
            getattr(engine.state.pending_decision, "kind", None),
        )

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase_index = TURN_STEPS.index(
            ("ending", "cleanup")
        )
        engine._enter_step()

        decision = engine.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual("cleanup.discard", decision.kind)
        context = decision.payload_by_actor["A"]
        self.assertEqual(3, context["count"])
        result = session.act(
            "pilot:A",
            {
                "a": "discard",
                "cards": [
                    item["id"] for item in context["hand"][:3]
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(player.max_hand_size, len(player.zones["hand"]))

    def test_library_to_hand_move_is_not_a_draw(self):
        session = self.make_session(402021, players=2)
        engine = session.engine
        player = engine.state.players["B"]
        hidden = engine.state.cards[player.zones["library"][-1]]
        history_before = tuple(player.draw_history)
        event_before = engine.state.event_sequence

        engine.move_card(
            hidden.object_id,
            "hand",
            reason="CR 121.5 non-draw library-to-hand move",
        )

        self.assertEqual(history_before, tuple(player.draw_history))
        self.assertFalse(
            any(
                event.event_id > event_before
                and event.code.startswith("card.draw")
                for event in engine.state.events
            )
        )
        self.assertFalse(player.attempted_empty_draw)

    def test_hidden_card_put_into_hand_keeps_identity_private(self):
        session = self.make_session(40203, players=4)
        engine = session.engine
        session.packet("pilot:A", full=True)
        session.packet("pilot:B", full=True)

        player = engine.state.players["B"]
        hidden = engine.state.cards[player.zones["library"][-1]]
        before = len(player.zones["hand"])
        engine.move_card(
            hidden.object_id,
            "hand",
            reason="CR 402.3 private move",
        )

        opponent_packet = session.packet("pilot:A", full=True)
        opponent_view = opponent_packet["state"]["players"]["B"]
        opponent_events = json.dumps(
            opponent_packet.get("events", []),
            sort_keys=True,
        )
        self.assertEqual(before + 1, opponent_view["hand_n"])
        self.assertNotIn("hand", opponent_view)
        self.assertNotIn("known_hand", opponent_view)
        self.assertNotIn(hidden.ref, opponent_events)
        self.assertNotIn(hidden.printed_name, opponent_events)
        self.assertTrue(
            any(
                event["c"] == "zone.move"
                and "moved a card" in event["s"]
                for event in opponent_packet.get("events", [])
            )
        )

        owner_packet = session.packet("pilot:B", full=True)
        owner_view = owner_packet["state"]["players"]["B"]
        self.assertIn(
            hidden.ref,
            {item["id"] for item in owner_view["hand"]},
        )
        self.assertTrue(
            any(
                event["c"] == "zone.move.private"
                and hidden.ref in event["s"]
                for event in owner_packet.get("events", [])
            )
        )

    def test_public_card_returned_to_hand_remains_known_not_lookable(self):
        session = self.make_session(40204, players=4)
        engine = session.engine
        player = engine.state.players["B"]
        card = engine.state.cards[player.zones["hand"][0]]
        engine.move_card(
            card.object_id,
            "graveyard",
            reason="public hand witness",
            log=False,
        )

        engine.move_card(
            card.object_id,
            "hand",
            reason="CR 402.3 public-to-private witness",
        )
        packet = session.packet("pilot:A", full=True)
        opponent_view = packet["state"]["players"]["B"]

        self.assertNotIn("hand", opponent_view)
        self.assertIn("known_hand", opponent_view)
        self.assertIn(
            card.ref,
            {item["id"] for item in opponent_view["known_hand"]},
        )
        self.assertIn(
            card.printed_name,
            {item["n"] for item in opponent_view["known_hand"]},
        )

    def test_revealed_hand_identity_is_scoped_to_authorized_viewers(self):
        session = self.make_session(40240, players=4)
        engine = session.engine
        player = engine.state.players["B"]
        card = engine.state.cards[player.zones["library"][-1]]

        engine.move_card(
            card.object_id,
            "hand",
            reveal_to=["A"],
            reason="CR 402.3 scoped reveal witness",
        )

        authorized = session.packet("pilot:A", full=True)
        unauthorized = session.packet("pilot:C", full=True)
        self.assertIn(
            card.ref,
            {
                item["id"]
                for item in authorized["state"]["players"]["B"][
                    "known_hand"
                ]
            },
        )
        self.assertNotIn(
            "known_hand",
            unauthorized["state"]["players"]["B"],
        )
        self.assertIn(
            card.ref,
            json.dumps(authorized.get("events", []), sort_keys=True),
        )
        self.assertNotIn(
            card.ref,
            json.dumps(unauthorized.get("events", []), sort_keys=True),
        )

    def test_owner_hand_remains_visible_while_controlling_a_player(self):
        session = self.make_session(40205)
        engine = session.engine
        engine.state.players["B"].stats["turn_controlled_by"] = "A"
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        between_decisions = session.packet("pilot:A", full=True)
        self.assertIn(
            "hand",
            between_decisions["state"]["players"]["A"],
        )
        self.assertIn(
            "hand",
            between_decisions["state"]["players"]["B"],
        )

        engine.permissions.issue(
            kind="priority",
            role="pilot",
            actors=["B"],
            allowed_actions=["pass"],
            payload_by_actor={"B": {"legal_actions": []}},
        )

        packet = session.packet("pilot:A", full=True)
        view = packet["state"]["players"]
        self.assertIn("hand", view["A"])
        self.assertIn("hand", view["B"])
        self.assertEqual(
            len(engine.state.players["A"].zones["hand"]),
            view["A"]["hand_n"],
        )
        self.assertEqual(
            len(engine.state.players["B"].zones["hand"]),
            view["B"]["hand_n"],
        )

    def test_hand_order_is_private_and_owner_projection_is_always_available(
        self,
    ):
        session = self.make_session(40206, players=4)
        engine = session.engine
        owner_before = session.packet("pilot:A", full=True)
        opponent_before = session.packet("pilot:B", full=True)
        original_ids = [
            item["id"]
            for item in owner_before["state"]["players"]["A"]["hand"]
        ]

        engine.state.players["A"].zones["hand"].reverse()
        engine._assert_invariants()
        owner_after = session.packet("pilot:A", full=True)
        opponent_after = session.packet("pilot:B", full=True)
        rearranged_ids = [
            item["id"]
            for item in owner_after["state"]["players"]["A"]["hand"]
        ]

        self.assertEqual(list(reversed(original_ids)), rearranged_ids)
        self.assertEqual(
            opponent_before["state"]["players"]["A"],
            opponent_after["state"]["players"]["A"],
        )
        self.assertNotIn(
            "hand",
            opponent_after["state"]["players"]["A"],
        )


if __name__ == "__main__":
    unittest.main()
