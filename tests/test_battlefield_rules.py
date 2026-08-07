from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.ability_fragments import ability_fragment_to_dict
from quorune.aura import SimpleEnchantSpec
from quorune.engine import (
    GameRuleError,
    StateInvariantError,
)
from quorune.targets import TargetGroup


class BattlefieldRuleTests(unittest.TestCase):
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
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine.state.priority_player = None
        return session

    @staticmethod
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    def test_contract_traces_every_cr_403_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "battlefield.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "403",
                "403.1",
                "403.2",
                "403.3",
                "403.4",
                "403.5",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("403")
            },
        )

    def test_battlefield_starts_empty_and_is_one_shared_target_domain(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=40301,
            auto_pass_empty=False,
        )
        engine = session.engine
        self.assertTrue(
            all(
                not player.zones["battlefield"]
                for player in engine.state.players.values()
            )
        )

        ring = self.card(engine, "A", "Sol Ring")
        elves = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.move_card(
            elves.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        group = TargetGroup.from_mapping(
            {
                "categories": ["permanent"],
                "count": 1,
            }
        )

        candidates = engine._target_candidates("C", group)
        self.assertIn(ring.ref, candidates)
        self.assertIn(elves.ref, candidates)
        self.assertEqual(
            {
                card.ref
                for card in engine.state.cards.values()
                if card.zone == "battlefield"
            },
            set(candidates),
        )

    def test_controller_index_and_cross_controller_attachment_are_preserved(self):
        session = self.make_session(40302, players=4)
        engine = session.engine
        creature = self.card(engine, "B", "Elves of Deep Shadow")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        aura_ref = engine.create_token(
            "A",
            name="Shared Battlefield Aura",
            characteristics={
                "type_line": "Token Enchantment — Aura",
                "oracle_text": "Enchant creature",
                "ability_fragments": [
                    ability_fragment_to_dict(SimpleEnchantSpec("creature"))
                ],
            },
            aura_target_ref=creature.ref,
        )[0]
        aura = engine._resolve_object(
            "A",
            aura_ref,
            zones={"battlefield"},
        )
        engine._assert_invariants()
        packet = session.packet("pilot:C", full=True)
        aura_view = next(
            item
            for item in packet["state"]["players"]["A"]["bf"]
            if item["id"] == aura.ref
        )
        self.assertEqual(creature.ref, aura_view["at"])
        self.assertIn(
            creature.ref,
            {
                item["id"]
                for item in packet["state"]["players"]["B"]["bf"]
            },
        )

        engine.state.players["A"].zones["battlefield"].remove(
            aura.object_id
        )
        engine.state.players["B"].zones["battlefield"].append(
            aura.object_id
        )
        with self.assertRaisesRegex(
            StateInvariantError,
            "indexed under B but controlled by A",
        ):
            engine._assert_invariants()

    def test_unqualified_effect_and_target_scope_default_to_battlefield(self):
        session = self.make_session(40303)
        engine = session.engine
        ring = self.card(engine, "A", "Sol Ring")
        top = self.card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.move_card(top.object_id, "hand", log=False)
        default_group = TargetGroup.from_mapping(
            {
                "categories": ["permanent"],
                "artifact": True,
                "count": 1,
            }
        )

        candidates = engine._target_candidates("B", default_group)
        self.assertIn(ring.ref, candidates)
        self.assertNotIn(top.ref, candidates)
        with self.assertRaisesRegex(GameRuleError, "requested zones"):
            engine.apply_effect(
                {
                    "op": "destroy",
                    "card": top.ref,
                    "reason": "unqualified CR 403.2 witness",
                },
                actor="B",
            )
        self.assertEqual("hand", top.zone)

        engine.apply_effect(
            {
                "op": "move",
                "card": top.ref,
                "destination": "graveyard",
                "reason": "explicit nonbattlefield-zone witness",
            },
            actor="B",
        )
        graveyard_group = TargetGroup.from_mapping(
            {
                "zones": ["graveyard"],
                "categories": ["card"],
                "artifact": True,
                "count": 1,
            }
        )
        self.assertIn(
            top.ref,
            engine._target_candidates("B", graveyard_group),
        )

    def test_permanent_category_exists_only_on_the_battlefield(self):
        session = self.make_session(40304)
        engine = session.engine
        ring = self.card(engine, "A", "Sol Ring")
        permanent_group = TargetGroup.from_mapping(
            {
                "categories": ["permanent"],
                "artifact": True,
                "count": 1,
            }
        )
        card_group = TargetGroup.from_mapping(
            {
                "zones": ["graveyard"],
                "categories": ["card"],
                "artifact": True,
                "count": 1,
            }
        )

        engine.move_card(ring.object_id, "graveyard", log=False)
        self.assertNotIn(
            ring.ref,
            engine._target_candidates("B", permanent_group),
        )
        self.assertIn(
            ring.ref,
            engine._target_candidates("B", card_group),
        )

        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertIn(
            ring.ref,
            engine._target_candidates("B", permanent_group),
        )
        self.assertNotIn(
            ring.ref,
            engine._target_candidates("B", card_group),
        )

        force = self.card(engine, "B", "Force of Vigor")
        origin = force.zone
        engine.move_card(
            force.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        self.assertEqual(origin, force.zone)
        self.assertNotIn(
            force.ref,
            engine._target_candidates("A", permanent_group),
        )

    def test_battlefield_entry_allocates_a_new_incarnation_except_400_7a(self):
        session = self.make_session(40305)
        engine = session.engine
        ring = self.card(engine, "A", "Sol Ring")
        before = ring.logical_object_id
        ring.counters["stale"] = 1

        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertNotEqual(before, ring.logical_object_id)
        self.assertEqual({}, ring.counters)

        engine.move_card(ring.object_id, "graveyard", log=False)
        prior_permanent = ring.logical_object_id
        ring.annotations["stale"] = True
        engine.move_card(
            ring.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertNotEqual(prior_permanent, ring.logical_object_id)
        self.assertNotIn("stale", ring.annotations)

        top = self.card(engine, "A", "Sensei's Divining Top")
        engine._remove_from_zone(top)
        engine._reset_zone_change(top, "stack")
        top.zone = "stack"
        top.controller = "A"
        stack_incarnation = top.logical_object_id
        engine.move_card(
            top.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.assertEqual(stack_incarnation, top.logical_object_id)

    def test_pinned_oracle_data_uses_battlefield_not_legacy_in_play_terms(
        self,
    ):
        fixture = (
            Path(__file__).resolve().parent
            / "fixtures"
            / "scryfall-exact-lists.json"
        )
        cards = json.loads(
            fixture.read_text(encoding="utf-8")
        )["cards"]
        legacy = re.compile(
            r"\b(?:in play|from play|into play)\b",
            re.IGNORECASE,
        )

        self.assertFalse(
            [
                card["name"]
                for card in cards
                if legacy.search(str(card.get("oracle_text") or ""))
            ]
        )


if __name__ == "__main__":
    unittest.main()
