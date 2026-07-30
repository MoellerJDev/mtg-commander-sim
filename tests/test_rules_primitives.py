from __future__ import annotations

import random
import unittest

from mtg_commander_sim.continuous_effects import (
    CharacteristicState,
    ContinuousEffect,
    ContinuousOperation,
    Layer,
    evaluate_continuous_effects,
    order_continuous_effects,
)
from mtg_commander_sim.replacement_effects import (
    ReplaceableEvent,
    ReplacementClass,
    ReplacementEffect,
    ReplacementEffectError,
    apply_replacement,
    replacement_choice,
    resolve_replacements,
)


def effect(
    effect_id,
    layer,
    sublayer,
    timestamp,
    op,
    value,
    *,
    depends_on=(),
    source_present=True,
):
    return ContinuousEffect(
        effect_id=effect_id,
        source_id=f"source:{effect_id}",
        layer=layer,
        sublayer=sublayer,
        timestamp=timestamp,
        operations=(ContinuousOperation(op, value),),
        depends_on=depends_on,
        source_present=source_present,
    )


class ContinuousLayerTests(unittest.TestCase):
    def test_layer_order_dominates_timestamp(self):
        values = [
            effect(
                "ability",
                Layer.ABILITY,
                "6",
                1,
                "add_ability",
                "Flying",
            ),
            effect(
                "copy",
                Layer.COPY,
                "1a",
                99,
                "copy_values",
                {"name": "Copied", "abilities": []},
            ),
            effect(
                "type",
                Layer.TYPE,
                "4",
                50,
                "add_types",
                ["Artifact"],
            ),
        ]
        result = evaluate_continuous_effects(
            CharacteristicState(
                name="Original",
                card_types={"Creature"},
            ),
            reversed(values),
        )
        self.assertEqual(
            ("copy", "type", "ability"),
            result.applied_effects,
        )
        self.assertEqual("Copied", result.characteristics["name"])
        self.assertEqual(
            ["Artifact", "Creature"],
            result.characteristics["card_types"],
        )
        self.assertEqual(
            ["Flying"], result.characteristics["abilities"]
        )

    def test_power_toughness_sublayers_set_modify_then_switch(self):
        result = evaluate_continuous_effects(
            CharacteristicState(
                name="Creature",
                card_types={"Creature"},
                power=1,
                toughness=4,
            ),
            [
                effect(
                    "switch",
                    Layer.POWER_TOUGHNESS,
                    "7d",
                    1,
                    "switch_power_toughness",
                    None,
                ),
                effect(
                    "modify",
                    Layer.POWER_TOUGHNESS,
                    "7c",
                    3,
                    "modify_power_toughness",
                    [1, -1],
                ),
                effect(
                    "set",
                    Layer.POWER_TOUGHNESS,
                    "7b",
                    8,
                    "set_power_toughness",
                    [2, 5],
                ),
            ],
        )
        self.assertEqual(4, result.characteristics["power"])
        self.assertEqual(3, result.characteristics["toughness"])

    def test_dependency_overrides_timestamp_and_cycles_are_audited(self):
        dependent = effect(
            "dependent",
            Layer.COLOR,
            "5",
            1,
            "set_colors",
            ["U"],
            depends_on=("base",),
        )
        base = effect(
            "base",
            Layer.COLOR,
            "5",
            20,
            "set_colors",
            ["G"],
        )
        ordered, cycles = order_continuous_effects(
            [dependent, base]
        )
        self.assertEqual(["base", "dependent"], [
            value.effect_id for value in ordered
        ])
        self.assertFalse(cycles)

        left = effect(
            "left",
            Layer.COLOR,
            "5",
            2,
            "set_colors",
            ["W"],
            depends_on=("right",),
        )
        right = effect(
            "right",
            Layer.COLOR,
            "5",
            1,
            "set_colors",
            ["B"],
            depends_on=("left",),
        )
        ordered, cycles = order_continuous_effects([left, right])
        self.assertEqual(["right", "left"], [
            value.effect_id for value in ordered
        ])
        self.assertEqual([("right", "left")], cycles)

    def test_absent_source_and_predicate_are_inapplicable(self):
        result = evaluate_continuous_effects(
            CharacteristicState(
                name="Object",
                card_types={"Artifact"},
            ),
            [
                effect(
                    "gone",
                    Layer.ABILITY,
                    "6",
                    1,
                    "add_ability",
                    "Hexproof",
                    source_present=False,
                ),
                ContinuousEffect(
                    effect_id="creatures",
                    source_id="source:creatures",
                    layer=Layer.ABILITY,
                    sublayer="6",
                    timestamp=2,
                    operations=(
                        ContinuousOperation(
                            "add_ability", "Vigilance"
                        ),
                    ),
                    applies={
                        "card_types": {"contains": "Creature"}
                    },
                ),
            ],
        )
        self.assertEqual(
            ("gone", "creatures"), result.inapplicable_effects
        )
        self.assertFalse(result.characteristics["abilities"])

    def test_effect_order_is_stable_under_input_mutation(self):
        values = [
            effect(
                f"e{index}",
                Layer.ABILITY,
                "6",
                index,
                "add_ability",
                f"Ability {index}",
            )
            for index in range(30)
        ]
        expected = [value.effect_id for value in values]
        randomizer = random.Random(613)
        for _ in range(50):
            randomizer.shuffle(values)
            ordered, cycles = order_continuous_effects(values)
            self.assertEqual(
                expected, [value.effect_id for value in ordered]
            )
            self.assertFalse(cycles)


class ReplacementOrderingTests(unittest.TestCase):
    def setUp(self):
        self.event = ReplaceableEvent(
            event_id="event:1",
            kind="zone_change",
            affected_player="A",
            payload={
                "card": "A01",
                "from": "battlefield",
                "destination": "graveyard",
            },
        )

    @staticmethod
    def replacement(
        effect_id,
        replacement_class,
        destination,
        *,
        optional=False,
    ):
        return ReplacementEffect(
            effect_id=effect_id,
            source_id=f"source:{effect_id}",
            event_kind="zone_change",
            replacement_class=replacement_class,
            operations=(
                {
                    "op": "set",
                    "field": "destination",
                    "value": destination,
                },
            ),
            optional=optional,
        )

    def test_self_replacement_must_be_chosen_before_other_effects(self):
        effects = [
            self.replacement(
                "other", ReplacementClass.OTHER, "exile"
            ),
            self.replacement(
                "self",
                ReplacementClass.SELF_REPLACEMENT,
                "library",
            ),
        ]
        choice = replacement_choice(self.event, effects)
        self.assertEqual("A", choice.chooser)
        self.assertEqual(("self",), choice.options)
        changed = apply_replacement(choice, effects, "self")
        next_choice = replacement_choice(changed, effects)
        self.assertEqual(("other",), next_choice.options)

    def test_each_effect_applies_at_most_once_to_one_event(self):
        effects = [
            self.replacement(
                "first", ReplacementClass.OTHER, "exile"
            ),
            self.replacement(
                "second", ReplacementClass.OTHER, "library"
            ),
        ]
        changed = resolve_replacements(
            self.event,
            effects,
            selections=["first", "second"],
        )
        self.assertEqual("library", changed.payload["destination"])
        self.assertEqual(
            ("first", "second"), changed.applied_effects
        )
        self.assertIsNone(replacement_choice(changed, effects))

    def test_optional_decline_is_recorded_and_not_offered_again(self):
        optional = self.replacement(
            "optional",
            ReplacementClass.OTHER,
            "exile",
            optional=True,
        )
        changed = resolve_replacements(
            self.event,
            [optional],
            selections=[None],
        )
        self.assertEqual(
            "graveyard", changed.payload["destination"]
        )
        self.assertEqual(("optional",), changed.applied_effects)

    def test_mandatory_replacement_cannot_be_declined(self):
        mandatory = self.replacement(
            "mandatory",
            ReplacementClass.OTHER,
            "exile",
        )
        choice = replacement_choice(self.event, [mandatory])
        with self.assertRaises(ReplacementEffectError):
            apply_replacement(choice, [mandatory], None)

    def test_prevention_never_prevents_more_than_remaining_damage(self):
        event = ReplaceableEvent(
            event_id="damage:1",
            kind="damage",
            affected_player="B",
            payload={"amount": 2},
        )
        prevention = ReplacementEffect(
            effect_id="prevent",
            source_id="shield",
            event_kind="damage",
            replacement_class=ReplacementClass.OTHER,
            operations=({"op": "prevent", "amount": 5},),
        )
        changed = resolve_replacements(
            event, [prevention], selections=["prevent"]
        )
        self.assertEqual(0, changed.payload["amount"])
        self.assertEqual(2, changed.payload["prevented"])


if __name__ == "__main__":
    unittest.main()
