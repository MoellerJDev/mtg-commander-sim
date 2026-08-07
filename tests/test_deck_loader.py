from __future__ import annotations

import unittest

from quorune.deck import (
    DeckDefinition,
    DeckEntry,
    DeckLoader,
    extract_moxfield_id,
    is_moxfield_source,
    parse_deck_text,
    parse_moxfield_json,
)
from common import load_assets


class DeckLoaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()
        cls.loader = DeckLoader(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_bundled_decks_are_complete_commander_lists(self):
        self.assertEqual(100, self.mishra.total_cards())
        self.assertEqual(100, self.zimone.total_cards())
        self.assertEqual(["Mishra, Eminent One"], self.mishra.commanders)
        self.assertEqual(["Zimone and Dina"], self.zimone.commanders)

    def test_parse_nested_moxfield_v3_shape(self):
        payload = {
            "name": "Example",
            "boards": {
                "commanders": {
                    "cards": {
                        "Mishra, Eminent One": {
                            "quantity": 1,
                            "card": {"name": "Mishra, Eminent One"},
                        }
                    }
                },
                "mainboard": {
                    "cards": {
                        "Sol Ring": {
                            "quantity": 1,
                            "card": {"name": "Sol Ring"},
                            "tags": ["Mana-Fast"],
                        },
                        "Island": {
                            "quantity": 3,
                            "card": {"name": "Island"},
                        },
                    }
                },
            },
        }
        deck = parse_moxfield_json(payload, source="https://www.moxfield.com/decks/example")
        self.assertEqual(["Mishra, Eminent One"], deck.commanders)
        by_name = {entry.name: entry for entry in deck.entries}
        self.assertEqual(3, by_name["Island"].quantity)
        self.assertEqual(["Mana-Fast"], by_name["Sol Ring"].tags)

    def test_plain_text_tags_do_not_change_card_name(self):
        deck = parse_deck_text(
            "Commander:\n1 Zimone and Dina\nMainboard:\n1 Sol Ring #Mana-Fast\n1 Forest #Land-Mana\n"
        )
        names = {entry.name for entry in deck.entries}
        self.assertIn("Sol Ring", names)
        self.assertNotIn("Sol Ring #Mana-Fast", names)

    def test_moxfield_source_parsing_is_host_and_path_aware(self):
        public_id = "g5vtVfRuS0W5KxZuYqZHGQ"
        self.assertEqual(
            public_id,
            extract_moxfield_id(
                f"https://moxfield.com/decks/{public_id}?utm_source=test"
            ),
        )
        self.assertEqual(
            public_id,
            extract_moxfield_id(f"www.moxfield.com/decks/{public_id}/primer"),
        )
        self.assertTrue(is_moxfield_source(public_id))
        self.assertFalse(
            is_moxfield_source(f"https://example.invalid/moxfield.com/decks/{public_id}")
        )
        with self.assertRaises(ValueError):
            extract_moxfield_id(f"https://moxfield.com/users/{public_id}")

    def test_declared_non_commander_format_is_rejected(self):
        deck = DeckDefinition(
            name="Not Commander",
            entries=[DeckEntry("Island", 99), DeckEntry("Zimone and Dina", 1, "commander")],
            commanders=["Zimone and Dina"],
            metadata={"format": "modern"},
        )
        issues = self.loader.validate_commander_deck(deck, check_color_identity=False)
        self.assertIn("expected 'commander'", issues[0])


if __name__ == "__main__":
    unittest.main()
