from __future__ import annotations

import unittest

from quorune.drawing import (
    DrawDecisionContinuation,
    DrawError,
    DrawResume,
    QueuedDraw,
)
from quorune.replacement import (
    DredgeDraw,
    FrozenMap,
    ReplacementClass,
    ReplacementEffect,
)


def continuation() -> DrawDecisionContinuation:
    return DrawDecisionContinuation(
        event_id="draw:event:1",
        seat="B",
        remaining_draws=2,
        library_size=17,
        reason="Draw two cards",
        private=True,
        effects=(
            ReplacementEffect(
                effect_id="dredge:B17@3",
                source_id="object:B17@3",
                event_kind="draw",
                replacement_class=ReplacementClass.OTHER,
                conditions={"library_size": {"gte": 3}},
                operations=(DredgeDraw("B17", "object:B17", 3, 3),),
                optional=True,
            ),
        ),
        selections=(),
        after=DrawResume(
            kind="semantic_resolution",
            stack_ref="stack:4",
            effects=(
                FrozenMap({"op": "gain_life", "amount": 2}),
            ),
            destination="graveyard",
            note="finish resolution",
            instruction_pointer=4,
        ),
    )


class DrawContinuationTests(unittest.TestCase):
    def test_round_trip_is_exact_and_deeply_isolated(self):
        value = continuation().to_dict()
        parsed = DrawDecisionContinuation.from_dict(value)
        value["effects"][0]["label"] = "tampered"
        value["after"]["effects"][0]["amount"] = 99

        self.assertEqual(continuation(), parsed)
        self.assertEqual(continuation().to_dict(), parsed.to_dict())

    def test_unknown_outer_or_nested_fields_fail_closed(self):
        value = continuation().to_dict()
        value["unknown"] = True
        with self.assertRaisesRegex(DrawError, "unknown"):
            DrawDecisionContinuation.from_dict(value)

        value = continuation().to_dict()
        value["after"]["unknown"] = True
        with self.assertRaisesRegex(DrawError, "unknown"):
            DrawDecisionContinuation.from_dict(value)

    def test_malformed_effect_list_and_selection_coercion_fail_closed(self):
        value = continuation().to_dict()
        value["effects"].append("not an effect")
        with self.assertRaisesRegex(DrawError, "effects must be objects"):
            DrawDecisionContinuation.from_dict(value)

        value = continuation().to_dict()
        value["selections"] = [1]
        with self.assertRaisesRegex(DrawError, "canonical strings"):
            DrawDecisionContinuation.from_dict(value)

    def test_resume_variants_reject_cross_shape_state(self):
        self.assertEqual(
            {"kind": "none"}, DrawResume.from_dict({"kind": "none"}).to_dict()
        )
        self.assertEqual(
            {"kind": "turn_draw", "seat": "A"},
            DrawResume.from_dict({"kind": "turn_draw", "seat": "A"}).to_dict(),
        )
        with self.assertRaisesRegex(DrawError, "unknown"):
            DrawResume.from_dict({"kind": "none", "seat": "A"})

    def test_draw_batch_resume_is_typed_strict_and_round_trips(self):
        resume = DrawResume(
            kind="draw_batch",
            draws=(
                QueuedDraw("B", 1, "B draws", True),
                QueuedDraw("C", 2, "C draws", False),
            ),
        )
        self.assertEqual(
            resume,
            DrawResume.from_dict(resume.to_dict()),
        )
        malformed = resume.to_dict()
        malformed["draws"][0]["count"] = "1"
        with self.assertRaisesRegex(DrawError, "nonnegative integer"):
            DrawResume.from_dict(malformed)
        with self.assertRaisesRegex(DrawError, "extra state"):
            DrawResume(
                kind="draw_batch",
                stack_ref="stack:wrong",
                draws=(QueuedDraw("A", 1, "draw"),),
            )


if __name__ == "__main__":
    unittest.main()
