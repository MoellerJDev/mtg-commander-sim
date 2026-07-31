from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import (
    HIDDEN_ZONES,
    PUBLIC_ZONES,
    GameRuleError,
)
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import authoritative_state_hash


class ZoneGeneralRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 2):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    def test_contract_traces_every_cr_400_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "object-zone-identity.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "400",
                "400.1",
                "400.2",
                "400.3",
                "400.4",
                "400.4a",
                "400.4b",
                "400.5",
                "400.6",
                "400.7",
                "400.7a",
                "400.7b",
                "400.7c",
                "400.7d",
                "400.7e",
                "400.7f",
                "400.7g",
                "400.7h",
                "400.7i",
                "400.7j",
                "400.7k",
                "400.7m",
                "400.8",
                "400.9",
                "400.10",
                "400.11",
                "400.11a",
                "400.11b",
                "400.11c",
                "400.12",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("400")
            },
        )

    def test_zone_topology_and_visibility_match_the_pinned_rules(self):
        session = self.make_session(40001)
        engine = session.engine
        projector = StateProjector(self.db, engine.state)

        self.assertEqual({"hand", "library"}, HIDDEN_ZONES)
        self.assertEqual(
            {
                "battlefield",
                "graveyard",
                "exile",
                "command",
                "stack",
            },
            PUBLIC_ZONES,
        )
        self.assertNotIn("outside", PUBLIC_ZONES)
        for seat in engine.seats:
            self.assertIsNot(
                engine.state.players[seat].zones["library"],
                engine.state.players[
                    engine._next_active_after(seat)
                ].zones["library"],
            )
            self.assertIsNot(
                engine.state.players[seat].zones["hand"],
                engine.state.players[
                    engine._next_active_after(seat)
                ].zones["hand"],
            )
            self.assertIsNot(
                engine.state.players[seat].zones["graveyard"],
                engine.state.players[
                    engine._next_active_after(seat)
                ].zones["graveyard"],
            )

        card = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            card.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        card.face_down = True
        card.known_to = ["B"]
        card.revealed_to = []

        self.assertEqual("?", projector._obj(card, "pilot:A")["n"])
        self.assertEqual(
            "Elves of Deep Shadow",
            projector._obj(card, "pilot:B")["n"],
        )

    def test_nonbattlefield_destination_uses_the_owners_zone(self):
        session = self.make_session(40003)
        engine = session.engine
        card = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            card.object_id,
            "battlefield",
            controller="B",
            log=False,
        )

        engine.move_card(card.object_id, "graveyard", log=False)

        self.assertEqual("A", card.owner)
        self.assertEqual("A", card.controller)
        self.assertIn(
            card.object_id,
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertNotIn(
            card.object_id,
            engine.state.players["B"].zones["graveyard"],
        )

    def test_instant_or_sorcery_cannot_enter_battlefield(self):
        session = self.make_session(40041)
        engine = session.engine
        card = self.card(engine, "B", "Force of Vigor")
        origin = card.zone
        before_hash = authoritative_state_hash(engine.state)

        moved = engine.move_card(
            card.object_id,
            "battlefield",
            controller="B",
            log=False,
        )

        self.assertIs(card, moved)
        self.assertEqual(origin, card.zone)
        self.assertEqual(before_hash, authoritative_state_hash(engine.state))

    def test_same_graveyard_move_is_a_no_op(self):
        session = self.make_session(40005)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(first.object_id, "graveyard", log=False)
        engine.move_card(second.object_id, "graveyard", log=False)
        before_order = list(
            engine.state.players["A"].zones["graveyard"]
        )
        before_hash = authoritative_state_hash(engine.state)

        engine.move_card(first.object_id, "graveyard", log=False)

        self.assertEqual(
            before_order,
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertEqual(before_hash, authoritative_state_hash(engine.state))

    def test_hidden_card_moved_outside_is_not_revealed_or_targetable(
        self,
    ):
        session = self.make_session(40011)
        engine = session.engine
        projector = StateProjector(self.db, engine.state)
        card = self.card(engine, "B", "Elves of Deep Shadow")
        card.known_to = ["B"]
        card.revealed_to = []

        engine.move_card(card.object_id, "outside", log=False)

        self.assertEqual("outside", card.zone)
        self.assertEqual(["B"], card.known_to)
        self.assertEqual([], card.revealed_to)
        self.assertEqual("?", projector._obj(card, "pilot:A")["n"])
        self.assertEqual(
            "Elves of Deep Shadow",
            projector._obj(card, "pilot:B")["n"],
        )
        self.assertFalse(
            any(
                card.object_id in zone
                for player in engine.state.players.values()
                for zone in player.zones.values()
            )
        )
        with self.assertRaisesRegex(GameRuleError, "Could not find"):
            engine._resolve_object("A", card.ref)


if __name__ == "__main__":
    unittest.main()
