from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from common import ROOT, load_assets, make_session
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.model import GameState
from mtg_commander_sim.record import (
    event_for_trace,
    inspect_game,
    migrate_v2_game,
    replay_record,
)
from mtg_commander_sim.report import derive_review, write_review_artifacts
from mtg_commander_sim.semantics import SemanticRegistry
from mtg_commander_sim.session import CommanderSession


class GameRecordV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_v3_save_omits_raw_capabilities_and_replays(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=31,
            auto_pass_empty=False,
        )
        principal = session.pending_principals()[0]
        packet = session.packet(principal, full=True)
        raw_token = packet["decision"]["cap"]
        result = session.act(
            principal,
            {
                "action_id": "keep",
                "reason": "Functional opening hand.",
                "plan": ["develop mana"],
                "confidence": 0.9,
                "model_id": "test-pilot",
            },
        )
        self.assertTrue(result.ok, result.summary)
        seat_log = session.decisions[0]
        self.assertTrue(
            all(
                item["id"].startswith("A")
                for item in seat_log["decision_context"]["hand"]
            )
        )
        self.assertIsNotNone(seat_log["projected_state_hash"])
        self.assertLessEqual(len(seat_log["reason"]), 160)
        pending_principal = session.pending_principals()[0]
        old_pending_token = session.engine.permissions.capability_for(pending_principal).token

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "game"
            session.save(record_dir)
            expected = {
                "manifest.json",
                "checkpoint.json",
                "commands.jsonl",
                "events.jsonl",
                "decisions.jsonl",
                "review.json",
                "review.md",
                "initial-checkpoint.json.gz",
            }
            self.assertTrue(expected.issubset({path.name for path in record_dir.iterdir()}))
            self.assertFalse((record_dir / "game.json").exists())
            for path in record_dir.iterdir():
                if path.suffix == ".gz" or not path.is_file():
                    continue
                self.assertNotIn(raw_token, path.read_text(encoding="utf-8"))
            with gzip.open(record_dir / "initial-checkpoint.json.gz", "rt", encoding="utf-8") as handle:
                self.assertNotIn(raw_token, handle.read())
            checkpoint = json.loads((record_dir / "checkpoint.json").read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["state"]["capabilities"], {})
            self.assertTrue(
                all(not item["id"].startswith("c_") for item in checkpoint["active_capabilities"])
            )
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"])
            self.assertEqual(replay["commands"], 1)
            loaded = CommanderSession.load(
                self.db,
                record_dir,
                semantics_path=record_dir / "semantics.json",
            )
            next_principal = loaded.pending_principals()[0]
            refreshed = loaded.packet(next_principal, full=True)["decision"]["cap"]
            self.assertNotEqual(refreshed, old_pending_token)

    def test_trace_levels_remove_bookkeeping_but_debug_retains_it(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=2,
            auto_pass_empty=False,
        )
        event = next(event for event in session.state.events if event.code == "card.draw.private")
        self.assertIsNotNone(event_for_trace(event, "debug"))
        self.assertIsNotNone(event_for_trace(event, "standard"))
        self.assertIsNone(event_for_trace(event, "minimal"))
        session.engine._log("A", "priority.pass", "A passed priority.", importance=0)
        pass_event = session.state.events[-1]
        self.assertIsNotNone(event_for_trace(pass_event, "debug"))
        self.assertIsNone(event_for_trace(pass_event, "standard"))
        self.assertIsNone(event_for_trace(pass_event, "minimal"))

    def test_rejected_attempt_is_a_decision_but_not_a_replay_command(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=12,
            auto_pass_empty=False,
        )
        principal = session.pending_principals()[0]
        session.packet(principal, full=True)
        result = session.act(
            principal,
            {
                "action_id": "cast:not-a-real-object",
                "reason": "Intentional invalid-action regression.",
            },
        )
        self.assertFalse(result.ok)
        self.assertEqual(len(session.commands), 0)
        self.assertEqual(len(session.decisions), 1)
        self.assertFalse(session.decisions[0]["accepted"])
        self.assertEqual(session.pending_principals()[0], principal)

    def test_inspect_and_migrate_completed_v2_fixture(self):
        fixture = ROOT / "run" / "live-duel" / "game.json"
        if not fixture.exists():
            self.skipTest("completed live-duel v2 fixture is not present in this source bundle")
        expected = json.loads(
            (ROOT / "tests" / "fixtures" / "live-duel-characterization.json").read_text(
                encoding="utf-8"
            )
        )
        inspection = inspect_game(fixture)
        self.assertEqual(inspection["record_version"], 2)
        self.assertEqual(inspection["events"], 1331)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "migrated"
            manifest = migrate_v2_game(fixture, output, self.db)
            state = GameState.load(fixture)
            engine = CommanderEngine(self.db, state, SemanticRegistry())
            decisions = []
            for event in state.events:
                if event.code == "decision.response":
                    decisions.append(
                        {
                            "action": event.details.get("action"),
                            "accepted": True,
                            "legacy_incomplete": True,
                        }
                    )
            review = derive_review(engine, decisions=decisions, manifest=manifest)
            self.assertEqual(review["fidelity"]["classification"], expected["classification"])
            self.assertFalse(review["fidelity"]["review_eligible"])
            self.assertEqual(
                {seat: hand["kept"] for seat, hand in review["opening_hands"].items()},
                expected["opening_hand_sizes"],
            )
            self.assertEqual(
                {seat: player["turns_begun"] for seat, player in review["players"].items()},
                expected["turns_begun"],
            )
            self.assertEqual(
                {
                    seat: [spell["name"] for spell in player["spells_cast"]]
                    for seat, player in review["players"].items()
                },
                expected["spells_cast"],
            )
            self.assertEqual(
                sum(review["players"]["B"]["commander_damage_received"].values()),
                expected["commander_damage_to_b"],
            )
            self.assertEqual(review["land_entry"]["plays"], expected["land_plays"])
            self.assertTrue(review["land_entry"]["all_recorded_tapped"])
            self.assertEqual(
                review["land_entry"]["conflict_count"],
                expected["land_entry_conflicts"],
            )
            self.assertEqual(review["fetchlands"]["activations"], 0)
            self.assertEqual(
                review["players"]["B"]["cleanup_discards"],
                expected["b_cleanup_discards"],
            )
            self.assertIn(
                "incomplete relevant Oracle semantics",
                review["fidelity"]["failures"],
            )
            self.assertEqual(
                review["fidelity"]["dimensions"]["card_semantics"],
                "fail",
            )
            replay = replay_record(output, self.db, verify=True)
            self.assertTrue(replay["ok"])
            self.assertEqual(replay["mode"], "legacy_snapshot")
            write_review_artifacts(output, engine, decisions=decisions, manifest=manifest)


if __name__ == "__main__":
    unittest.main()
