from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from common import load_assets, make_session
from mtg_commander_sim.record import checkpoint_envelope, replay_record


class RulesAuthorityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _session(self, *, players=2):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=5,
            auto_pass_empty=False,
        )
        session.engine.permissions.invalidate_current()
        session.state.capabilities = {}
        session.state.started = True
        session.state.active_player = "A"
        session.state.phase = "precombat_main"
        session.state.step = "main"
        session.state.priority_player = "A"
        return session

    @staticmethod
    def _card(session, seat, name):
        return next(
            card
            for card in session.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def test_land_entry_is_server_derived_for_duel_and_multiplayer(self):
        duel = self._session(players=2)
        forest = self.db.lookup("Forest")
        confluence = self.db.lookup("Mana Confluence")
        strand = self.db.lookup("Flooded Strand")
        wooded = self.db.lookup("Wooded Foothills")
        bog = self.db.lookup("Bojuka Bog")
        field = self.db.lookup("Field of the Dead")
        training = self.db.lookup("Training Center")
        shifting = self.db.lookup("Shifting Woodland")
        mistrise = self.db.lookup("Mistrise Village")
        self.assertFalse(duel.engine._land_enters_tapped("A", forest, {}))
        self.assertFalse(duel.engine._land_enters_tapped("A", confluence, {}))
        self.assertFalse(duel.engine._land_enters_tapped("A", strand, {}))
        self.assertFalse(duel.engine._land_enters_tapped("A", wooded, {}))
        self.assertTrue(duel.engine._land_enters_tapped("A", bog, {}))
        self.assertTrue(duel.engine._land_enters_tapped("A", field, {}))
        self.assertTrue(duel.engine._land_enters_tapped("A", training, {}))
        self.assertTrue(duel.engine._land_enters_tapped("B", shifting, {}))
        forest_card = self._card(duel, "B", "Forest")
        duel.engine.move_card(forest_card.object_id, "battlefield", controller="B")
        self.assertFalse(duel.engine._land_enters_tapped("B", shifting, {}))
        self.assertFalse(duel.engine._land_enters_tapped("B", mistrise, {}))

        mountain_only = self._session(players=2)
        mountain = next(
            card
            for card in mountain_only.state.cards.values()
            if "Mountain"
            in self.db.lookup(card.printed_name).type_line.split()
        )
        mountain_only.engine.move_card(
            mountain.object_id,
            "battlefield",
            controller="B",
        )
        self.assertFalse(
            mountain_only.engine._land_enters_tapped("B", mistrise, {})
        )
        self.assertTrue(
            self._session(players=2).engine._land_enters_tapped(
                "B",
                mistrise,
                {},
            )
        )

        multiplayer = self._session(players=4)
        self.assertFalse(multiplayer.engine._land_enters_tapped("A", training, {}))

    def test_fetchland_exposes_search_choices_and_resolves_authoritatively(self):
        session = self._session(players=2)
        session.state.active_player = "B"
        session.state.priority_player = "B"
        strand = self._card(session, "B", "Flooded Strand")
        tropical = self._card(session, "B", "Tropical Island")
        session.engine.move_card(strand.object_id, "battlefield", controller="B")
        session.engine.move_card(tropical.object_id, "library")
        session.engine._issue_priority("B")
        packet = session.packet("pilot:B", full=True)
        ability = next(
            item
            for item in packet["decision"]["ctx"]["legal"]["abilities"]
            if item["s"] == strand.ref
        )
        self.assertEqual(ability["search_types"], ["plains", "island"])
        action_id = f"activate:{strand.ref}:{ability['a']}"
        result = session.act(
            "pilot:B",
            {
                "action_id": action_id,
                "reason": "Activate the fetchland before selecting on resolution.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(strand.zone, "graveyard")
        item = session.state.stack[-1]
        self.assertEqual(item.context["builtin"], "fetch_land")
        self.assertFalse(item.context["choice_made"])
        session.engine.permissions.invalidate_current()
        session.engine._prepare_stack_resolution()
        search_packet = session.packet("pilot:B", full=True)
        self.assertIn(
            tropical.ref,
            {
                option["id"]
                for option in search_packet["decision"]["ctx"]["search_cards"]
            },
        )
        choice = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "search_card": tropical.ref,
                "reason": "Select the untapped blue-green source.",
            },
        )
        self.assertTrue(choice.ok, choice.summary)
        self.assertEqual(tropical.zone, "battlefield")
        self.assertFalse(tropical.tapped)
        self.assertTrue(any(event.code == "library.search" for event in session.state.events))
        wooded = self._card(session, "B", "Wooded Foothills")
        wooded_ability = session.engine._activated_abilities(wooded)[0]
        self.assertEqual(
            session.engine._fetch_land_types(wooded_ability.effect_text),
            ("mountain", "forest"),
        )

    def test_mana_confluence_makes_one_mana_noncreatures_legally_castable(self):
        session = self._session(players=2)
        confluence = self._card(session, "A", "Mana Confluence")
        lantern = self._card(session, "A", "Soul-Guide Lantern")
        sol_ring = self._card(session, "A", "Sol Ring")
        session.engine.move_card(confluence.object_id, "battlefield", controller="A")
        session.engine.move_card(lantern.object_id, "hand")
        session.engine.move_card(sol_ring.object_id, "hand")
        session.engine._issue_priority("A")
        packet = session.packet("pilot:A", full=True)
        castable = set(packet["decision"]["ctx"]["legal"]["cast"])
        mana_abilities = packet["decision"]["ctx"]["legal"]["mana_abilities"]
        self.assertIn(lantern.ref, castable)
        self.assertIn(sol_ring.ref, castable)
        self.assertTrue(any(item["s"] == confluence.ref for item in mana_abilities))
        lantern_action = next(
            item["id"]
            for item in packet["decision"]["legal_actions"]
            if item.get("card") == lantern.ref
        )
        life_before = session.state.players["A"].life
        result = session.act(
            "pilot:A",
            {
                "action_id": lantern_action,
                "reason": "Deploy graveyard interaction.",
                "plan": ["cast lantern", "hold priority"],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(session.state.players["A"].life, life_before - 1)
        self.assertTrue(confluence.tapped)
        self.assertEqual(lantern.zone, "stack")

    def test_ordered_plan_executes_only_while_next_action_remains_legal(self):
        session = self._session(players=2)
        confluence = self._card(session, "A", "Mana Confluence")
        lantern = self._card(session, "A", "Soul-Guide Lantern")
        session.engine.move_card(confluence.object_id, "hand")
        session.engine.move_card(lantern.object_id, "hand")
        session.engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(session.state)
        first = session.packet("pilot:A", full=True)
        land_action = next(
            item["id"]
            for item in first["decision"]["legal_actions"]
            if item.get("card") == confluence.ref
        )
        cast_action = f"cast:{lantern.ref}"
        result = session.act(
            "pilot:A",
            {
                "reason": "Develop the source needed for the one-drop.",
                "plan": [
                    {"action_id": land_action},
                    {"action_id": cast_action},
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(confluence.zone, "battlefield")
        session.next_task()
        self.assertEqual(lantern.zone, "stack")
        self.assertEqual(len(session.commands), 2)
        self.assertEqual(len(session.decisions), 1)
        self.assertEqual(len(session.decisions[0]["plan"]), 2)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "planned-game"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"])
            self.assertEqual(replay["commands"], 2)


if __name__ == "__main__":
    unittest.main()
