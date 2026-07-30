from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import StackItem
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

        first = session.act(
            "pilot:A",
            {
                "action_id": "pass",
                "reason": "Pass priority on the test trigger.",
                "plan": "HOLD",
            },
        )
        self.assertTrue(first.ok, first.summary)
        second = session.act(
            "pilot:B",
            {
                "action_id": "pass",
                "reason": "Allow the test trigger to resolve.",
                "plan": "HOLD",
            },
        )
        self.assertTrue(second.ok, second.summary)
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
