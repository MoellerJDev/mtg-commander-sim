from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.record import replay_record


class BeginningPhaseRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_contract_traces_every_cr_501_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "beginning-phase.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"501", "501.1"},
            set(contract["rule_references"]),
        )

    def test_beginning_phase_has_exactly_untap_upkeep_then_draw(self):
        self.assertEqual(
            [
                ("beginning", "untap"),
                ("beginning", "upkeep"),
                ("beginning", "draw"),
            ],
            [
                (phase, step)
                for phase, step in TURN_STEPS
                if phase == "beginning"
            ],
        )

    def test_turn_one_skips_only_the_draw_action_and_replays_phase_order(
        self,
    ):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=50101,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        turn = engine.state.turn_sequence

        self.assertEqual(1, turn)
        self.assertEqual("A", engine.state.active_player)
        self.assertEqual(
            ("beginning", "upkeep"),
            (engine.state.phase, engine.state.step),
        )

        for expected_step in ("upkeep", "draw"):
            self.assertEqual(expected_step, engine.state.step)
            for seat in ("A", "B"):
                result = session.act(
                    f"pilot:{seat}",
                    {
                        "a": "pass",
                        "reason": (
                            "Advance through the ordinary beginning phase."
                        ),
                    },
                )
                self.assertTrue(result.ok, result.summary)

        self.assertEqual(
            ("precombat_main", "main"),
            (engine.state.phase, engine.state.step),
        )
        beginning_steps = [
            event.step
            for event in engine.state.events
            if event.code == "step.begin"
            and event.turn_sequence == turn
            and event.phase == "beginning"
        ]
        self.assertEqual(["untap", "upkeep", "draw"], beginning_steps)

        draw_step = next(
            event
            for event in engine.state.events
            if event.code == "step.begin"
            and event.turn_sequence == turn
            and event.phase == "beginning"
            and event.step == "draw"
        )
        draw_skip = next(
            event
            for event in engine.state.events
            if event.code == "draw.skip"
            and event.turn_sequence == turn
        )
        precombat = next(
            event
            for event in engine.state.events
            if event.code == "step.begin"
            and event.turn_sequence == turn
            and event.phase == "precombat_main"
            and event.step == "main"
        )
        self.assertLess(draw_step.event_id, draw_skip.event_id)
        self.assertLess(draw_skip.event_id, precombat.event_id)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "beginning-phase"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(6, replay["commands"])


if __name__ == "__main__":
    unittest.main()
