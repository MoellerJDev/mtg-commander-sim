from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import StateInvariantError
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import authoritative_state_hash


class GraveyardRuleTests(unittest.TestCase):
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
        session.engine.state.priority_passes = []
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

    def stage_spell(
        self,
        engine,
        owner: str,
        name: str,
        *,
        ref: str,
    ) -> StackItem:
        card = self.card(engine, owner, name)
        engine._remove_from_zone(card)
        engine._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = owner
        card.known_to = list(engine.seats)
        card.revealed_to = list(engine.seats)
        item = StackItem(
            stack_id=engine._stable_runtime_id("stack", ref),
            ref=ref,
            kind="spell",
            controller=owner,
            label=name,
            card_object_id=card.object_id,
            default_destination=(
                "battlefield"
                if self.db.lookup(name).is_permanent_spell
                else "graveyard"
            ),
            visibility=list(engine.seats),
            context={"dynamic_effects": []},
        )
        engine.state.stack.append(item)
        return item

    def test_contract_traces_every_cr_404_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "graveyard.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"404", "404.1", "404.2", "404.3"},
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("404")
            },
        )

    def test_graveyards_start_empty_and_common_causes_use_owner_top(self):
        session = self.make_session(40401, players=4)
        engine = session.engine
        self.assertTrue(
            all(
                not player.zones["graveyard"]
                for player in engine.state.players.values()
            )
        )

        destroyed = self.card(engine, "A", "Sol Ring")
        engine.move_card(
            destroyed.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        engine.apply_effect(
            {
                "op": "destroy",
                "card": destroyed.ref,
                "reason": "CR 404.1 destroy witness",
            },
            actor="B",
        )

        discarded = self.card(engine, "A", "Lightning Greaves")
        engine.move_card(discarded.object_id, "hand", log=False)
        engine.apply_effect(
            {
                "op": "discard",
                "card": discarded.ref,
                "reason": "CR 404.1 discard witness",
            },
            actor="A",
        )

        sacrificed = self.card(engine, "A", "Panharmonicon")
        engine.move_card(
            sacrificed.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.apply_effect(
            {
                "op": "sacrifice",
                "card": sacrificed.ref,
                "reason": "CR 404.1 sacrifice witness",
            },
            actor="A",
        )

        countered_item = self.stage_spell(
            engine,
            "A",
            "Sensei's Divining Top",
            ref="S-404-countered",
        )
        countered = engine.state.cards[countered_item.card_object_id]
        engine._counter_stack_item(
            countered_item.ref,
            reason="CR 404.1 counter witness",
            countered_by="B",
        )

        resolved_item = self.stage_spell(
            engine,
            "A",
            "Chaos Warp",
            ref="S-404-resolved",
        )
        resolved = engine.state.cards[resolved_item.card_object_id]
        engine._begin_resolve_item(
            resolved_item,
            [],
            "graveyard",
            note="CR 404.1 instant resolution witness",
        )

        self.assertEqual(
            [
                destroyed.object_id,
                discarded.object_id,
                sacrificed.object_id,
                countered.object_id,
                resolved.object_id,
            ],
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertTrue(
            all(
                card.zone == "graveyard"
                and card.owner == "A"
                and card.controller == "A"
                for card in (
                    destroyed,
                    discarded,
                    sacrificed,
                    countered,
                    resolved,
                )
            )
        )
        self.assertNotIn(
            destroyed.object_id,
            engine.state.players["B"].zones["graveyard"],
        )

    def test_rules_countered_permanent_spell_uses_graveyard_not_resolution_destination(
        self,
    ):
        session = self.make_session(40402)
        engine = session.engine
        aura = self.card(engine, "B", "Animate Dead")
        creature = self.card(engine, "A", "Goblin Engineer")
        engine.move_card(creature.object_id, "graveyard", log=False)

        item = self.stage_spell(
            engine,
            "B",
            "Animate Dead",
            ref="S-404-aura",
        )
        program = engine.semantics.get(
            f"{aura.oracle_id}:spell:front"
        )
        self.assertIsNotNone(program)
        selected, grouped = engine._validate_semantic_targets(
            "B",
            program,
            [creature.ref],
            source_ref=item.ref,
        )
        item.semantic_key = program.key
        item.targets = selected
        item.context.update(
            {
                "target_groups": grouped,
                "target_snapshots": {
                    creature.ref: engine._target_snapshot(creature.ref)
                },
                "targets_revalidated": False,
            }
        )

        engine.move_card(
            creature.object_id,
            "hand",
            reason="remove the only Aura target",
            log=False,
        )
        engine._prepare_stack_resolution()

        self.assertEqual("graveyard", aura.zone)
        self.assertIn(
            aura.object_id,
            engine.state.players["B"].zones["graveyard"],
        )
        self.assertNotIn(
            aura.object_id,
            engine.state.players["B"].zones["battlefield"],
        )
        counter_event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "stack.counter"
            and event.details.get("stack") == item.ref
        )
        self.assertEqual("rules", counter_event.details["counter_kind"])
        self.assertEqual(
            "graveyard",
            counter_event.details["destination"],
        )

    def test_graveyard_is_face_up_public_ordered_and_not_reordered_by_same_zone_move(
        self,
    ):
        session = self.make_session(40403, players=4)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")
        first.face_down = True
        first.known_to = ["A"]
        first.revealed_to = []

        engine.move_card(first.object_id, "graveyard", log=False)
        engine.move_card(second.object_id, "graveyard", log=False)
        before_hash = authoritative_state_hash(engine.state)
        engine.move_card(first.object_id, "graveyard", log=False)

        self.assertEqual(before_hash, authoritative_state_hash(engine.state))
        self.assertFalse(first.face_down)
        self.assertEqual(list(engine.seats), first.known_to)
        self.assertEqual(list(engine.seats), first.revealed_to)
        packet = session.packet("pilot:D", full=True)
        graveyard = packet["state"]["players"]["A"]["gy"]
        self.assertEqual(
            [first.ref, second.ref],
            [item["id"] for item in graveyard],
        )
        self.assertEqual(
            [first.printed_name, second.printed_name],
            [item["n"] for item in graveyard],
        )

    def test_graveyard_owner_index_is_an_authoritative_invariant(self):
        session = self.make_session(40404)
        engine = session.engine
        card = self.card(engine, "A", "Sol Ring")
        engine.move_card(card.object_id, "graveyard", log=False)
        engine.state.players["A"].zones["graveyard"].remove(
            card.object_id
        )
        engine.state.players["B"].zones["graveyard"].append(
            card.object_id
        )

        with self.assertRaisesRegex(
            StateInvariantError,
            "indexed under B but owned by A",
        ):
            engine._assert_invariants()

    def test_graveyard_replacement_is_decided_before_the_move(self):
        session = self.make_session(40405)
        engine = session.engine
        voidwalker = self.card(engine, "B", "Dauthi Voidwalker")
        engine.move_card(
            voidwalker.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        opponent_card = self.card(
            engine,
            "A",
            "Goblin Engineer",
        )

        engine.move_card(
            opponent_card.object_id,
            "graveyard",
            reason="CR 404/614 replacement witness",
            log=False,
        )

        self.assertEqual("exile", opponent_card.zone)
        self.assertNotIn(
            opponent_card.object_id,
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertEqual(1, opponent_card.counters["void"])

        token_ref = engine.create_token(
            "A",
            name="Replacement Witness",
            characteristics={"type_line": "Token Creature"},
        )[0]
        token = next(
            card
            for card in engine.state.cards.values()
            if card.ref == token_ref
        )
        engine.move_card(
            token.object_id,
            "graveyard",
            reason="Dauthi does not replace token movement",
            log=False,
        )
        self.assertEqual("graveyard", token.zone)

    def test_simultaneous_same_owner_order_is_still_caller_determined(self):
        session = self.make_session(40406)
        engine = session.engine
        first = self.card(engine, "A", "Sol Ring")
        second = self.card(engine, "A", "Sensei's Divining Top")

        engine._move_cards_simultaneously(
            [
                (second.object_id, "graveyard"),
                (first.object_id, "graveyard"),
            ],
            reason="CR 404.3 blocked ordering witness",
            log=False,
        )

        self.assertEqual(
            [second.object_id, first.object_id],
            engine.state.players["A"].zones["graveyard"],
        )
        self.assertIsNone(engine.state.pending_decision)


if __name__ == "__main__":
    unittest.main()
