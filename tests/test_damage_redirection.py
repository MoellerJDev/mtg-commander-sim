from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from quorune.damage import (
    commit_prepared_damage_batch,
    prepare_damage_batch,
)
from quorune.damage_prevention import (
    ChosenDamageSource,
    DamageModifierDuration,
    DamageRedirectionEffect,
    DamageSubject,
)
from quorune.model import StackItem
from quorune.oracle_ir import register_generated_programs
from quorune.record import checkpoint_envelope, replay_record
from quorune.rules.capabilities import (
    load_default_capability_registry,
)
from quorune.semantics import SemanticProgram


class DamageRedirectionTests(DamageReplacementPipelineBase):
    def palisade(self, engine, *, ref: str = "b-palisade"):
        record = self.db.lookup("Palisade Giant")
        register_generated_programs(
            self.db,
            engine.semantics,
            (record,),
            trust_level="trusted",
            capability_registry=load_default_capability_registry(),
            capability_profile="commander_review",
            promote_exact_runtime_handlers=True,
        )
        return self.add_permanent(
            engine, seat="B", name=record.name, ref=ref
        )

    def redirection(
        self,
        engine,
        *,
        subject: str = "B",
        destination: str = "C",
        chosen_source=None,
    ) -> DamageRedirectionEffect:
        effect = DamageRedirectionEffect(
            redirection_id="fixture-redirection",
            source_id="effect:fixture-redirection",
            controller="B",
            subject=DamageSubject(subject, "player", subject),
            destination=DamageSubject(destination, "player", destination),
            duration=DamageModifierDuration.UNTIL_END_OF_TURN,
            created_turn_sequence=engine.state.turn_sequence,
            chosen_source=chosen_source,
            label="Fixture redirection",
        )
        engine.state.damage_redirections.append(effect)
        return effect

    def test_redirection_replaces_complete_recipient_and_is_consumed(self):
        engine = self.session(614090, players=4).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        effect = self.redirection(engine)
        prepared = prepare_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=3),),
        )
        event = prepared.events[0]
        self.assertEqual("C", event.affected_player)
        self.assertEqual("C", event.payload["target"])
        self.assertEqual("C", event.payload["target_controller"])
        self.assertIn(effect.effect_id, event.applied_effects)
        self.assertEqual(1, len(engine.state.damage_redirections))

        result = commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(37, engine.state.players["C"].life)
        self.assertEqual("C", result.events[0].target)
        self.assertEqual([], engine.state.damage_redirections)

    def test_departed_destination_makes_redirection_do_nothing(self):
        engine = self.session(614091, players=4).engine
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        self.redirection(engine)
        engine.state.players["C"].in_game = False
        prepared = prepare_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=2),),
        )
        self.assertEqual("B", prepared.events[0].payload["target"])
        commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(38, engine.state.players["B"].life)
        self.assertEqual(1, len(engine.state.damage_redirections))

    def test_chosen_source_redirection_uses_physical_identity(self):
        engine = self.session(614092, players=4).engine
        chosen = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="chosen"
        )
        other = self.add_permanent(
            engine, seat="A", name="White Knight", ref="other"
        )
        self.redirection(
            engine,
            chosen_source=ChosenDamageSource(
                ref=chosen.ref,
                object_id=chosen.object_id,
            ),
        )

        first = prepare_damage_batch(
            engine,
            (self.proposal(engine, source=other, target="B", amount=1),),
        )
        commit_prepared_damage_batch(engine, first)
        self.assertEqual(39, engine.state.players["B"].life)
        self.assertEqual(40, engine.state.players["C"].life)
        self.assertEqual(1, len(engine.state.damage_redirections))

        second = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine,
                    source=chosen,
                    target="B",
                    amount=2,
                    event_id="damage:chosen",
                ),
            ),
        )
        commit_prepared_damage_batch(engine, second)
        self.assertEqual(39, engine.state.players["B"].life)
        self.assertEqual(38, engine.state.players["C"].life)

    def test_redirection_round_trip_rejects_unknown_fields(self):
        engine = self.session(614093, players=4).engine
        effect = self.redirection(engine)
        restored = DamageRedirectionEffect.from_dict(effect.to_dict())
        self.assertEqual(effect, restored)
        malformed = effect.to_dict()
        malformed["unknown"] = True
        with self.assertRaisesRegex(ValueError, "unknown"):
            DamageRedirectionEffect.from_dict(malformed)

    def test_static_redirection_compiles_and_runs_from_card_program(self):
        engine = self.session(614094, players=4).engine
        palisade = self.palisade(engine)
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        program = next(
            program
            for program in engine.semantics.programs_for_oracle(
                palisade.oracle_id
            )
            if program.handlers
        )
        self.assertEqual("trusted", program.trust_level)
        self.assertEqual(
            "replacement.damage.redirect-to-source.v1",
            program.handlers[0]["handler_id"],
        )

        result = commit_prepared_damage_batch(
            engine,
            prepare_damage_batch(
                engine,
                (self.proposal(engine, source=source, target="B", amount=3),),
            ),
        )
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(3, palisade.marked_damage)
        self.assertEqual(palisade.ref, result.events[0].target)

    def test_static_redirection_uses_complete_recipient_snapshot(self):
        engine = self.session(614095, players=4).engine
        palisade = self.palisade(engine)
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        prepared = prepare_damage_batch(
            engine,
            (self.proposal(engine, source=source, target="B", amount=2),),
        )
        event = prepared.events[0]
        self.assertIsNone(event.affected_player)
        self.assertEqual(palisade.object_id, event.affected_object.object_id)
        self.assertEqual(palisade.ref, event.payload["target"])
        self.assertEqual("permanent", event.payload["target_kind"])
        self.assertEqual(palisade.object_id, event.payload["target_object_id"])
        self.assertEqual(
            palisade.logical_object_id,
            event.payload["target_logical_object_id"],
        )
        self.assertIn("creature", event.payload["target_types"])

    def test_static_redirection_stops_when_source_leaves(self):
        engine = self.session(614096, players=4).engine
        palisade = self.palisade(engine)
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        engine.move_card(palisade.object_id, "graveyard", log=False)
        result = commit_prepared_damage_batch(
            engine,
            prepare_damage_batch(
                engine,
                (self.proposal(engine, source=source, target="B", amount=2),),
            ),
        )
        self.assertEqual(38, engine.state.players["B"].life)
        self.assertEqual("B", result.events[0].target)

    def test_static_redirection_does_not_replace_damage_to_its_source(self):
        engine = self.session(614099, players=4).engine
        palisade = self.palisade(engine)
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        prepared = prepare_damage_batch(
            engine,
            (
                self.proposal(
                    engine, source=source, target=palisade, amount=2
                ),
            ),
        )
        self.assertEqual((), prepared.events[0].applied_effects)
        commit_prepared_damage_batch(engine, prepared)
        self.assertEqual(2, palisade.marked_damage)

    def test_static_redirection_redirects_simultaneous_multiplayer_damage(self):
        engine = self.session(614097, players=4).engine
        palisade = self.palisade(engine)
        source_a = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        source_c = self.add_permanent(
            engine, seat="C", name="Mishra, Eminent One", ref="c-source"
        )
        result = commit_prepared_damage_batch(
            engine,
            prepare_damage_batch(
                engine,
                (
                    self.proposal(
                        engine,
                        source=source_a,
                        target="B",
                        amount=2,
                        event_id="damage:a",
                    ),
                    self.proposal(
                        engine,
                        source=source_c,
                        target="B",
                        amount=3,
                        event_id="damage:c",
                    ),
                ),
            ),
        )
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(5, palisade.marked_damage)
        self.assertEqual(
            [palisade.ref, palisade.ref],
            [event.target for event in result.events],
        )

    def test_static_redirection_command_replays_exactly(self):
        session = self.session(614098)
        engine = session.engine
        palisade = self.palisade(engine)
        source = self.add_permanent(
            engine, seat="A", name="Mishra, Eminent One", ref="a-source"
        )
        program = SemanticProgram(
            key="test:static-redirection-replay",
            label="Static redirection replay",
            effects=[
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "B",
                    "amount": 2,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="static-redirection-replay",
                ref="S-static-redirection-replay",
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
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(2, palisade.marked_damage)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "static-redirection-replay"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)


if __name__ == "__main__":
    unittest.main()
