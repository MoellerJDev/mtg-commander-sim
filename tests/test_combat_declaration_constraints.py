from __future__ import annotations

import unittest

from mtg_commander_sim.combat_constraints import (
    DeclarationProblem,
    DeclarationRequirement,
    DeclarationRestriction,
    DeclarationSearchLimitError,
)


class CombatDeclarationConstraintTests(unittest.TestCase):
    def test_conflicting_requirements_accept_any_maximal_declaration(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",), "A2": ("B",)},
            requirements=(
                DeclarationRequirement("r1", "choose", variable="A1"),
                DeclarationRequirement("r2", "choose", variable="A2"),
            ),
            restrictions=(
                DeclarationRestriction(
                    "only-one",
                    "maximum_option_uses",
                    option="B",
                    count=1,
                ),
            ),
        )

        self.assertEqual(1, problem.maximum_satisfied_requirements())
        self.assertTrue(problem.evaluate({"A1": "B"}).legal)
        self.assertTrue(problem.evaluate({"A2": "B"}).legal)
        self.assertFalse(problem.evaluate({}).legal)
        self.assertFalse(problem.evaluate({"A1": "B", "A2": "B"}).legal)

    def test_impossible_requirement_has_zero_maximum(self):
        problem = DeclarationProblem(
            domains={},
            requirements=(
                DeclarationRequirement(
                    "missing", "choose", variable="not-eligible"
                ),
            ),
        )
        evaluation = problem.evaluate({})
        self.assertEqual(0, evaluation.maximum)
        self.assertTrue(evaluation.legal)

    def test_search_limit_fails_closed(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",), "A2": ("B",)},
            requirements=(
                DeclarationRequirement(
                    "impossible", "choose", variable="A3"
                ),
            ),
            max_search_states=1,
        )
        with self.assertRaises(DeclarationSearchLimitError):
            problem.maximum_satisfied_requirements()


if __name__ == "__main__":
    unittest.main()
