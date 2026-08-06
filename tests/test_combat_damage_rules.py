from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.combat_damage_engine_adapter import (
    EngineCombatDamageQuery,
)
from mtg_commander_sim.combat_damage_snapshot import (
    CombatDamageSnapshotError,
)
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.semantics import SemanticProgram


class CombatDamageRuleTests(unittest.TestCase):
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

    def test_unblocked_attacker_damages_planeswalker_loyalty(self):
        session = self.make_session(51018)
        engine = session.engine
        attacker = self.token(engine, "A", "Walker Attacker", 3)
        walker_ref = engine.create_token(
            "B",
            name="Damage Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "5",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )
        attacker.attacking = walker.ref
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: walker.ref},
            attack_target_context={
                attacker.object_id: {
                    "target": walker.ref,
                    "kind": "planeswalker",
                    "defending_player": "B",
                }
            },
            defending_players=["B"],
        )

        engine._begin_combat_damage()

        self.assertEqual(2, walker.counters["loyalty"])
        damage = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "combat.damage"
        )
        self.assertEqual(walker.ref, damage.details["assignments"][0]["target"])

    def test_lethal_planeswalker_combat_damage_applies_state_action(self):
        session = self.make_session(51019)
        engine = session.engine
        attacker = self.token(engine, "A", "Lethal Walker Attacker", 4)
        walker_ref = engine.create_token(
            "B",
            name="Lethal Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "3",
            },
        )[0]
        walker = engine._resolve_object(
            "A", walker_ref, zones={"battlefield"}
        )
        attacker.attacking = walker.ref
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: walker.ref},
            attack_target_context={
                attacker.object_id: {
                    "target": walker.ref,
                    "kind": "planeswalker",
                    "defending_player": "B",
                }
            },
            defending_players=["B"],
        )

        engine._begin_combat_damage()

        self.assertEqual("outside", walker.zone)

    def test_unblocked_attacker_damages_battle_defense(self):
        session = self.make_session(51020, players=3)
        engine = session.engine
        attacker = self.token(engine, "A", "Battle Attacker", 2)
        battle_ref = engine.create_token(
            "C",
            name="Damage Battle",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "5",
            },
        )[0]
        battle = engine._resolve_object(
            "A", battle_ref, zones={"battlefield"}
        )
        attacker.attacking = battle.ref
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: battle.ref},
            attack_target_context={
                attacker.object_id: {
                    "target": battle.ref,
                    "kind": "battle",
                    "defending_player": "B",
                }
            },
            defending_players=["B"],
        )

        engine._begin_combat_damage()

        self.assertEqual(3, battle.counters["defense"])

    def test_multiplayer_assignment_contract_traces_cr_802_5(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "multiplayer-combat-damage-order.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual({"802.5"}, set(contract["rule_references"]))

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
        self.assertEqual(3, attacker.marked_damage)
        self.assertEqual(1, first.marked_damage)
        self.assertEqual(3, second.marked_damage)
        self.assertEqual("A", session.state.priority_player)
        announcements = [
            event
            for event in session.state.events
            if event.code == "combat.damage.assigned"
        ]
        self.assertEqual(["A", "B"], [event.actor for event in announcements])
        self.assertEqual(
            [False, True],
            [event.details["automatic"] for event in announcements],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-damage"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

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

        self.assertIsNone(
            session.packet("pilot:B", full=True)["decision"]
        )
        damage_b = session.engine._combat_damage_source_options("B")
        self.assertEqual(
            {attacker.ref}, set(damage_b[first.ref]["targets"])
        )
        self.assertEqual(
            {attacker.ref}, set(damage_b[second.ref]["targets"])
        )

    def test_discretionary_assignments_are_collected_in_apnap_order_and_replay(
        self,
    ):
        session = self.make_session(51012)
        engine = session.engine
        first_attacker = self.token(engine, "A", "First Attacker", 2)
        second_attacker = self.token(engine, "A", "Second Attacker", 2)
        first_blocker = self.token(engine, "B", "First Multi-Blocker", 2)
        second_blocker = self.token(engine, "B", "Second Multi-Blocker", 2)
        for attacker in (first_attacker, second_attacker):
            attacker.attacking = "B"
        first_blocker.blocking = first_attacker.object_id
        second_blocker.blocking = second_attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={
                first_attacker.object_id: "B",
                second_attacker.object_id: "B",
            },
            defending_players=["B"],
            # Effects such as banding can produce relationships the ordinary
            # declaration UI does not yet create. The damage step must still
            # honor a legal authoritative combat state.
            blockers={
                first_attacker.object_id: [
                    first_blocker.object_id,
                    second_blocker.object_id,
                ],
                second_attacker.object_id: [
                    first_blocker.object_id,
                    second_blocker.object_id,
                ],
            },
        )
        engine._begin_combat_damage()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        self.assertEqual(["A"], engine.state.pending_decision.actors)
        self.assertIsNone(session.packet("pilot:B", full=True)["decision"])
        assignments_a = [
            {
                "source": first_attacker.ref,
                "target": first_blocker.ref,
                "amount": 2,
            },
            {
                "source": second_attacker.ref,
                "target": second_blocker.ref,
                "amount": 2,
            },
        ]
        result_a = session.act(
            "pilot:A",
            {"a": "dmg", "assignments": assignments_a},
        )
        self.assertTrue(result_a.ok, result_a.summary)
        self.assertEqual(["B"], engine.state.pending_decision.actors)
        self.assertEqual(0, first_blocker.marked_damage)

        packet_b = session.packet("pilot:B", full=True)
        combat = packet_b["decision"]["legal_actions"][0]["form"][
            "fields"
        ][0]["combat"]
        self.assertEqual(assignments_a, combat["announced_assignments"])
        before_b = authoritative_state_hash(session.state)
        rejected_b = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": first_blocker.ref,
                        "target": first_attacker.ref,
                        "amount": 3,
                    },
                    {
                        "source": second_blocker.ref,
                        "target": second_attacker.ref,
                        "amount": 2,
                    },
                ],
            },
        )
        self.assertFalse(rejected_b.ok)
        self.assertEqual(before_b, authoritative_state_hash(session.state))
        self.assertEqual(
            ["A"],
            [
                event.actor
                for event in engine.state.events
                if event.code == "combat.damage.assigned"
            ],
        )
        result_b = session.act(
            "pilot:B",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": first_blocker.ref,
                        "target": first_attacker.ref,
                        "amount": 2,
                    },
                    {
                        "source": second_blocker.ref,
                        "target": second_attacker.ref,
                        "amount": 2,
                    },
                ],
            },
        )
        self.assertTrue(result_b.ok, result_b.summary)
        self.assertEqual(
            2,
            engine._resolve_object(
                "B", first_blocker.ref, zones={"battlefield"}
            ).marked_damage,
        )
        self.assertEqual(
            2,
            engine._resolve_object(
                "B", second_blocker.ref, zones={"battlefield"}
            ).marked_damage,
        )
        announcements = [
            event
            for event in engine.state.events
            if event.code == "combat.damage.assigned"
        ]
        self.assertEqual(["A", "B"], [event.actor for event in announcements])
        self.assertEqual(
            [0, 1],
            [event.details["announcement_index"] for event in announcements],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-apnap-assignments"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_multiplayer_assignment_announcements_follow_apnap(self):
        session = self.make_session(51014, players=4)
        engine = session.engine
        attacker = self.token(engine, "A", "Multiplayer Attacker", 2)
        blocker = self.token(engine, "C", "Multiplayer Blocker", 2)
        attacker.attacking = "C"
        blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "C"},
            defending_players=["C"],
            blockers={attacker.object_id: [blocker.object_id]},
        )

        engine._begin_combat_damage()

        announcements = [
            event
            for event in engine.state.events
            if event.code == "combat.damage.assigned"
        ]
        self.assertEqual(["A", "C"], [event.actor for event in announcements])
        self.assertEqual(
            [0, 1],
            [event.details["announcement_index"] for event in announcements],
        )
        self.assertEqual(2, attacker.marked_damage)
        self.assertEqual(2, blocker.marked_damage)

    def test_damage_and_resulting_death_triggers_share_one_order_batch(
        self,
    ):
        session = self.make_session(51013)
        engine = session.engine
        engine.state.active_player = "B"
        monitor = self.token(engine, "A", "Damage Monitor", 0)
        witness_ref = engine.create_token(
            "A",
            name="Dying Witness",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        witness = engine._resolve_object(
            "A", witness_ref, zones={"battlefield"}
        )
        attacker_ref = engine.create_token(
            "B",
            name="Damage Source",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        attacker = engine._resolve_object(
            "B", attacker_ref, zones={"battlefield"}
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{monitor.oracle_id}:test:damage-dealt",
                label="Damage was dealt trigger",
                oracle_id=monitor.oracle_id,
                ability_id="test:damage-dealt",
                active_zone="battlefield",
                event="damage.dealt",
                event_condition={
                    "field": "source_controller",
                    "op": "eq",
                    "value": "B",
                },
                effects=[],
            )
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{witness.oracle_id}:test:self-dies",
                label="Witness died trigger",
                oracle_id=witness.oracle_id,
                ability_id="test:self-dies",
                active_zone="battlefield",
                event="creature.dies.self",
                effects=[],
            )
        )
        attacker.attacking = "A"
        witness.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "A"},
            defending_players=["A"],
            blockers={attacker.object_id: [witness.object_id]},
        )

        engine._begin_combat_damage()

        self.assertEqual("outside", witness.zone)
        self.assertFalse(engine.state.stack)
        self.assertIsNone(engine.state.priority_player)
        self.assertEqual("trigger.order", engine.state.pending_decision.kind)
        self.assertEqual(1, len(engine.state.pending_trigger_batches))
        packet = session.packet("pilot:A", full=True)
        by_label = {
            item["label"]: item["id"]
            for item in packet["decision"]["ctx"]["triggers"]
        }
        self.assertEqual(
            {"Damage was dealt trigger", "Witness died trigger"},
            set(by_label),
        )
        damage_item = next(
            item
            for group in engine.state.pending_trigger_batches[0]["groups"]
            for item in group["items"]
            if item["label"] == "Damage was dealt trigger"
        )
        self.assertEqual(2, damage_item["context"]["amount"])
        self.assertEqual(witness.ref, damage_item["context"]["target"])
        self.assertTrue(damage_item["context"]["combat"])

        session.initial_checkpoint = checkpoint_envelope(session.state)
        result = session.act(
            "pilot:A",
            {
                "action_id": "order",
                "triggers": [
                    by_label["Damage was dealt trigger"],
                    by_label["Witness died trigger"],
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            ["Damage was dealt trigger", "Witness died trigger"],
            [item.label for item in engine.state.stack],
        )
        self.assertEqual("B", engine.state.priority_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "post-damage-trigger-batch"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_assignment_above_power_is_rejected_atomically(self):
        session = self.make_session(51002)
        attacker, first, second = self.set_up_multiblock(session)
        before = authoritative_state_hash(session.state)
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
        self.assertFalse(result_a.ok)
        self.assertIn("exactly 4", result_a.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual(0, attacker.marked_damage)
        self.assertEqual(0, first.marked_damage)

    def test_noncombat_source_is_rejected(self):
        session = self.make_session(51003)
        attacker, first, second = self.set_up_multiblock(session)
        bystander = self.token(session.engine, "A", "Bystander", 10)
        result = session.act(
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
        result = session.act(
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

        self.assertFalse(result.ok)
        self.assertIn("illegal combat-damage target", result.summary)

    def test_assignment_rejects_client_supplied_semantic_fields(self):
        session = self.make_session(51006)
        attacker, first, second = self.set_up_multiblock(session)
        result = session.act(
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

        self.assertFalse(result.ok)
        self.assertIn(
            "requires exactly source, target, and amount",
            result.summary,
        )

    def test_nonpositive_source_cannot_submit_zero_assignment(self):
        session = self.make_session(51007)
        attacker, first, second = self.set_up_multiblock(session)
        attacker.annotations["copy_overrides"]["power"] = "0"
        result = session.act(
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

    def test_damage_step_identity_is_stable_and_distinguishes_extra_combats(
        self,
    ):
        session = self.make_session(51015)
        engine = session.engine

        engine.state.phase_index = TURN_STEPS.index(
            ("combat", "beginning_combat")
        )
        engine._enter_step()
        engine._initialize_combat_damage_steps()
        first = EngineCombatDamageQuery(engine).damage_step_identity()
        serialized = engine.state.combat.to_dict()
        self.assertEqual(
            serialized,
            CombatState.from_dict(serialized).to_dict(),
        )
        engine.state.combat.damage_step_index = 1
        second_step = EngineCombatDamageQuery(engine).damage_step_identity()

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine._enter_step()
        engine._initialize_combat_damage_steps()
        extra_combat = EngineCombatDamageQuery(engine).damage_step_identity()

        self.assertNotEqual(first, second_step)
        self.assertNotEqual(first, extra_combat)
        self.assertEqual(
            first.rsplit(":step:", 1)[0],
            second_step.rsplit(":step:", 1)[0],
        )
        self.assertNotIn("damage_sequence_id", CombatState().to_dict())

    def test_malformed_snapshot_fails_before_a_damage_decision(self):
        session = self.make_session(51016)
        engine = session.engine
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={"missing-attacker": "B"},
            defending_players=["B"],
        )

        with self.assertRaises(CombatDamageSnapshotError):
            engine._begin_combat_damage()

        self.assertIsNone(engine.state.pending_decision)
        self.assertEqual([], engine.state.combat.damage_assignments)

    def test_departing_attacker_preserves_blocker_without_damage_assignment(self):
        session = self.make_session(51017)
        engine = session.engine
        attacker = self.token(engine, "A", "Departing Attacker", 2)
        blocker = self.token(engine, "B", "Former Blocker", 2)
        attacker.attacking = "B"
        blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
            blockers={attacker.object_id: [blocker.object_id]},
        )

        engine.move_card(attacker.object_id, "graveyard")

        self.assertEqual(attacker.object_id, blocker.blocking)
        self.assertNotIn(attacker.object_id, engine.state.combat.attackers)
        self.assertEqual(
            [blocker.object_id],
            engine.state.combat.blockers[attacker.object_id],
        )
        self.assertEqual(
            (),
            EngineCombatDamageQuery(engine).participant_object_ids(),
        )
        engine._begin_combat_damage()
        self.assertEqual([], engine.state.combat.damage_assignments)


if __name__ == "__main__":
    unittest.main()
