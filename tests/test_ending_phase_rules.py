from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import TURN_STEPS
from quorune.record import checkpoint_envelope, replay_record


class EndingPhaseRuleTests(unittest.TestCase):
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
    def enter_end_step(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("ending", "end_step")
        )
        engine._enter_step()
        engine.pump()

    def test_contract_traces_every_cr_512_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "ending-phase.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"512", "512.1"},
            set(contract["rule_references"]),
        )

    def test_ending_phase_has_exactly_end_then_cleanup(self):
        self.assertEqual(
            [
                ("ending", "end_step"),
                ("ending", "cleanup"),
            ],
            [
                (phase, step)
                for phase, step in TURN_STEPS
                if phase == "ending"
            ],
        )

    def test_end_then_cleanup_then_next_turn_order_replays_exactly(self):
        session = self.make_session(51201)
        engine = session.engine
        self.enter_end_step(session)
        turn = engine.state.turn_sequence
        before_event = engine.state.event_sequence
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for seat in ("A", "B"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Advance through the ending phase.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        cleanup_begin = next(
            event
            for event in engine.state.events
            if event.event_id > before_event
            and event.code == "step.begin"
            and event.turn_sequence == turn
            and event.phase == "ending"
            and event.step == "cleanup"
        )
        cleanup_action = next(
            event
            for event in engine.state.events
            if event.event_id > cleanup_begin.event_id
            and event.code == "turn.cleanup"
            and event.turn_sequence == turn
        )
        next_turn = next(
            event
            for event in engine.state.events
            if event.event_id > cleanup_action.event_id
            and event.code == "turn.begin"
            and event.turn_sequence == turn + 1
        )
        self.assertLess(cleanup_begin.event_id, cleanup_action.event_id)
        self.assertLess(cleanup_action.event_id, next_turn.event_id)
        self.assertEqual("B", engine.state.active_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "ending-phase"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_cleanup_discard_prevents_ending_phase_from_skipping_cleanup(
        self,
    ):
        session = self.make_session(51202)
        engine = session.engine
        player = engine.state.players["A"]
        player.max_hand_size = len(player.zones["hand"]) - 1
        turn = engine.state.turn_sequence
        self.enter_end_step(session)

        for seat in ("A", "B"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Advance from end step to cleanup.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual(turn, engine.state.turn_sequence)
        self.assertEqual("A", engine.state.active_player)
        self.assertEqual(("ending", "cleanup"), (
            engine.state.phase,
            engine.state.step,
        ))
        self.assertEqual(
            "cleanup.discard",
            engine.state.pending_decision.kind,
        )


if __name__ == "__main__":
    unittest.main()
