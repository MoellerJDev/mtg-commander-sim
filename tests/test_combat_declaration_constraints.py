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

    def test_costed_option_is_optional_for_requirement_maximization(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",)},
            requirements=(
                DeclarationRequirement("must-attack", "choose", variable="A1"),
            ),
            costed_options=frozenset({("A1", "B")}),
        )

        self.assertEqual(0, problem.maximum_satisfied_requirements())
        self.assertTrue(problem.evaluate({}).legal)
        paid = problem.evaluate({"A1": "B"})
        self.assertEqual(1, paid.maximum)
        self.assertTrue(paid.legal)
        self.assertEqual(
            [{"variable": "A1", "option": "B"}],
            problem.projection()["costed_options"],
        )

    def test_elected_cost_does_not_hide_free_requirements(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",), "A2": ("B",)},
            requirements=(
                DeclarationRequirement("costed", "choose", variable="A1"),
                DeclarationRequirement("free", "choose", variable="A2"),
            ),
            costed_options=frozenset({("A1", "B")}),
        )

        self.assertFalse(problem.evaluate({"A1": "B"}).legal)
        self.assertTrue(problem.evaluate({"A2": "B"}).legal)
        self.assertTrue(
            problem.evaluate({"A1": "B", "A2": "B"}).legal
        )

    def test_costed_menace_blocks_must_be_elected_together(self):
        problem = DeclarationProblem(
            domains={"B1": ("A1",), "B2": ("A1",)},
            restrictions=(
                DeclarationRestriction(
                    "menace",
                    "minimum_option_uses",
                    option="A1",
                    count=2,
                    when_used=True,
                ),
            ),
            costed_options=frozenset(
                {("B1", "A1"), ("B2", "A1")}
            ),
        )

        self.assertTrue(problem.evaluate({}).legal)
        self.assertFalse(problem.evaluate({"B1": "A1"}).legal)
        self.assertTrue(
            problem.evaluate({"B1": "A1", "B2": "A1"}).legal
        )

    def test_selected_creature_can_require_another_declaration(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",), "A2": ("C",)},
            restrictions=(
                DeclarationRestriction(
                    "not-alone",
                    "minimum_total_selections",
                    count=2,
                    trigger_variable="A1",
                ),
            ),
        )

        self.assertTrue(problem.evaluate({}).legal)
        self.assertFalse(problem.evaluate({"A1": "B"}).legal)
        self.assertTrue(problem.evaluate({"A2": "C"}).legal)
        self.assertTrue(
            problem.evaluate({"A1": "B", "A2": "C"}).legal
        )

    def test_global_maximum_applies_before_requirement_maximization(self):
        problem = DeclarationProblem(
            domains={"A1": ("B",), "A2": ("B",)},
            requirements=(
                DeclarationRequirement("r1", "choose", variable="A1"),
                DeclarationRequirement("r2", "choose", variable="A2"),
            ),
            restrictions=(
                DeclarationRestriction(
                    "only-one",
                    "maximum_total_selections",
                    count=1,
                ),
            ),
        )

        self.assertEqual(1, problem.maximum_satisfied_requirements())
        self.assertTrue(problem.evaluate({"A1": "B"}).legal)
        self.assertTrue(problem.evaluate({"A2": "B"}).legal)
        self.assertFalse(problem.evaluate({"A1": "B", "A2": "B"}).legal)

    def test_restriction_projection_identifies_trigger_variable(self):
        restriction = DeclarationRestriction(
            "not-alone",
            "minimum_total_selections",
            count=2,
            trigger_variable="A1",
            label="A1 can't attack alone",
        )

        self.assertEqual(
            {
                "id": "not-alone",
                "kind": "minimum_total_selections",
                "option": None,
                "count": 2,
                "when_used": False,
                "trigger_variable": "A1",
                "label": "A1 can't attack alone",
            },
            restriction.to_dict(),
        )


if __name__ == "__main__":
    unittest.main()
