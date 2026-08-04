from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.ability_fragments import ability_fragment_to_dict
from mtg_commander_sim.aura import SimpleEnchantSpec
from mtg_commander_sim.engine import GameRuleError, TURN_STEPS
from mtg_commander_sim.model import CombatState, DecisionGroup
from mtg_commander_sim.record import checkpoint_envelope, replay_record


class CombatPhaseRuleTests(unittest.TestCase):
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
    def enter_step(session, step: str) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(("combat", step))
        engine._enter_step()

    @staticmethod
    def token(
        engine,
        controller: str,
        name: str,
        *,
        haste: bool = False,
    ):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "2",
                "toughness": "2",
            },
            temporary_keywords=(["Haste"] if haste else []),
        )[0]
        return next(
            card
            for card in engine.state.cards.values()
            if card.ref == ref
        )

    def test_contract_traces_every_cr_506_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "combat-phase.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            "506",
            "506.1",
            "506.2",
            "506.2a",
            "506.2b",
            "506.3",
            "506.3a",
            "506.3b",
            "506.3c",
            "506.3d",
            "506.3e",
            "506.3f",
            "506.3g",
            "506.4",
            "506.4a",
            "506.4b",
            "506.4c",
            "506.4d",
            "506.4e",
            "506.5",
            "506.6",
            "506.7",
            "506.7a",
            "506.7b",
            "506.7c",
            "506.7d",
            "506.7e",
            "506.7f",
            "506.7g",
        }
        self.assertEqual(expected, set(contract["rule_references"]))

    def test_empty_combat_step_sequence_and_replay_are_exact(self):
        session = self.make_session(50601)
        engine = session.engine

        self.enter_step(session, "beginning_combat")
        engine.pump()
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for _ in range(3):
            for seat in ("A", "B"):
                result = session.act(
                    f"pilot:{seat}",
                    {
                        "a": "pass",
                        "reason": "Pass the represented combat boundary.",
                    },
                )
                self.assertTrue(result.ok, result.summary)

        self.assertEqual(
            ("postcombat_main", "main"),
            (engine.state.phase, engine.state.step),
        )
        combat_steps = [
            event.summary.split("combat/", 1)[1].rstrip(".")
            for event in engine.state.events
            if event.code == "step.begin"
            and "combat/" in event.summary
        ]
        self.assertEqual(
            ["beginning_combat", "declare_attackers", "end_combat"],
            combat_steps[-3:],
        )
        self.assertNotIn("declare_blockers", combat_steps[-3:])
        self.assertNotIn("combat_damage", combat_steps[-3:])

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-phase"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(6, replay["commands"])

    def test_supported_attacking_and_defending_roles_are_authoritative(
        self,
    ):
        session = self.make_session(50602, players=4)
        engine = session.engine
        active = self.token(
            engine,
            "A",
            "Active Attacker",
            haste=True,
        )
        nonactive = self.token(
            engine,
            "B",
            "Nonactive Creature",
            haste=True,
        )

        self.enter_step(session, "beginning_combat")
        self.assertEqual(["B", "C", "D"], engine.state.combat.defending_players)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        self.enter_step(session, "declare_attackers")
        payload = engine.state.pending_decision.payload_by_actor["A"]

        self.assertEqual(
            {active.ref},
            {candidate["id"] for candidate in payload["candidates"]},
        )
        self.assertEqual(
            {"B", "C", "D"},
            set(payload["defenders"]),
        )
        with self.assertRaisesRegex(GameRuleError, "Could not find"):
            engine._complete_attackers(
                DecisionGroup(
                    decision_id="cr506-wrong-attacker",
                    kind="combat.attackers",
                    role="pilot",
                    actors=["A"],
                    allowed_actions=["attack"],
                    responses={
                        "A": {
                            "attackers": {
                                nonactive.ref: "C",
                            }
                        }
                    },
                )
            )

    def test_zone_and_control_changes_remove_objects_from_combat(
        self,
    ):
        session = self.make_session(50603, players=4)
        engine = session.engine
        attacker_one = self.token(engine, "A", "Attacker One")
        attacker_two = self.token(engine, "A", "Attacker Two")
        blocker_one = self.token(engine, "B", "Blocker One")
        blocker_two = self.token(engine, "B", "Blocker Two")
        attacker_one.attacking = "B"
        attacker_two.attacking = "B"
        blocker_one.blocking = attacker_one.object_id
        blocker_two.blocking = attacker_two.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers={
                attacker_one.object_id: "B",
                attacker_two.object_id: "B",
            },
            defending_players=["B", "C", "D"],
            blockers={
                attacker_one.object_id: [blocker_one.object_id],
                attacker_two.object_id: [blocker_two.object_id],
            },
        )

        engine.move_card(
            attacker_one.object_id,
            "graveyard",
            reason="CR 506 zone-change witness",
        )
        self.assertNotIn(
            attacker_one.object_id,
            engine.state.combat.attackers,
        )
        self.assertIsNone(attacker_one.attacking)
        self.assertEqual(
            attacker_one.object_id,
            blocker_one.blocking,
        )

        engine.change_control(
            attacker_two.object_id,
            "C",
            reason="CR 506 control-change witness",
        )
        self.assertNotIn(
            attacker_two.object_id,
            engine.state.combat.attackers,
        )
        self.assertIsNone(attacker_two.attacking)
        self.assertEqual(
            attacker_two.object_id,
            blocker_two.blocking,
        )

        engine.change_control(
            blocker_two.object_id,
            "C",
            reason="CR 506 blocker control-change witness",
        )
        self.assertIsNone(blocker_two.blocking)
        self.assertNotIn(
            blocker_two.object_id,
            engine.state.combat.blockers[attacker_two.object_id],
        )

    def test_postdeclaration_restriction_does_not_remove_attacker(self):
        session = self.make_session(50607)
        engine = session.engine
        attacker = self.token(engine, "A", "Already Attacking", haste=True)
        attacker.attacking = "B"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "B"},
            attack_target_context={
                attacker.object_id: {
                    "target": "B",
                    "kind": "player",
                    "defending_player": "B",
                }
            },
            defending_players=["B"],
        )
        aura_ref = engine.create_token(
            "B",
            name="Late Restraint",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": (
                    "Enchant creature\n"
                    "Enchanted creature can't attack."
                ),
                "ability_fragments": [
                    ability_fragment_to_dict(SimpleEnchantSpec("creature"))
                ],
            },
            aura_target_ref=attacker.ref,
        )[0]
        aura = engine._resolve_object(
            "A", aura_ref, zones={"battlefield"}
        )
        self.assertFalse(engine._stabilize())

        self.assertEqual("B", attacker.attacking)
        self.assertEqual(
            "B", engine.state.combat.attackers[attacker.object_id]
        )

    def test_phasing_and_type_loss_remove_combatants_during_stabilization(
        self,
    ):
        session = self.make_session(50604)
        engine = session.engine
        attacker = self.token(engine, "A", "Phasing Attacker")
        blocker = self.token(engine, "B", "Dormant Blocker")
        attacker.attacking = "B"
        blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
            blockers={attacker.object_id: [blocker.object_id]},
        )
        attacker.phased_out = True
        blocker.annotations["copy_overrides"] = {
            "name": "Dormant Blocker",
            "type_line": "Artifact",
        }

        self.assertFalse(engine._stabilize())

        self.assertIsNone(attacker.attacking)
        self.assertIsNone(blocker.blocking)
        self.assertFalse(engine.state.combat.attackers)
        self.assertEqual(
            [],
            engine.state.combat.blockers[attacker.object_id],
        )

    def test_tapping_and_untapping_do_not_remove_a_creature_from_combat(
        self,
    ):
        session = self.make_session(50605)
        engine = session.engine
        attacker = self.token(engine, "A", "Tapped Attacker")
        attacker.attacking = "B"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
        )

        attacker.tapped = True
        self.assertFalse(engine._remove_invalid_combat_objects())
        self.assertEqual("B", attacker.attacking)
        self.assertIn(attacker.object_id, engine.state.combat.attackers)

        attacker.tapped = False
        self.assertFalse(engine._remove_invalid_combat_objects())
        self.assertEqual("B", attacker.attacking)
        self.assertIn(attacker.object_id, engine.state.combat.attackers)


if __name__ == "__main__":
    unittest.main()
