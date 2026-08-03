from __future__ import annotations

import copy
from pathlib import Path
import tempfile

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import resolve_damage_batch, source_snapshot
from mtg_commander_sim.damage_modifier_state import (
    DamageModifierDuration,
    DamagePreventionShield,
    DamageSubject,
    PreventionMode,
)
from mtg_commander_sim.model import GameState
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.prevention_triggers import (
    DealDamagePreventionTrigger,
    DrawCardsPreventionTrigger,
    PlaceCountersPreventionTrigger,
    PreventionTriggeredAbility,
    PreventionTriggerError,
    prevention_trigger_result_from_dict,
)
from mtg_commander_sim.trigger_processing import begin_pending_trigger_batch
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.semantics import SemanticProgram


class PreventionTriggerStackTests(DamageReplacementPipelineBase):
    def _ability(self, engine, source, *, player: str = "B"):
        pinned = source_snapshot(
            engine,
            source.ref,
            controller=source.controller,
        )
        return PreventionTriggeredAbility(
            controller=source.controller,
            source=pinned,
            label="Damage prevented this way",
            results=(
                DealDamagePreventionTrigger(
                    source=pinned,
                    recipient_kind="prevented_source_controller",
                    per_prevented=1,
                ),
                DrawCardsPreventionTrigger(
                    player=player,
                    per_prevented=1,
                ),
            ),
        )

    def _shield(
        self,
        engine,
        prevention_source,
        *,
        shield_id: str = "prevention-trigger",
        subject: DamageSubject | None = None,
        mode: PreventionMode = PreventionMode.NEXT_INSTANCE,
    ) -> DamagePreventionShield:
        shield = DamagePreventionShield(
            shield_id=shield_id,
            source_id=prevention_source.ref,
            controller=prevention_source.controller,
            subject=subject
            or DamageSubject(ref="B", kind="player", controller="B"),
            mode=mode,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            label="Prevent that damage",
            triggered_ability=self._ability(engine, prevention_source),
        )
        engine.state.damage_prevention_shields.append(shield)
        return shield

    def test_trigger_model_is_immutable_strict_and_checkpoint_safe(self):
        engine = self.session(615601).engine
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="new-way-forward",
        )
        target_schema = {
            "zones": ["player", "battlefield"],
            "categories": ["player", "permanent"],
            "predicate": "damageable",
            "count": 1,
        }
        pinned = source_snapshot(engine, prevention_source.ref, controller="B")
        ability = PreventionTriggeredAbility(
            controller="B",
            source=pinned,
            label="Prevented-damage trigger",
            results=(
                DealDamagePreventionTrigger(
                    source=pinned,
                    recipient_kind="selected_target",
                    per_prevented=1,
                ),
            ),
            target_schema=target_schema,
        )
        target_schema["zones"].append("graveyard")
        self.assertEqual(
            ["player", "battlefield"],
            ability.to_dict()["target_schema"]["zones"],
        )

        shield = DamagePreventionShield(
            shield_id="serialized-trigger",
            source_id=prevention_source.ref,
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.ALL,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            triggered_ability=ability,
        )
        engine.state.damage_prevention_shields.append(shield)
        restored = GameState.from_dict(copy.deepcopy(engine.state.to_dict()))
        self.assertEqual(
            shield.to_dict(), restored.damage_prevention_shields[0].to_dict()
        )

        malformed = ability.to_dict()
        malformed["unexpected"] = True
        with self.assertRaises(PreventionTriggerError):
            PreventionTriggeredAbility.from_dict(malformed)

        malformed = ability.to_dict()
        malformed["controller"] = 7
        with self.assertRaises(PreventionTriggerError):
            PreventionTriggeredAbility.from_dict(malformed)

        malformed_result = DrawCardsPreventionTrigger(
            player="B", fixed_amount=1
        ).to_dict()
        malformed_result["player"] = True
        with self.assertRaises(PreventionTriggerError):
            prevention_trigger_result_from_dict(malformed_result)

        with self.assertRaises(PreventionTriggerError):
            PlaceCountersPreventionTrigger(
                subject_ref="B",
                counter_name=1,  # type: ignore[arg-type]
                placing_player="B",
                fixed_amount=1,
            )

    def test_one_trigger_is_created_per_effect_for_simultaneous_damage(self):
        engine = self.session(615602, players=4).engine
        damage_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="prevention-source",
        )
        self._shield(
            engine,
            prevention_source,
            subject=DamageSubject(ref="*", kind="any", controller="B"),
            mode=PreventionMode.ALL,
        )

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=damage_source,
                    target="B",
                    amount=2,
                    event_id="damage:simultaneous:b",
                ),
                self.proposal(
                    engine,
                    source=damage_source,
                    target="D",
                    amount=3,
                    event_id="damage:simultaneous:d",
                ),
            ),
        )

        self.assertEqual(1, len(result.prevention_events))
        self.assertEqual(5, result.prevention_events[0].prevented_amount)
        waiting = [
            item
            for batch in engine.state.pending_trigger_batches
            for group in batch["groups"]
            for item in group["items"]
            if item["label"] == "Damage prevented this way"
        ]
        self.assertEqual(1, len(waiting))
        self.assertEqual(5, waiting[0]["context"]["prevented_amount"])
        self.assertEqual(
            ["damage:simultaneous:b", "damage:simultaneous:d"],
            waiting[0]["context"]["damage_event_ids"],
        )

    def test_unpreventable_damage_creates_no_prevention_trigger(self):
        engine = self.session(615603).engine
        damage_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="prevention-source",
        )
        self._shield(engine, prevention_source)

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=damage_source,
                    target="B",
                    amount=4,
                    event_id="damage:unpreventable",
                    unpreventable=True,
                ),
            ),
        )

        self.assertEqual((), result.prevention_events)
        self.assertEqual([], engine.state.pending_trigger_batches)
        self.assertEqual(36, engine.state.players["B"].life)

    def test_four_player_apnap_preserves_created_controller_after_control_change(self):
        engine = self.session(615609, players=4).engine
        engine.state.active_player = "A"
        damage_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        source_b = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="prevention-b"
        )
        source_d = self.add_permanent(
            engine, seat="D", name="Goblin Engineer", ref="prevention-d"
        )
        self._shield(
            engine,
            source_b,
            shield_id="prevention-trigger-b",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.ALL,
        )
        self._shield(
            engine,
            source_d,
            shield_id="prevention-trigger-d",
            subject=DamageSubject(ref="D", kind="player", controller="D"),
            mode=PreventionMode.ALL,
        )
        engine.change_control(
            source_b.object_id,
            "C",
            reason="prevention trigger controller characterization",
        )

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=damage_source,
                    target="B",
                    amount=2,
                    event_id="damage:apnap:b",
                ),
                self.proposal(
                    engine,
                    source=damage_source,
                    target="D",
                    amount=3,
                    event_id="damage:apnap:d",
                ),
            ),
        )

        self.assertEqual(2, len(result.prevention_events))
        groups = engine.state.pending_trigger_batches[0]["groups"]
        self.assertEqual(["B", "D"], [group["controller"] for group in groups])
        self.assertEqual("C", source_b.controller)
        self.assertEqual(
            "B",
            next(
                item["controller"]
                for group in groups
                for item in group["items"]
                if item["source_object_id"] == source_b.object_id
            ),
        )

    def test_general_prevention_trigger_uses_affected_player_condition(self):
        engine = self.session(615606, players=4).engine
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        monitor_b = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="monitor-b"
        )
        monitor_c = self.add_permanent(
            engine, seat="C", name="Goblin Engineer", ref="monitor-c"
        )
        engine.semantics.put(
            SemanticProgram(
                key=(
                    f"{monitor_b.oracle_id}:"
                    "test:affected-player-prevention"
                ),
                label="Damage to this controller was prevented",
                oracle_id=monitor_b.oracle_id,
                ability_id="test:affected-player-prevention",
                active_zone="battlefield",
                event="damage.prevented",
                event_condition={
                    "field": "affected_players",
                    "op": "contains_any",
                    "value": ["$source.controller"],
                },
                effects=[
                    {
                        "op": "counter",
                        "card": "$source",
                        "counter": "+1/+1",
                        "delta": "$context.prevented_amount",
                        "source": "$source",
                    }
                ],
            )
        )
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="general-prevention-trigger",
                source_id=monitor_b.ref,
                controller="B",
                subject=DamageSubject(ref="B", kind="player", controller="B"),
                mode=PreventionMode.ALL,
                remaining=None,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
            )
        )

        resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source_a,
                    target="B",
                    amount=3,
                    event_id="damage:general-prevention-trigger",
                ),
            ),
        )

        waiting = [
            item
            for batch in engine.state.pending_trigger_batches
            for group in batch["groups"]
            for item in group["items"]
            if item["label"] == "Damage to this controller was prevented"
        ]
        self.assertEqual(1, len(waiting))
        self.assertEqual("B", waiting[0]["controller"])
        self.assertEqual(monitor_b.object_id, waiting[0]["source_object_id"])
        self.assertNotEqual(monitor_c.object_id, waiting[0]["source_object_id"])
        self.assertFalse(begin_pending_trigger_batch(engine))
        self.assertEqual(1, len(engine.state.stack))
        engine._prepare_stack_resolution()
        self.assertEqual(3, monitor_b.counters["+1/+1"])
        self.assertEqual(0, monitor_c.counters.get("+1/+1", 0))

    def test_targeted_prevention_trigger_chooses_target_when_put_on_stack(self):
        engine = self.session(615607).engine
        damage_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="targeted-prevention-source",
        )
        pinned = source_snapshot(
            engine,
            prevention_source.ref,
            controller=prevention_source.controller,
        )
        ability = PreventionTriggeredAbility(
            controller="B",
            source=pinned,
            label="Deal prevented damage to any target",
            results=(
                DealDamagePreventionTrigger(
                    source=pinned,
                    recipient_kind="selected_target",
                    per_prevented=1,
                ),
            ),
            target_schema={
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            },
        )
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="targeted-prevention-trigger",
                source_id=prevention_source.ref,
                controller="B",
                subject=DamageSubject(ref="B", kind="player", controller="B"),
                mode=PreventionMode.ALL,
                remaining=None,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
                triggered_ability=ability,
            )
        )

        resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=damage_source,
                    target="B",
                    amount=3,
                    event_id="damage:targeted-prevention-trigger",
                ),
            ),
        )
        self.assertFalse(begin_pending_trigger_batch(engine))
        self.assertTrue(engine._begin_pending_trigger_target_selection())
        self.assertEqual("semantic.target", engine.state.pending_decision.kind)
        hidden_ref = engine.state.cards[
            engine.state.players["A"].zones["hand"][0]
        ].ref
        self.assertIn(
            "A",
            engine.state.pending_decision.payload_by_actor["B"][
                "target_schema"
            ]["legal_refs"],
        )
        self.assertNotIn(
            hidden_ref,
            engine.state.pending_decision.payload_by_actor["B"][
                "target_schema"
            ]["legal_refs"],
        )

        capability = engine.permissions.capability_for("pilot:B")
        self.assertIsNotNone(capability)
        response = engine.submit(
            token=capability.token,
            principal="pilot:B",
            action="choose",
            payload={"targets": ["A"]},
        )
        self.assertTrue(response.ok, response.summary)
        self.assertEqual(["A"], engine.state.stack[-1].targets)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine._prepare_stack_resolution()
        self.assertEqual(37, engine.state.players["A"].life)
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual([], engine.state.stack)

    def test_runtime_lowers_trigger_descriptor_and_rejects_bad_shape_atomically(self):
        engine = self.session(615605).engine
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="prevention-source",
        )
        effect = {
            "op": "create_damage_prevention_shield",
            "source": prevention_source.ref,
            "subject": "B",
            "mode": "next_instance",
            "duration": "until_end_of_turn",
            "triggered_ability": {
                "source": prevention_source.ref,
                "label": "When damage is prevented this way",
                "target_schema": {},
                "results": [
                    {
                        "kind": "draw_cards",
                        "player": "B",
                        "per_prevented": 1,
                        "fixed_amount": 0,
                        "private": True,
                    }
                ],
            },
        }
        malformed = copy.deepcopy(effect)
        malformed["triggered_ability"]["unexpected"] = True
        with self.assertRaises(GameRuleError):
            engine.apply_effect(malformed, actor="B")
        self.assertEqual([], engine.state.damage_prevention_shields)

        engine.apply_effect(effect, actor="B")
        self.assertEqual(1, len(engine.state.damage_prevention_shields))
        trigger = engine.state.damage_prevention_shields[0].triggered_ability
        self.assertIsNotNone(trigger)
        self.assertEqual(
            "draw_cards", trigger.results[0].to_dict()["kind"]
        )

    def test_damage_result_rejects_mismatched_source_lki_before_mutation(self):
        engine = self.session(615608).engine
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="prevention-source",
        )
        pinned = source_snapshot(engine, prevention_source.ref, controller="B")

        with self.assertRaises(GameRuleError):
            engine.apply_effect(
                {
                    "op": "damage",
                    "source": "different-source",
                    "source_snapshot": pinned.to_dict(),
                    "target": "A",
                    "amount": 3,
                },
                actor="B",
            )

        self.assertEqual(40, engine.state.players["A"].life)

    def test_trigger_uses_source_lki_resolves_on_stack_and_replays(self):
        session = self.session(615604)
        engine = session.engine
        damage_source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        prevention_source = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="new-way-forward",
        )
        self._shield(engine, prevention_source)
        engine.move_card(prevention_source.object_id, "graveyard", log=False)
        hand_before = len(engine.state.players["B"].zones["hand"])

        resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=damage_source,
                    target="B",
                    amount=4,
                    event_id="damage:new-way-forward",
                ),
            ),
        )
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(40, engine.state.players["A"].life)
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="nested-trigger-damage-prevention",
                source_id=damage_source.ref,
                controller="A",
                subject=DamageSubject(ref="A", kind="player", controller="A"),
                mode=PreventionMode.NEXT_INSTANCE,
                remaining=None,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
            )
        )
        self.assertFalse(begin_pending_trigger_batch(engine))
        self.assertEqual(1, len(engine.state.stack))
        item = engine.state.stack[-1]
        self.assertEqual(
            "battlefield",
            item.context["dynamic_effects"][0]["source_snapshot"]["zone"],
        )

        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in ("pilot:A", "pilot:B"):
            response = session.act(principal, {"action_id": "pass"})
            self.assertTrue(response.ok, response.summary)

        self.assertEqual(40, engine.state.players["A"].life)
        self.assertEqual(
            hand_before + 4,
            len(engine.state.players["B"].zones["hand"]),
        )
        self.assertEqual([], engine.state.stack)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "prevention-trigger-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    import unittest

    unittest.main()
