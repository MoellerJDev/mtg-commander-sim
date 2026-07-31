from __future__ import annotations

import json
import unittest
from pathlib import Path

from mtg_commander_sim.model import StackItem
from mtg_commander_sim.semantics import SemanticProgram

from common import keep_all, load_assets, make_session


class TriggeredAbilityRuleTests(unittest.TestCase):
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
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.stack.clear()
        return engine

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    def test_contract_traces_every_cr_603_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "handling-triggered-abilities.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "603",
                "603.1",
                "603.1a",
                "603.1b",
                "603.2",
                "603.2a",
                "603.2b",
                "603.2c",
                "603.2d",
                "603.2e",
                "603.2f",
                "603.2g",
                "603.2h",
                "603.3",
                "603.3a",
                "603.3b",
                "603.3c",
                "603.3d",
                "603.4",
                "603.5",
                "603.6",
                "603.6a",
                "603.6b",
                "603.6c",
                "603.6d",
                "603.6e",
                "603.7",
                "603.7a",
                "603.7b",
                "603.7c",
                "603.7d",
                "603.7e",
                "603.7f",
                "603.7g",
                "603.7h",
                "603.8",
                "603.9",
                "603.10",
                "603.10a",
                "603.10b",
                "603.10c",
                "603.10d",
                "603.10e",
                "603.10f",
                "603.10g",
                "603.11",
                "603.12",
                "603.12a",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("603")
            },
        )

    def test_trigger_waits_for_stabilization_then_becomes_top_stack_object(self):
        engine = self.make_engine(60301)
        source = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:603.3",
                label="CR 603.3 trigger",
                oracle_id=source.oracle_id,
                ability_id="test:603.3",
                active_zone="battlefield",
                event="test.cr603",
                effects=[],
            )
        )
        engine.state.stack.append(
            StackItem(
                stack_id="existing-stack-object",
                ref="S-existing",
                kind="spell",
                controller="B",
                label="Existing spell",
                visibility=["A", "B"],
            )
        )

        engine._dispatch_semantic_event(
            "test.cr603",
            {},
            sources=[source],
        )

        self.assertEqual(["Existing spell"], [
            item.label for item in engine.state.stack
        ])
        self.assertTrue(engine.state.pending_trigger_batches)

        engine._grant_priority("A")

        self.assertEqual(
            ["Existing spell", "CR 603.3 trigger"],
            [item.label for item in engine.state.stack],
        )
        self.assertFalse(engine.state.pending_trigger_batches)
        self.assertEqual("A", engine.state.priority_player)

    def test_trigger_controller_is_frozen_at_trigger_time(self):
        engine = self.make_engine(60302)
        source = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:603.3a",
                label="CR 603.3a trigger",
                oracle_id=source.oracle_id,
                ability_id="test:603.3a",
                active_zone="battlefield",
                event="test.cr603-controller",
                effects=[],
            )
        )

        engine._dispatch_semantic_event(
            "test.cr603-controller",
            {},
            sources=[source],
        )
        engine.change_control(
            source.object_id,
            "A",
            reason="CR 603.3a controller-freeze witness",
        )
        engine._grant_priority("A")

        trigger = engine.state.stack[-1]
        self.assertEqual("B", trigger.controller)
        self.assertEqual("A", source.controller)


if __name__ == "__main__":
    unittest.main()
