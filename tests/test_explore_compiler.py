from __future__ import annotations

import unittest
from pathlib import Path
import os

from quorune.carddb import CardDatabase
from quorune.compiler.explore_templates import (
    single_explore_effect_template,
)
from quorune.oracle_ir import compile_oracle_card


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(
    os.environ.get(
        "MTG_CARD_DB",
        ROOT / "data" / "scryfall-20260728-compact.sqlite3",
    )
)
from quorune.rules.node_capability_shapes import (
    single_explore_node_capabilities,
)


class ExploreCompilerTests(unittest.TestCase):
    def test_single_source_and_controlled_target_shapes_are_typed(self):
        source = single_explore_effect_template("This creature explores.")
        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(
            (
                {
                    "op": "explore",
                    "player": "$source.controller",
                    "card": "$source",
                },
            ),
            source.effects,
        )
        self.assertEqual(
            ("keyword_action.explore.single",),
            single_explore_node_capabilities(
                effects=source.effects,
                target_schema=source.target_schema,
                mechanic_ids=source.mechanics,
            ),
        )

        target = single_explore_effect_template(
            "Target creature you control explores."
        )
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual("you", target.target_schema["controller_relation"])
        self.assertEqual(
            (
                "keyword_action.explore.single",
                "target.revalidate_resolution",
            ),
            single_explore_node_capabilities(
                effects=target.effects,
                target_schema=target.target_schema,
                mechanic_ids=target.mechanics,
            ),
        )

    def test_trigger_pronoun_requires_explicit_source_binding(self):
        self.assertIsNone(single_explore_effect_template("It explores."))
        bound = single_explore_effect_template(
            "It explores.",
            allow_source_pronoun=True,
        )
        self.assertIsNotNone(bound)
        assert bound is not None
        self.assertEqual("$source", bound.effects[0]["card"])

    def test_unsupported_explore_variants_remain_outside_closed_grammar(self):
        for text in (
            "Explore.",
            "This creature explores twice.",
            "Each creature you control explores.",
            "Target creature explores.",
            "Up to two target creatures you control explore.",
            "This creature explores, then it explores again.",
            "If this creature would explore, it explores twice instead.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(single_explore_effect_template(text))

    def test_capability_shape_rejects_malformed_effects(self):
        valid = {
            "op": "explore",
            "player": "$source.controller",
            "card": "$source",
        }
        for mutation in (
            {**valid, "times": 2},
            {**valid, "card": "$target.0"},
            {**valid, "player": "$controller"},
            {**valid, "op": "explore_many"},
        ):
            with self.subTest(mutation=mutation):
                self.assertEqual(
                    (),
                    single_explore_node_capabilities(
                        effects=(mutation,),
                        target_schema=None,
                        mechanic_ids=("explore",),
                    ),
                )

    def test_oracle_nodes_preserve_trigger_and_activation_source_spans(self):
        with CardDatabase(DB_PATH) as database:
            trigger = compile_oracle_card(
                database.lookup("Cenote Scout"),
                trusted_mechanics={
                    "explore",
                    "cr-603-handling-triggered-abilities",
                },
            ).faces[0].nodes[0]
            activation = compile_oracle_card(
                database.lookup("Seeker of Sunlight"),
                trusted_mechanics={"explore"},
            ).faces[0].nodes[0]
        self.assertEqual("explore-source-permanent-once-v1", trigger.template_id)
        self.assertEqual("permanent.enter.self", trigger.event)
        self.assertEqual(1, trigger.span.line)
        self.assertEqual("$source", trigger.effects[0]["card"])
        self.assertEqual("activated_ability", activation.kind)
        self.assertEqual("explore-source-permanent-once-v1", activation.template_id)
        self.assertEqual(1, activation.span.line)


if __name__ == "__main__":
    unittest.main()
