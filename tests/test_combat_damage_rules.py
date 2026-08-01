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


class CombatDamageRuleTests(unittest.TestCase):
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
        engine.state.step = "combat_damage"
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def token(engine, controller: str, name: str, power: int):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": str(power),
                "toughness": "20",
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    def set_up_multiblock(self, session):
        engine = session.engine
        attacker = self.token(engine, "A", "CR 510 Attacker", 4)
        first = self.token(engine, "B", "CR 510 First Blocker", 2)
        second = self.token(engine, "B", "CR 510 Second Blocker", 1)
        attacker.attacking = "B"
        first.blocking = attacker.object_id
        second.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
            blockers={
                attacker.object_id: [
                    first.object_id,
                    second.object_id,
                ]
            },
        )
        engine._begin_combat_damage()
        return attacker, first, second

    @staticmethod
    def blocker_assignments(attacker, first, second):
        return [
            {
                "source": first.ref,
                "target": attacker.ref,
                "amount": 2,
            },
            {
                "source": second.ref,
                "target": attacker.ref,
                "amount": 1,
            },
        ]

    def test_contract_traces_every_cr_510_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "combat-damage-step.json"
            ).read_text(encoding="utf-8")
        )
        expected = {
            "510",
            "510.1",
            "510.1a",
            "510.1b",
            "510.1c",
            "510.1d",
            "510.1e",
            "510.2",
            "510.3",
            "510.3a",
            "510.4",
        }
        self.assertEqual(expected, set(contract["rule_references"]))

    def test_multiblocker_assignment_deals_all_damage_simultaneously(self):
        session = self.make_session(51001)
        attacker, first, second = self.set_up_multiblock(session)
        session.initial_checkpoint = checkpoint_envelope(session.state)

        result_a = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": attacker.ref,
                        "target": first.ref,
                        "amount": 1,
                    },
                    {
                        "source": attacker.ref,
                        "target": second.ref,
                        "amount": 3,
                    },
                ],
            },
        )
        self.assertTrue(result_a.ok, result_a.summary)
        self.assertEqual(0, first.marked_damage)
        self.assertEqual(0, second.marked_damage)

        result_b = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )
        self.assertTrue(result_b.ok, result_b.summary)
        self.assertEqual(3, attacker.marked_damage)
        self.assertEqual(1, first.marked_damage)
        self.assertEqual(3, second.marked_damage)
        self.assertEqual("A", session.state.priority_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-damage"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_projected_damage_form_uses_authoritative_source_options(self):
        session = self.make_session(51011)
        attacker, first, second = self.set_up_multiblock(session)

        packet_a = session.packet("pilot:A", full=True)
        form_a = packet_a["decision"]["legal_actions"][0]["form"]
        damage_a = form_a["fields"][0]["combat"]["damage_sources"]
        self.assertEqual(4, damage_a[attacker.ref]["power"])
        self.assertEqual(
            sorted([first.ref, second.ref]),
            damage_a[attacker.ref]["targets"],
        )

        packet_b = session.packet("pilot:B", full=True)
        form_b = packet_b["decision"]["legal_actions"][0]["form"]
        damage_b = form_b["fields"][0]["combat"]["damage_sources"]
        self.assertEqual(
            {attacker.ref}, set(damage_b[first.ref]["targets"])
        )
        self.assertEqual(
            {attacker.ref}, set(damage_b[second.ref]["targets"])
        )

    def test_assignment_above_power_is_rejected_atomically(self):
        session = self.make_session(51002)
        attacker, first, second = self.set_up_multiblock(session)
        result_a = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": attacker.ref,
                        "target": first.ref,
                        "amount": 5,
                    }
                ],
            },
        )
        self.assertTrue(result_a.ok, result_a.summary)
        before = authoritative_state_hash(session.state)

        result_b = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )

        self.assertFalse(result_b.ok)
        self.assertIn("exactly 4", result_b.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual(0, attacker.marked_damage)
        self.assertEqual(0, first.marked_damage)

    def test_noncombat_source_is_rejected(self):
        session = self.make_session(51003)
        attacker, first, second = self.set_up_multiblock(session)
        bystander = self.token(session.engine, "A", "Bystander", 10)
        session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": bystander.ref,
                        "target": first.ref,
                        "amount": 10,
                    },
                    {
                        "source": attacker.ref,
                        "target": second.ref,
                        "amount": 4,
                    },
                ],
            },
        )

        result = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("not assigning combat damage", result.summary)

    def test_attacker_cannot_assign_damage_to_unrelated_target(self):
        session = self.make_session(51004)
        attacker, first, second = self.set_up_multiblock(session)
        unrelated = self.token(
            session.engine,
            "B",
            "Unrelated Target",
            0,
        )
        session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": attacker.ref,
                        "target": unrelated.ref,
                        "amount": 4,
                    }
                ],
            },
        )

        result = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("illegal combat-damage target", result.summary)

    def test_assignment_rejects_client_supplied_semantic_fields(self):
        session = self.make_session(51006)
        attacker, first, second = self.set_up_multiblock(session)
        session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": attacker.ref,
                        "target": first.ref,
                        "amount": 4,
                        "deathtouch": True,
                    }
                ],
            },
        )

        result = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )

        self.assertFalse(result.ok)
        self.assertIn(
            "requires exactly source, target, and amount",
            result.summary,
        )

    def test_nonpositive_source_cannot_submit_zero_assignment(self):
        session = self.make_session(51007)
        attacker, first, second = self.set_up_multiblock(session)
        attacker.annotations["copy_overrides"]["power"] = "0"
        session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": attacker.ref,
                        "target": first.ref,
                        "amount": 0,
                    }
                ],
            },
        )

        result = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": self.blocker_assignments(
                    attacker,
                    first,
                    second,
                ),
            },
        )

        self.assertFalse(result.ok)
        self.assertIn("power is 0 or less", result.summary)

    def test_blocked_attacker_assigns_nothing_after_blocker_leaves(self):
        session = self.make_session(51008)
        engine = session.engine
        attacker = self.token(engine, "A", "Blocked Attacker", 4)
        blocker = self.token(engine, "B", "Departing Blocker", 2)
        attacker.attacking = "B"
        blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
            blockers={attacker.object_id: [blocker.object_id]},
        )
        engine.move_card(blocker.object_id, "graveyard")
        life_before = engine.state.players["B"].life

        engine._begin_combat_damage()

        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual([], engine.state.combat.damage_assignments)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.damage"
        )
        self.assertEqual([], event.details["declared_assignments"])

    def test_first_strike_creates_the_initial_combat_damage_step(self):
        session = self.make_session(51005)
        engine = session.engine
        ref = engine.create_token(
            "A",
            name="First-Strike Witness",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
                "keywords": ["First strike"],
            },
        )[0]
        attacker = engine._resolve_object(
            "A",
            ref,
            zones={"battlefield"},
        )
        attacker.attacking = "B"
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
        )
        life_before = engine.state.players["B"].life

        engine._begin_combat_damage()

        self.assertTrue(engine.state.combat.first_strike_step)
        self.assertEqual(0, engine.state.combat.damage_step_index)
        self.assertEqual(life_before - 2, engine.state.players["B"].life)
        self.assertIsNone(engine.state.pending_decision)


if __name__ == "__main__":
    unittest.main()
