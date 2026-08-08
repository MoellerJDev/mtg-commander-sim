from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import TURN_STEPS
from quorune.record import checkpoint_envelope, replay_record
from quorune.semantics import SemanticProgram


class UpkeepStepRuleTests(unittest.TestCase):
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
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def card(session, owner: str, name: str):
        return next(
            card
            for card in session.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def enter_step(session, step: str) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("beginning", step)
        )
        engine._enter_step()

    @staticmethod
    def add_untap_and_upkeep_programs(engine, source) -> None:
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr503-untapped",
                label="CR 503 became-untapped trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr503-untapped",
                active_zone="battlefield",
                event="permanent.untap.self",
                effects=[],
            )
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr503-upkeep",
                label="CR 503 beginning-of-upkeep trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr503-upkeep",
                active_zone="battlefield",
                event="step.begin",
                event_condition={
                    "all": [
                        {
                            "field": "player",
                            "op": "eq",
                            "value": "$source.controller",
                        },
                        {
                            "field": "step",
                            "op": "eq",
                            "value": "upkeep",
                        },
                    ]
                },
                effects=[],
            )
        )

    def test_contract_traces_every_cr_503_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "upkeep-step.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "118.12",
                "503",
                "503.1",
                "503.1a",
                "503.2",
                "702.24",
                "702.24a",
                "702.24b",
            },
            set(contract["rule_references"]),
        )

    def test_upkeep_has_no_turn_action_then_active_gets_priority_and_replays(
        self,
    ):
        session = self.make_session(50301)
        engine = session.engine
        before_event = engine.state.event_sequence

        self.enter_step(session, "upkeep")

        events = [
            event
            for event in engine.state.events
            if event.event_id > before_event
        ]
        self.assertEqual(["step.begin"], [event.code for event in events])
        self.assertEqual("A", engine.state.priority_player)
        self.assertFalse(engine.state.stack)

        engine.pump()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        for seat in ("A", "B"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass the ordinary upkeep priority window.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual(
            ("beginning", "draw"),
            (engine.state.phase, engine.state.step),
        )
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "upkeep-priority"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_untap_and_upkeep_triggers_share_one_apnap_order_batch_and_replay(
        self,
    ):
        session = self.make_session(50302)
        engine = session.engine
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        source.tapped = True
        self.add_untap_and_upkeep_programs(engine, source)
        engine.schedule_delayed_trigger(
            controller="A",
            label="CR 503 active delayed upkeep trigger",
            event_kind="step.begin",
            condition={
                "phase": "beginning",
                "step": "upkeep",
            },
            stack_template={
                "label": "CR 503 active delayed upkeep trigger",
            },
        )
        engine.schedule_delayed_trigger(
            controller="B",
            label="CR 503 nonactive delayed upkeep trigger",
            event_kind="step.begin",
            condition={
                "phase": "beginning",
                "step": "upkeep",
            },
            stack_template={
                "label": "CR 503 nonactive delayed upkeep trigger",
            },
        )

        self.enter_step(session, "untap")

        self.assertEqual(
            ("beginning", "upkeep"),
            (engine.state.phase, engine.state.step),
        )
        self.assertFalse(source.tapped)
        self.assertIsNone(engine.state.priority_player)
        self.assertEqual("trigger.order", engine.state.pending_decision.kind)
        packet = session.packet("pilot:A", full=True)
        by_label = {
            item["label"]: item["id"]
            for item in packet["decision"]["ctx"]["triggers"]
        }
        self.assertEqual(
            {
                "CR 503 became-untapped trigger",
                "CR 503 beginning-of-upkeep trigger",
                "CR 503 active delayed upkeep trigger",
            },
            set(by_label),
        )
        submitted_order = [
            by_label["CR 503 beginning-of-upkeep trigger"],
            by_label["CR 503 active delayed upkeep trigger"],
            by_label["CR 503 became-untapped trigger"],
        ]
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        result = session.act(
            "pilot:A",
            {
                "action_id": "order",
                "triggers": submitted_order,
                "reason": (
                    "Choose one bottom-to-top order for every active-player "
                    "trigger waiting since untap."
                ),
            },
        )
        self.assertTrue(result.ok, result.summary)

        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual(
            [
                "CR 503 beginning-of-upkeep trigger",
                "CR 503 active delayed upkeep trigger",
                "CR 503 became-untapped trigger",
                "CR 503 nonactive delayed upkeep trigger",
            ],
            [item.label for item in engine.state.stack],
        )
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "upkeep-trigger-order"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_late_permanent_and_delayed_trigger_wait_for_later_upkeep(
        self,
    ):
        session = self.make_session(50303, players=4)
        engine = session.engine

        self.enter_step(session, "upkeep")
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.add_untap_and_upkeep_programs(engine, source)
        delayed = engine.schedule_delayed_trigger(
            controller="C",
            label="CR 503 late delayed upkeep trigger",
            event_kind="step.begin",
            condition={
                "phase": "beginning",
                "step": "upkeep",
            },
            stack_template={
                "label": "CR 503 late delayed upkeep trigger",
            },
        )

        self.assertFalse(engine.state.stack)
        self.assertTrue(delayed.active)
        self.assertEqual("A", engine.state.priority_player)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        self.enter_step(session, "upkeep")

        self.assertEqual(
            {
                "CR 503 beginning-of-upkeep trigger",
                "CR 503 late delayed upkeep trigger",
            },
            {item.label for item in engine.state.stack},
        )
        self.assertFalse(delayed.active)
        self.assertEqual("A", engine.state.priority_player)

    def test_state_actions_precede_waiting_trigger_placement_and_priority(
        self,
    ):
        session = self.make_session(50304)
        engine = session.engine
        source = self.card(session, "A", "Goblin Engineer")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        source.tapped = True
        source.counters["-1/-1"] = 2
        self.add_untap_and_upkeep_programs(engine, source)

        self.enter_step(session, "untap")

        self.assertEqual("graveyard", source.zone)
        self.assertFalse(engine.state.stack)
        self.assertIsNone(engine.state.priority_player)
        self.assertEqual("trigger.order", engine.state.pending_decision.kind)

        packet = session.packet("pilot:A", full=True)
        trigger_refs = [
            item["id"]
            for item in packet["decision"]["ctx"]["triggers"]
        ]
        result = session.act(
            "pilot:A",
            {
                "action_id": "order",
                "triggers": trigger_refs,
                "reason": (
                    "Order the waiting abilities after state-based actions."
                ),
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(2, len(engine.state.stack))
        self.assertEqual("A", engine.state.priority_player)


if __name__ == "__main__":
    unittest.main()
