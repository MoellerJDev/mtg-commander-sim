from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import StateInvariantError
from quorune.model import StackItem
from quorune.targets import TargetGroup


class ExileRuleTests(unittest.TestCase):
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
            auto_pass_empty=False,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine.state.priority_player = None
        session.engine.state.priority_passes = []
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

    def stage_spell(
        self,
        engine,
        owner: str,
        name: str,
        *,
        ref: str,
    ) -> StackItem:
        card = self.card(engine, owner, name)
        engine._remove_from_zone(card)
        engine._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = owner
        card.known_to = list(engine.seats)
        card.revealed_to = list(engine.seats)
        item = StackItem(
            stack_id=engine._stable_runtime_id("stack", ref),
            ref=ref,
            kind="spell",
            controller=owner,
            label=name,
            card_object_id=card.object_id,
            default_destination=(
                "battlefield"
                if self.db.lookup(name).is_permanent_spell
                else "graveyard"
            ),
            visibility=list(engine.seats),
            context={"dynamic_effects": []},
        )
        engine.state.stack.append(item)
        return item

    def test_contract_traces_every_cr_406_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "exile.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "406",
                "406.1",
                "406.2",
                "406.3",
                "406.3a",
                "406.3b",
                "406.4",
                "406.5",
                "406.6",
                "406.7",
                "406.8",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("406")
            },
        )

    def test_exile_is_owner_indexed_public_holding_from_ordinary_zones(self):
        session = self.make_session(40601, players=4)
        engine = session.engine
        self.assertTrue(
            all(
                not player.zones["exile"]
                for player in engine.state.players.values()
            )
        )

        library_card = self.card(
            engine,
            "A",
            "The Mightstone and Weakstone",
        )
        hand_card = self.card(engine, "A", "Lightning Greaves")
        battlefield_card = self.card(engine, "A", "Panharmonicon")
        graveyard_card = self.card(
            engine,
            "A",
            "Sensei's Divining Top",
        )
        commander = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.is_commander
        )
        engine.move_card(library_card.object_id, "library", log=False)
        engine.move_card(hand_card.object_id, "hand", log=False)
        engine.move_card(
            battlefield_card.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.move_card(
            graveyard_card.object_id,
            "graveyard",
            log=False,
        )
        self.assertEqual("command", commander.zone)

        cards = [
            library_card,
            hand_card,
            battlefield_card,
            graveyard_card,
            commander,
        ]
        for card in cards:
            engine.move_card(
                card.object_id,
                "exile",
                reason="CR 406.2 ordinary-zone witness",
                log=False,
            )

        self.assertEqual(
            [card.object_id for card in cards],
            engine.state.players["A"].zones["exile"],
        )
        self.assertTrue(
            all(
                card.zone == "exile"
                and card.controller == card.owner == "A"
                and not card.face_down
                and card.known_to == list(engine.seats)
                for card in cards
            )
        )
        self.assertFalse(
            engine.state.players["B"].zones["exile"]
        )

        engine.move_card(
            library_card.object_id,
            "hand",
            reason="temporary exile return witness",
            log=False,
        )
        self.assertEqual("hand", library_card.zone)
        self.assertNotIn(
            library_card.object_id,
            engine.state.players["A"].zones["exile"],
        )

    def test_exiling_card_spell_removes_its_stack_object_and_ghosts_fail_invariant(
        self,
    ):
        session = self.make_session(40602)
        engine = session.engine
        item = self.stage_spell(
            engine,
            "A",
            "Panharmonicon",
            ref="S-406-exile",
        )
        card = engine.state.cards[item.card_object_id]

        engine.apply_effect(
            {
                "op": "exile",
                "card": card.ref,
                "reason": "CR 406.2 stack witness",
            },
            actor="B",
        )

        self.assertEqual("exile", card.zone)
        self.assertNotIn(item, engine.state.stack)
        engine._assert_invariants()

        ghost = self.stage_spell(
            engine,
            "A",
            "Sol Ring",
            ref="S-406-ghost",
        )
        ghost_card = engine.state.cards[ghost.card_object_id]
        ghost_card.zone = "exile"
        ghost_card.controller = ghost_card.owner
        engine.state.players["A"].zones["exile"].append(
            ghost_card.object_id
        )
        with self.assertRaisesRegex(
            StateInvariantError,
            "Stack item references nonstack object",
        ):
            engine._assert_invariants()

    def test_default_exile_is_face_up_and_authorized_face_down_identity_is_scoped(
        self,
    ):
        session = self.make_session(40603, players=4)
        engine = session.engine
        public = self.card(engine, "A", "Sol Ring")
        public.face_down = True
        public.known_to = ["A"]
        public.revealed_to = []
        engine.move_card(public.object_id, "exile", log=False)

        hidden = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(hidden.object_id, "exile", log=False)
        hidden.face_down = True
        hidden.known_to = ["B"]
        hidden.revealed_to = []

        opponent_packet = session.packet("pilot:A", full=True)
        owner_packet = session.packet("pilot:B", full=True)
        public_view = next(
            item
            for item in opponent_packet["state"]["players"]["A"]["ex"]
            if item["id"] == public.ref
        )
        hidden_opponent_view = next(
            item
            for item in opponent_packet["state"]["players"]["B"]["ex"]
            if item["id"] == hidden.ref
        )
        hidden_owner_view = next(
            item
            for item in owner_packet["state"]["players"]["B"]["ex"]
            if item["id"] == hidden.ref
        )
        self.assertEqual(public.printed_name, public_view["n"])
        self.assertEqual("?", hidden_opponent_view["n"])
        self.assertNotIn("cid", hidden_opponent_view)
        self.assertEqual(hidden.printed_name, hidden_owner_view["n"])

        creature_group = TargetGroup.from_mapping(
            {
                "zones": ["exile"],
                "categories": ["card"],
                "creature": True,
                "count": 1,
            }
        )
        self.assertNotIn(
            hidden.ref,
            engine._target_candidates("A", creature_group),
        )
        self.assertIn(
            hidden.ref,
            engine._target_candidates("B", creature_group),
        )

    def test_face_down_exile_piles_and_random_selection_are_not_represented(
        self,
    ):
        session = self.make_session(40604, players=4)
        engine = session.engine
        first = self.card(engine, "B", "Elves of Deep Shadow")
        second = self.card(engine, "B", "Birds of Paradise")
        for card in (first, second):
            engine.move_card(card.object_id, "exile", log=False)
            card.face_down = True
            card.known_to = ["B"]
            card.revealed_to = []

        projected = session.packet("pilot:A", full=True)["state"][
            "players"
        ]["B"]["ex"]
        hidden = [
            item
            for item in projected
            if item["id"] in {first.ref, second.ref}
        ]
        self.assertEqual({first.ref, second.ref}, {item["id"] for item in hidden})
        self.assertTrue(all(item["n"] == "?" for item in hidden))
        self.assertTrue(all("pile" not in item for item in hidden))
        self.assertIsNone(engine.state.pending_decision)

    def test_reexiling_creates_a_new_object_and_moves_it_to_exile_top(self):
        session = self.make_session(40607)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(first.object_id, "exile", log=False)
        engine.move_card(second.object_id, "exile", log=False)
        logical_before = first.logical_object_id
        counter_before = first.zone_change_counter
        timestamp_before = first.zone_timestamp

        engine.move_card(
            first.object_id,
            "exile",
            reason="CR 406.7 re-exile witness",
            log=False,
        )

        self.assertEqual("exile", first.zone)
        self.assertNotEqual(logical_before, first.logical_object_id)
        self.assertEqual(
            counter_before + 1,
            first.zone_change_counter,
        )
        self.assertGreater(first.zone_timestamp, timestamp_before)
        self.assertEqual(
            [second.object_id, first.object_id],
            engine.state.players["A"].zones["exile"],
        )

    def test_pinned_oracle_data_uses_exile_not_legacy_removed_terms(self):
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "scryfall-exact-lists.json"
        )
        cards = json.loads(
            fixture.read_text(encoding="utf-8")
        )["cards"]
        legacy = re.compile(
            r"\b(?:remove(?:d|s)? from the game|set(?:s|ting)? aside)\b",
            re.IGNORECASE,
        )

        self.assertFalse(
            [
                card["name"]
                for card in cards
                if legacy.search(str(card.get("oracle_text") or ""))
            ]
        )


if __name__ == "__main__":
    unittest.main()
