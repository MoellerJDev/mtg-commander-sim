from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session


class ExactDeckTriggerFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 4):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.state.pending_decision = None
        session.state.priority_player = None
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    @staticmethod
    def resolve_top(engine):
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()

    def test_ichor_wellspring_draws_on_enter_and_graveyard(self):
        session = self.make_session(820, players=2)
        engine = session.engine
        wellspring = self.card(engine, "A", "Ichor Wellspring")
        before = len(engine.state.players["A"].draw_history)

        engine.move_card(
            wellspring.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
            reason="Ichor enters scenario",
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(
            ["Ichor Wellspring enters"],
            [item.label for item in engine.state.stack],
        )
        self.resolve_top(engine)
        self.assertEqual(
            before + 1,
            len(engine.state.players["A"].draw_history),
        )

        engine.apply_effect(
            {"op": "sacrifice", "card": wellspring.ref},
            actor="A",
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(
            ["Ichor Wellspring graveyard trigger"],
            [item.label for item in engine.state.stack],
        )
        self.resolve_top(engine)
        self.assertEqual(
            before + 2,
            len(engine.state.players["A"].draw_history),
        )

    def test_bastion_enter_and_multiplayer_death_triggers(self):
        session = self.make_session(821)
        engine = session.engine
        bastion = self.card(engine, "B", "Bastion of Remembrance")
        life_before = {
            seat: player.life
            for seat, player in engine.state.players.items()
        }

        engine.move_card(
            bastion.object_id,
            "battlefield",
            controller="B",
            semantic_events=True,
            reason="Bastion enters scenario",
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        soldier = next(
            card
            for card in engine.state.cards.values()
            if card.controller == "B"
            and card.is_token
            and card.printed_name == "Human Soldier"
        )
        data = engine._effective_card_data(soldier)
        self.assertEqual("1", data["power"])
        self.assertEqual("1", data["toughness"])
        self.assertIn("creature", data["type_line"].casefold())

        engine.apply_effect(
            {"op": "sacrifice", "card": soldier.ref},
            actor="B",
        )
        self.assertFalse(engine._stabilize())
        self.resolve_top(engine)
        self.assertEqual(
            life_before["B"] + 1,
            engine.state.players["B"].life,
        )
        for seat in ("A", "C", "D"):
            self.assertEqual(
                life_before[seat] - 1,
                engine.state.players[seat].life,
            )

    def test_reckless_fireweaver_damages_each_opponent(self):
        session = self.make_session(822)
        engine = session.engine
        fireweaver = self.card(engine, "A", "Reckless Fireweaver")
        engine.move_card(
            fireweaver.object_id,
            "battlefield",
            controller="A",
        )
        life_before = {
            seat: player.life
            for seat, player in engine.state.players.items()
        }

        engine.create_token(
            "A",
            name="Treasure",
            characteristics={"type_line": "Token Artifact — Treasure"},
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(
            ["Reckless Fireweaver artifact-enter trigger"],
            [item.label for item in engine.state.stack],
        )
        self.resolve_top(engine)
        self.assertEqual(life_before["A"], engine.state.players["A"].life)
        for seat in ("B", "C", "D"):
            self.assertEqual(
                life_before[seat] - 1,
                engine.state.players[seat].life,
            )

        engine.create_token(
            "B",
            name="Opponent Treasure",
            characteristics={"type_line": "Token Artifact — Treasure"},
        )
        self.assertFalse(engine._stabilize())
        self.assertFalse(engine.state.stack)


if __name__ == "__main__":
    unittest.main()
