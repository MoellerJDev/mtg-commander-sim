from __future__ import annotations

import json
import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import StackItem


class ExactDeckInteractionFamilyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
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

    def test_bojuka_bog_targets_and_exiles_one_graveyard(self):
        session = self.make_session(830)
        engine = session.engine
        bog = self.card(engine, "B", "Bojuka Bog")
        opposing_card = self.card(engine, "A", "Ichor Wellspring")
        own_card = self.card(engine, "B", "Faerie Mastermind")
        engine.move_card(opposing_card.object_id, "graveyard")
        engine.move_card(own_card.object_id, "graveyard")

        engine.move_card(
            bog.object_id,
            "battlefield",
            controller="B",
            tapped=True,
            semantic_events=True,
            reason="Bojuka Bog scenario",
        )
        self.assertTrue(engine._stabilize())
        packet = session.packet("pilot:B", full=True)
        self.assertEqual("semantic.target", packet["decision"]["kind"])
        candidates = set(
            packet["decision"]["ctx"]["target_schema"]["legal_refs"]
        )
        self.assertEqual({"A", "B"}, candidates)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "targets": ["A"],
                "plan": "DISRUPT_GRAVEYARD",
                "reason": "Exile A's graveyard with Bojuka Bog.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertEqual("exile", opposing_card.zone)
        self.assertEqual("graveyard", own_card.zone)

    def test_reanimate_uses_any_graveyard_and_exact_mana_value_loss(self):
        session = self.make_session(831)
        engine = session.engine
        spell = self.card(engine, "B", "Reanimate")
        target = self.card(engine, "A", "Brudiclad, Telchor Engineer")
        engine.move_card(target.object_id, "graveyard")
        engine._remove_from_zone(spell)
        spell.zone = "stack"
        item = StackItem(
            stack_id="reanimate-scenario",
            ref="S-reanimate",
            kind="spell",
            controller="B",
            label="Reanimate",
            card_object_id=spell.object_id,
            semantic_key=f"{spell.oracle_id}:spell:front",
            default_destination="graveyard",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)
        before_life = engine.state.players["B"].life

        engine._prepare_stack_resolution()
        packet = session.packet("pilot:B", full=True)
        self.assertEqual("semantic.target", packet["decision"]["kind"])
        candidates = set(
            packet["decision"]["ctx"]["target_schema"]["legal_refs"]
        )
        self.assertIn(target.ref, candidates)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "targets": [target.ref],
                "plan": "DEVELOP_ENGINE",
                "reason": "Reanimate the six-mana artifact creature.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertEqual("battlefield", target.zone)
        self.assertEqual("B", target.controller)
        self.assertEqual(
            before_life - 6,
            engine.state.players["B"].life,
        )

    def test_sylvan_safekeeper_pays_land_and_grants_temporary_shroud(self):
        session = self.make_session(832)
        engine = session.engine
        safekeeper = self.card(engine, "B", "Sylvan Safekeeper")
        creature = self.card(engine, "B", "Deathrite Shaman")
        land = self.card(engine, "B", "Island")
        for card in (safekeeper, creature, land):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller="B",
            )
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "B"
        engine._issue_priority("B")
        packet = session.packet("pilot:B", full=True)
        action = next(
            action
            for action in packet["decision"]["legal_actions"]
            if action.get("source") == safekeeper.ref
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": action["id"],
                "cost_cards": [land.ref],
                "targets": [creature.ref],
                "plan": "PROTECT_ENGINE",
                "reason": "Sacrifice the land to protect Deathrite Shaman.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("graveyard", land.zone)
        self.resolve_top(engine)
        self.assertIn("Shroud", creature.temporary_keywords)

    def test_senseis_divining_top_reorders_and_draws_to_library(self):
        session = self.make_session(833)
        engine = session.engine
        top = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id,
            "battlefield",
            controller="A",
        )
        original_top_first = [
            engine.state.cards[object_id].ref
            for object_id in reversed(
                engine.state.players["A"].zones["library"][-3:]
            )
        ]
        engine.state.players["A"].mana_pool["C"] = 1
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"
        engine._issue_priority("A")
        packet = session.packet("pilot:A", full=True)
        look_action = next(
            action
            for action in packet["decision"]["legal_actions"]
            if action.get("source") == top.ref
            and action.get("ability") == "ab1"
        )
        result = session.act(
            "pilot:A",
            {
                "action_id": look_action["id"],
                "plan": "SET_UP_DRAW",
                "reason": "Inspect and reorder the top three cards.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        choice = session.packet("pilot:A", full=True)
        self.assertEqual("semantic.choice", choice["decision"]["kind"])
        options = [
            item["id"] for item in choice["decision"]["ctx"]["cards"]
        ]
        self.assertEqual(set(original_top_first), set(options))
        opposing = json.dumps(session.packet("pilot:B", full=True))
        self.assertTrue(all(ref not in opposing for ref in options))
        selected = list(reversed(options))
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "cards": selected,
                "plan": "SET_UP_DRAW",
                "reason": "Put the selected card on top and preserve the rest.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            selected[0],
            engine.state.cards[
                engine.state.players["A"].zones["library"][-1]
            ].ref,
        )

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = "A"
        engine._issue_priority("A")
        packet = session.packet("pilot:A", full=True)
        draw_action = next(
            action
            for action in packet["decision"]["legal_actions"]
            if action.get("source") == top.ref
            and action.get("ability") == "ab2"
        )
        result = session.act(
            "pilot:A",
            {
                "action_id": draw_action["id"],
                "plan": "GAIN_CARDS",
                "reason": "Draw the arranged card and put Top on the library.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.resolve_top(engine)
        self.assertIn(
            next(
                card.object_id
                for card in engine.state.cards.values()
                if card.ref == selected[0]
            ),
            engine.state.players["A"].zones["hand"],
        )
        self.assertEqual("library", top.zone)
        self.assertEqual(
            top.object_id,
            engine.state.players["A"].zones["library"][-1],
        )


if __name__ == "__main__":
    unittest.main()
