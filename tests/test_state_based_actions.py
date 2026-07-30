from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim.carddb import CardRecord
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.model import DecisionGroup, StackItem
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.semantics import SemanticProgram
from mtg_commander_sim.state_based_actions import (
    ObjectSnapshot,
    PermanentSnapshot,
    counter_maximums_from_oracle,
    evaluate_state_based_actions,
    evaluate_permanent_state_based_actions,
)


class StateBasedActionPrimitiveTests(unittest.TestCase):
    def test_contract_is_pinned_to_the_current_rules_snapshot(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads(
            (root / "rules" / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "state-based-actions.json"
            ).read_text(encoding="utf-8")
        )
        registry = json.loads(
            (root / "mechanics" / "registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            manifest["source_sha256"], contract["source_sha256"]
        )
        self.assertEqual(
            manifest["effective_date"], contract["effective_date"]
        )
        self.assertIn("704.5q", contract["rule_references"])
        self.assertIn("704.5r", contract["rule_references"])
        self.assertIn("704.5v", contract["rule_references"])
        self.assertIn("704.5w", contract["rule_references"])
        self.assertIn("704.5x", contract["rule_references"])
        row = next(
            item
            for item in registry["mechanics"]
            if item["mechanic_id"]
            == "cr-704-state-based-actions"
        )
        self.assertEqual("partial", row["coverage_status"])
        self.assertEqual(
            "mechanics/contracts/state-based-actions.json",
            row["contract_path"],
        )
        for mechanic_id, filename, rule_id in (
            ("cr-120-damage", "damage.json", "120.3h"),
            ("cr-210-defense", "defense.json", "210.1"),
            ("cr-310-battles", "battles.json", "310.11b"),
        ):
            related = json.loads(
                (
                    root / "mechanics" / "contracts" / filename
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["source_sha256"],
                related["source_sha256"],
            )
            self.assertEqual(
                manifest["effective_date"],
                related["effective_date"],
            )
            self.assertIn(rule_id, related["rule_references"])
            registry_row = next(
                item
                for item in registry["mechanics"]
                if item["mechanic_id"] == mechanic_id
            )
            self.assertEqual("partial", registry_row["coverage_status"])
            self.assertEqual(
                f"mechanics/contracts/{filename}",
                registry_row["contract_path"],
            )

    def test_snapshot_distinguishes_put_into_graveyard_from_destroy(self):
        batch = evaluate_permanent_state_based_actions(
            [
                PermanentSnapshot(
                    "zero",
                    card_types=frozenset({"creature"}),
                    toughness=0,
                    indestructible=True,
                ),
                PermanentSnapshot(
                    "lethal",
                    card_types=frozenset({"creature"}),
                    toughness=3,
                    marked_damage=3,
                ),
                PermanentSnapshot(
                    "deathtouch",
                    card_types=frozenset({"creature"}),
                    toughness=10,
                    deathtouch_damage=True,
                ),
                PermanentSnapshot(
                    "indestructible",
                    card_types=frozenset({"creature"}),
                    toughness=2,
                    marked_damage=99,
                    indestructible=True,
                ),
                PermanentSnapshot(
                    "walker",
                    card_types=frozenset({"planeswalker"}),
                    loyalty=0,
                ),
            ]
        )
        self.assertEqual(("walker", "zero"), batch.put_in_graveyard)
        self.assertEqual(("deathtouch", "lethal"), batch.destroy)
        self.assertNotIn("indestructible", batch.destroy)

    def test_zero_defense_battle_waits_for_its_pending_trigger(self):
        batch = evaluate_permanent_state_based_actions(
            [
                PermanentSnapshot(
                    "defeated",
                    card_types=frozenset({"battle"}),
                    defense=0,
                ),
                PermanentSnapshot(
                    "trigger-pending",
                    card_types=frozenset({"battle"}),
                    defense=0,
                    battle_trigger_pending=True,
                ),
                PermanentSnapshot(
                    "defended",
                    card_types=frozenset({"battle"}),
                    defense=1,
                ),
            ]
        )

        self.assertEqual(("defeated",), batch.put_in_graveyard)

    def test_attachment_and_counter_actions_are_snapshot_based(self):
        batch = evaluate_permanent_state_based_actions(
            [
                PermanentSnapshot(
                    "aura",
                    card_types=frozenset({"enchantment"}),
                    subtypes=frozenset({"aura"}),
                    attached_to="land",
                    attachment_legal=False,
                ),
                PermanentSnapshot(
                    "equipment",
                    card_types=frozenset({"artifact"}),
                    subtypes=frozenset({"equipment"}),
                    attached_to="land",
                    attachment_legal=False,
                ),
                PermanentSnapshot(
                    "creature-equipment",
                    card_types=frozenset({"artifact", "creature"}),
                    subtypes=frozenset({"equipment"}),
                    toughness=2,
                    attached_to="creature",
                    attachment_legal=True,
                ),
                PermanentSnapshot(
                    "creature-aura",
                    card_types=frozenset({"creature", "enchantment"}),
                    subtypes=frozenset({"aura"}),
                    toughness=2,
                    attached_to="creature",
                    attachment_legal=True,
                ),
                PermanentSnapshot(
                    "counters",
                    card_types=frozenset({"creature"}),
                    toughness=4,
                    counters={"+1/+1": 3, "-1/-1": 2},
                ),
            ]
        )
        self.assertEqual(
            ("aura", "creature-aura"), batch.put_in_graveyard
        )
        self.assertEqual(
            ("creature-equipment", "equipment"), batch.detach
        )
        self.assertEqual(
            (("counters", 2),), batch.counter_pairs_to_remove
        )

    def test_counter_maximum_sentence_and_snapshot_action(self):
        self.assertEqual(
            {"dream": 7},
            counter_maximums_from_oracle(
                "Rasputin can't have more than seven dream "
                "counters on it."
            ),
        )
        self.assertEqual(
            {"+1/+1": 2},
            counter_maximums_from_oracle(
                "This creature can’t have more than 2 +1/+1 "
                "counters on it."
            ),
        )
        self.assertEqual(
            {},
            counter_maximums_from_oracle(
                "Remove up to seven dream counters from it."
            ),
        )

        batch = evaluate_permanent_state_based_actions(
            [
                PermanentSnapshot(
                    "rasputin",
                    counters={"dream": 9},
                    counter_maximums={"dream": 7},
                ),
                PermanentSnapshot(
                    "at-limit",
                    counters={"dream": 7},
                    counter_maximums={"dream": 7},
                ),
            ]
        )
        self.assertEqual(
            (("rasputin", "dream", 2),),
            batch.counter_maximums_to_remove,
        )

    def test_input_mutation_cannot_change_batch(self):
        values = [
            PermanentSnapshot(
                f"counter-{index}",
                card_types=frozenset({"creature"}),
                toughness=2,
                counters={
                    "+1/+1": index + 1,
                    "-1/-1": 1,
                    "charge": index,
                },
                counter_maximums={"charge": 3},
            )
            for index in range(20)
        ]
        expected = evaluate_permanent_state_based_actions(values)
        randomizer = random.Random(704)
        for _ in range(50):
            randomizer.shuffle(values)
            self.assertEqual(
                expected,
                evaluate_permanent_state_based_actions(values),
            )

    def test_nonbattlefield_tokens_cease_from_the_shared_snapshot(self):
        batch = evaluate_state_based_actions(
            permanents=[],
            objects=[
                ObjectSnapshot(
                    "grave-token",
                    zone="graveyard",
                    is_token=True,
                ),
                ObjectSnapshot(
                    "battlefield-token",
                    zone="battlefield",
                    is_token=True,
                ),
                ObjectSnapshot(
                    "ordinary-card",
                    zone="graveyard",
                ),
            ],
        )
        self.assertEqual(("grave-token",), batch.cease)

    def test_noncard_copies_cease_only_outside_their_valid_zones(self):
        batch = evaluate_state_based_actions(
            permanents=[],
            objects=[
                ObjectSnapshot(
                    "resolved-spell-copy",
                    zone="graveyard",
                    is_spell_copy=True,
                ),
                ObjectSnapshot(
                    "stack-spell-copy",
                    zone="stack",
                    is_spell_copy=True,
                ),
                ObjectSnapshot(
                    "exiled-card-copy",
                    zone="exile",
                    is_card_copy=True,
                ),
                ObjectSnapshot(
                    "stack-card-copy",
                    zone="stack",
                    is_card_copy=True,
                ),
                ObjectSnapshot(
                    "permanent-card-copy",
                    zone="battlefield",
                    is_card_copy=True,
                ),
            ],
        )
        self.assertEqual(
            ("exiled-card-copy", "resolved-spell-copy"),
            batch.cease,
        )

    def test_world_rule_keeps_only_the_unique_newest_world(self):
        batch = evaluate_permanent_state_based_actions(
            [
                PermanentSnapshot(
                    "old-world",
                    world=True,
                    world_timestamp=10,
                ),
                PermanentSnapshot(
                    "new-world",
                    world=True,
                    world_timestamp=20,
                ),
                PermanentSnapshot("ordinary"),
            ]
        )

        self.assertEqual(("old-world",), batch.world_rule)

    def test_tied_newest_world_permanents_all_leave_order_independently(
        self,
    ):
        values = [
            PermanentSnapshot(
                "world-b",
                world=True,
                world_timestamp=20,
            ),
            PermanentSnapshot(
                "world-a",
                world=True,
                world_timestamp=20,
            ),
            PermanentSnapshot(
                "older-world",
                world=True,
                world_timestamp=10,
            ),
        ]
        expected = ("older-world", "world-a", "world-b")

        self.assertEqual(
            expected,
            evaluate_permanent_state_based_actions(values).world_rule,
        )
        values.reverse()
        self.assertEqual(
            expected,
            evaluate_permanent_state_based_actions(values).world_rule,
        )

    def test_world_rule_requires_a_since_timestamp(self):
        with self.assertRaisesRegex(
            ValueError,
            "World permanent requires",
        ):
            evaluate_permanent_state_based_actions(
                [
                    PermanentSnapshot(
                        "missing-world-time",
                        world=True,
                    ),
                    PermanentSnapshot(
                        "other-world",
                        world=True,
                        world_timestamp=1,
                    ),
                ]
            )


class StateBasedActionEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_engine(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.priority_player = None
        return session.engine

    @staticmethod
    def card(engine, ref):
        return next(
            card for card in engine.state.cards.values() if card.ref == ref
        )

    @staticmethod
    def attach(attachment, target):
        attachment.attached_to = target.object_id
        target.attachments.append(attachment.object_id)

    def test_opposing_power_toughness_counters_cancel_in_pairs(self):
        engine = self.make_engine(7041)
        ref = engine.create_token(
            "A",
            name="Counter Bear",
            characteristics={
                "type_line": "Token Creature — Bear",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        creature = self.card(engine, ref)
        creature.counters.update({"+1/+1": 3, "-1/-1": 1})

        self.assertFalse(engine._stabilize())

        self.assertEqual(2, creature.counters["+1/+1"])
        self.assertNotIn("-1/-1", creature.counters)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "state.counters_annihilated"
        )
        self.assertEqual(
            [{"object": ref, "pairs_removed": 1}],
            event.details["changes"],
        )

    def test_battle_enters_with_printed_defense_and_copies_reset_it(self):
        engine = self.make_engine(7052)
        original_ref = engine.create_token(
            "A",
            name="Test Battle",
            characteristics={
                "type_line": "Token Battle",
                "defense": "4",
            },
        )[0]
        original = self.card(engine, original_ref)
        self.assertEqual(4, original.counters["defense"])
        engine._change_permanent_counter(original, "defense", -3)

        copied_ref = engine.create_token(
            "A",
            name="Test Battle Copy",
            copy_of=original.ref,
        )[0]
        copied = self.card(engine, copied_ref)

        self.assertEqual(1, original.counters["defense"])
        self.assertEqual(4, copied.counters["defense"])
        self.assertEqual(
            "4",
            engine._effective_card_data(copied)["defense"],
        )

    def test_battle_damage_removes_defense_instead_of_marking_damage(self):
        engine = self.make_engine(7053)
        source_ref = engine.create_token(
            "A",
            name="Battle Tester",
            characteristics={
                "type_line": "Token Creature — Wizard",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        battle_ref = engine.create_token(
            "B",
            name="Test Battle",
            characteristics={
                "type_line": "Token Battle",
                "defense": "5",
            },
        )[0]
        battle = self.card(engine, battle_ref)

        engine._apply_combat_assignments(
            [
                {
                    "source": source_ref,
                    "target": battle_ref,
                    "amount": 2,
                }
            ]
        )

        self.assertEqual(3, battle.counters["defense"])
        self.assertEqual(0, battle.marked_damage)

    def test_planeswalker_damage_removes_loyalty_counters(self):
        engine = self.make_engine(7061)
        walker_ref = engine.create_token(
            "A",
            name="Test Planeswalker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "4",
            },
        )[0]
        walker = self.card(engine, walker_ref)
        self.assertEqual(4, walker.counters["loyalty"])

        result = engine._apply_damage_results_to_permanent(
            walker,
            2,
        )

        self.assertEqual(2, result["loyalty_removed"])
        self.assertEqual(2, walker.counters["loyalty"])
        self.assertEqual(0, walker.marked_damage)

    def test_battle_trigger_from_same_incarnation_defers_state_action(self):
        engine = self.make_engine(7054)
        battle_ref = engine.create_token(
            "A",
            name="Triggered Battle",
            characteristics={
                "type_line": "Token Battle",
                "defense": "1",
            },
        )[0]
        battle = self.card(engine, battle_ref)
        trigger = StackItem(
            stack_id="battle-trigger",
            ref="S-battle-trigger",
            kind="triggered_ability",
            controller="A",
            label="Battle trigger",
            source_object_id=battle.object_id,
            visibility=["A", "B"],
            context={
                "source_logical_object_id": battle.logical_object_id,
            },
        )
        engine.state.stack.append(trigger)
        engine._change_permanent_counter(battle, "defense", -1)

        self.assertFalse(engine._stabilize())
        self.assertEqual("battlefield", battle.zone)

        engine.state.stack.remove(trigger)
        self.assertFalse(engine._stabilize())
        self.assertEqual("outside", battle.zone)

    def test_old_incarnation_trigger_does_not_defer_battle_state_action(self):
        engine = self.make_engine(7061)
        battle_ref = engine.create_token(
            "A",
            name="Reentered Battle",
            characteristics={
                "type_line": "Token Battle",
                "defense": "1",
            },
        )[0]
        battle = self.card(engine, battle_ref)
        engine.state.stack.append(
            StackItem(
                stack_id="old-battle-trigger",
                ref="S-old-battle-trigger",
                kind="triggered_ability",
                controller="A",
                label="Trigger from an old object incarnation",
                source_object_id=battle.object_id,
                visibility=["A", "B", "C", "D"],
                context={
                    "source_logical_object_id": "old-incarnation",
                },
            )
        )
        engine._change_permanent_counter(battle, "defense", -1)

        self.assertFalse(engine._battle_trigger_pending(battle))
        self.assertFalse(engine._stabilize())
        self.assertEqual("outside", battle.zone)

    def test_last_siege_defense_counter_queues_intrinsic_trigger(self):
        engine = self.make_engine(7055)
        siege_ref = engine.create_token(
            "A",
            name="Test Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "2",
            },
        )[0]
        siege = self.card(engine, siege_ref)
        engine.state.stack.append(
            StackItem(
                stack_id="other-siege-trigger",
                ref="S-other-siege-trigger",
                kind="triggered_ability",
                controller="A",
                label="Unrelated Siege trigger",
                source_object_id=siege.object_id,
                semantic_key="test:other-siege-trigger",
                visibility=["A", "B", "C", "D"],
                context={
                    "source_logical_object_id": (
                        siege.logical_object_id
                    )
                },
            )
        )

        result = engine._apply_damage_results_to_permanent(siege, 2)
        self.assertEqual(2, result["defense_removed"])
        self.assertFalse(engine._stabilize())

        trigger = next(
            item
            for item in engine.state.stack
            if item.semantic_key == "builtin:siege-defeated"
        )
        self.assertEqual(siege.object_id, trigger.source_object_id)
        self.assertEqual(
            siege.logical_object_id,
            trigger.context["source_logical_object_id"],
        )
        self.assertEqual("battlefield", siege.zone)
        engine._prepare_stack_resolution()
        self.assertEqual(
            "arbiter.resolve",
            engine.state.pending_decision.kind,
        )
        self.assertEqual(
            "builtin:siege-defeated",
            engine.state.pending_decision.payload_by_actor["arbiter"][
                "semantic_key"
            ],
        )

    def test_departed_combat_source_deals_no_damage(self):
        engine = self.make_engine(7062)
        source_ref = engine.create_token(
            "A",
            name="Departed Attacker",
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        source = self.card(engine, source_ref)
        engine.move_card(source.object_id, "graveyard")
        life_before = engine.state.players["B"].life

        engine._apply_combat_assignments(
            [
                {
                    "source": source_ref,
                    "target": "B",
                    "amount": 2,
                }
            ]
        )

        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual(
            "combat.damage.no_source",
            next(
                event
                for event in reversed(engine.state.events)
                if event.code == "combat.damage.no_source"
            ).code,
        )


    def test_invalid_siege_protector_is_repaired_by_its_controller(self):
        engine = self.make_engine(7057)
        siege_ref = engine.create_token(
            "A",
            name="Protector Test Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "3",
            },
        )[0]
        siege = self.card(engine, siege_ref)
        engine.state.players["B"].in_game = False

        self.assertTrue(engine._stabilize())
        self.assertEqual(
            "state.battle_protector",
            engine.state.pending_decision.kind,
        )
        payload = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual(["C", "D"], payload["protectors"])
        capability = next(
            value
            for value in engine.state.capabilities.values()
            if (
                value.decision_id
                == engine.state.pending_decision.decision_id
                and value.principal == "pilot:A"
                and not value.consumed
            )
        )

        result = engine.try_submit(
            token=capability.token,
            principal="pilot:A",
            action="choose",
            payload={"protector": "C"},
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("C", siege.battle_protector)
        projected = StateProjector(self.db, engine.state)._obj(
            siege,
            "pilot:A",
        )
        self.assertEqual("C", projected["protect"])
        self.assertNotIn("object_id", projected)
        self.assertNotIn("logical_object_id", projected)

    def test_battle_protector_choice_replays_exactly(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=7060,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        siege_ref = engine.create_token(
            "A",
            name="Replay Protector Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "3",
            },
        )[0]
        siege = self.card(engine, siege_ref)
        engine.state.players["B"].in_game = False
        self.assertTrue(engine._stabilize())
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choices": {"protector": "C"},
                "reason": "Choose a legal replacement protector.",
                "plan": "RULES_CHOICE",
            },
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("C", siege.battle_protector)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "battle-protector-record"
            session.save(record_dir)
            replay = replay_record(
                record_dir,
                self.db,
                verify=True,
            )
        self.assertTrue(replay["ok"], replay)

    def test_siege_is_attackable_and_its_protector_blocks(self):
        engine = self.make_engine(7058)
        attacker_ref = engine.create_token(
            "A",
            name="Siege Attacker",
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "1",
                "toughness": "1",
                "keywords": ["Haste"],
            },
        )[0]
        siege_ref = engine.create_token(
            "A",
            name="Attackable Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Battle — Siege",
                "defense": "3",
            },
        )[0]
        blocker_ref = engine.create_token(
            "B",
            name="Siege Blocker",
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine._complete_attackers(
            DecisionGroup(
                decision_id="attack-siege",
                kind="combat.attackers",
                role="pilot",
                actors=["A"],
                allowed_actions=["attack"],
                responses={
                    "A": {
                        "attackers": {
                            attacker_ref: siege_ref,
                        }
                    }
                },
            )
        )

        attacker = self.card(engine, attacker_ref)
        siege = self.card(engine, siege_ref)
        self.assertEqual(siege.ref, attacker.attacking)
        self.assertEqual(["B"], engine.state.combat.defending_players)
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine._issue_next_blocker()
        payload = engine.state.pending_decision.payload_by_actor["B"]
        self.assertIn(attacker_ref, payload["attackers"])
        self.assertEqual(
            [attacker_ref],
            payload["legal_blocks"][blocker_ref],
        )
        engine._complete_blockers(
            DecisionGroup(
                decision_id="block-siege",
                kind="combat.blockers",
                role="pilot",
                actors=["B"],
                allowed_actions=["block"],
                responses={
                    "B": {
                        "blocks": {
                            blocker_ref: attacker_ref,
                        }
                    }
                },
            )
        )
        self.assertEqual(
            [self.card(engine, blocker_ref).object_id],
            engine.state.combat.blockers[
                self.card(engine, attacker_ref).object_id
            ],
        )

    def test_battle_creature_cannot_attack_or_block(self):
        engine = self.make_engine(7063)
        battle_creature_ref = engine.create_token(
            "A",
            name="Animated Battle",
            characteristics={
                "type_line": "Token Battle Creature",
                "power": "3",
                "toughness": "3",
                "defense": "3",
                "keywords": ["Haste"],
            },
        )[0]
        attacker_ref = engine.create_token(
            "A",
            name="Ordinary Attacker",
            characteristics={
                "type_line": "Token Creature — Soldier",
                "power": "2",
                "toughness": "2",
                "keywords": ["Haste"],
            },
        )[0]
        battle_blocker_ref = engine.create_token(
            "B",
            name="Animated Blocking Battle",
            characteristics={
                "type_line": "Token Battle Creature",
                "power": "3",
                "toughness": "3",
                "defense": "3",
            },
        )[0]
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"

        engine._issue_attackers()
        candidates = engine.state.pending_decision.payload_by_actor["A"][
            "candidates"
        ]
        self.assertNotIn(
            battle_creature_ref,
            [candidate["id"] for candidate in candidates],
        )
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        with self.assertRaisesRegex(
            GameRuleError,
            "cannot attack because it is a Battle",
        ):
            engine._complete_attackers(
                DecisionGroup(
                    decision_id="illegal-battle-attack",
                    kind="combat.attackers",
                    role="pilot",
                    actors=["A"],
                    allowed_actions=["attack"],
                    responses={
                        "A": {
                            "attackers": {
                                battle_creature_ref: "B",
                            }
                        }
                    },
                )
            )

        engine._complete_attackers(
            DecisionGroup(
                decision_id="ordinary-attack",
                kind="combat.attackers",
                role="pilot",
                actors=["A"],
                allowed_actions=["attack"],
                responses={
                    "A": {
                        "attackers": {
                            attacker_ref: "B",
                        }
                    }
                },
            )
        )
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine._issue_next_blocker()
        blocker_payload = (
            engine.state.pending_decision.payload_by_actor["B"]
        )
        self.assertNotIn(
            battle_blocker_ref,
            blocker_payload["blockers"],
        )
        self.assertEqual(
            (False, "blocker_is_battle"),
            engine._can_block(
                self.card(engine, attacker_ref),
                self.card(engine, battle_blocker_ref),
            ),
        )

    def test_siege_protector_is_chosen_as_the_spell_resolves(self):
        engine = self.make_engine(7059)
        object_id = engine.state.players["A"].zones["hand"][0]
        card = engine.state.cards[object_id]
        original_card_record = engine.card_record
        siege_record = CardRecord(
            oracle_id=card.oracle_id,
            name="Invasion of Test // Test Victor",
            mana_cost="{1}",
            mana_value=1,
            type_line="Battle — Siege // Creature — Soldier",
            oracle_text="",
            power=None,
            toughness=None,
            loyalty=None,
            defense=None,
            colors=(),
            color_identity=(),
            keywords=(),
            produced_mana=(),
            layout="transform",
            released_at="2023-04-21",
            legalities={"commander": "legal"},
            faces=(
                {
                    "name": "Invasion of Test",
                    "mana_cost": "{1}",
                    "type_line": "Battle — Siege",
                    "oracle_text": "",
                    "power": None,
                    "toughness": None,
                    "loyalty": None,
                    "defense": "3",
                    "colors": [],
                },
                {
                    "name": "Test Victor",
                    "mana_cost": "",
                    "type_line": "Creature — Soldier",
                    "oracle_text": "",
                    "power": "3",
                    "toughness": "3",
                    "loyalty": None,
                    "defense": None,
                    "colors": [],
                },
            ),
            raw={},
        )

        def staged_record(value):
            candidate = (
                value
                if hasattr(value, "object_id")
                else engine.state.cards.get(str(value))
            )
            if (
                candidate is not None
                and candidate.object_id == card.object_id
            ):
                return siege_record
            return original_card_record(value)

        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"
        engine.state.players["A"].mana_pool["C"] = 1
        with patch.object(
            engine,
            "card_record",
            side_effect=staged_record,
        ):
            hints = engine._priority_action_hints("A")
            action = next(
                value
                for value in hints["actions"]
                if value["id"] == f"cast:{card.ref}"
            )
            self.assertNotIn("choice_schema", action)
            engine._cast(
                "A",
                {
                    "card": card.ref,
                    "from": "hand",
                    "auto_pay": True,
                },
            )
            self.assertEqual("stack", card.zone)
            self.assertEqual("Invasion of Test", card.active_face)
            self.assertIsNone(card.battle_protector)
            self.assertTrue(
                engine._begin_battle_entry_protector_choice(
                    engine.state.stack[-1]
                )
            )
            self.assertEqual(
                "battle.enter_protector",
                engine.state.pending_decision.kind,
            )
            self.assertEqual(
                ["B", "C", "D"],
                engine.state.pending_decision.payload_by_actor["A"][
                    "protectors"
                ],
            )
            capability = next(
                value
                for value in engine.state.capabilities.values()
                if (
                    value.decision_id
                    == engine.state.pending_decision.decision_id
                    and value.principal == "pilot:A"
                    and not value.consumed
                )
            )
            result = engine.try_submit(
                token=capability.token,
                principal="pilot:A",
                action="choose",
                payload={"protector": "B"},
            )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("battlefield", card.zone)
        self.assertEqual("B", card.battle_protector)
        self.assertEqual(3, card.counters["defense"])

    def test_battle_damage_and_state_action_replay_exactly(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=7056,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        battle_ref = engine.create_token(
            "B",
            name="Replay Battle",
            characteristics={
                "type_line": "Token Battle",
                "defense": "2",
            },
        )[0]
        battle = self.card(engine, battle_ref)
        program = SemanticProgram(
            key="test:defeat-battle",
            label="Deal two damage to a Battle",
            effects=[
                {
                    "op": "damage",
                    "target": battle.ref,
                    "amount": 2,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="defeat-battle",
                ref="S-defeat-battle",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in (
            "pilot:A",
            "pilot:B",
            "pilot:C",
            "pilot:D",
        ):
            result = session.act(
                principal,
                {
                    "action_id": "pass",
                    "reason": "Allow Battle damage to resolve.",
                    "plan": "HOLD",
                },
            )
            self.assertTrue(result.ok, result.summary)
        self.assertEqual("outside", battle.zone)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "battle-sba-record"
            session.save(record_dir)
            replay = replay_record(
                record_dir,
                self.db,
                verify=True,
            )
        self.assertTrue(replay["ok"], replay)

    def test_counter_maximum_overlaps_opposing_pair_removal(self):
        engine = self.make_engine(7050)
        ref = engine.create_token(
            "A",
            name="Counter-Limited Bear",
            characteristics={
                "type_line": "Token Creature — Bear",
                "oracle_text": (
                    "This creature can't have more than two +1/+1 "
                    "counters on it."
                ),
                "power": "2",
                "toughness": "2",
            },
        )[0]
        creature = self.card(engine, ref)
        creature.counters.update({"+1/+1": 10, "-1/-1": 4})

        self.assertFalse(engine._stabilize())

        self.assertEqual(2, creature.counters["+1/+1"])
        self.assertNotIn("-1/-1", creature.counters)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "state.counter_maximums"
        )
        self.assertEqual(
            [
                {
                    "object": ref,
                    "counter": "+1/+1",
                    "before": 10,
                    "maximum": 2,
                    "required_removal": 8,
                    "after": 2,
                }
            ],
            event.details["changes"],
        )

    def test_rasputin_counter_maximum_replays_exactly(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=7051,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        rasputin_ref = engine.create_token(
            "A",
            name="Rasputin Dreamweaver Copy",
            characteristics={
                "type_line": (
                    "Token Legendary Creature — Human Wizard"
                ),
                "oracle_text": (
                    "Rasputin can't have more than seven dream "
                    "counters on it."
                ),
                "power": "4",
                "toughness": "1",
            },
        )[0]
        rasputin = self.card(engine, rasputin_ref)
        rasputin.counters["dream"] = 7
        program = SemanticProgram(
            key="test:rasputin-counter-overflow",
            label="Put two dream counters on Rasputin",
            effects=[
                {
                    "op": "counter",
                    "card": rasputin_ref,
                    "counter": "dream",
                    "delta": 2,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="rasputin-counter-overflow",
                ref="S-rasputin-counter-overflow",
                kind="triggered",
                controller="A",
                label=program.label,
                source_object_id=rasputin.object_id,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in (
            "pilot:A",
            "pilot:B",
            "pilot:C",
            "pilot:D",
        ):
            result = session.act(
                principal,
                {
                    "action_id": "pass",
                    "reason": "Allow the test trigger to resolve.",
                    "plan": "HOLD",
                },
            )
            self.assertTrue(result.ok, result.summary)
        self.assertEqual(7, rasputin.counters["dream"])

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "counter-maximum-record"
            session.save(record_dir)
            replay = replay_record(
                record_dir,
                self.db,
                verify=True,
            )
        self.assertTrue(replay["ok"], replay)

    def test_unattached_and_illegally_attached_auras_leave(self):
        engine = self.make_engine(7042)
        land_ref = engine.create_token(
            "A",
            name="Test Land",
            characteristics={"type_line": "Token Land"},
        )[0]
        land = self.card(engine, land_ref)
        aura_ref = engine.create_token(
            "A",
            name="Creature Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": "Enchant creature",
            },
        )[0]
        aura = self.card(engine, aura_ref)
        self.attach(aura, land)
        unattached_ref = engine.create_token(
            "A",
            name="Unattached Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": "Enchant creature",
            },
        )[0]
        unattached = self.card(engine, unattached_ref)

        self.assertFalse(engine._stabilize())

        self.assertEqual("outside", aura.zone)
        self.assertEqual("outside", unattached.zone)
        self.assertNotIn(aura.object_id, land.attachments)

    def test_equipment_detaches_from_illegal_or_protected_object(self):
        engine = self.make_engine(7043)
        land_ref = engine.create_token(
            "A",
            name="Test Land",
            characteristics={"type_line": "Token Land"},
        )[0]
        red_equipment_ref = engine.create_token(
            "A",
            name="Red Equipment",
            characteristics={
                "type_line": "Token Artifact — Equipment",
                "colors": ["R"],
            },
        )[0]
        protected_ref = engine.create_token(
            "B",
            name="Protected Bear",
            characteristics={
                "type_line": "Token Creature — Bear",
                "oracle_text": "Protection from red",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        colorless_equipment_ref = engine.create_token(
            "A",
            name="Colorless Equipment",
            characteristics={
                "type_line": "Token Artifact — Equipment",
            },
        )[0]
        land = self.card(engine, land_ref)
        red_equipment = self.card(engine, red_equipment_ref)
        protected = self.card(engine, protected_ref)
        colorless_equipment = self.card(
            engine, colorless_equipment_ref
        )
        self.attach(red_equipment, protected)
        self.attach(colorless_equipment, land)

        self.assertFalse(engine._stabilize())

        self.assertEqual("battlefield", red_equipment.zone)
        self.assertIsNone(red_equipment.attached_to)
        self.assertIsNone(colorless_equipment.attached_to)
        self.assertNotIn(
            red_equipment.object_id, protected.attachments
        )
        self.assertNotIn(
            colorless_equipment.object_id, land.attachments
        )

    def test_fixed_point_moves_aura_after_enchanted_creature_dies(self):
        engine = self.make_engine(7044)
        creature_ref = engine.create_token(
            "A",
            name="Doomed Bear",
            characteristics={
                "type_line": "Token Creature — Bear",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        aura_ref = engine.create_token(
            "A",
            name="Creature Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": "Enchant creature",
            },
        )[0]
        creature = self.card(engine, creature_ref)
        aura = self.card(engine, aura_ref)
        self.attach(aura, creature)
        creature.marked_damage = 2

        self.assertFalse(engine._stabilize())

        self.assertEqual("outside", creature.zone)
        self.assertEqual("outside", aura.zone)
        state_events = [
            event
            for event in engine.state.events
            if event.code == "state.creatures_died"
        ]
        self.assertGreaterEqual(len(state_events), 2)
        self.assertEqual(
            [creature_ref], state_events[-2].details["destroyed"]
        )
        self.assertEqual(
            [aura_ref],
            state_events[-1].details["put_in_graveyard"],
        )

    def test_simultaneous_move_captures_all_lki_before_mutation(self):
        engine = self.make_engine(7045)
        source_ref = engine.create_token(
            "A",
            name="Static Source",
            characteristics={
                "type_line": "Token Creature — Wizard",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        recipient_ref = engine.create_token(
            "A",
            name="Static Recipient",
            characteristics={
                "type_line": "Token Creature — Bear",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        source = self.card(engine, source_ref)
        recipient = self.card(engine, recipient_ref)
        effective_card_data = engine._effective_card_data
        captured: dict[str, dict] = {}

        def derived_data(card):
            data = effective_card_data(card)
            if (
                card.object_id == recipient.object_id
                and source.zone == "battlefield"
            ):
                data["power"] = "9"
            return data

        def capture(card, **kwargs):
            captured[card.ref] = kwargs["origin_data"]

        with (
            patch.object(
                engine,
                "_effective_card_data",
                side_effect=derived_data,
            ),
            patch.object(
                engine,
                "_dispatch_zone_change_events",
                side_effect=capture,
            ),
        ):
            engine._move_cards_simultaneously(
                [
                    (source.object_id, "graveyard"),
                    (recipient.object_id, "graveyard"),
                ],
                reason="state-based action",
            )

        self.assertEqual("9", captured[recipient_ref]["power"])

    def test_unrecognized_enchant_suffix_is_not_prefix_matched(self):
        engine = self.make_engine(7046)
        aura_ref = engine.create_token(
            "A",
            name="Unsupported Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": (
                    "Enchant creature with flying or a Vehicle you control"
                ),
            },
        )[0]
        aura = self.card(engine, aura_ref)
        self.assertIsNone(engine._enchant_target_schema(aura))

    @staticmethod
    def stage_as_world(engine, card):
        engine._remove_from_zone(card)
        engine._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = card.owner
        card.annotations["copy_overrides"] = {
            "type_line": "World Enchantment",
        }

    def test_new_world_moves_the_older_world_to_graveyard(self):
        engine = self.make_engine(7047)
        object_ids = list(
            engine.state.players["A"].zones["library"][:2]
        )
        old_world, new_world = [
            engine.state.cards[object_id] for object_id in object_ids
        ]
        self.stage_as_world(engine, old_world)
        engine.move_card(
            old_world.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertFalse(engine._stabilize())

        self.stage_as_world(engine, new_world)
        engine.move_card(
            new_world.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertLess(
            old_world.world_supertype_timestamp,
            new_world.world_supertype_timestamp,
        )
        self.assertFalse(engine._stabilize())

        self.assertEqual("graveyard", old_world.zone)
        self.assertEqual("battlefield", new_world.zone)
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "state.world_rule"
        )
        self.assertEqual(
            [old_world.ref],
            [item["object"] for item in event.details["moved"]],
        )
        self.assertEqual([new_world.ref], event.details["survivors"])

    def test_worlds_entering_simultaneously_are_tied_and_all_leave(self):
        engine = self.make_engine(7048)
        object_ids = list(
            engine.state.players["A"].zones["library"][:2]
        )
        worlds = [
            engine.state.cards[object_id] for object_id in object_ids
        ]
        for card in worlds:
            self.stage_as_world(engine, card)

        engine._move_cards_simultaneously(
            [
                (card.object_id, "battlefield")
                for card in worlds
            ],
            reason="simultaneous World entry",
            log=False,
        )

        self.assertEqual(
            1, len({card.zone_timestamp for card in worlds})
        )
        self.assertEqual(
            1,
            len(
                {
                    card.world_supertype_timestamp
                    for card in worlds
                }
            ),
        )
        self.assertFalse(engine._stabilize())
        self.assertEqual(
            {"graveyard"},
            {card.zone for card in worlds},
        )
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "state.world_rule"
        )
        self.assertEqual([], event.details["survivors"])

    def test_losing_and_regaining_world_gets_a_new_since_time(self):
        engine = self.make_engine(7049)
        card = engine.state.cards[
            engine.state.players["A"].zones["library"][0]
        ]
        engine.move_card(
            card.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        card.annotations["copy_overrides"] = {
            "type_line": "World Enchantment",
        }
        self.assertFalse(engine._stabilize())
        first = card.world_supertype_timestamp
        self.assertIsNotNone(first)

        card.annotations.pop("copy_overrides")
        self.assertFalse(engine._stabilize())
        self.assertIsNone(card.world_supertype_timestamp)

        card.annotations["copy_overrides"] = {
            "type_line": "World Enchantment",
        }
        self.assertFalse(engine._stabilize())
        self.assertGreater(card.world_supertype_timestamp, first)


if __name__ == "__main__":
    unittest.main()
