from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import damage_proposal, resolve_damage_batch
from mtg_commander_sim.damage_prevention import (
    expire_end_of_turn_damage_modifiers,
)
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.oracle_ir import (
    compile_oracle_card,
    register_generated_programs,
)
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantics import SemanticProgram


_ORACLE_TEXT = (
    "Prevent the next 3 damage that would be dealt to any target this turn "
    "by a source of your choice. You gain 3 life."
)


class PreventionImmediateSequencingTests(DamageReplacementPipelineBase):
    def _compiled_node(self):
        return compile_oracle_card(
            replace(
                self.db.lookup("Force of Vigor"),
                oracle_id="fixture:fixed-independent-prevention-life",
                name="Fixture Prevention Sequence",
                oracle_text=_ORACLE_TEXT,
            )
        ).faces[0].nodes[0]

    def _stack_program(self, engine, target_ref: str):
        node = self._compiled_node()
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and card.is_card_object
            and card.zone not in {"command", "outside"}
        )
        engine._remove_from_zone(source)
        engine._reset_zone_change(source, "stack")
        source.zone = "stack"
        source.controller = "A"
        source.known_to = list(engine.seats)
        source.revealed_to = list(engine.seats)
        key = "test:prevention-immediate-sequence"
        program = SemanticProgram(
            key=key,
            label="Fixture prevention and immediate life",
            effects=[dict(effect) for effect in node.effects],
            destination="graveyard",
            target_schema=dict(node.target_schema or {}),
        )
        engine.semantics.put(program)
        selected, grouped = engine._validate_semantic_targets(
            "A",
            program,
            [target_ref],
            source_ref=source.ref,
        )
        item = StackItem(
            stack_id=uuid.uuid4().hex,
            ref="S-prevention-immediate-sequence",
            kind="spell",
            controller="A",
            label=program.label,
            card_object_id=source.object_id,
            semantic_key=key,
            targets=selected,
            default_destination="graveyard",
            visibility=list(engine.seats),
            context={
                "target_groups": grouped,
                "target_snapshots": {
                    ref: engine._target_snapshot(ref) for ref in selected
                },
                "targets_revalidated": False,
            },
        )
        engine.state.stack.append(item)
        return source, item, program

    @staticmethod
    def _choose_source(session, source_ref: str):
        return session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "source": source_ref,
                "plan": "PROTECT_LIFE",
                "reason": "Choose the public source required by the spell.",
            },
        )

    def _begin_successful_resolution(self, seed: int):
        session = self.session(seed)
        engine = session.engine
        engine.state.players["A"].life = 30
        chosen = self.add_permanent(
            engine,
            seat="B",
            name="Mishra, Eminent One",
            ref=f"chosen-source-{seed}",
        )
        _source, item, program = self._stack_program(engine, "A")
        engine._begin_resolve_item(
            item,
            program.effects,
            program.destination,
            note="fixed independent life sequencing",
        )
        self.assertEqual("semantic.choice", engine.state.pending_decision.kind)
        return session, chosen

    def test_life_is_gained_immediately_and_unused_shield_remains(self):
        session, chosen = self._begin_successful_resolution(615301)
        engine = session.engine

        result = self._choose_source(session, chosen.ref)

        self.assertTrue(result.ok, result.summary)
        self.assertEqual(33, engine.state.players["A"].life)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))
        shield = engine.state.damage_prevention_shields[0]
        self.assertEqual(3, shield.remaining)
        self.assertEqual((), shield.aftermath)
        self.assertFalse(
            any(
                event.code == "damage.prevention.aftermath"
                for event in engine.state.events
            )
        )

    def test_later_damage_uses_shield_without_gaining_life_again(self):
        session, chosen = self._begin_successful_resolution(615302)
        engine = session.engine
        result = self._choose_source(session, chosen.ref)
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(33, engine.state.players["A"].life)

        damage = resolve_damage_batch(
            engine,
            (
                damage_proposal(
                    engine,
                    proposal_id="damage:fixed-independent-life",
                    actor="B",
                    source_ref=chosen.ref,
                    target="A",
                    amount=2,
                    combat=False,
                    reason="later chosen-source damage",
                ),
            ),
        )

        self.assertEqual(0, damage.dealt_amount)
        self.assertEqual(2, damage.events[0].prevented_amount)
        self.assertEqual((), damage.aftermath_events)
        self.assertEqual(33, engine.state.players["A"].life)

    def test_unused_shield_expiration_does_not_control_life_gain(self):
        session, chosen = self._begin_successful_resolution(615303)
        engine = session.engine
        result = self._choose_source(session, chosen.ref)
        self.assertTrue(result.ok, result.summary)

        expired = expire_end_of_turn_damage_modifiers(engine.state)

        self.assertTrue(expired)
        self.assertFalse(engine.state.damage_prevention_shields)
        self.assertEqual(33, engine.state.players["A"].life)

    def test_immediate_life_gain_uses_static_replacement_once(self):
        session, chosen = self._begin_successful_resolution(615304)
        engine = session.engine
        boon = self.add_permanent(
            engine,
            seat="A",
            name="Boon Reflection",
            ref="a-boon-immediate-life",
        )
        register_generated_programs(
            self.db,
            engine.semantics,
            (self.db.lookup(boon.printed_name),),
            capability_registry=load_default_capability_registry(),
            capability_profile="commander_review",
            promote_exact_runtime_handlers=True,
        )

        result = self._choose_source(session, chosen.ref)

        self.assertTrue(result.ok, result.summary)
        self.assertEqual(36, engine.state.players["A"].life)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))
        self.assertEqual((), engine.state.damage_prevention_shields[0].aftermath)
        replacements = [
            event
            for event in engine.state.events
            if event.code == "replacement.apply"
            and "life.gain.multiplier" in str(event.details.get("effect_id"))
        ]
        self.assertEqual(1, len(replacements))
        life_event = next(
            event
            for event in engine.state.events
            if event.code == "effect.life"
        )
        self.assertNotEqual(chosen.ref, life_event.details["source"])
        life_source = next(
            card
            for card in engine.state.cards.values()
            if card.ref == life_event.details["source"]
        )
        self.assertEqual("A", life_source.owner)
        self.assertEqual("graveyard", life_source.zone)
        self.assertEqual("spell_resolution", life_event.details["cause"])
        self.assertEqual(3, life_event.details["requested_delta"])
        self.assertEqual(6, life_event.details["delta"])
        self.assertEqual(
            [
                {
                    "event_id": life_event.details["life_events"][0][
                        "event_id"
                    ],
                    "path": [],
                    "chooser": "A",
                    "effect_id": replacements[0].details["effect_id"],
                }
            ],
            life_event.details["replacement_journal"],
        )

    def test_all_targets_illegal_stops_before_choice_shield_and_life(self):
        session = self.session(615305)
        engine = session.engine
        engine.state.players["A"].life = 30
        target = self.add_permanent(
            engine,
            seat="B",
            name="Goblin Engineer",
            ref="doomed-prevention-target",
        )
        _source, item, program = self._stack_program(engine, target.ref)
        engine.move_card(target.object_id, "graveyard", reason="response", log=False)

        engine._begin_resolve_item(
            item,
            program.effects,
            program.destination,
            note="all targets illegal",
        )

        self.assertIsNone(engine.state.pending_decision)
        self.assertFalse(engine.state.damage_prevention_shields)
        self.assertEqual(30, engine.state.players["A"].life)

    def test_all_targets_illegal_resolution_mutant_is_killed(self):
        def assert_resolution_stops() -> None:
            session = self.session(615_307)
            engine = session.engine
            engine.state.players["A"].life = 30
            target = self.add_permanent(
                engine,
                seat="B",
                name="Goblin Engineer",
                ref="mutation-doomed-prevention-target",
            )
            _source, item, program = self._stack_program(engine, target.ref)
            engine.move_card(
                target.object_id,
                "graveyard",
                reason="response",
                log=False,
            )
            engine._begin_resolve_item(
                item,
                program.effects,
                program.destination,
                note="all-targets-illegal mutation witness",
            )
            self.assertIsNone(engine.state.pending_decision)
            self.assertFalse(engine.state.damage_prevention_shields)
            self.assertEqual(30, engine.state.players["A"].life)

        assert_resolution_stops()
        with patch(
            "mtg_commander_sim.engine.CommanderEngine."
            "_revalidate_resolution_targets",
            return_value=True,
        ):
            with self.assertRaises(AssertionError):
                assert_resolution_stops()

    def test_source_choice_resume_replays_sibling_life_once_and_stays_private(self):
        session, chosen = self._begin_successful_resolution(615306)
        engine = session.engine
        hidden = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B" and card.zone == "hand"
        )
        packet_a = session.packet("pilot:A", full=True)
        packet_b = session.packet("pilot:B", full=True)
        self.assertEqual("semantic.choice", packet_a["decision"]["kind"])
        self.assertIsNone(packet_b["decision"])
        self.assertNotIn(hidden.ref, str(packet_a))

        session.commands.clear()
        session.decisions.clear()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        result = self._choose_source(session, chosen.ref)
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(33, engine.state.players["A"].life)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "prevention-immediate-sequence"
            session.save(record)
            replay = replay_record(record, self.db, verify=True)

        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    unittest.main()
