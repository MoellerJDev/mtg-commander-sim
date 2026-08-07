from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from quorune import replacement_effects

from common import ROOT, keep_all, make_session
from property_budget import property_transitions
from scripts.build_test_database import build_fixture_database
from quorune.carddb import CardDatabase
from quorune.damage import (
    commit_prepared_damage_batch,
    damage_proposal,
    DamageEvent,
    DamageError,
    DamageRecipientSnapshot,
    prepare_damage_batch,
)
from quorune.deck import DeckLoader
from quorune.engine import GameRuleError
from quorune.model import CardInstance, StackItem
from quorune.projection import StateProjector
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from quorune.replacement_effects import (
    ReplacementChoiceRequired,
    resolve_replacements,
)
from quorune.semantic_runtime import (
    DamageQuantityReplacementHandler,
    DamageReplacementSourceContext,
    FixedDamagePreventionHandler,
    StaticDamageRedirectionHandler,
    SemanticNodeError,
    default_damage_replacement_registry,
)
from quorune.semantics import SemanticProgram


from damage_replacement_support import (
    DamageReplacementPipelineBase,
    damage_condition,
    prevention_descriptor,
    quantity_descriptor,
)


class DamageReplacementModelTests(DamageReplacementPipelineBase):
    """Focused CR 120/614/615/616 damage transaction witnesses."""

    def test_runtime_components_validate_exact_bounded_shapes(self):
        quantity = DamageQuantityReplacementHandler()
        prevention = FixedDamagePreventionHandler()
        context = DamageReplacementSourceContext(
            source_ref="replacement-source",
            source_controller="A",
        )

        doubled = quantity.replacement_effect(quantity_descriptor(), context)
        self.assertEqual("damage", doubled.event_kind)
        self.assertEqual(
            ({"op": "multiply", "field": "amount", "factor": 2},),
            tuple(operation.to_dict() for operation in doubled.operations),
        )
        fixed = prevention.replacement_effect(
            prevention_descriptor(amount=2), context
        )
        self.assertEqual(
            ({"op": "prevent", "amount": 2},),
            tuple(operation.to_dict() for operation in fixed.operations),
        )

        redirect = StaticDamageRedirectionHandler()
        destination = replacement_effects.RedirectDamage(
            target="C1",
            target_kind="permanent",
            target_controller="B",
            target_object_id="source-object",
            target_logical_object_id="source-incarnation",
            target_owner="B",
            target_types=("creature",),
        )
        redirected = redirect.replacement_effect(
            {
                "handler_id": redirect.handler_id,
                "schema_version": 1,
                "event": "damage",
                "condition": damage_condition(
                    target_controller_relation="source_controller",
                    target_kinds=["player"],
                ),
                "modification": {"destination": "source"},
            },
            DamageReplacementSourceContext(
                source_ref="C1",
                source_controller="B",
                source_destination=destination,
            ),
        )
        self.assertEqual(
            destination.to_dict(), redirected.operations[0].to_dict()
        )

        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            quantity.validate(quantity_descriptor(multiplier=0))
        with self.assertRaisesRegex(SemanticNodeError, "positive integer"):
            prevention.validate(prevention_descriptor(amount=0))
        malformed = quantity_descriptor()
        malformed["condition"]["combat"] = "sometimes"
        with self.assertRaisesRegex(SemanticNodeError, "boolean or null"):
            quantity.validate(malformed)
        malformed = prevention_descriptor()
        malformed["condition"]["unknown"] = True
        with self.assertRaisesRegex(SemanticNodeError, "unknown fields"):
            prevention.validate(malformed)

        inventory = default_damage_replacement_registry().inventory()
        self.assertEqual(
            [
                "prevention.damage.fixed.v1",
                "replacement.damage.quantity.v1",
                "replacement.damage.redirect-to-source.v1",
            ],
            sorted(item["handler_id"] for item in inventory),
        )


    def test_damage_value_objects_reject_unknown_recipient_kinds(self):
        with self.assertRaisesRegex(DamageError, "player or permanent"):
            DamageRecipientSnapshot(  # type: ignore[arg-type]
                ref="B",
                kind="battlefield",
                controller="B",
            )
        with self.assertRaisesRegex(ValueError, "player or permanent"):
            DamageEvent(  # type: ignore[arg-type]
                source="source",
                source_object_id="source-object",
                source_logical_object_id="source-incarnation",
                source_oracle_id=None,
                source_commander_designation_id=None,
                source_controller="A",
                source_owner="A",
                source_types=(),
                source_subtypes=(),
                source_colors=(),
                source_keywords=(),
                source_is_commander=False,
                target="B",
                target_kind="battlefield",
                target_object_id=None,
                target_controller="B",
                target_types=(),
                target_subtypes=(),
                assigned_amount=1,
                dealt_amount=1,
                prevented_amount=0,
                combat=False,
            )


    def test_prevention_to_zero_ends_the_damage_replacement_event(self):
        context = DamageReplacementSourceContext(
            source_ref="replacement-source",
            source_controller="A",
        )
        multiply = DamageQuantityReplacementHandler().replacement_effect(
            quantity_descriptor(multiplier=2), context
        )
        prevent = FixedDamagePreventionHandler().replacement_effect(
            prevention_descriptor(amount=1), context
        )

        resolved = resolve_replacements(
            self._property_event(1, 1208001),
            (multiply, prevent),
            selections=(prevent.effect_id,),
        )

        self.assertEqual(0, resolved.payload["amount"])
        self.assertEqual(1, resolved.payload["prevented"])
        self.assertEqual((prevent.effect_id,), resolved.applied_effects)


    def test_furnace_and_daunting_order_changes_final_damage(self):
        session = self.session(120461501)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        proposal = self.proposal(engine, source=source, target=defender)

        with self.assertRaises(ReplacementChoiceRequired) as required:
            prepare_damage_batch(engine, (proposal,))
        self.assertEqual("B", required.exception.pending.choice.chooser)
        options = required.exception.pending.choice.options
        furnace = next(value for value in options if "quantity" in value)
        prevention = next(value for value in options if "fixed" in value)

        prepared = prepare_damage_batch(
            engine,
            (proposal,),
            selections=(prevention,),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(4, result.events[0].dealt_amount)
        self.assertEqual(1, result.events[0].prevented_amount)
        self.assertEqual(3, result.events[0].assigned_amount)
        self.assertEqual(4, defender.marked_damage)

        defender.marked_damage = 0
        prepared = prepare_damage_batch(
            engine,
            (proposal,),
            selections=(furnace,),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(5, result.events[0].dealt_amount)
        self.assertEqual(1, result.events[0].prevented_amount)
        self.assertEqual(5, defender.marked_damage)


    def test_static_prevention_applies_to_each_simultaneous_event(self):
        session = self.session(120461502)
        engine = session.engine
        defender = self.add_permanent(
            engine,
            seat="B",
            name="Daunting Defender",
            ref="b-defender",
        )
        defender.counters["+1/+1"] = 5
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        proposals = (
            self.proposal(
                engine,
                source=source,
                target=defender,
                event_id="damage:one",
            ),
            self.proposal(
                engine,
                source=source,
                target=defender,
                event_id="damage:two",
            ),
        )

        prepared = prepare_damage_batch(engine, proposals)
        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual([2, 2], [event.dealt_amount for event in result.events])
        self.assertEqual([1, 1], [event.prevented_amount for event in result.events])
        self.assertEqual(4, defender.marked_damage)


    def test_unpreventable_damage_applies_prevention_without_reducing_damage(self):
        session = self.session(120461503)
        engine = session.engine
        defender = self.add_permanent(
            engine,
            seat="B",
            name="Daunting Defender",
            ref="b-defender",
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-source",
        )
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target=defender,
                    unpreventable=True,
                ),
            ),
        )
        result = commit_prepared_damage_batch(engine, prepared)
        event = result.events[0]
        self.assertEqual(3, event.dealt_amount)
        self.assertEqual(0, event.prevented_amount)
        self.assertTrue(event.unpreventable)
        self.assertEqual(1, len(event.applied_effects))


    def test_damage_amount_pipeline_property_1000_deterministic_transitions(self):
        quantity = DamageQuantityReplacementHandler()
        prevention = FixedDamagePreventionHandler()
        randomizer = random.Random(120461599)
        for index in range(property_transitions()):
            amount = randomizer.randint(1, 20)
            multiplier = randomizer.randint(2, 4)
            prevented = randomizer.randint(1, 8)
            context = DamageReplacementSourceContext(
                source_ref=f"source-{index}",
                source_controller="A",
            )
            multiply = quantity.replacement_effect(
                quantity_descriptor(multiplier=multiplier), context
            )
            prevent = prevention.replacement_effect(
                prevention_descriptor(amount=prevented), context
            )
            event = self._property_event(amount, index)
            first = resolve_replacements(
                event,
                (multiply, prevent),
                selections=(multiply.effect_id, prevent.effect_id),
            )
            second_selections = (
                (prevent.effect_id, multiply.effect_id)
                if prevented < amount
                else (prevent.effect_id,)
            )
            second = resolve_replacements(
                event,
                (multiply, prevent),
                selections=second_selections,
            )
            self.assertEqual(
                max(0, amount * multiplier - prevented),
                first.payload["amount"],
            )
            self.assertEqual(
                max(0, amount - prevented) * multiplier,
                second.payload["amount"],
            )



if __name__ == "__main__":
    unittest.main()
