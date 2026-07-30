from __future__ import annotations

import json
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim.state_based_actions import (
    ObjectSnapshot,
    PermanentSnapshot,
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

    def test_input_mutation_cannot_change_batch(self):
        values = [
            PermanentSnapshot(
                f"counter-{index}",
                card_types=frozenset({"creature"}),
                toughness=2,
                counters={"+1/+1": index + 1, "-1/-1": 1},
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


if __name__ == "__main__":
    unittest.main()
