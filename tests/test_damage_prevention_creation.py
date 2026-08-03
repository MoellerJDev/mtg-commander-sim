from __future__ import annotations

import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import resolve_damage_batch
from mtg_commander_sim.damage_modifier_state import (
    DamagePreventionShield,
    DamageModifierDuration,
    PreventionMode,
)
from mtg_commander_sim.damage_prevention_creation import (
    DealDamageAftermathRequest,
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
    def test_damage_aftermath_pins_source_lki_and_round_trips(self):
        engine = self.session(615115).engine
        prevention_source = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="palm"
        )
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id=prevention_source.ref,
                controller="B",
                mode=PreventionMode.NEXT_INSTANCE,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation("B", None),),
                aftermath=(
                    DealDamageAftermathRequest(
                        source_ref=prevention_source.ref,
                        recipient_kind="prevented_source_controller",
                        per_prevented=1,
                    ),
                ),
            ),
        )

        aftermath = plan.shields[0].aftermath[0]
        self.assertEqual("battlefield", aftermath.source.zone)
        self.assertEqual(
            prevention_source.logical_object_id,
            aftermath.source.logical_object_id,
        )
        self.assertEqual(
            plan.shields[0],
            DamagePreventionShield.from_dict(plan.shields[0].to_dict()),
        )

        isolated_payload = aftermath.source.to_dict()
        isolated = type(aftermath.source).from_dict(isolated_payload)
        isolated_payload["types"].append("mutated")
        self.assertNotIn("mutated", isolated.types)

        malformed = plan.shields[0].to_dict()
        malformed["aftermath"][0]["source"]["unknown"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            DamagePreventionShield.from_dict(malformed)

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

    def test_chosen_source_snapshot_is_canonical_and_does_not_follow_reentry(self):
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
        self.assertEqual(2, chosen.snapshot_version)
        self.assertEqual(source.logical_object_id, chosen.logical_object_id)
        self.assertEqual("battlefield", chosen.zone)
        self.assertIn("creature", chosen.types)

        restored = type(chosen).from_dict(chosen.to_dict())
        self.assertEqual(chosen, restored)
        commit_prevention_shield_creation(engine, plan)
        engine.move_card(source.object_id, "graveyard", log=False)
        engine.move_card(source.object_id, "battlefield", controller="A", log=False)

        result = resolve_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=1),),
        )
        self.assertEqual(1, result.dealt_amount)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

    def test_chosen_permanent_spell_continues_to_the_permanent_it_becomes(self):
        engine = self.session(615112).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source-spell"
        )
        engine._remove_from_zone(source)
        engine._reset_zone_change(source, "stack")
        source.zone = "stack"
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:permanent-spell",
                controller="B",
                mode=PreventionMode.NEXT_INSTANCE,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation("B", None),),
                chosen_source_ref=source.ref,
                required_source_types=("creature",),
            ),
        )
        chosen = plan.shields[0].chosen_source
        self.assertEqual(
            (
                f"{source.logical_object_id}|battlefield",
                f"{source.logical_object_id}|stack",
            ),
            chosen.identity_keys,
        )
        commit_prevention_shield_creation(engine, plan)
        engine.move_card(source.object_id, "battlefield", controller="A", log=False)

        result = resolve_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=1),),
        )
        self.assertEqual(0, result.dealt_amount)
        self.assertFalse(engine.state.damage_prevention_shields)

    def test_countered_chosen_permanent_spell_is_a_new_graveyard_object(self):
        engine = self.session(615113).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="countered-source"
        )
        engine._remove_from_zone(source)
        engine._reset_zone_change(source, "stack")
        source.zone = "stack"
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:countered-permanent-spell",
                controller="B",
                mode=PreventionMode.NEXT_INSTANCE,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation("B", None),),
                chosen_source_ref=source.ref,
            ),
        )
        commit_prevention_shield_creation(engine, plan)
        engine.move_card(source.object_id, "graveyard", log=False)

        result = resolve_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=1),),
        )

        self.assertEqual(1, result.dealt_amount)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

    def test_incarnation_safe_source_filters_are_rechecked_when_damage_happens(self):
        engine = self.session(615114).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="filtered-source"
        )
        plan = plan_prevention_shield_creation(
            engine,
            PreventionShieldCreationRequest(
                source_id="fixture:filtered-source",
                controller="B",
                mode=PreventionMode.NEXT_INSTANCE,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                subjects=(PreventionSubjectAllocation("B", None),),
                chosen_source_ref=source.ref,
                allowed_source_colors=("B", "R"),
                required_source_types=("creature",),
                required_source_subtypes=("artificer",),
                required_source_supertypes=("legendary",),
            ),
        )
        commit_prevention_shield_creation(engine, plan)

        source.annotations["copy_overrides"] = {
            "colors": ["G"],
            "type_line": "Legendary Artifact Creature — Artificer",
        }
        mismatch = resolve_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=1),),
        )
        self.assertEqual(1, mismatch.dealt_amount)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

        source.annotations.pop("copy_overrides")
        matching = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target="B",
                    amount=1,
                    event_id="damage:filtered-source-match",
                ),
            ),
        )
        self.assertEqual(0, matching.dealt_amount)
        self.assertFalse(engine.state.damage_prevention_shields)

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

    def test_runtime_lowers_typed_damage_aftermath_without_card_name_logic(self):
        engine = self.session(615116).engine
        original_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="original"
        )
        prevention_source = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="palm"
        )
        engine.apply_effect(
            {
                "op": "create_damage_prevention_shield",
                "source": prevention_source.ref,
                "subject": "B",
                "mode": "next_instance",
                "duration": "until_end_of_turn",
                "aftermath": [
                    {
                        "kind": "deal_damage",
                        "source": prevention_source.ref,
                        "recipient": None,
                        "recipient_kind": "prevented_source_controller",
                        "per_prevented": 1,
                        "fixed_amount": 0,
                    }
                ],
            },
            actor="B",
        )

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=original_source,
                    target="B",
                    amount=3,
                ),
            ),
        )

        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(37, engine.state.players["A"].life)
        self.assertEqual(3, result.nested_damage_results[0].dealt_amount)

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

    def test_source_choice_exposes_only_explicitly_referred_public_zone_objects(self):
        from mtg_commander_sim.object_query import ObjectQueryResult

        rows = (
            ObjectQueryResult(
                "referred-grave-id",
                "referred-grave-source",
                "Referred card",
                "A",
                "A",
                "graveyard",
            ),
            ObjectQueryResult(
                "unrelated-grave-id",
                "unrelated-grave-source",
                "Unrelated card",
                "A",
                "A",
                "graveyard",
            ),
            ObjectQueryResult(
                "hidden-id",
                "hidden-source",
                "Hidden card",
                "A",
                "A",
                "hand",
                known_to_actor=False,
            ),
        )
        query = SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"),
            active_order=("A", "B"),
            object_rows=rows,
            materialized_damage_source_candidates=(
                "referred-grave-source",
                "hidden-source",
            ),
        )

        prepared = ChooseDamageSourceHandler().prepare(
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
            ("referred-grave-source",),
            prepared.request.choice.legal_refs,
        )

    def test_materialized_empty_source_universe_does_not_use_legacy_fallback(self):
        from mtg_commander_sim.object_query import ObjectQueryResult

        query = SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"),
            active_order=("A", "B"),
            object_rows=(
                ObjectQueryResult(
                    "battlefield-id",
                    "battlefield-source",
                    "Unsupported face-down source",
                    "A",
                    "A",
                    "battlefield",
                ),
            ),
            materialized_damage_source_candidates=(),
        )

        with self.assertRaisesRegex(
            SemanticChoiceError,
            "No legally known damage source",
        ):
            ChooseDamageSourceHandler().prepare(
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

    def test_source_choice_any_color_and_extended_characteristics_are_exact(self):
        from mtg_commander_sim.object_query import ObjectQueryResult

        matching = ObjectQueryResult(
            "matching-id",
            "matching-source",
            "Matching source",
            "A",
            "A",
            "battlefield",
            types=("creature",),
            subtypes=("wizard",),
            supertypes=("legendary",),
            colors=("B",),
            keywords=("flying",),
        )
        wrong_color = ObjectQueryResult(
            "wrong-color-id",
            "wrong-color-source",
            "Wrong color",
            "A",
            "A",
            "battlefield",
            types=("creature",),
            subtypes=("wizard",),
            supertypes=("legendary",),
            colors=("G",),
            keywords=("flying",),
        )
        query = SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"),
            active_order=("A", "B"),
            object_rows=(matching, wrong_color),
        )
        prepared = ChooseDamageSourceHandler().prepare(
            {
                "op": "choose_damage_source",
                "allowed_colors": ["B", "R"],
                "required_types": ["creature"],
                "required_subtypes": ["wizard"],
                "required_supertypes": ["legendary"],
                "required_keywords": ["flying"],
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
            ("matching-source",), prepared.request.choice.legal_refs
        )
        completion = ChooseDamageSourceHandler().complete(
            self._continuation(prepared.continuation_effect),
            {"source": "matching-source"},
            query,
        )
        effect = completion.prepend_effects[0]
        self.assertEqual(("B", "R"), effect["source_colors_any"])
        self.assertEqual(("wizard",), effect["source_subtypes"])
        self.assertEqual(("legendary",), effect["source_supertypes"])
        self.assertEqual(("flying",), effect["source_keywords"])


if __name__ == "__main__":
    unittest.main()
