from __future__ import annotations

from pathlib import Path
import random
import tempfile
import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import (
    commit_prepared_damage_batch,
    prepare_damage_batch,
    resolve_damage_batch,
)
from mtg_commander_sim.damage_modifier_state import (
    DamageModifierDuration,
    DamagePreventionShield,
    DamageSubject,
    GainLifePreventionAftermath,
    PlaceCountersPreventionAftermath,
    PreventionMode,
)
from mtg_commander_sim.damage_prevention_aftermath import (
    prevention_applications,
)
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement import ReplaceableEvent
from mtg_commander_sim.semantics import SemanticProgram


class DamagePreventionAftermathTests(DamageReplacementPipelineBase):
    def test_life_aftermath_uses_one_aggregate_prevented_amount(self):
        engine = self.session(615201, players=4).engine
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source-a"
        )
        source_c = self.add_permanent(
            engine, seat="C", name="Mishra, Eminent One", ref="source-c"
        )
        engine.state.players["B"].life = 30
        shield = DamagePreventionShield(
            shield_id="reverse-damage",
            source_id="fixture:reverse-damage",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.AMOUNT,
            remaining=10,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            aftermath=(
                GainLifePreventionAftermath(player="B", per_prevented=1),
            ),
        )
        engine.state.damage_prevention_shields.append(shield)

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source_a,
                    target="B",
                    amount=2,
                    event_id="damage:aftermath:a",
                ),
                self.proposal(
                    engine,
                    source=source_c,
                    target="B",
                    amount=3,
                    event_id="damage:aftermath:c",
                ),
            ),
        )

        self.assertEqual(35, engine.state.players["B"].life)
        self.assertEqual(1, len(result.aftermath_events))
        self.assertEqual(5, result.aftermath_events[0].prevented_amount)
        self.assertEqual(5, result.aftermath_events[0].applied_amount)
        self.assertEqual("gain_life", result.aftermath_events[0].kind)

    def test_counter_aftermath_reuses_counter_replacement_pipeline(self):
        engine = self.session(615202).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source"
        )
        target = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="target"
        )
        target.counters["+1/+1"] = 5
        self.add_permanent(
            engine, seat="B", name="Doubling Season", ref="doubling"
        )
        subject = DamageSubject(
            ref=target.ref,
            kind="permanent",
            controller="B",
            object_id=target.object_id,
            logical_object_id=target.logical_object_id,
            owner="B",
        )
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="test-of-faith",
                source_id="fixture:test-of-faith",
                controller="B",
                subject=subject,
                mode=PreventionMode.AMOUNT,
                remaining=2,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
                aftermath=(
                    PlaceCountersPreventionAftermath(
                        subject=subject,
                        counter_name="+1/+1",
                        placing_player="B",
                        per_prevented=1,
                    ),
                ),
            )
        )

        result = resolve_damage_batch(
            engine,
            (self.proposal(engine, source=source, target=target, amount=2),),
        )

        self.assertEqual(9, target.counters["+1/+1"])
        self.assertEqual(4, result.aftermath_events[0].applied_amount)
        self.assertEqual("place_counters", result.aftermath_events[0].kind)

    def test_fixed_additional_effect_happens_when_damage_cannot_be_prevented(self):
        engine = self.session(615203).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source"
        )
        engine.state.players["B"].life = 30
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="fixed-additional-effect",
                source_id="fixture:fixed-additional-effect",
                controller="B",
                subject=DamageSubject(ref="B", kind="player", controller="B"),
                mode=PreventionMode.NEXT_INSTANCE,
                remaining=None,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
                aftermath=(
                    GainLifePreventionAftermath(player="B", fixed_amount=3),
                ),
            )
        )

        result = resolve_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=source,
                    target="B",
                    amount=2,
                    unpreventable=True,
                ),
            ),
        )

        self.assertEqual(31, engine.state.players["B"].life)
        self.assertEqual((), result.prevention_events)
        self.assertEqual(3, result.aftermath_events[0].applied_amount)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

    def test_stale_counter_aftermath_fails_before_life_or_damage_mutation(self):
        engine = self.session(615204).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source"
        )
        target = self.add_permanent(
            engine, seat="B", name="Goblin Engineer", ref="target"
        )
        target.counters["+1/+1"] = 5
        subject = DamageSubject(
            ref=target.ref,
            kind="permanent",
            controller="B",
            object_id=target.object_id,
            logical_object_id=target.logical_object_id,
            owner="B",
        )
        engine.state.damage_prevention_shields.append(
            DamagePreventionShield(
                shield_id="compound",
                source_id="fixture:compound",
                controller="B",
                subject=subject,
                mode=PreventionMode.AMOUNT,
                remaining=2,
                duration=DamageModifierDuration.UNTIL_END_OF_TURN,
                created_turn_sequence=engine.state.turn_sequence,
                aftermath=(
                    GainLifePreventionAftermath(player="B", fixed_amount=3),
                    PlaceCountersPreventionAftermath(
                        subject=subject,
                        counter_name="+1/+1",
                        placing_player="B",
                        per_prevented=1,
                    ),
                ),
            )
        )
        before_life = engine.state.players["B"].life
        prepared = prepare_damage_batch(
            engine,
            (self.proposal(engine, source=source, target=target, amount=2),),
        )
        target.zone_change_counter += 1

        with self.assertRaisesRegex(ValueError, "identity|changed"):
            commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(before_life, engine.state.players["B"].life)
        self.assertEqual(5, target.counters["+1/+1"])
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

    def test_aggregate_aftermath_amount_property_over_simultaneous_events(self):
        engine = self.session(615205, players=4).engine
        shield = DamagePreventionShield(
            shield_id="aggregate-property",
            source_id="fixture:aggregate-property",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.AMOUNT,
            remaining=1000,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            aftermath=(
                GainLifePreventionAftermath(player="B", per_prevented=1),
            ),
        )
        engine.state.damage_prevention_shields.append(shield)
        rng = random.Random(615205)
        for case in range(64):
            amounts = [rng.randrange(0, 11) for _ in range(rng.randrange(1, 9))]
            events = tuple(
                ReplaceableEvent(
                    event_id=f"property:{case}:{index}",
                    kind="damage",
                    affected_player="B",
                    payload={
                        "amount": 0,
                        "prevention_applied": {shield.effect_id: amount},
                    },
                    applied_effects=(shield.effect_id,),
                )
                for index, amount in enumerate(amounts)
            )
            applications = prevention_applications(engine, events)
            self.assertEqual(1, len(applications))
            self.assertEqual(sum(amounts), applications[0].prevented_amount)
            self.assertEqual(
                len(amounts), len(applications[0].damage_event_ids)
            )

    def test_prevention_aftermath_replays_from_exact_commands(self):
        session = self.session(615512)
        engine = session.engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="damage-source"
        )
        shield = DamagePreventionShield(
            shield_id="aftermath-replay",
            source_id="fixture:aftermath-replay",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.AMOUNT,
            remaining=2,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            aftermath=(
                GainLifePreventionAftermath(player="B", per_prevented=1),
            ),
        )
        engine.state.damage_prevention_shields.append(shield)
        program = SemanticProgram(
            key="test:prevention-aftermath-replay",
            label="Replay prevention aftermath",
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "B",
                    "amount": 3,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="prevention-aftermath-replay",
                ref="S-prevention-aftermath-replay",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                source_object_id=source.object_id,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
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
            result = session.act(principal, {"action_id": "pass"})
            self.assertTrue(result.ok, result.summary)
        self.assertEqual(41, engine.state.players["B"].life)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "prevention-aftermath-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    unittest.main()
