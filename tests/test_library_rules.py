from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import load_assets, make_session
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.record import authoritative_state_hash


def _json_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _json_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _json_strings(item)


class LibraryRuleTests(unittest.TestCase):
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
        )

    def test_contract_traces_every_cr_401_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "library.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "401",
                "401.1",
                "401.2",
                "401.3",
                "401.4",
                "401.5",
                "401.6",
                "401.7",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("401")
            },
        )

    def test_deck_cards_initialize_in_library_before_opening_draws(self):
        session = self.make_session(40101, players=4)
        engine = session.engine

        for seat in engine.seats:
            player = engine.state.players[seat]
            noncommanders = [
                card
                for card in engine.state.cards.values()
                if card.owner == seat and not card.is_commander
            ]
            self.assertEqual(
                len(noncommanders),
                len(player.zones["library"])
                + len(player.zones["hand"]),
            )
            self.assertTrue(
                all(
                    card.zone in {"library", "hand"}
                    for card in noncommanders
                )
            )
            self.assertTrue(
                all(
                    engine.state.cards[object_id].zone_change_counter == 0
                    for object_id in player.zones["library"]
                )
            )
            self.assertTrue(
                all(
                    engine.state.cards[object_id].zone_change_counter == 1
                    for object_id in player.zones["hand"]
                )
            )

    def test_library_order_is_hidden_but_every_count_is_public(self):
        session = self.make_session(40102, players=4)
        engine = session.engine
        packet = session.packet("pilot:A", full=True)

        for seat in engine.seats:
            self.assertEqual(
                len(engine.state.players[seat].zones["library"]),
                packet["state"]["players"][seat]["lib_n"],
            )
        self.assertNotIn(
            "known_top",
            packet["state"]["players"]["B"],
        )
        projected_strings = set(_json_strings(packet))
        for object_id in engine.state.players["B"].zones["library"]:
            self.assertNotIn(
                engine.state.cards[object_id].ref,
                projected_strings,
            )

    def test_look_top_zero_is_empty_and_negative_fails_atomically(self):
        session = self.make_session(40120)
        engine = session.engine
        library = engine.state.players["A"].zones["library"]
        before_order = list(library)
        before_knowledge = {
            object_id: (
                list(engine.state.cards[object_id].known_to),
                list(engine.state.cards[object_id].revealed_to),
            )
            for object_id in library
        }

        self.assertEqual(
            [],
            engine.apply_effect(
                {
                    "op": "look_top",
                    "player": "A",
                    "viewer": "A",
                    "count": 0,
                },
                actor="A",
            ),
        )
        self.assertEqual(before_order, library)
        self.assertEqual(
            before_knowledge,
            {
                object_id: (
                    list(engine.state.cards[object_id].known_to),
                    list(engine.state.cards[object_id].revealed_to),
                )
                for object_id in library
            },
        )

        state_before_rejection = authoritative_state_hash(engine.state)
        for invalid in (-1, "not-an-integer"):
            with self.assertRaisesRegex(
                GameRuleError,
                "count",
            ):
                engine.apply_effect(
                    {
                        "op": "look_top",
                        "player": "A",
                        "viewer": "A",
                        "count": invalid,
                    },
                    actor="A",
                )
            self.assertEqual(
                state_before_rejection,
                authoritative_state_hash(engine.state),
            )

    def test_reorder_requires_the_exact_known_current_top_set(self):
        session = self.make_session(40121)
        engine = session.engine
        library = engine.state.players["A"].zones["library"]
        looked = engine.apply_effect(
            {
                "op": "look_top",
                "player": "A",
                "viewer": "A",
                "count": 3,
            },
            actor="A",
        )
        former_identity = engine.state.cards[library[-4]].logical_object_id
        inserted = engine.state.cards[library[-4]]
        engine.move_card(
            inserted.object_id,
            "library",
            position="top",
            log=False,
        )
        self.assertEqual(former_identity, inserted.logical_object_id)
        self.assertNotIn(
            "known_top",
            session.packet("pilot:A", full=True)["state"]["players"]["A"],
        )

        before_rejection = list(library)
        with self.assertRaisesRegex(
            GameRuleError,
            "exact known cards currently on top",
        ):
            engine.apply_effect(
                {
                    "op": "reorder_top",
                    "player": "A",
                    "viewer": "A",
                    "cards": looked,
                },
                actor="A",
            )
        self.assertEqual(before_rejection, library)

        current = engine.apply_effect(
            {
                "op": "look_top",
                "player": "A",
                "viewer": "A",
                "count": 3,
            },
            actor="A",
        )
        with self.assertRaisesRegex(GameRuleError, "cannot be reordered twice"):
            engine.apply_effect(
                {
                    "op": "reorder_top",
                    "player": "A",
                    "viewer": "A",
                    "cards": [current[0], current[0]],
                },
                actor="A",
            )
        self.assertEqual(before_rejection, library)

        requested = list(reversed(current))
        self.assertEqual(
            requested,
            engine.apply_effect(
                {
                    "op": "reorder_top",
                    "player": "A",
                    "viewer": "A",
                    "cards": requested,
                },
                actor="A",
            ),
        )
        self.assertEqual(
            requested,
            [
                engine.state.cards[object_id].ref
                for object_id in reversed(library[-3:])
            ],
        )

    def test_nth_from_top_and_short_library_fallback_are_generic(self):
        session = self.make_session(40170)
        engine = session.engine
        player = engine.state.players["A"]
        first, second, third = [
            engine.state.cards[object_id]
            for object_id in player.zones["hand"][:3]
        ]

        engine.move_card(
            first.object_id,
            "library",
            position=3,
            log=False,
        )
        self.assertEqual(first.object_id, player.zones["library"][-3])

        too_large = len(player.zones["library"]) + 10
        engine.move_card(
            second.object_id,
            "library",
            position=too_large,
            log=False,
        )
        self.assertEqual(second.object_id, player.zones["library"][0])

        identity = first.logical_object_id
        counter = first.zone_change_counter
        engine.move_card(
            first.object_id,
            "library",
            position=2,
            log=False,
        )
        self.assertEqual(first.object_id, player.zones["library"][-2])
        self.assertEqual(identity, first.logical_object_id)
        self.assertEqual(counter, first.zone_change_counter)

        before_rejection = authoritative_state_hash(engine.state)
        for invalid in (0, -1, True, "middle"):
            with self.assertRaisesRegex(GameRuleError, "position|positive"):
                engine.move_card(
                    third.object_id,
                    "library",
                    position=invalid,
                    log=False,
                )
            self.assertEqual(
                before_rejection,
                authoritative_state_hash(engine.state),
            )

        engine.apply_effect(
            {
                "op": "move",
                "card": third.ref,
                "destination": "library",
                "position": 4,
            },
            actor="A",
        )
        self.assertEqual(third.object_id, player.zones["library"][-4])

    def test_shuffle_forgets_known_library_positions(self):
        session = self.make_session(40122)
        engine = session.engine
        player = engine.state.players["A"]
        known = engine.apply_effect(
            {
                "op": "look_top",
                "player": "A",
                "viewer": "A",
                "count": 3,
            },
            actor="A",
        )
        self.assertTrue(known)

        engine.shuffle_library("A", reason="CR 401 test")

        self.assertTrue(
            all(
                engine.state.cards[object_id].known_to == []
                and engine.state.cards[object_id].revealed_to == []
                for object_id in player.zones["library"]
            )
        )
        packet = session.packet("pilot:A", full=True)
        self.assertNotIn("known_top", packet["state"]["players"]["A"])


if __name__ == "__main__":
    unittest.main()
