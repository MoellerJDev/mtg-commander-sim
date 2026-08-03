from __future__ import annotations

import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import resolve_damage_batch
from mtg_commander_sim.damage_modifier_state import (
    DamageModifierDuration,
    PreventionMode,
)
from mtg_commander_sim.damage_prevention_creation import (
    PreventionShieldCreationRequest,
    PreventionSubjectAllocation,
    commit_prevention_shield_creation,
    plan_prevention_shield_creation,
)
from mtg_commander_sim.errors import GameRuleError
from mtg_commander_sim.semantic_choices.context import (
    SemanticChoiceContext,
    SnapshotSemanticChoiceQuery,
)
from mtg_commander_sim.semantic_choices.damage_prevention import (
    ChooseDamageSourceHandler,
)
from mtg_commander_sim.semantic_choices.model import (
    SemanticChoiceContinuation,
    SemanticChoiceFrame,
    SemanticChoiceError,
)
from mtg_commander_sim.replacement.immutable import FrozenMap


class DamagePreventionCreationTests(DamageReplacementPipelineBase):
    def test_dynamic_amount_and_divided_allocations_create_independent_shields(self):
        engine = self.session(615101).engine
        first = self.add_permanent(
            engine, seat="B", name="White Knight", ref="first-creature"
        )
        second = self.add_permanent(
            engine, seat="B", name="Daunting Defender", ref="second-creature"
        )
        request = PreventionShieldCreationRequest(
            source_id="fixture:embolden",
            controller="B",
            mode=PreventionMode.AMOUNT,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            subjects=(
                PreventionSubjectAllocation(first.ref, 1),
                PreventionSubjectAllocation(second.ref, 3),
            ),
            label="Divide four damage",
        )

        plan = plan_prevention_shield_creation(engine, request)
        self.assertEqual([], engine.state.damage_prevention_shields)
        self.assertEqual((1, 3), tuple(shield.remaining for shield in plan.shields))
        self.assertEqual(2, len({shield.shield_id for shield in plan.shields}))

        committed = commit_prevention_shield_creation(engine, plan)
        self.assertEqual(plan.shields, committed)
        self.assertEqual(
            [first.object_id, second.object_id],
            [shield.subject.object_id for shield in committed],
        )

    def test_one_amount_is_applied_independently_to_each_selected_object(self):
        engine = self.session(615102).engine
        first = self.add_permanent(
            engine, seat="B", name="White Knight", ref="first-creature"
        )
        second = self.add_permanent(
            engine, seat="B", name="Daunting Defender", ref="second-creature"
        )
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:wojek",
                controller="B",
                mode=PreventionMode.AMOUNT,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(
                    PreventionSubjectAllocation(first.ref, 2),
                    PreventionSubjectAllocation(second.ref, 2),
                ),
            ),
        )
        commit_prevention_shield_creation(engine, plan)

        self.assertEqual([2, 2], [shield.remaining for shield in plan.shields])
        self.assertNotEqual(plan.shields[0].shield_id, plan.shields[1].shield_id)

    def test_creation_plan_is_stale_if_subject_changes_object_identity(self):
        engine = self.session(615103).engine
        creature = self.add_permanent(
            engine, seat="B", name="White Knight", ref="protected-creature"
        )
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:shield",
                controller="B",
                mode=PreventionMode.AMOUNT,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation(creature.ref, 2),),
            ),
        )
        creature.zone_change_counter += 1

        with self.assertRaisesRegex(ValueError, "identity"):
            commit_prevention_shield_creation(engine, plan)
        self.assertEqual([], engine.state.damage_prevention_shields)

    def test_chosen_source_snapshot_is_canonical_and_survives_zone_change(self):
        engine = self.session(615104).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="chosen-source"
        )
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:reverse-damage",
                controller="B",
                mode=PreventionMode.NEXT_INSTANCE,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation("B", None),),
                chosen_source_ref=source.ref,
                required_source_types=("creature",),
            ),
        )
        chosen = plan.shields[0].chosen_source
        self.assertIsNotNone(chosen)
        self.assertEqual(1, chosen.snapshot_version)
        self.assertEqual(source.logical_object_id, chosen.logical_object_id)
        self.assertEqual("battlefield", chosen.zone)
        self.assertIn("creature", chosen.types)

        restored = type(chosen).from_dict(chosen.to_dict())
        self.assertEqual(chosen, restored)
        source.zone = "graveyard"
        commit_prevention_shield_creation(engine, plan)
        self.assertEqual(source.object_id, plan.shields[0].chosen_source.object_id)

    def test_runtime_division_requires_the_exact_resolved_total(self):
        engine = self.session(615105).engine
        first = self.add_permanent(
            engine, seat="B", name="White Knight", ref="first-creature"
        )
        second = self.add_permanent(
            engine, seat="B", name="Daunting Defender", ref="second-creature"
        )
        effect = {
            "op": "create_damage_prevention_shield",
            "source": "fixture:division",
            "mode": "amount",
            "amount": 4,
            "allocations": {first.ref: 1, second.ref: 2},
            "duration": "until_end_of_turn",
        }
        with self.assertRaisesRegex(GameRuleError, "equal"):
            engine.apply_effect(effect, actor="B")
        self.assertFalse(engine.state.damage_prevention_shields)

        effect["allocations"][second.ref] = 3
        engine.apply_effect(effect, actor="B")
        self.assertEqual(
            [1, 3],
            [shield.remaining for shield in engine.state.damage_prevention_shields],
        )

    def test_runtime_shared_color_selector_creates_one_shield_per_creature(self):
        engine = self.session(615106).engine
        anchor = self.add_permanent(
            engine, seat="B", name="White Knight", ref="anchor-creature"
        )
        shared = self.add_permanent(
            engine, seat="B", name="Daunting Defender", ref="shared-creature"
        )
        excluded = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="excluded-creature"
        )
        engine.apply_effect(
            {
                "op": "create_damage_prevention_shield",
                "source": "fixture:radiance",
                "selector": {
                    "kind": "shares_color_with",
                    "anchor": anchor.ref,
                    "types_all": ["creature"],
                },
                "mode": "amount",
                "amount": 1,
                "duration": "until_end_of_turn",
            },
            actor="B",
        )
        protected = {
            shield.subject.object_id
            for shield in engine.state.damage_prevention_shields
        }
        self.assertEqual({anchor.object_id, shared.object_id}, protected)
        self.assertNotIn(excluded.object_id, protected)

    def test_each_untargeted_creature_uses_its_own_prevention_shield(self):
        engine = self.session(615111).engine
        def creature(seat: str, name: str):
            ref = engine.create_token(
                seat,
                name=name,
                characteristics={
                    "type_line": "Token Creature — Test",
                    "power": "2",
                    "toughness": "4",
                },
            )[0]
            return engine._resolve_object(seat, ref, zones={"battlefield"})

        first = creature("B", "First protected creature")
        second = creature("B", "Second protected creature")
        source = creature("A", "Damage source")
        engine.apply_effect(
            {
                "op": "create_damage_prevention_shield",
                "source": "fixture:each-creature",
                "subjects": [first.ref, second.ref],
                "mode": "amount",
                "amount": 1,
                "duration": "until_end_of_turn",
            },
            actor="B",
        )

        first_result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target=first,
                    amount=2,
                    event_id="damage:first-creature",
                ),
            ),
        )
        second_result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target=second,
                    amount=2,
                    event_id="damage:second-creature",
                ),
            ),
        )

        self.assertEqual(1, first_result.dealt_amount)
        self.assertEqual(1, second_result.dealt_amount)
        self.assertEqual(1, first.marked_damage)
        self.assertEqual(1, second.marked_damage)
        self.assertFalse(engine.state.damage_prevention_shields)


class DamageSourceChoiceHandlerTests(unittest.TestCase):
    @staticmethod
    def _context(query: SnapshotSemanticChoiceQuery) -> SemanticChoiceContext:
        return SemanticChoiceContext(
            actor="B",
            stack_ref="STACK1",
            stack_controller="B",
            stack_label="Choose a source",
            source_ref="shield-spell",
            card_ref="shield-spell",
            semantic_program_id="fixture:prevention",
            semantic_program_version=1,
            query=query,
        )

    @staticmethod
    def _continuation(effect: FrozenMap) -> SemanticChoiceContinuation:
        return SemanticChoiceContinuation(
            handler_id="choice.damage.choose-source.v1",
            handler_version=1,
            stack_ref="STACK1",
            effect=effect,
            remaining=(),
            destination="graveyard",
            note="",
            semantic_frame=SemanticChoiceFrame(
                semantic_program_id="fixture:prevention",
                semantic_program_version=1,
                stack_object="STACK1",
                instruction_pointer=0,
                controller="B",
            ),
        )

    def test_source_choice_exposes_only_rule_legal_public_candidates(self):
        from mtg_commander_sim.object_query import ObjectQueryResult

        rows = (
            ObjectQueryResult("battlefield-id", "battlefield-source", "Source", "A", "A", "battlefield"),
            ObjectQueryResult("stack-id", "stack-source", "Spell", "A", "A", "stack"),
            ObjectQueryResult("command-id", "command-source", "Commander", "A", "A", "command"),
            ObjectQueryResult("grave-id", "grave-source", "Old card", "A", "A", "graveyard"),
            ObjectQueryResult("hidden-id", "hidden-source", "Hidden", "A", "A", "hand", known_to_actor=False),
        )
        query = SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"),
            active_order=("A", "B"),
            object_rows=rows,
        )
        handler = ChooseDamageSourceHandler()
        prepared = handler.prepare(
            {
                "op": "choose_damage_source",
                "shield": {
                    "op": "create_damage_prevention_shield",
                    "source": "shield-spell",
                    "subject": "B",
                    "mode": "next_instance",
                    "duration": "until_end_of_turn",
                },
            },
            self._context(query),
        )

        self.assertEqual(
            ("battlefield-source", "command-source", "stack-source"),
            prepared.request.choice.legal_refs,
        )
        serialized = str(prepared.request.payload())
        self.assertNotIn("hidden", serialized)
        self.assertNotIn("grave-source", serialized)

    def test_source_choice_revalidates_and_prepends_resolved_shield(self):
        from mtg_commander_sim.object_query import ObjectQueryResult

        row = ObjectQueryResult(
            "source-id", "chosen-source", "Source", "A", "A", "battlefield",
            types=("creature",), colors=("U",),
        )
        query = SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"), active_order=("A", "B"), object_rows=(row,)
        )
        handler = ChooseDamageSourceHandler()
        prepared = handler.prepare(
            {
                "op": "choose_damage_source",
                "required_types": ["creature"],
                "required_colors": ["U"],
                "shield": {
                    "op": "create_damage_prevention_shield",
                    "source": "shield-spell",
                    "subject": "B",
                    "mode": "next_instance",
                    "duration": "until_end_of_turn",
                },
            },
            self._context(query),
        )
        completion = handler.complete(
            self._continuation(prepared.continuation_effect),
            {"source": "chosen-source"},
            query,
        )
        self.assertEqual("chosen-source", completion.prepend_effects[0]["chosen_source"])
        self.assertEqual(("U",), completion.prepend_effects[0]["source_colors"])

        with self.assertRaises(SemanticChoiceError):
            handler.complete(
                self._continuation(prepared.continuation_effect),
                {"source": "not-legal"},
                query,
            )


if __name__ == "__main__":
    unittest.main()
