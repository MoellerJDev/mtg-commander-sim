from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session


class ActivatedAbilityAndCostTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def _owned_named(engine, seat: str, name: str):
        matches = [
            card for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name and card.zone != "outside"
        ]
        if len(matches) != 1:
            raise AssertionError(f"Expected one {seat} {name}, found {len(matches)}")
        return matches[0]

    @staticmethod
    def _priority_for(session, seat: str):
        session.engine.permissions.invalidate_current()
        session.engine.state.priority_player = None
        session.engine._grant_priority(seat)
        session.engine.pump()
        assert session.pending_principals() == [f"pilot:{seat}"]

    def test_channel_is_exposed_from_hand_and_pays_authoritative_discounted_cost(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=501)
        keep_all(session)
        engine = session.engine
        boseiju = self._owned_named(engine, "B", "Boseiju, Who Endures")
        if boseiju.zone != "hand":
            engine.move_card(boseiju.object_id, "hand", log=False)
        commander_id = engine.state.players["B"].zones["command"][0]
        engine.move_card(commander_id, "battlefield", controller="B", log=False)
        engine.state.players["B"].mana_pool["G"] = 1
        self._priority_for(session, "B")

        packet = session.packet("pilot:B")
        abilities = packet["decision"]["ctx"]["legal"]["abilities"]
        hint = next(item for item in abilities if item["s"] == boseiju.ref and item["a"] == "ab2")
        self.assertEqual("hand", hint["z"])
        self.assertEqual({"GENERIC": 1, "G": 1}, hint["m"])
        self.assertEqual(1, hint["legend_discount"])

        result = session.act(
            "pilot:B",
            {
                "a": "x",
                "source": boseiju.ref,
                "from": "hand",
                "ability": "ab2",
                "targets": ["A"],
                "pay": "manual",
                "payment": {"G": 1},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("graveyard", boseiju.zone)
        self.assertEqual(0, engine.state.players["B"].mana_pool["G"])
        self.assertEqual("activated_ability", engine.state.stack[-1].kind)
        self.assertEqual(boseiju.object_id, engine.state.stack[-1].source_object_id)

    def test_zimone_cost_selection_is_validated_and_paid_by_kernel(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=502)
        keep_all(session)
        engine = session.engine
        commander_id = engine.state.players["B"].zones["command"][0]
        commander = engine.move_card(commander_id, "battlefield", controller="B", log=False)
        commander.acquired_control_turn_count = engine.state.players["B"].turns_begun - 1
        token_ref = engine.create_token(
            "B",
            name="Test Creature",
            characteristics={"type_line": "Creature — Test", "power": "1", "toughness": "1"},
        )[0]
        token = next(card for card in engine.state.cards.values() if card.ref == token_ref)
        self._priority_for(session, "B")

        result = session.act(
            "pilot:B",
            {
                "a": "x",
                "source": commander.ref,
                "ability": "ab2",
                "cost_cards": [token.ref],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(commander.tapped)
        self.assertEqual("outside", token.zone)  # token ceases to exist after leaving the battlefield
        self.assertEqual("activated_ability", engine.state.stack[-1].kind)

    def test_strategic_mana_ability_with_sacrifice_is_not_auto_hidden(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=503)
        keep_all(session)
        engine = session.engine
        tower = self._owned_named(engine, "B", "Phyrexian Tower")
        engine.move_card(tower.object_id, "battlefield", controller="B", log=False)
        token_ref = engine.create_token(
            "B",
            name="Tower Fodder",
            characteristics={"type_line": "Creature — Test", "power": "1", "toughness": "1"},
        )[0]
        token = next(card for card in engine.state.cards.values() if card.ref == token_ref)
        self._priority_for(session, "B")

        packet = session.packet("pilot:B")
        abilities = packet["decision"]["ctx"]["legal"]["abilities"]
        self.assertTrue(any(item["s"] == tower.ref and item["a"] == "ab2" for item in abilities))
        result = session.act(
            "pilot:B",
            {"a": "x", "source": tower.ref, "ability": "ab2", "cost_cards": [token.ref]},
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(tower.tapped)
        self.assertEqual(2, engine.state.players["B"].mana_pool["B"])
        self.assertEqual("outside", token.zone)
        self.assertFalse(engine.state.stack)  # mana abilities do not use the stack


    def test_pilot_cannot_cast_from_graveyard_without_compiled_permission(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=505)
        keep_all(session)
        engine = session.engine
        signet = self._owned_named(engine, "A", "Arcane Signet")
        engine.move_card(signet.object_id, "graveyard", log=False)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        self._priority_for(session, "A")
        result = session.act(
            "pilot:A",
            {"a": "c", "card": signet.ref, "from": "graveyard", "pay": "manual", "payment": {}},
        )
        self.assertFalse(result.ok)
        self.assertIn("not authorized by a compiled zone permission", result.summary)
        self.assertEqual("graveyard", signet.zone)

    def test_pilot_cannot_understate_ordinary_spell_cost(self):
        session = make_session(self.db, self.mishra, self.zimone, seed=504)
        keep_all(session)
        engine = session.engine
        signet = self._owned_named(engine, "A", "Arcane Signet")
        if signet.zone != "hand":
            engine.move_card(signet.object_id, "hand", log=False)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        self._priority_for(session, "A")

        result = session.act(
            "pilot:A",
            {"a": "c", "card": signet.ref, "declared_cost": {"GENERIC": 0}},
        )
        self.assertFalse(result.ok)
        self.assertIn("does not match authoritative cost", result.summary)
        self.assertEqual("hand", signet.zone)
        self.assertIsNotNone(engine.permissions.capability_for("pilot:A"))


if __name__ == "__main__":
    unittest.main()
