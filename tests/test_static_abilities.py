from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session


class StaticAbilityRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_engine(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine.state.priority_player = "A"
        return session.engine

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def prepare_main(engine, seat: str = "A") -> None:
        engine.state.active_player = seat
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.clear()
        engine.state.priority_player = seat
        engine.state.priority_passes = []
        engine.state.pending_decision = None

    @staticmethod
    def resolve_top(engine) -> None:
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()

    def test_contract_traces_every_cr_604_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "handling-static-abilities.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "604",
                "604.1",
                "604.2",
                "604.3",
                "604.3a",
                "604.4",
                "604.5",
                "604.6",
                "604.7",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("604")
            },
        )

    def test_battlefield_static_effect_stops_when_source_leaves(self):
        engine = self.make_engine(60401)
        padeem = self.card(
            engine,
            "A",
            "Padeem, Consul of Innovation",
        )
        ring = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            padeem.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )

        self.assertIn(
            "Hexproof",
            engine._effective_card_data(ring)["keywords"],
        )
        engine.move_card(padeem.object_id, "graveyard", log=False)
        self.assertNotIn(
            "Hexproof",
            engine._effective_card_data(ring)["keywords"],
        )

    def test_moving_equipment_moves_its_static_effect(self):
        engine = self.make_engine(60402)
        greaves = self.card(engine, "A", "Lightning Greaves")
        mishra = self.card(engine, "A", "Mishra, Eminent One")
        engineer = self.card(engine, "A", "Goblin Engineer")
        for permanent in (greaves, mishra, engineer):
            engine.move_card(
                permanent.object_id,
                "battlefield",
                controller="A",
                log=False,
            )
        self.prepare_main(engine)

        engine._activate(
            "A",
            {
                "source": greaves.ref,
                "ability": "ab2",
                "targets": [mishra.ref],
            },
        )
        self.resolve_top(engine)
        self.assertIn(
            "Shroud",
            engine._effective_card_data(mishra)["keywords"],
        )
        self.assertNotIn(
            "Shroud",
            engine._effective_card_data(engineer)["keywords"],
        )

        self.prepare_main(engine)
        engine._activate(
            "A",
            {
                "source": greaves.ref,
                "ability": "ab2",
                "targets": [engineer.ref],
            },
        )
        self.resolve_top(engine)

        self.assertNotIn(
            "Shroud",
            engine._effective_card_data(mishra)["keywords"],
        )
        self.assertIn(
            "Shroud",
            engine._effective_card_data(engineer)["keywords"],
        )
        self.assertEqual(engineer.object_id, greaves.attached_to)


if __name__ == "__main__":
    unittest.main()
