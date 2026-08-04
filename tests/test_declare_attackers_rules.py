from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session, pass_current
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.tap_state import TapStateError, tap_declared_attackers
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class DeclareAttackersRuleTests(unittest.TestCase):
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
        engine.state.phase_index = 5
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine.state.combat = CombatState()
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def token(
        engine,
        name: str,
        *,
        tapped: bool = False,
        keywords: tuple[str, ...] = ("Haste",),
        type_line: str = "Token Creature — Test",
        oracle_text: str = "",
    ):
        characteristics = {
            "type_line": type_line,
            "oracle_text": oracle_text,
            "power": "2",
            "toughness": "2",
        }
        if "battle" in type_line.casefold():
            characteristics["defense"] = "3"
        ref = engine.create_token(
            "A",
            name=name,
            tapped=tapped,
            battle_protector=(
                "B" if "battle" in type_line.casefold() else None
            ),
            characteristics=characteristics,
            temporary_keywords=keywords,
        )[0]
        return engine._resolve_object(
            "A",
            ref,
            zones={"battlefield"},
        )

    def test_contract_traces_every_cr_508_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "declare-attackers-step.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            "508",
            "508.1",
            "508.1a",
            "508.1b",
            "508.1c",
            "508.1d",
            "508.1e",
            "508.1f",
            "508.1g",
            "508.1h",
            "508.1i",
            "508.1j",
            "508.1k",
            "508.1m",
            "508.2",
            "508.2a",
            "508.2b",
            "508.3",
            "508.3a",
            "508.3b",
            "508.3c",
            "508.3d",
            "508.3e",
            "508.3f",
            "508.4",
            "508.4a",
            "508.4b",
            "508.4c",
            "508.4d",
            "508.5",
            "508.5a",
            "508.6",
            "508.7",
            "508.7a",
            "508.7b",
            "508.7c",
            "508.7d",
            "508.7e",
            "508.8",
        }
        self.assertEqual(expected, set(contract["rule_references"]))

    def test_only_currently_eligible_creatures_are_offered(self):
        session = self.make_session(50801)
        engine = session.engine
        eligible = self.token(engine, "Eligible Attacker")
        tapped = self.token(engine, "Tapped Attacker", tapped=True)
        phased = self.token(engine, "Phased Attacker")
        phased.phased_out = True
        sick = self.token(
            engine,
            "Summoning-Sick Attacker",
            keywords=(),
        )
        battle = self.token(
            engine,
            "Animated Battle",
            type_line="Token Battle Creature",
        )

        engine._issue_attackers()

        candidates = {
            row["id"]
            for row in engine.state.pending_decision.payload_by_actor[
                "A"
            ]["candidates"]
        }
        self.assertEqual({eligible.ref}, candidates)
        self.assertNotIn(tapped.ref, candidates)
        self.assertNotIn(phased.ref, candidates)
        self.assertNotIn(sick.ref, candidates)
        self.assertNotIn(battle.ref, candidates)

    def test_attackers_tap_except_vigilance_then_active_player_gets_priority(self):
        session = self.make_session(50802)
        engine = session.engine
        ordinary = self.token(engine, "Ordinary Attacker")
        vigilant = self.token(
            engine,
            "Vigilant Attacker",
            keywords=("Haste", "Vigilance"),
        )
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {
                    ordinary.ref: "B",
                    vigilant.ref: "B",
                },
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(ordinary.tapped)
        self.assertFalse(vigilant.tapped)
        self.assertEqual("B", ordinary.attacking)
        self.assertEqual("B", vigilant.attacking)
        self.assertEqual(["B"], engine.state.combat.defending_players)
        self.assertEqual("A", engine.state.priority_player)
        self.assertFalse(
            any(
                row["incorrectly_suppressed"]
                for row in session.state.action_opportunities
            )
        )
        self.assertEqual(
            0,
            sum(
                int(
                    player.stats.get(
                        "decision_optimization", {}
                    ).get("suppressed_meaningful_windows", 0)
                )
                for player in session.state.players.values()
            ),
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "declare-attackers"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_vigilance_tap_owner_uses_current_effective_keywords(self):
        session = self.make_session(50821)
        engine = session.engine
        ordinary = self.token(engine, "Ordinary Tap Witness")
        vigilant = self.token(
            engine,
            "Vigilance Tap Witness",
            keywords=("Haste", "Vigilance", "Vigilance"),
        )

        tapped = tap_declared_attackers(engine, (ordinary, vigilant))

        self.assertEqual([ordinary.ref], tapped)
        self.assertTrue(ordinary.tapped)
        self.assertFalse(vigilant.tapped)

    def test_vigilance_tap_owner_fails_closed_before_batch_mutation(self):
        session = self.make_session(50822)
        engine = session.engine
        ordinary = self.token(engine, "Rollback Tap Witness")
        malformed = self.token(engine, "Malformed Tap Witness")
        malformed.zone = "graveyard"

        with self.assertRaisesRegex(TapStateError, "battlefield"):
            tap_declared_attackers(engine, (ordinary, malformed))

        self.assertFalse(ordinary.tapped)

    def test_vigilance_is_defender_independent_in_four_player_combat(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=50823,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase_index = 5
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine.state.combat = CombatState()
        attackers = [
            self.token(
                engine,
                f"Vigilance Attacker {defender}",
                keywords=("Haste", "Vigilance"),
            )
            for defender in ("B", "C", "D")
        ]
        engine._issue_attackers()

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {
                    card.ref: defender
                    for card, defender in zip(
                        attackers, ("B", "C", "D"), strict=True
                    )
                },
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertTrue(all(not card.tapped for card in attackers))
        self.assertEqual(
            ["B", "C", "D"],
            engine.state.combat.defending_players,
        )

    def test_attack_requirement_is_projected_maximized_and_replayed(self):
        session = self.make_session(50809)
        engine = session.engine
        required = self.token(
            engine,
            "Required Attacker",
            oracle_text=(
                "Required Attacker attacks each combat if able."
            ),
        )
        optional = self.token(engine, "Optional Attacker")
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(1, constraints["maximum_requirements"])
        self.assertEqual(
            required.ref,
            constraints["requirements"][0]["variable"],
        )
        before = authoritative_state_hash(session.state)
        rejected = session.act("pilot:A", {"a": "attack", "atk": {}})
        self.assertFalse(rejected.ok)
        self.assertIn("possible 1 requirements", rejected.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {
                    required.ref: "B",
                    optional.ref: "B",
                },
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            "B",
            session.engine._resolve_object(
                "A", required.ref, zones={"battlefield"}
            ).attacking,
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "attack-requirement"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_malicious_phased_attacker_rolls_back_valid_partial_attack(self):
        session = self.make_session(50803)
        engine = session.engine
        valid = self.token(engine, "Valid Attacker")
        phased = self.token(engine, "Phased Attacker")
        phased.phased_out = True
        engine._issue_attackers()
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {
                    valid.ref: "B",
                    phased.ref: "B",
                },
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("phased out", result.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        restored = session.engine._resolve_object(
            "A",
            valid.ref,
            zones={"battlefield"},
        )
        self.assertFalse(restored.tapped)
        self.assertIsNone(restored.attacking)
        self.assertEqual({}, session.state.combat.attackers)

    def test_phased_out_battle_is_not_an_attack_target(self):
        session = self.make_session(50804)
        engine = session.engine
        attacker = self.token(engine, "Battle Attacker")
        battle_ref = engine.create_token(
            "A",
            name="Phased Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "3",
            },
        )[0]
        battle = engine._resolve_object(
            "A",
            battle_ref,
            zones={"battlefield"},
        )
        battle.phased_out = True
        engine._issue_attackers()
        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertNotIn(battle.ref, payload["defenders"])

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: battle.ref},
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("Invalid attack defender", result.summary)

    def test_planeswalker_is_labeled_attackable_and_replays_exactly(self):
        session = self.make_session(50809)
        engine = session.engine
        attacker = self.token(engine, "Planeswalker Attacker")
        walker_ref = engine.create_token(
            "B",
            name="Defending Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "4",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertIn(walker.ref, payload["defenders"])
        self.assertEqual(
            [
                {
                    "id": walker.ref,
                    "name": "Defending Walker",
                    "controller": "B",
                    "loyalty": 4,
                }
            ],
            payload["planeswalker_defenders"],
        )
        result = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: walker.ref}},
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(walker.ref, attacker.attacking)
        self.assertEqual(
            {
                "target": walker.ref,
                "kind": "planeswalker",
                "defending_player": "B",
            },
            engine.state.combat.attack_target_context[attacker.object_id],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "planeswalker-attack"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_departed_planeswalker_keeps_defender_but_not_damage_target(self):
        session = self.make_session(50810)
        engine = session.engine
        attacker = self.token(engine, "Persistent Attacker")
        blocker_ref = engine.create_token(
            "B",
            name="Late Blocker",
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        blocker = engine._resolve_object(
            "A", blocker_ref, zones={"battlefield"}
        )
        walker_ref = engine.create_token(
            "B",
            name="Departing Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "4",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )
        engine._issue_attackers()
        result = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: walker.ref}},
        )
        self.assertTrue(result.ok, result.summary)

        engine.move_card(
            walker.object_id,
            "graveyard",
            reason="attacked planeswalker left combat",
        )
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.phase_index = TURN_STEPS.index(
            ("combat", "declare_blockers")
        )
        engine.state.phase = "combat"
        engine.state.step = "declare_blockers"
        engine._issue_next_blocker()

        self.assertEqual(["B"], engine.state.pending_decision.actors)
        problem = engine._block_declaration_problem("B")
        self.assertEqual((attacker.ref,), problem.domains[blocker.ref])
        self.assertEqual(
            [],
            engine._combat_damage_source_options("A")[attacker.ref][
                "targets"
            ],
        )

    def test_duplicate_structured_attacker_is_rejected(self):
        session = self.make_session(50805)
        engine = session.engine
        attacker = self.token(engine, "Duplicate Attacker")
        engine._issue_attackers()
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "attacks": [
                    {"attacker": attacker.ref, "defender": "B"},
                    {"attacker": attacker.ref, "defender": "B"},
                ],
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("declared twice", result.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

    def test_no_attackers_skips_blockers_and_combat_damage_steps(self):
        session = self.make_session(50806)
        engine = session.engine
        engine._issue_attackers()
        self.assertTrue(engine.state.combat.attackers_declared)
        self.assertEqual("A", engine.state.priority_player)
        self.assertIsNotNone(session.next_task())
        session.initial_checkpoint = checkpoint_envelope(session.state)

        while (
            (
                engine.state.phase,
                engine.state.step,
            ) == ("combat", "declare_attackers")
            and session.pending_principals()
        ):
            pass_current(session)

        self.assertEqual(("combat", "end_combat"), (
            engine.state.phase,
            engine.state.step,
        ))
        skipped = {
            (event.phase, event.step)
            for event in engine.state.events
            if event.code == "step.begin"
            and event.event_id > 0
            and event.phase == "combat"
            and event.step in {"declare_blockers", "combat_damage"}
        }
        self.assertEqual(set(), skipped)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "no-attackers"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertGreaterEqual(replay["commands"], 1)

        departed_session = self.make_session(50808)
        departed_engine = departed_session.engine
        departed = self.token(
            departed_engine,
            "Departing Attacker",
        )
        departed_engine._issue_attackers()
        attack_result = departed_session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {departed.ref: "B"},
            },
        )
        self.assertTrue(attack_result.ok, attack_result.summary)
        departed_engine.move_card(
            departed.object_id,
            "graveyard",
            reason="CR 508.8 departure witness",
        )
        departed_engine.permissions.invalidate_current()
        departed_engine.state.pending_decision = None
        departed_engine.state.priority_player = None
        departed_engine._advance_step()

        self.assertEqual(
            ("combat", "declare_blockers"),
            (
                departed_engine.state.phase,
                departed_engine.state.step,
            ),
        )
        self.assertTrue(
            departed_engine.state.combat.blockers_declared
        )
        self.assertEqual("A", departed_engine.state.priority_player)

    def test_attacking_marker_clears_when_combat_phase_ends(self):
        session = self.make_session(50807)
        engine = session.engine
        attacker = self.token(engine, "Marker Attacker")
        engine._issue_attackers()
        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {attacker.ref: "B"},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("B", attacker.attacking)

        engine._finish_combat_phase()

        self.assertIsNone(attacker.attacking)
        self.assertEqual(CombatState(), engine.state.combat)


if __name__ == "__main__":
    unittest.main()
