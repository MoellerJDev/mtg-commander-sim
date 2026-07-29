from __future__ import annotations

import gzip
import json
import tempfile
import unittest
from pathlib import Path

from common import ROOT, load_assets
from mtg_commander_sim.cli import _scripted_choice
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.model import GameState
from mtg_commander_sim.pilot import (
    ScriptedPilot,
    SequentialPilotRunner,
)
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticRegistry
from mtg_commander_sim.session import CommanderSession


class Seed20260730RegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()
        cls.fixture = json.loads(
            (
                ROOT
                / "tests"
                / "fixtures"
                / "seed-20260730-yield-regression.json"
            ).read_text(encoding="utf-8")
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _session_from_exact_initial_state(self) -> CommanderSession:
        record = ROOT / self.fixture["source_record"]
        with gzip.open(
            record / "initial-checkpoint.json.gz",
            "rt",
            encoding="utf-8",
        ) as handle:
            envelope = json.load(handle)
        state = GameState.from_dict(envelope["state"])
        state.config.auto_pass_empty_priority = True
        state.config.profile = "commander_duel"
        engine = CommanderEngine(
            self.db,
            state,
            SemanticRegistry(record / "semantics.json"),
        )
        engine.permissions.reissue_pending()
        return CommanderSession(
            card_db=self.db,
            engine=engine,
            projector=StateProjector(self.db, state),
            initial_checkpoint=checkpoint_envelope(state),
        )

    @staticmethod
    def _names_for_action_ids(session, action_ids):
        by_ref = {card.ref: card.printed_name for card in session.state.cards.values()}
        result = []
        for action_id in action_ids:
            parts = str(action_id).split(":")
            if len(parts) >= 2 and parts[0] in {"play-land", "cast"}:
                result.append(by_ref.get(parts[1], parts[1]))
        return result

    def test_exact_opening_state_and_corrected_main_phase_delivery(self):
        session = self._session_from_exact_initial_state()
        for seat, expected in self.fixture["opening_hands"].items():
            actual = [
                session.state.cards[object_id].printed_name
                for object_id in session.state.players[seat].zones["hand"]
            ]
            self.assertEqual(expected, actual)

        runner = SequentialPilotRunner(
            session,
            {
                "pilot:A": ScriptedPilot(chooser=_scripted_choice),
                "pilot:B": ScriptedPilot(chooser=_scripted_choice),
            },
            arbiter=ScriptedPilot(
                chooser=_scripted_choice,
                implementation_id="provisional-arbiter-v1",
            ),
        )
        invocations = 0
        while (
            not session.state.game_over
            and session.state.turn_sequence < 8
            and invocations < 200
        ):
            if not runner.step():
                break
            invocations += 1

        rows = session.state.action_opportunities
        by_turn = {
            turn: [
                row
                for row in rows
                if row["turn_sequence"] == turn
                and row["phase"] == "precombat_main"
                and row["step"] == "main"
                and row["seat"] == row["active_player"]
                and row["meaningful_actions_exist"]
            ]
            for turn in range(3, 8)
        }
        for turn in range(3, 8):
            self.assertTrue(by_turn[turn], f"no main-phase opportunity on turn {turn}")
            self.assertTrue(
                all(
                    row["outcome"]
                    in {"pilot_task_issued", "ordered_plan"}
                    for row in by_turn[turn]
                )
            )

        turn3_names = self._names_for_action_ids(
            session,
            by_turn[3][0]["meaningful_action_ids"],
        )
        for name in ("Island", "Verdant Catacombs", "Boseiju, Who Endures"):
            self.assertIn(name, turn3_names)

        turn4_names = [
            name
            for row in by_turn[4]
            for name in self._names_for_action_ids(
                session, row["meaningful_action_ids"]
            )
        ]
        self.assertIn("Watery Grave", turn4_names)

        turn6_names = [
            name
            for row in by_turn[6]
            for name in self._names_for_action_ids(
                session, row["meaningful_action_ids"]
            )
        ]
        self.assertIn("Sol Ring", turn6_names)

        telemetry = [
            player.stats.get("decision_optimization", {})
            for player in session.state.players.values()
        ]
        self.assertEqual(
            0,
            sum(
                int(row.get("suppressed_meaningful_windows", 0))
                for row in telemetry
            ),
        )
        self.assertGreater(
            sum(
                int(row.get("yields_invalidated_by_phase", 0))
                for row in telemetry
            ),
            0,
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "corrected"
            session.save(output)
            replay = replay_record(output, self.db, verify=True)
            self.assertTrue(replay["ok"])


if __name__ == "__main__":
    unittest.main()
