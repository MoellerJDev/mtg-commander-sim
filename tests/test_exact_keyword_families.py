from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session


class ExactKeywordFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_exact_list_cycling_pays_three_discards_and_draws(self):
        for seat, name in (
            ("A", "Xander's Lounge"),
            ("B", "Zagoth Triome"),
        ):
            with self.subTest(card=name):
                session = make_session(
                    self.db,
                    self.mishra,
                    self.zimone,
                    players=2,
                    seed=840 + ord(seat),
                )
                keep_all(session)
                engine = session.engine
                engine.permissions.invalidate_current()
                engine.state.pending_decision = None
                card = next(
                    card
                    for card in engine.state.cards.values()
                    if card.owner == seat
                    and card.printed_name == name
                )
                engine.move_card(card.object_id, "hand", log=False)
                before = len(
                    engine.state.players[seat].draw_history
                )
                engine.state.players[seat].mana_pool["C"] = 3
                engine.state.priority_player = seat
                engine.state.priority_passes = []

                engine._activate(
                    seat,
                    {
                        "source": card.ref,
                        "from": "hand",
                        "ability": "ab3",
                        "pay": "manual",
                        "payment": {"C": 3},
                    },
                )
                self.assertEqual("graveyard", card.zone)
                engine.state.priority_player = None
                engine._prepare_stack_resolution()

                self.assertEqual(
                    before + 1,
                    len(engine.state.players[seat].draw_history),
                )
                self.assertEqual(
                    0, engine.state.players[seat].mana_pool["C"]
                )

    def test_food_and_treasure_tokens_have_authoritative_abilities(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=843,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        treasure_ref = engine.create_token(
            "B",
            name="Treasure",
            characteristics={
                "type_line": "Token Artifact — Treasure",
                "oracle_text": (
                    "{T}, Sacrifice this token: Add one mana of any color."
                ),
            },
        )[0]
        food_ref = engine.create_token(
            "B",
            name="Food",
            characteristics={
                "type_line": "Token Artifact — Food",
                "oracle_text": (
                    "{2}, {T}, Sacrifice this token: You gain 3 life."
                ),
            },
        )[0]
        treasure = next(
            card
            for card in engine.state.cards.values()
            if card.ref == treasure_ref
        )
        food = next(
            card
            for card in engine.state.cards.values()
            if card.ref == food_ref
        )

        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": treasure.ref,
                "ability": "ab1",
                "mana_choice": "G",
            },
        )
        self.assertEqual("outside", treasure.zone)
        self.assertEqual(1, engine.state.players["B"].mana_pool["G"])
        self.assertFalse(engine.state.stack)

        before_life = engine.state.players["B"].life
        engine.state.players["B"].mana_pool["C"] = 2
        engine.state.priority_player = "B"
        engine._activate(
            "B",
            {
                "source": food.ref,
                "ability": "ab1",
                "pay": "manual",
                "payment": {"C": 2},
            },
        )
        self.assertEqual("outside", food.zone)
        engine.state.priority_player = None
        engine._prepare_stack_resolution()
        self.assertEqual(
            before_life + 3, engine.state.players["B"].life
        )


if __name__ == "__main__":
    unittest.main()
