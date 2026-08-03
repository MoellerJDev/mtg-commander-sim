from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.damage import commit_prepared_damage_batch, prepare_damage_batch
from mtg_commander_sim.damage_modifier_state import (
    DamageModifierDuration,
    DamagePreventionShield,
    DamageSubject,
    PreventionMode,
)
from mtg_commander_sim.replacement_effects import ReplacementChoiceRequired
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class ReplacementEventOrderingTests(DamageReplacementPipelineBase):
    def test_chooser_selects_which_simultaneous_event_uses_next_instance_shield(self):
        engine = self.session(616101, players=4).engine
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source-a"
        )
        source_c = self.add_permanent(
            engine, seat="C", name="Mishra, Eminent One", ref="source-c"
        )
        shield = DamagePreventionShield(
            shield_id="next-instance",
            source_id="fixture:next-instance",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.NEXT_INSTANCE,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
        )
        engine.state.damage_prevention_shields.append(shield)
        proposals = (
            self.proposal(
                engine,
                source=source_a,
                target="B",
                amount=2,
                event_id="damage:event-a",
            ),
            self.proposal(
                engine,
                source=source_c,
                target="B",
                amount=3,
                event_id="damage:event-c",
            ),
        )

        with self.assertRaises(ReplacementChoiceRequired) as required:
            prepare_damage_batch(engine, proposals)
        pending = required.exception.pending
        self.assertEqual(
            ("damage:event-a", "damage:event-c"),
            pending.event_order_options,
        )

        prepared = prepare_damage_batch(
            engine,
            proposals,
            selections=(
                {
                    "event_id": "damage:event-c",
                    "effect_id": shield.effect_id,
                },
            ),
        )
        self.assertEqual(
            [2, 0], [event.payload["amount"] for event in prepared.events]
        )
        self.assertEqual("damage:event-c", prepared.journal[0].event_id)
        self.assertEqual(1, len(prepared.journal))

        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(38, engine.state.players["B"].life)
        self.assertEqual([], engine.state.damage_prevention_shields)
        self.assertEqual([0, 3], [event.prevented_amount for event in result.events])

    def test_event_order_selection_fails_closed_for_unknown_event(self):
        engine = self.session(616102, players=4).engine
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source-a"
        )
        source_c = self.add_permanent(
            engine, seat="C", name="Mishra, Eminent One", ref="source-c"
        )
        shield = DamagePreventionShield(
            shield_id="next-instance",
            source_id="fixture:next-instance",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.NEXT_INSTANCE,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
        )
        engine.state.damage_prevention_shields.append(shield)
        proposals = (
            self.proposal(engine, source=source_a, target="B", event_id="damage:a"),
            self.proposal(engine, source=source_c, target="B", event_id="damage:c"),
        )

        with self.assertRaisesRegex(ValueError, "event"):
            prepare_damage_batch(
                engine,
                proposals,
                selections=(
                    {
                        "event_id": "damage:tampered",
                        "effect_id": shield.effect_id,
                    },
                ),
            )
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(1, len(engine.state.damage_prevention_shields))

    def test_combat_event_order_is_seat_scoped_and_replays_exactly(self):
        session = self.session(616103, players=4)
        engine = session.engine
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="source-a"
        )
        source_b = self.add_permanent(
            engine, seat="A", name="White Knight", ref="source-b"
        )
        shield = DamagePreventionShield(
            shield_id="next-instance-replay",
            source_id="fixture:next-instance-replay",
            controller="B",
            subject=DamageSubject(ref="B", kind="player", controller="B"),
            mode=PreventionMode.NEXT_INSTANCE,
            remaining=None,
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
        )
        engine.state.damage_prevention_shields.append(shield)
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"

        waiting = engine._apply_combat_assignments(
            [
                {"source": source_a.ref, "target": "B", "amount": 2},
                {"source": source_b.ref, "target": "B", "amount": 3},
            ]
        )
        self.assertTrue(waiting)
        self.assertEqual("replacement.order", engine.state.pending_decision.kind)
        self.assertEqual(["B"], engine.state.pending_decision.actors)
        packet_b = session.packet("pilot:B", full=True)
        self.assertIsNone(session.packet("pilot:A", full=True)["decision"])
        event_ids = packet_b["decision"]["ctx"]["event_order_options"]
        self.assertEqual(2, len(event_ids))
        selected_event = event_ids[1]
        selected_effect = packet_b["decision"]["ctx"]["options"][0]["id"]
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choices": {
                    "replacement": selected_effect,
                    "replacement_event": selected_event,
                },
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(38, engine.state.players["B"].life)
        self.assertFalse(engine.state.damage_prevention_shields)
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "combat-event-order"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    unittest.main()
