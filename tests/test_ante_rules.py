from __future__ import annotations

import json
import unittest
from pathlib import Path

from common import load_assets, make_session
from quorune.carddb import CardRecord
from quorune.deck import DeckDefinition, DeckEntry, DeckLoader
from quorune.engine import GameRuleError
from quorune.model import GameConfig
from quorune.record import authoritative_state_hash
from quorune.session import CommanderSession


class _CardLookup:
    def __init__(self, cards: list[CardRecord]):
        self.cards = {card.name: card for card in cards}

    def lookup(self, name: str) -> CardRecord:
        return self.cards[name]


def _record(
    name: str,
    *,
    type_line: str,
    commander_legality: str,
) -> CardRecord:
    return CardRecord(
        oracle_id=f"test-{name.casefold().replace(' ', '-')}",
        name=name,
        mana_cost="",
        mana_value=0,
        type_line=type_line,
        oracle_text="",
        power=None,
        toughness=None,
        loyalty=None,
        defense=None,
        colors=("B",),
        color_identity=("B",),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="1993-08-05",
        legalities={"commander": commander_legality},
        faces=(),
        raw={},
    )


class AnteRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_contract_traces_every_cr_407_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root / "mechanics" / "contracts" / "ante.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"407", "407.1", "407.2", "407.3", "407.4"},
            {
                rule_id
                for rule_id in contract["rule_references"]
                if str(rule_id).startswith("407")
            },
        )

    def test_commander_profiles_reject_ante_and_have_no_ante_zone(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=40701,
        )
        self.assertTrue(
            all(
                "ante" not in player.zones
                for player in session.state.players.values()
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "Unsupported Commander format profile 'ante'",
        ):
            CommanderSession.create(
                self.db,
                {"A": self.mishra, "B": self.zimone},
                first_player="A",
                config=GameConfig(profile="ante", seed=40702),
            )

    def test_ante_moves_fail_closed_without_state_change(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=40703,
        )
        engine = session.engine
        card = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.zone == "library"
        )
        before = authoritative_state_hash(engine.state)

        with self.assertRaisesRegex(
            GameRuleError,
            "Unsupported destination ante",
        ):
            engine.move_card(card.object_id, "ante")

        self.assertEqual(before, authoritative_state_hash(engine.state))
        self.assertEqual("library", card.zone)

    def test_commander_legality_rejects_ante_cards_in_deck_and_sideboard(
        self,
    ):
        commander = _record(
            "Witness Commander",
            type_line="Legendary Creature — Human",
            commander_legality="legal",
        )
        swamp = _record(
            "Swamp",
            type_line="Basic Land — Swamp",
            commander_legality="legal",
        )
        ante_card = _record(
            "Contract from Below",
            type_line="Sorcery",
            commander_legality="banned",
        )
        loader = DeckLoader(_CardLookup([commander, swamp, ante_card]))
        deck = DeckDefinition(
            name="Ante rejection witness",
            entries=[
                DeckEntry(commander.name, 1, "commander"),
                DeckEntry(swamp.name, 98, "mainboard"),
                DeckEntry(ante_card.name, 1, "mainboard"),
                DeckEntry(ante_card.name, 1, "sideboard"),
            ],
            commanders=[commander.name],
            metadata={"format": "commander"},
        )

        issues = loader.validate_commander_deck(deck)

        self.assertIn(
            "Commander legality: Contract from Below is banned "
            "on the mainboard",
            issues,
        )
        self.assertIn(
            "Commander legality: Contract from Below is banned "
            "on the sideboard",
            issues,
        )

    def test_supported_commander_lists_remain_legal(self):
        loader = DeckLoader(self.db)

        self.assertEqual(
            [],
            loader.validate_commander_deck(self.mishra),
        )
        self.assertEqual(
            [],
            loader.validate_commander_deck(self.zimone),
        )


if __name__ == "__main__":
    unittest.main()
