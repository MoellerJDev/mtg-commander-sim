from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class DeclareBlockersRuleTests(unittest.TestCase):
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
        engine.state.phase = "combat"
        engine.state.step = "declare_blockers"
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def token(
        engine,
        controller: str,
        name: str,
        *,
        tapped: bool = False,
    ):
        ref = engine.create_token(
            controller,
            name=name,
            tapped=tapped,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    def set_up_blocker_decision(self, session):
        engine = session.engine
        attacker = self.token(engine, "A", "CR 509 Attacker")
        blocker = self.token(engine, "B", "CR 509 Blocker")
        attacker.attacking = "B"
        engine.state.combat = CombatState(
            attackers_declared=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
        )
        engine._begin_blocker_decisions()
        self.assertEqual(
            "combat.blockers",
            engine.state.pending_decision.kind,
        )
        return attacker, blocker

    def test_contract_traces_every_cr_509_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "declare-blockers-step.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            "509",
            "509.1",
            "509.1a",
            "509.1b",
            "509.1c",
            "509.1d",
            "509.1e",
            "509.1f",
            "509.1g",
            "509.1h",
            "509.1i",
            "509.2",
            "509.2a",
            "509.3",
            "509.3a",
            "509.3b",
            "509.3c",
            "509.3d",
            "509.3e",
            "509.3f",
            "509.3g",
            "509.4",
            "509.4a",
            "509.4b",
        }
        self.assertEqual(expected, set(contract["rule_references"]))

    def test_ordinary_block_becomes_blocking_then_grants_priority(self):
        session = self.make_session(50901)
        attacker, blocker = self.set_up_blocker_decision(session)
        payload = session.packet("pilot:B", full=True)["decision"]["ctx"]
        self.assertEqual([attacker.ref], payload["legal_blocks"][blocker.ref])
        session.initial_checkpoint = checkpoint_envelope(session.state)

        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blk": {blocker.ref: attacker.ref},
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(session.state.combat.blockers_declared)
        self.assertEqual(
            [blocker.object_id],
            session.state.combat.blockers[attacker.object_id],
        )
        self.assertEqual(attacker.object_id, blocker.blocking)
        self.assertEqual("A", session.state.priority_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "declare-blockers"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_phased_or_tapped_creature_is_not_offered_as_blocker(self):
        session = self.make_session(50902)
        attacker, valid = self.set_up_blocker_decision(session)
        engine = session.engine
        phased = self.token(engine, "B", "Phased Blocker")
        tapped = self.token(
            engine,
            "B",
            "Tapped Blocker",
            tapped=True,
        )
        phased.phased_out = True
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.combat.blocker_cursor = 0
        engine._issue_next_blocker()

        legal = engine.state.pending_decision.payload_by_actor["B"][
            "legal_blocks"
        ]
        self.assertIn(valid.ref, legal)
        self.assertNotIn(phased.ref, legal)
        self.assertNotIn(tapped.ref, legal)
        self.assertEqual([attacker.ref], legal[valid.ref])

    def test_malicious_phased_block_rolls_back_valid_partial_block(self):
        session = self.make_session(50903)
        attacker, valid = self.set_up_blocker_decision(session)
        engine = session.engine
        phased = self.token(engine, "B", "Phased Blocker")
        phased.phased_out = True
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blk": {
                    valid.ref: attacker.ref,
                    phased.ref: attacker.ref,
                },
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("cannot block", result.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual({}, session.state.combat.blockers)
        restored = session.engine._resolve_object(
            "B",
            valid.ref,
            zones={"battlefield"},
        )
        self.assertIsNone(restored.blocking)

    def test_blocking_marker_clears_when_combat_phase_ends(self):
        session = self.make_session(50904)
        attacker, blocker = self.set_up_blocker_decision(session)
        result = session.act(
            "pilot:B",
            {
                "a": "block",
                "blk": {blocker.ref: attacker.ref},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(attacker.object_id, blocker.blocking)

        session.engine._finish_combat_phase()

        self.assertIsNone(blocker.blocking)
        self.assertIsNone(attacker.attacking)
        self.assertEqual(CombatState(), session.state.combat)


if __name__ == "__main__":
    unittest.main()
