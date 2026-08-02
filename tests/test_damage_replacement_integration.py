from __future__ import annotations

import json
from pathlib import Path
import random
import tempfile
import unittest

from common import ROOT, keep_all, make_session
from scripts.build_test_database import build_fixture_database
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.damage import (
    commit_prepared_damage_batch,
    damage_proposal,
    DamageEvent,
    DamageError,
    DamageRecipientSnapshot,
    prepare_damage_batch,
)
from mtg_commander_sim.deck import DeckLoader
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.model import CardInstance, StackItem
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement_effects import (
    ReplacementChoiceRequired,
    resolve_replacements,
)
from mtg_commander_sim.semantic_runtime import (
    DamageQuantityReplacementHandler,
    DamageReplacementSourceContext,
    FixedDamagePreventionHandler,
    SemanticNodeError,
    default_damage_replacement_registry,
)
from mtg_commander_sim.semantics import SemanticProgram


from damage_replacement_support import (
    DamageReplacementPipelineBase,
    damage_condition,
    prevention_descriptor,
    quantity_descriptor,
)


class DamageReplacementIntegrationTests(DamageReplacementPipelineBase):
    """Focused CR 120/614/615/616 damage transaction witnesses."""

    def test_damage_fidelity_pause_stops_remaining_resolution_effects(self):
        session = self.session(120461515)
        engine = session.engine
        engine.state.config.semantic_policy = "trusted_only"
        monitor_ref = engine.create_token(
            "A",
            name="Untrusted Damage Monitor",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
            },
        )[0]
        monitor = engine._resolve_object(
            "A", monitor_ref, zones={"battlefield"}
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"{monitor.oracle_id}:test:untrusted-damage",
                label="Untrusted damage trigger",
                oracle_id=monitor.oracle_id,
                ability_id="test:untrusted-damage",
                active_zone="battlefield",
                event="damage.dealt",
                effects=[],
                trust_level="provisional",
            )
        )
        source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-pause-source",
        )
        item = StackItem(
            stack_id="damage-pause-resolution",
            ref="S-damage-pause-resolution",
            kind="triggered_ability",
            controller="A",
            label="Damage then gain life",
            source_object_id=source.object_id,
            visibility=["A", "B"],
        )
        engine.state.stack.append(item)
        life_before = engine.state.players["B"].life

        engine._continue_resolution(
            stack_ref=item.ref,
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "B",
                    "amount": 1,
                },
                {"op": "life", "player": "B", "delta": 5},
            ],
            destination=None,
            note="fidelity stop witness",
        )

        self.assertEqual(life_before - 1, engine.state.players["B"].life)
        self.assertIsNotNone(engine._semantic_pause_annotation())
        self.assertIn(item, engine.state.stack)


    def test_infect_creature_result_commits_with_other_damage_atomically(self):
        session = self.session(120461509)
        engine = session.engine
        normal_source = self.add_permanent(
            engine,
            seat="A",
            name="Mishra, Eminent One",
            ref="a-normal-source",
        )
        target = self.add_permanent(
            engine,
            seat="B",
            name="White Knight",
            ref="b-target",
        )
        infect_ref = engine.create_token(
            "A",
            name="Infect Source",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "1",
                "toughness": "1",
                "keywords": ["Infect"],
                "colors": ["G"],
            },
        )[0]
        infect_source = engine._resolve_object(
            "A", infect_ref, zones={"battlefield"}
        )
        life_before = engine.state.players["B"].life
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=normal_source,
                    target="B",
                    event_id="damage:valid-first",
                ),
                self.proposal(
                    engine,
                    source=infect_source,
                    target=target,
                    amount=1,
                    event_id="damage:infect-second",
                ),
            ),
        )

        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(life_before - 3, engine.state.players["B"].life)
        self.assertEqual(0, target.marked_damage)
        self.assertEqual(1, target.counters["-1/-1"])
        self.assertEqual(4, result.dealt_amount)
        self.assertEqual(
            {"life.change", "counter.place"},
            {event.kind for event in result.result_events},
        )


    def test_mana_ability_damage_uses_transaction_or_fails_before_damage(self):
        session = self.session(120461510)
        engine = session.engine
        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace-one",
        )
        source = self.add_permanent(
            engine,
            seat="B",
            name="Elves of Deep Shadow",
            ref="b-pain-source",
        )
        life_before = engine.state.players["B"].life

        engine._apply_mana_mode_side_effects(
            "B",
            ({"op": "damage_self", "amount": 1},),
            source=source,
        )
        self.assertEqual(life_before - 2, engine.state.players["B"].life)

        self.add_permanent(
            engine,
            seat="A",
            name="Furnace of Rath",
            ref="a-furnace-two",
        )
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "B"
        engine.state.priority_passes = []
        engine.state.players["B"].turns_begun = (
            source.acquired_control_turn_count + 1
        )
        ability = next(
            candidate
            for candidate in engine._activated_abilities(source)
            if "Add {B}" in candidate.effect_text
        )
        before_rejected_choice = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(GameRuleError, "not yet resumable"):
            with engine.transaction():
                engine._activate(
                    "B",
                    {
                        "source": source.ref,
                        "ability": ability.ability_id,
                        "mana_output": {"B": 1},
                    },
                )
        self.assertEqual(
            before_rejected_choice, authoritative_state_hash(engine.state)
        )
        self.assertFalse(engine.state.cards[source.object_id].tapped)
        self.assertEqual(0, engine.state.players["B"].mana_pool["B"])


    def test_validation_failure_is_atomic_before_any_damage_result(self):
        session = self.session(120461504)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(DamageError, "selections"):
            prepare_damage_batch(
                engine,
                (
                    self.proposal(
                        engine,
                        source=source,
                        target=defender,
                        amount=0,
                    ),
                ),
                selections=("not-applicable",),
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))


    def test_combat_replacement_choice_is_seat_scoped_and_precommit(self):
        session = self.session(120461505)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        life_before = engine.state.players["B"].life

        waiting = engine._apply_combat_assignments(
            [{"source": source.ref, "target": defender.ref, "amount": 3}]
        )
        self.assertTrue(waiting)
        self.assertEqual(0, defender.marked_damage)
        self.assertEqual(life_before, engine.state.players["B"].life)
        decision = engine.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual("replacement.order", decision.kind)
        self.assertEqual(["B"], decision.actors)

        projector = StateProjector(self.db, engine.state)
        projected_b = projector._decision("pilot:B")
        self.assertIsNotNone(projected_b)
        self.assertIsNone(projector._decision("pilot:A"))
        serialized = json.dumps(projected_b, sort_keys=True)
        self.assertNotIn("replacement_batch", serialized)
        self.assertNotIn("replacement_effects", serialized)
        self.assertNotIn(defender.object_id, serialized)

        selected = next(
            option["id"]
            for option in projected_b["ctx"]["options"]
            if "fixed" in option["id"]
        )
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()
        accepted = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choices": {"replacement": selected},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.assertEqual(4, defender.marked_damage)
        self.assertIsNotNone(engine.state.pending_decision)
        self.assertEqual("priority", engine.state.pending_decision.kind)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-damage-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])


    def test_semantic_damage_replacement_choice_replays_exactly(self):
        session = self.session(120461506)
        engine = session.engine
        _furnace, defender, source = self.stage_sources(engine)
        program = SemanticProgram(
            key="test:damage-replacement-replay",
            label="Replay a damage replacement choice",
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": defender.ref,
                    "amount": 3,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="damage-replacement-replay",
                ref="S-damage-replacement-replay",
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
        self.assertEqual(
            "replacement.order", engine.state.pending_decision.kind
        )
        projected = StateProjector(self.db, engine.state)._decision("pilot:B")
        selected = next(
            option["id"]
            for option in projected["ctx"]["options"]
            if "fixed" in option["id"]
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choices": {"replacement": selected},
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(4, defender.marked_damage)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "damage-replacement-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(3, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])



if __name__ == "__main__":
    unittest.main()
