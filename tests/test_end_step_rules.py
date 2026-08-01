from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticProgram


class EndStepRuleTests(unittest.TestCase):
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
    def enter_end_step(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("ending", "end_step")
        )
        engine._enter_step()

    @staticmethod
    def add_end_step_program(engine, source) -> None:
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr513-end-step",
                label="CR 513 permanent end-step trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr513-end-step",
                active_zone="battlefield",
                event="step.begin",
                event_condition={
                    "all": [
                        {
                            "field": "phase",
                            "op": "eq",
                            "value": "ending",
                        },
                        {
                            "field": "step",
                            "op": "eq",
                            "value": "end_step",
                        },
                    ]
                },
                effects=[],
            )
        )

    def test_contract_traces_every_cr_513_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "end-step.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"513", "513.1", "513.1a", "513.2"},
            set(contract["rule_references"]),
        )

    def test_end_step_has_no_turn_action_then_active_gets_priority_and_replays(
        self,
    ):
        session = self.make_session(51301)
        engine = session.engine
        before_event = engine.state.event_sequence

        self.enter_end_step(session)

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
                    "reason": "Pass the ordinary end-step priority window.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual("B", engine.state.active_player)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "end-step-priority"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_permanent_and_delayed_end_step_triggers_both_precede_priority(
        self,
    ):
        session = self.make_session(51302)
        engine = session.engine
        source = self.card(session, "A", "Sai, Master Thopterist")
        artifact = self.card(session, "A", "Sol Ring")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.move_card(
            artifact.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.add_end_step_program(engine, source)
        warform_ref = engine._create_mishra_warform(
            "A",
            artifact.ref,
            reason="CR 513 delayed-trigger witness",
        )

        self.enter_end_step(session)

        self.assertEqual("trigger.order", engine.state.pending_decision.kind)
        packet = session.packet("pilot:A", full=True)
        by_label = {
            item["label"]: item["id"]
            for item in packet["decision"]["ctx"]["triggers"]
        }
        result = session.act(
            "pilot:A",
            {
                "action_id": "order",
                "triggers": [
                    by_label["CR 513 permanent end-step trigger"],
                    by_label[f"Sacrifice {warform_ref}"],
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            {
                "CR 513 permanent end-step trigger",
                f"Sacrifice {warform_ref}",
            },
            {item.label for item in engine.state.stack},
        )
        self.assertEqual("A", engine.state.priority_player)
        self.assertFalse(
            any(
                trigger.active
                and trigger.source_object_id
                == engine._resolve_object(
                    "A", warform_ref, zones={"battlefield"}
                ).object_id
                for trigger in engine.state.delayed_triggers
            )
        )

    def test_late_permanent_and_delayed_trigger_wait_for_next_end_step(
        self,
    ):
        session = self.make_session(51303, players=4)
        engine = session.engine

        self.enter_end_step(session)
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.add_end_step_program(engine, source)
        delayed = engine.schedule_delayed_trigger(
            controller="C",
            label="CR 513 late delayed trigger",
            event_kind="step.begin",
            condition={
                "phase": "ending",
                "step": "end_step",
            },
            stack_template={
                "label": "CR 513 late delayed trigger",
                "context": {"test": "CR 513.2"},
            },
        )

        self.assertFalse(engine.state.stack)
        self.assertTrue(delayed.active)
        self.assertEqual("A", engine.state.priority_player)

        for seat in ("A", "B", "C", "D"):
            engine._pass_priority(seat)
        self.assertEqual("B", engine.state.active_player)

        engine.state.priority_player = None
        engine.state.priority_passes = []
        self.enter_end_step(session)

        self.assertEqual(
            {
                "CR 513 permanent end-step trigger",
                "CR 513 late delayed trigger",
            },
            {item.label for item in engine.state.stack},
        )
        self.assertFalse(delayed.active)
        self.assertEqual("B", engine.state.priority_player)

    def test_end_step_created_turn_duration_survives_until_cleanup(self):
        session = self.make_session(51304)
        engine = session.engine
        permanent = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            permanent.object_id,
            "battlefield",
            controller="A",
            log=False,
        )

        self.enter_end_step(session)
        permanent.temporary_keywords.append("Haste")
        permanent.annotations["until_end_of_turn"] = {"power": 2}
        self.assertIn(
            "Haste",
            engine._effective_card_data(permanent)["keywords"],
        )
        self.assertIn("until_end_of_turn", permanent.annotations)

        engine._pass_priority("A")
        engine._pass_priority("B")

        self.assertEqual("B", engine.state.active_player)
        self.assertNotIn(
            "Haste",
            engine._effective_card_data(permanent)["keywords"],
        )
        self.assertNotIn("until_end_of_turn", permanent.annotations)


if __name__ == "__main__":
    unittest.main()
