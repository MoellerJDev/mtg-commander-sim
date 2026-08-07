from __future__ import annotations

import unittest

from quorune.delayed_triggers import materialize_delayed_trigger
from quorune.model import DelayedTrigger


class DelayedTriggerMaterializationTests(unittest.TestCase):
    def test_materialization_preserves_typed_referred_object_provenance(self):
        trigger = DelayedTrigger(
            trigger_id="delayed-1",
            ref="DT1",
            controller="A",
            label="Delayed effect",
            source_object_id="source-object",
            event_kind="phase.begin",
            condition={"phase": "ending"},
            stack_template={
                "label": "Materialized effect",
                "semantic_key": "program:delayed",
                "targets": ["B"],
                "context": {"nested": {"value": 1}},
            },
            referred_object_ids=["former-zone-object"],
        )

        item = materialize_delayed_trigger(
            trigger,
            ref="S1",
            stack_id="stack-1",
            visibility=("A", "B"),
        )

        self.assertEqual(["former-zone-object"], item.referred_object_ids)
        self.assertEqual("DT1", item.context["delayed_trigger_ref"])
        self.assertEqual(["A", "B"], item.visibility)
        self.assertEqual("Materialized effect", item.label)

        trigger.stack_template["context"]["nested"]["value"] = 2
        self.assertEqual(1, item.context["nested"]["value"])

    def test_materialization_keeps_historical_empty_provenance_shape(self):
        trigger = DelayedTrigger(
            trigger_id="delayed-2",
            ref="DT2",
            controller="A",
            label="Historical trigger",
            source_object_id=None,
            event_kind="turn.begin",
            condition={},
            stack_template={},
        )

        item = materialize_delayed_trigger(
            trigger,
            ref="S2",
            stack_id="stack-2",
            visibility=("A",),
        )

        self.assertEqual([], item.referred_object_ids)
        self.assertNotIn("referred_object_ids", item.to_dict())


if __name__ == "__main__":
    unittest.main()
