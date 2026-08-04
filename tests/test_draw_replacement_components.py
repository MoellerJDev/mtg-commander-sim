from __future__ import annotations

import unittest

from mtg_commander_sim.replacement import DredgeDraw
from mtg_commander_sim.semantic_runtime import (
    DREDGE_HANDLER_ID,
    default_draw_replacement_registry,
    DredgeReplacementHandler,
    DrawReplacementSourceContext,
)
from mtg_commander_sim.semantic_runtime.context import SemanticNodeError


def descriptor(count: int = 3):
    return {
        "handler_id": DREDGE_HANDLER_ID,
        "schema_version": 1,
        "event": "draw",
        "modification": {"mill_count": count},
    }


class DrawReplacementComponentTests(unittest.TestCase):
    def test_dredge_descriptor_lowers_to_one_optional_typed_effect(self):
        context = DrawReplacementSourceContext(
            source_ref="A17",
            source_object_id="object:A17",
            source_zone_change_counter=4,
            source_owner="A",
            component_id="program:0",
        )
        effect = DredgeReplacementHandler().replacement_effect(
            descriptor(), context
        )

        self.assertTrue(effect.optional)
        self.assertEqual("draw", effect.event_kind)
        self.assertEqual({"eq": "A"}, effect.conditions["affected_player"])
        self.assertEqual({"gte": 3}, effect.conditions["library_size"])
        self.assertEqual(1, len(effect.operations))
        self.assertIsInstance(effect.operations[0], DredgeDraw)
        self.assertEqual(3, effect.operations[0].mill_count)
        self.assertIn("object:A17@4", effect.effect_id)

    def test_dredge_descriptor_rejects_unknown_and_coerced_fields(self):
        handler = DredgeReplacementHandler()
        malformed = descriptor()
        malformed["unknown"] = True
        with self.assertRaisesRegex(SemanticNodeError, "unknown"):
            handler.validate(malformed)

        malformed = descriptor()
        malformed["modification"]["mill_count"] = "3"
        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            handler.validate(malformed)

        malformed = descriptor()
        malformed["modification"]["mill_count"] = True
        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            handler.validate(malformed)

    def test_draw_registry_is_frozen_and_capability_bound(self):
        registry = default_draw_replacement_registry()
        inventory = registry.inventory()

        self.assertEqual(1, len(inventory))
        self.assertEqual(DREDGE_HANDLER_ID, inventory[0]["handler_id"])
        self.assertEqual(
            ["zone.draw.library_to_hand"],
            inventory[0]["capability_dependencies"],
        )
        with self.assertRaisesRegex(SemanticNodeError, "frozen"):
            registry.register(DredgeReplacementHandler())

    def test_source_context_rejects_unstable_identity(self):
        with self.assertRaisesRegex(SemanticNodeError, "nonempty string"):
            DrawReplacementSourceContext(
                source_ref="",
                source_object_id="object:A17",
                source_zone_change_counter=0,
                source_owner="A",
            )
        with self.assertRaisesRegex(SemanticNodeError, "nonnegative"):
            DrawReplacementSourceContext(
                source_ref="A17",
                source_object_id="object:A17",
                source_zone_change_counter=-1,
                source_owner="A",
            )


if __name__ == "__main__":
    unittest.main()
