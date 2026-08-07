from __future__ import annotations

from dataclasses import replace
import unittest

from common import DB_PATH
from quorune.card_programs.adapters import compile_card_program
from quorune.carddb import CardDatabase, CardRecord
from quorune.compiler.zone_templates import (
    static_zone_destination_replacement_handler,
)
from quorune.rules.capabilities import load_default_capability_registry


ORACLE_TEXT = (
    "If a card would be put into an opponent's graveyard from anywhere, "
    "instead exile it with a void counter on it."
)


def _replacement_fixture(text: str = ORACLE_TEXT) -> CardRecord:
    return CardRecord(
        oracle_id="00000000-0000-4000-8000-000000400600",
        name="Generic Destination Replacement Fixture",
        mana_cost="{1}{B}",
        mana_value=2.0,
        type_line="Enchantment",
        oracle_text=text,
        power=None,
        toughness=None,
        loyalty=None,
        defense=None,
        colors=("B",),
        color_identity=("B",),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class ZoneReplacementCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db = CardDatabase(DB_PATH)
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.db.close()

    def test_closed_family_lowers_to_capability_closed_card_program(self):
        compiled = static_zone_destination_replacement_handler(ORACLE_TEXT)
        self.assertEqual(
            (
                "zone-opponent-card-graveyard-to-exile-with-counter-v1",
                {
                    "handler_id": "replacement.zone.destination.v1",
                    "schema_version": 1,
                    "event": "zone.change",
                    "condition": {
                        "destination": "graveyard",
                        "object_kind": "card",
                        "owner_relation": "opponent",
                    },
                    "destination": "exile",
                    "counters": {"void": 1},
                },
                "zone.change.destination_replacement",
            ),
            compiled,
        )

        program = compile_card_program(
            self.db,
            _replacement_fixture(),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            trust_level="trusted",
        )

        self.assertEqual(
            ("zone.change.destination_replacement",),
            program.capability_dependencies,
        )
        self.assertTrue(program.trust_closure["trusted"])
        self.assertEqual([], program.to_dict()["residuals"])
        ability = program.to_dict()["abilities"][0]
        self.assertEqual("static", ability["kind"])
        self.assertEqual(
            {"line": 1, "start": 0, "end": len(ORACLE_TEXT)},
            ability["source_span"],
        )
        self.assertEqual(
            ["replacement.zone.destination.v1"],
            [row["handler_id"] for row in ability["runtime"]["handlers"]],
        )

    def test_unrepresented_destination_variants_remain_residual(self):
        variants = (
            "If a token would be put into an opponent's graveyard from anywhere, instead exile it with a void counter on it.",
            "If a card would be put into your graveyard from anywhere, instead exile it with a void counter on it.",
            "If a card would be put into an opponent's graveyard from the battlefield, instead exile it with a void counter on it.",
            "If a card would be put into an opponent's graveyard from anywhere, you may exile it with a void counter on it instead.",
            "If a card would be put into an opponent's graveyard from anywhere, instead exile it.",
            "If a card would be put into an opponent's graveyard from anywhere, instead put it into its owner's library.",
        )
        for index, text in enumerate(variants, start=1):
            with self.subTest(text=text):
                self.assertIsNone(
                    static_zone_destination_replacement_handler(text)
                )
                program = compile_card_program(
                    self.db,
                    replace(
                        _replacement_fixture(text),
                        oracle_id=(
                            f"00000000-0000-4000-8000-{400600 + index:012d}"
                        ),
                    ),
                    capability_registry=self.capabilities,
                    capability_profile="commander_review",
                    trust_level="provisional",
                )
                self.assertFalse(program.trust_closure["trusted"])
                self.assertTrue(program.to_dict()["residuals"])


if __name__ == "__main__":
    unittest.main()
