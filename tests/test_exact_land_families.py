from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session


class ExactLandFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    def test_bounce_lands_require_controller_to_return_one_land(self):
        for index, name in enumerate(
            ("Golgari Rot Farm", "Simic Growth Chamber", "Dimir Aqueduct")
        ):
            with self.subTest(card=name):
                session = make_session(
                    self.db,
                    self.mishra,
                    self.zimone,
                    players=2,
                    seed=850 + index,
                )
                keep_all(session)
                engine = session.engine
                engine.permissions.invalidate_current()
                engine.state.pending_decision = None
                engine.state.priority_player = None
                bounce = self.card(engine, "B", name)
                own_land = self.card(engine, "B", "Island")
                opposing_land = self.card(engine, "A", "Island")
                engine.move_card(
                    own_land.object_id,
                    "battlefield",
                    controller="B",
                )
                engine.move_card(
                    opposing_land.object_id,
                    "battlefield",
                    controller="A",
                )

                engine.move_card(
                    bounce.object_id,
                    "battlefield",
                    controller="B",
                    tapped=True,
                    semantic_events=True,
                    reason=f"{name} scenario",
                )
                self.assertFalse(engine._stabilize())
                engine._prepare_stack_resolution()
                packet = session.packet("pilot:B", full=True)
                options = {
                    row["id"]
                    for row in packet["decision"]["ctx"]["objects"]
                }
                self.assertEqual({bounce.ref, own_land.ref}, options)
                result = session.act(
                    "pilot:B",
                    {
                        "action_id": "choose",
                        "objects": [own_land.ref],
                        "plan": "FIX_COLORS",
                        "reason": "Return the basic land and keep the bounce land.",
                    },
                )

                self.assertTrue(result.ok, result.summary)
                self.assertEqual("hand", own_land.zone)
                self.assertEqual("battlefield", bounce.zone)
                self.assertTrue(bounce.tapped)


if __name__ == "__main__":
    unittest.main()
