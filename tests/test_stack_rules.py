from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import GameRuleError
from quorune.model import StackItem
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class StackRuleTests(unittest.TestCase):
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
        engine.state.stack.clear()
        session.commands.clear()
        session.decisions.clear()
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

    def put_spell_on_stack(
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

    def test_contract_traces_every_cr_405_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "stack.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "405",
                "405.1",
                "405.2",
                "405.3",
                "405.4",
                "405.5",
                "405.6",
                "405.6a",
                "405.6b",
                "405.6c",
                "405.6d",
                "405.6e",
                "405.6f",
                "405.6g",
                "405.6h",
            },
            set(contract["rule_references"]),
        )

    def test_stack_is_last_in_first_out_and_replays_exactly(self):
        session = self.make_session(40502)
        engine = session.engine
        lower = self.put_spell_on_stack(
            engine,
            "A",
            "Sol Ring",
            ref="S-lower",
        )
        top = self.put_spell_on_stack(
            engine,
            "B",
            "Elves of Deep Shadow",
            ref="S-top",
        )
        lower_card = engine.state.cards[lower.card_object_id]
        top_card = engine.state.cards[top.card_object_id]
        engine.state.priority_player = "A"
        engine.pump()
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        first = session.act("pilot:A", {"a": "pass"})
        self.assertTrue(first.ok, first.summary)
        self.assertEqual([lower, top], engine.state.stack)

        second = session.act("pilot:B", {"a": "pass"})
        self.assertTrue(second.ok, second.summary)
        self.assertEqual([lower], engine.state.stack)
        self.assertEqual("battlefield", top_card.zone)
        self.assertEqual("stack", lower_card.zone)

        third = session.act("pilot:A", {"a": "pass"})
        self.assertTrue(third.ok, third.summary)
        self.assertEqual([lower], engine.state.stack)

        fourth = session.act("pilot:B", {"a": "pass"})
        self.assertTrue(fourth.ok, fourth.summary)
        self.assertFalse(engine.state.stack)
        self.assertEqual("battlefield", lower_card.zone)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "stack-lifo"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(4, replay["commands"])

    def test_non_top_stack_object_cannot_begin_resolution(self):
        session = self.make_session(40505)
        engine = session.engine
        lower = self.put_spell_on_stack(
            engine,
            "A",
            "Sol Ring",
            ref="S-lower",
        )
        self.put_spell_on_stack(
            engine,
            "B",
            "Elves of Deep Shadow",
            ref="S-top",
        )
        before_hash = authoritative_state_hash(engine.state)

        with self.assertRaisesRegex(
            GameRuleError,
            "Only the top object of the stack can begin resolving",
        ):
            engine._begin_resolve_item(lower, [], "battlefield")

        self.assertEqual(before_hash, authoritative_state_hash(engine.state))

    def test_activated_mana_ability_is_immediate_and_preserves_priority(
        self,
    ):
        session = self.make_session(40506)
        engine = session.engine
        island = self.card(engine, "A", "Island")
        engine.move_card(
            island.object_id,
            "battlefield",
            controller="A",
            reason="CR 405.6c fixture",
            log=False,
            semantic_events=False,
        )
        island.tapped = False
        engine.state.priority_player = "A"
        before_stack = list(engine.state.stack)

        engine._activate_mana_plan(
            "A",
            [
                {
                    "source": island.ref,
                    "bundle": {"U": 1},
                }
            ],
        )

        self.assertEqual(before_stack, engine.state.stack)
        self.assertTrue(island.tapped)
        self.assertEqual(1, engine.state.players["A"].mana_pool["U"])
        self.assertEqual("A", engine.state.priority_player)

    def test_effect_and_state_action_execute_without_stack_objects(self):
        session = self.make_session(40561, players=3)
        engine = session.engine
        before_life = engine.state.players["A"].life

        engine.apply_effect(
            {
                "op": "life",
                "player": "A",
                "delta": -1,
                "reason": "CR 405.6a fixture",
            },
            actor="A",
            as_cost=False,
        )

        self.assertEqual(before_life - 1, engine.state.players["A"].life)
        self.assertFalse(engine.state.stack)

        engine.state.players["B"].life = 0
        engine._stabilize()

        self.assertNotIn("B", engine.active_seats)
        self.assertFalse(engine.state.stack)

    def test_player_leaving_removes_owned_spell_and_controlled_ability(
        self,
    ):
        session = self.make_session(40568, players=3)
        engine = session.engine
        spell = self.put_spell_on_stack(
            engine,
            "B",
            "Elves of Deep Shadow",
            ref="S-owned",
        )
        ability = StackItem(
            stack_id=engine._stable_runtime_id(
                "stack",
                "S-controlled",
            ),
            ref="S-controlled",
            kind="activated_ability",
            controller="B",
            label="Controlled ability",
            visibility=list(engine.seats),
            context={"dynamic_effects": []},
        )
        engine.state.stack.append(ability)
        spell_card = engine.state.cards[spell.card_object_id]

        engine._eliminate_players(["B"], reason="CR 405.6h fixture")

        self.assertNotIn("B", engine.active_seats)
        self.assertEqual("outside", spell_card.zone)
        self.assertFalse(engine.state.stack)


if __name__ == "__main__":
    unittest.main()
