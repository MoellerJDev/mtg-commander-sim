from __future__ import annotations

import json
import tempfile
import unittest
from itertools import groupby
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import GameRuleError, TURN_STEPS
from mtg_commander_sim.model import TurnEntry
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class TurnStructureRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 4):
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
    def enter_precombat_main(session, *, issue_task: bool) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("precombat_main", "main")
        )
        engine._enter_step()
        if issue_task:
            engine.pump()

    def test_contract_traces_every_cr_500_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "turn-structure.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "500",
                "500.1",
                "500.2",
                "500.3",
                "500.4",
                "500.5",
                "500.5a",
                "500.5b",
                "500.6",
                "500.7",
                "500.8",
                "500.9",
                "500.10",
                "500.10a",
                "500.11",
                "500.12",
            },
            set(contract["rule_references"]),
        )

    def test_ordinary_turn_table_has_all_five_phases_in_order(self):
        self.assertEqual(
            [
                "beginning",
                "precombat_main",
                "combat",
                "postcombat_main",
                "ending",
            ],
            [
                phase
                for phase, _ in groupby(
                    phase for phase, _step in TURN_STEPS
                )
            ],
        )

    def test_empty_stack_window_requires_every_player_to_pass_and_replays(
        self,
    ):
        session = self.make_session(50002, players=4)
        engine = session.engine
        self.enter_precombat_main(session, issue_task=True)
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for seat in ("A", "B", "C"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass the current empty-stack priority window.",
                },
            )
            self.assertTrue(result.ok, result.summary)
            self.assertEqual(
                ("precombat_main", "main"),
                (engine.state.phase, engine.state.step),
            )

        final = session.act(
            "pilot:D",
            {
                "a": "pass",
                "reason": "Complete the empty-stack priority round.",
            },
        )
        self.assertTrue(final.ok, final.summary)
        self.assertEqual(
            ("combat", "beginning_combat"),
            (engine.state.phase, engine.state.step),
        )
        self.assertEqual("A", engine.state.priority_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "turn-priority"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(4, replay["commands"])

    def test_unspent_mana_empties_before_the_next_step_begins(self):
        session = self.make_session(50003, players=4)
        engine = session.engine
        self.enter_precombat_main(session, issue_task=False)
        engine.state.players["A"].mana_pool["G"] = 1
        engine.state.players["C"].mana_pool["U"] = 2
        before_event = engine.state.event_sequence

        for seat in ("A", "B", "C", "D"):
            engine._pass_priority(seat)

        self.assertEqual(
            ("combat", "beginning_combat"),
            (engine.state.phase, engine.state.step),
        )
        self.assertFalse(
            any(
                any(player.mana_pool.values())
                for player in engine.state.players.values()
            )
        )
        events = [
            event
            for event in engine.state.events
            if event.event_id > before_event
        ]
        mana_events = [
            event for event in events if event.code == "mana.empty"
        ]
        next_step = next(
            event
            for event in events
            if event.code == "step.begin"
            and event.phase == "combat"
            and event.step == "beginning_combat"
        )
        self.assertEqual({"A", "C"}, {event.actor for event in mana_events})
        self.assertTrue(
            all(event.event_id < next_step.event_id for event in mana_events)
        )
        self.assertTrue(
            all(
                event.phase == "precombat_main"
                and event.step == "main"
                for event in mana_events
            )
        )

    def test_unimplemented_skip_schedule_is_rejected_without_mutation(
        self,
    ):
        session = self.make_session(50011, players=2)
        engine = session.engine
        entry = TurnEntry(
            turn_id="skip-test",
            player="B",
            extra=True,
            source="CR 500.11 regression",
            created_sequence=engine.state.turn_sequence,
            skip_steps=["draw"],
        )
        before_hash = authoritative_state_hash(engine.state)

        with self.assertRaisesRegex(
            GameRuleError,
            "Skipped-step turn entries are not implemented",
        ):
            engine._begin_turn(entry)

        self.assertEqual(before_hash, authoritative_state_hash(engine.state))


if __name__ == "__main__":
    unittest.main()
