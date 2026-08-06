from __future__ import annotations

import unittest

from mtg_commander_sim.combat_constraints import DeclarationProblem
from mtg_commander_sim.menace import (
    MenaceBlockRestriction,
    MenaceRuleError,
    current_menace_restriction,
)


def _declaration_is_legal(
    restriction: MenaceBlockRestriction,
    blocker_count: int,
) -> bool:
    domains = {
        f"B{index}": (restriction.attacker_ref,)
        for index in range(blocker_count)
    }
    return DeclarationProblem(
        domains=domains,
        restrictions=(restriction.declaration_restriction(),),
    ).evaluate(
        {blocker: restriction.attacker_ref for blocker in domains}
    ).legal


class MenaceRuleTests(unittest.TestCase):
    def test_current_attacking_creature_has_one_redundant_restriction(self):
        restriction = current_menace_restriction(
            {
                "type_line": "Legendary Creature — Horror",
                "keywords": ["Menace", "MENACE", "Haste"],
            },
            "A17",
            is_attacking=True,
        )

        self.assertEqual(
            MenaceBlockRestriction(attacker_ref="A17"), restriction
        )
        declaration = restriction.declaration_restriction()
        self.assertEqual("block:A17:menace", declaration.restriction_id)
        self.assertEqual("minimum_option_uses", declaration.kind)
        self.assertEqual("A17", declaration.option)
        self.assertEqual(2, declaration.count)
        self.assertTrue(declaration.when_used)

    def test_nonattacker_noncreature_and_nonmenace_have_no_restriction(self):
        for data, is_attacking in (
            (
                {"type_line": "Creature — Horror", "keywords": ["Menace"]},
                False,
            ),
            (
                {"type_line": "Artifact", "keywords": ["Menace"]},
                True,
            ),
            (
                {"type_line": "Creature — Horror", "keywords": ["Haste"]},
                True,
            ),
        ):
            with self.subTest(data=data, is_attacking=is_attacking):
                self.assertIsNone(
                    current_menace_restriction(
                        data,
                        "A17",
                        is_attacking=is_attacking,
                    )
                )

    def test_malformed_current_characteristics_and_identity_fail_closed(self):
        cases = (
            (None, "A17", True, "mapping"),
            ({"type_line": [], "keywords": []}, "A17", True, "type line"),
            (
                {"type_line": "Creature", "keywords": "Menace"},
                "A17",
                True,
                "keywords",
            ),
            (
                {"type_line": "Creature", "keywords": [""]},
                "A17",
                True,
                "keywords",
            ),
            (
                {"type_line": "Creature", "keywords": []},
                "",
                True,
                "reference",
            ),
            (
                {"type_line": "Creature", "keywords": []},
                " ",
                True,
                "reference",
            ),
            (
                {"type_line": "Creature", "keywords": []},
                " A17",
                True,
                "reference",
            ),
            (
                {"type_line": "Creature", "keywords": []},
                "A17",
                1,
                "boolean",
            ),
        )
        for data, attacker_ref, is_attacking, pattern in cases:
            with self.subTest(
                data=data,
                attacker_ref=attacker_ref,
                is_attacking=is_attacking,
            ):
                with self.assertRaisesRegex(MenaceRuleError, pattern):
                    current_menace_restriction(
                        data,
                        attacker_ref,
                        is_attacking=is_attacking,
                    )

    def test_zero_or_two_blockers_is_the_exact_conditional_minimum(self):
        restriction = MenaceBlockRestriction("A17")
        for blocker_count in range(4):
            with self.subTest(blockers=blocker_count):
                self.assertEqual(
                    blocker_count != 1,
                    _declaration_is_legal(restriction, blocker_count),
                )
        for malformed in (True, 1, 3):
            with self.subTest(minimum=malformed):
                with self.assertRaises(MenaceRuleError):
                    MenaceBlockRestriction("A17", malformed)

    def test_typed_restriction_participates_in_the_generic_solver(self):
        restriction = MenaceBlockRestriction("A17")
        problem = DeclarationProblem(
            domains={"B01": ("A17",), "B02": ("A17",)},
            restrictions=(restriction.declaration_restriction(),),
        )

        self.assertTrue(problem.evaluate({}).legal)
        one = problem.evaluate({"B01": "A17"})
        self.assertFalse(one.legal)
        self.assertIn("menace", one.restriction_errors[0])
        self.assertTrue(
            problem.evaluate({"B01": "A17", "B02": "A17"}).legal
        )

    def test_menace_verdict_holds_across_bounded_characteristic_grid(self):
        for creature in (False, True):
            for attacking in (False, True):
                for copies in range(4):
                    data = {
                        "type_line": (
                            "Artifact Creature — Wall"
                            if creature
                            else "Artifact"
                        ),
                        "keywords": ["mEnAcE"] * copies,
                    }
                    restriction = current_menace_restriction(
                        data,
                        "A17",
                        is_attacking=attacking,
                    )
                    self.assertEqual(
                        creature and attacking and copies > 0,
                        restriction is not None,
                    )
                    if restriction is not None:
                        for blocker_count in range(5):
                            self.assertEqual(
                                blocker_count != 1,
                                _declaration_is_legal(
                                    restriction,
                                    blocker_count,
                                ),
                            )


if __name__ == "__main__":
    unittest.main()
