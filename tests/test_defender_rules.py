from __future__ import annotations

import unittest
from types import SimpleNamespace

from mtg_commander_sim.defender import (
    defender_prohibits_attack,
    DefenderRuleError,
)


class _Host:
    def __init__(self, data):
        self.data = data

    def _effective_card_data(self, _card):
        return self.data

    @staticmethod
    def _type_parts(type_line: str):
        before_dash = type_line.casefold().split("—", 1)[0]
        return set(before_dash.split()), set(), set()


class DefenderRuleTests(unittest.TestCase):
    def test_current_effective_defender_is_case_insensitive_and_redundant(self):
        host = _Host(
            {
                "type_line": "Token Creature — Wall",
                "keywords": ["Defender", "DEFENDER", "Haste"],
            }
        )

        self.assertTrue(
            defender_prohibits_attack(host, SimpleNamespace())
        )

        host.data = {
            "type_line": "Token Creature — Wall",
            "keywords": ["Haste"],
        }
        self.assertFalse(
            defender_prohibits_attack(host, SimpleNamespace())
        )

    def test_noncreature_and_nondefender_are_not_restricted(self):
        for type_line, keywords in (
            ("Token Artifact", ["Defender"]),
            ("Token Creature — Wall", []),
        ):
            with self.subTest(type_line=type_line, keywords=keywords):
                self.assertFalse(
                    defender_prohibits_attack(
                        _Host(
                            {
                                "type_line": type_line,
                                "keywords": keywords,
                            }
                        ),
                        SimpleNamespace(),
                    )
                )

    def test_malformed_current_creature_characteristics_fail_closed(self):
        for data, pattern in (
            (None, "mapping"),
            ({"type_line": [], "keywords": []}, "type line"),
            (
                {"type_line": "Creature", "keywords": "Defender"},
                "keywords",
            ),
            (
                {"type_line": "Creature", "keywords": [""]},
                "keywords",
            ),
        ):
            with self.subTest(data=data):
                with self.assertRaisesRegex(DefenderRuleError, pattern):
                    defender_prohibits_attack(
                        _Host(data),
                        SimpleNamespace(),
                    )

    def test_defender_verdict_holds_across_bounded_characteristic_grid(self):
        for creature in (False, True):
            for copies in range(4):
                keywords = ["dEfEnDeR"] * copies
                with self.subTest(creature=creature, copies=copies):
                    self.assertEqual(
                        creature and copies > 0,
                        defender_prohibits_attack(
                            _Host(
                                {
                                    "type_line": (
                                        "Artifact Creature"
                                        if creature
                                        else "Artifact"
                                    ),
                                    "keywords": keywords,
                                }
                            ),
                            SimpleNamespace(),
                        ),
                    )


if __name__ == "__main__":
    unittest.main()
