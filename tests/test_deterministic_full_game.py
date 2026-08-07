from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from tests.common import load_assets
from quorune import (
    CommanderSession,
    GameConfig,
    ScriptedPilot,
    SequentialPilotRunner,
)
from quorune.cli import _scripted_choice
from quorune.deck import DeckDefinition, DeckEntry
from quorune.record import replay_record


class DeterministicFourPlayerSoakTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, _, _ = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def _micro_pool() -> DeckDefinition:
        return DeckDefinition(
            name="Deterministic micro-pool",
            entries=[
                DeckEntry(
                    name="Zimone and Dina",
                    quantity=1,
                    board="commander",
                ),
                DeckEntry(name="Island", quantity=8, board="mainboard"),
            ],
            commanders=["Zimone and Dina"],
            metadata={
                "fixture_kind": "deterministic_micro_pool",
                "evidence_scope": "rules_runtime_not_format_legality",
            },
        )

    def test_trusted_only_four_player_game_reaches_natural_winner_and_replays(self):
        deck = self._micro_pool()
        session = CommanderSession.create(
            self.db,
            {seat: deck for seat in "ABCD"},
            first_player="A",
            seed=20260731,
            config=GameConfig(
                seed=20260731,
                profile="commander_multiplayer",
                review_profile="commander_review",
                semantic_policy="trusted_only",
                auto_pass_empty_priority=True,
                realistic_mulligan_guard=False,
            ),
        )
        runner = SequentialPilotRunner(
            session,
            {
                f"pilot:{seat}": ScriptedPilot(chooser=_scripted_choice)
                for seat in "ABCD"
            },
        )

        while not session.state.game_over:
            self.assertTrue(runner.step())

        self.assertEqual("D", session.state.winner)
        self.assertEqual(7, session.state.turn_sequence)
        self.assertEqual(8, runner.metrics.pilot_invocations)
        self.assertEqual(0, runner.metrics.arbiter_invocations)
        self.assertTrue(
            all(
                not session.state.players[seat].in_game
                and session.state.players[seat].attempted_empty_draw
                for seat in "ABC"
            )
        )
        self.assertTrue(session.state.players["D"].in_game)

        opportunities = session.state.action_opportunities
        # CR 508.8 removes the empty blocker and combat-damage priority
        # windows. The soak must still exercise a substantial opportunity
        # journal without counting those skipped steps as coverage.
        self.assertGreater(len(opportunities), 150)
        self.assertFalse(
            any(row["outcome"] == "incorrect_suppression" for row in opportunities)
        )
        self.assertEqual(
            0,
            sum(
                int(
                    player.stats.get("decision_optimization", {}).get(
                        "suppressed_meaningful_windows",
                        0,
                    )
                )
                for player in session.state.players.values()
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "deterministic-four-player-soak"
            session.save(output)
            replay = replay_record(output, self.db, verify=True)
            hidden_audit = json.loads(
                (output / "hidden-information-audit.json").read_text(
                    encoding="utf-8"
                )
            )
            review = json.loads(
                (output / "review.json").read_text(encoding="utf-8")
            )

        self.assertTrue(replay["ok"])
        self.assertTrue(hidden_audit["seat_projection_verified"])
        self.assertEqual("rules_test", review["fidelity"]["classification"])
        self.assertFalse(review["fidelity"]["matchup_evidence"])


if __name__ == "__main__":
    unittest.main()
