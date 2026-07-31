from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import StackItem


class ResolutionRuleTests(unittest.TestCase):
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
            players=2,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine.state.priority_player = None
        return session.engine

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

    def test_contract_traces_every_cr_608_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "resolving-spells-and-abilities.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "608",
                "608.1",
                "608.2",
                "608.2a",
                "608.2b",
                "608.2c",
                "608.2d",
                "608.2e",
                "608.2f",
                "608.2g",
                "608.2h",
                "608.2i",
                "608.2j",
                "608.2k",
                "608.2m",
                "608.2n",
                "608.2p",
                "608.3",
                "608.3a",
                "608.3b",
                "608.3c",
                "608.3d",
                "608.3e",
                "608.3f",
                "608.3g",
            },
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("608")
            },
        )

    def test_only_top_spell_resolves_after_all_players_pass(self):
        engine = self.make_engine(60801)
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
        top_card = engine.state.cards[top.card_object_id]
        lower_card = engine.state.cards[lower.card_object_id]
        engine.state.priority_player = "A"
        engine.state.priority_passes = []

        engine._pass_priority("A")
        self.assertEqual([lower, top], engine.state.stack)
        engine._pass_priority("B")

        self.assertEqual([lower], engine.state.stack)
        self.assertEqual("battlefield", top_card.zone)
        self.assertEqual("B", top_card.controller)
        self.assertEqual("stack", lower_card.zone)

    def test_resolution_continues_after_underlying_card_moves(self):
        engine = self.make_engine(60802)
        item = self.put_spell_on_stack(
            engine,
            "A",
            "Chaos Warp",
            ref="S-self-move",
        )
        card = engine.state.cards[item.card_object_id]
        life_before = engine.state.players["A"].life

        engine._begin_resolve_item(
            item,
            [
                {
                    "op": "exile",
                    "card": "$card",
                    "reason": "move resolving card",
                },
                {
                    "op": "life",
                    "player": "A",
                    "delta": 2,
                    "reason": "later resolution instruction",
                },
            ],
            "graveyard",
        )

        self.assertEqual("exile", card.zone)
        self.assertEqual(
            life_before + 2,
            engine.state.players["A"].life,
        )
        self.assertNotIn(item, engine.state.stack)

    def test_spell_and_ability_leave_stack_after_resolution(self):
        engine = self.make_engine(60803)
        spell = self.put_spell_on_stack(
            engine,
            "A",
            "Chaos Warp",
            ref="S-finish-spell",
        )
        spell_card = engine.state.cards[spell.card_object_id]

        engine._begin_resolve_item(spell, [], "graveyard")

        self.assertEqual("graveyard", spell_card.zone)
        self.assertNotIn(spell, engine.state.stack)

        ability = StackItem(
            stack_id=engine._stable_runtime_id(
                "stack",
                "S-finish-ability",
            ),
            ref="S-finish-ability",
            kind="activated",
            controller="B",
            label="Test ability",
            visibility=list(engine.seats),
            context={"dynamic_effects": []},
        )
        engine.state.stack.append(ability)

        engine._begin_resolve_item(ability, [], None)

        self.assertNotIn(ability, engine.state.stack)


if __name__ == "__main__":
    unittest.main()
