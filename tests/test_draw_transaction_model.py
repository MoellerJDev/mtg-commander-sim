from __future__ import annotations

from dataclasses import replace
import unittest

from mtg_commander_sim.drawing import (
    DrawError,
    DrawEventRequest,
    DrawInstructionRequest,
    prepare_draw_event,
    prepare_draw_instruction,
    validate_prepared_draw,
)
from mtg_commander_sim.replacement import (
    DredgeDraw,
    MultiplyAmount,
    PreventDraw,
    ReplacementClass,
    ReplacementEffect,
    operation_from_dict,
    operation_to_dict,
)
from mtg_commander_sim.replacement.operations import ReplacementOperationError


ORDER = ("A", "B", "C", "D")


def dredge_effect(
    effect_id: str = "dredge:A17@2",
    *,
    source_ref: str = "A17",
    object_id: str = "object:A17",
    incarnation: int = 2,
    count: int = 3,
) -> ReplacementEffect:
    return ReplacementEffect(
        effect_id=effect_id,
        source_id=f"{object_id}@{incarnation}",
        event_kind="draw",
        replacement_class=ReplacementClass.OTHER,
        conditions={
            "is_draw": {"eq": True},
            "library_size": {"gte": count},
        },
        operations=(
            DredgeDraw(
                source_ref=source_ref,
                source_object_id=object_id,
                source_zone_change_counter=incarnation,
                mill_count=count,
            ),
        ),
        optional=True,
        label=f"Dredge {count} — {source_ref}",
    )


class DrawTransactionModelTests(unittest.TestCase):
    def test_instruction_count_is_replaced_before_individual_draws(self):
        request = DrawInstructionRequest(
            event_id="draw:instruction:1",
            player="B",
            count=3,
        )
        prepared = prepare_draw_instruction(
            request,
            apnap_order=ORDER,
            effects=(
                ReplacementEffect(
                    effect_id="double-draw-instruction",
                    source_id="fixture:double",
                    event_kind="draw.instruction",
                    replacement_class=ReplacementClass.OTHER,
                    conditions={"count": {"gt": 0}},
                    operations=(
                        MultiplyAmount(field="count", factor=2),
                    ),
                ),
            ),
        )

        self.assertEqual(3, request.count)
        self.assertEqual(6, prepared.count)
        self.assertEqual(3, prepared.event.payload["requested_count"])

    def test_draw_prevention_applies_even_to_an_empty_library(self):
        prepared = prepare_draw_event(
            DrawEventRequest("draw:event:empty", "A", 0),
            apnap_order=ORDER,
            effects=(
                ReplacementEffect(
                    effect_id="prevent-empty-draw",
                    source_id="fixture:prevention",
                    event_kind="draw",
                    replacement_class=ReplacementClass.OTHER,
                    conditions={"is_draw": {"eq": True}},
                    operations=(PreventDraw(),),
                ),
            ),
        )

        self.assertEqual("prevented", prepared.resolution.kind)
        self.assertFalse(prepared.event.payload["is_draw"])
        validate_prepared_draw(prepared, apnap_order=ORDER)

    def test_dredge_is_optional_and_resolves_through_a_typed_result(self):
        request = DrawEventRequest("draw:event:dredge", "A", 8)
        effect = dredge_effect()

        pending = prepare_draw_event(
            request,
            apnap_order=ORDER,
            effects=(effect,),
            require_all_selections=False,
        )
        self.assertEqual((effect.effect_id,), pending.pending.choice.options)
        self.assertEqual(
            (effect.effect_id,), pending.pending.choice.optional_options
        )

        prepared = prepare_draw_event(
            request,
            apnap_order=ORDER,
            effects=(effect,),
            selections=(effect.effect_id,),
        )
        resolution = prepared.resolution
        self.assertEqual("dredge", resolution.kind)
        self.assertEqual("A17", resolution.dredge_source_ref)
        self.assertEqual("object:A17", resolution.dredge_source_object_id)
        self.assertEqual(2, resolution.dredge_source_zone_change_counter)
        self.assertEqual(3, resolution.dredge_mill_count)
        validate_prepared_draw(prepared, apnap_order=ORDER)

    def test_dredge_with_too_few_library_cards_is_not_applicable(self):
        prepared = prepare_draw_event(
            DrawEventRequest("draw:event:short", "A", 2),
            apnap_order=ORDER,
            effects=(dredge_effect(count=3),),
        )

        self.assertEqual("draw", prepared.resolution.kind)
        self.assertTrue(prepared.event.payload["is_draw"])

    def test_canonical_decline_replays_as_an_ordinary_draw(self):
        request = DrawEventRequest("draw:event:decline", "A", 8)
        effect = dredge_effect()
        prepared = prepare_draw_event(
            request,
            apnap_order=ORDER,
            effects=(effect,),
            selections=(f"decline:{effect.effect_id}",),
        )

        self.assertEqual("draw", prepared.resolution.kind)
        self.assertEqual(
            f"decline:{effect.effect_id}", prepared.journal[0].effect_id
        )
        validate_prepared_draw(prepared, apnap_order=ORDER)

    def test_replacement_journal_tampering_fails_closed(self):
        request = DrawEventRequest("draw:event:journal", "A", 8)
        effect = dredge_effect()
        ordinary = prepare_draw_event(
            request,
            apnap_order=ORDER,
            effects=(effect,),
            selections=(f"decline:{effect.effect_id}",),
        )
        dredged = prepare_draw_event(
            request,
            apnap_order=ORDER,
            effects=(effect,),
            selections=(effect.effect_id,),
        )

        tampered = replace(ordinary, journal=dredged.journal)
        with self.assertRaisesRegex(DrawError, "journal changed"):
            validate_prepared_draw(tampered, apnap_order=ORDER)

    def test_draw_operations_round_trip_and_reject_coercion(self):
        operations = (
            PreventDraw(),
            DredgeDraw("A17", "object:A17", 4, 3),
        )
        for operation in operations:
            self.assertEqual(
                operation,
                operation_from_dict(operation_to_dict(operation)),
            )

        malformed = DredgeDraw("A17", "object:A17", 4, 3).to_dict()
        malformed["source_zone_change_counter"] = True
        with self.assertRaisesRegex(
            ReplacementOperationError,
            "zone-change counter",
        ):
            operation_from_dict(malformed)

    def test_invalid_request_types_fail_before_replacement_resolution(self):
        with self.assertRaisesRegex(DrawError, "nonnegative integer"):
            DrawInstructionRequest("draw:bad", "A", True)
        with self.assertRaisesRegex(DrawError, "nonempty string"):
            DrawEventRequest("draw:bad", 1, 0)


if __name__ == "__main__":
    unittest.main()
