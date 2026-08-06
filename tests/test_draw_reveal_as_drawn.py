from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from common import keep_all, load_assets, make_session

from mtg_commander_sim.cast_timing import type_line_has_card_type
from mtg_commander_sim.drawing import (
    DrawError,
    RevealDrawnCardBySource,
    drawn_card_action_from_dict,
)
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement import (
    PreventDraw,
    ReplacementClass,
    ReplacementEffect,
)
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.semantic_runtime import (
    DRAW_REVEAL_FIRST_HANDLER_ID,
    DrawRevealFirstHandler,
    DrawRevealSourceContext,
)
from mtg_commander_sim.semantic_runtime.context import SemanticNodeError
from mtg_commander_sim.semantics import SemanticProgram


def reveal_descriptor(
    *, optional: bool = False, turn_relation: str = "any"
) -> dict:
    return {
        "handler_id": DRAW_REVEAL_FIRST_HANDLER_ID,
        "schema_version": 1,
        "event": "draw.reveal_as_drawn",
        "condition": {
            "affected_player_relation": "source_controller",
            "turn_relation": turn_relation,
            "draw_ordinal": 1,
        },
        "reveal": {"optional": optional, "public": True},
    }


def reveal_context(
    *, ordinal: int = 1, player: str = "A", active: str = "A"
) -> DrawRevealSourceContext:
    return DrawRevealSourceContext(
        source_object_id="object:A11",
        source_ref="A11",
        source_logical_object_id="object:A11@2",
        source_zone_change_counter=2,
        source_controller="A",
        prospective_player=player,
        active_player=active,
        draw_ordinal=ordinal,
        component_id="program:reveal:0",
    )


class DrawRevealModelTests(unittest.TestCase):
    def test_first_draw_policy_is_closed_and_strict(self):
        handler = DrawRevealFirstHandler()
        policy = handler.lower(reveal_descriptor(), reveal_context())

        self.assertEqual(1, len(policy))
        self.assertFalse(policy[0].optional)
        self.assertEqual("object:A11@2", policy[0].source_logical_object_id)
        self.assertEqual((), handler.lower(reveal_descriptor(), reveal_context(ordinal=2)))
        self.assertEqual((), handler.lower(reveal_descriptor(), reveal_context(player="B")))
        self.assertEqual(
            (),
            handler.lower(
                reveal_descriptor(turn_relation="source_controller_turn"),
                reveal_context(active="B"),
            ),
        )

        malformed = reveal_descriptor()
        malformed["reveal"]["optional"] = "yes"
        with self.assertRaisesRegex(SemanticNodeError, "boolean optional"):
            handler.validate(malformed)
        malformed = reveal_descriptor()
        malformed["unknown"] = True
        with self.assertRaisesRegex(SemanticNodeError, "unknown"):
            handler.validate(malformed)

    def test_source_linked_reveal_action_round_trips_and_fails_closed(self):
        action = RevealDrawnCardBySource(
            source_object_id="object:A11",
            source_ref="A11",
            source_logical_object_id="object:A11@2",
            source_zone_change_counter=2,
        )

        self.assertEqual(action, drawn_card_action_from_dict(action.to_dict()))
        malformed = action.to_dict()
        malformed["unknown"] = True
        with self.assertRaisesRegex(DrawError, "fields are invalid"):
            drawn_card_action_from_dict(malformed)
        malformed = action.to_dict()
        malformed["source_zone_change_counter"] = True
        with self.assertRaisesRegex(DrawError, "incarnation"):
            drawn_card_action_from_dict(malformed)

    def test_draw_reveal_policy_mutant_is_killed(self):
        handler = DrawRevealFirstHandler()

        def assert_first_only() -> None:
            self.assertEqual(
                1,
                len(handler.lower(reveal_descriptor(), reveal_context())),
            )
            self.assertEqual(
                (),
                handler.lower(reveal_descriptor(), reveal_context(ordinal=2)),
            )

        assert_first_only()
        original = DrawRevealFirstHandler.lower

        def every_draw(value, descriptor, context):
            return original(
                value,
                descriptor,
                replace(context, draw_ordinal=1),
            )

        with mock.patch.object(DrawRevealFirstHandler, "lower", every_draw):
            with self.assertRaises(AssertionError):
                assert_first_only()


class DrawRevealCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()
        cls.base = cls.db.lookup("Island")
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def compile(self, text: str, *, name: str = "Reveal Fixture"):
        return compile_oracle_card(
            replace(
                self.base,
                oracle_id=f"fixture:{name.casefold().replace(' ', '-')}",
                name=name,
                oracle_text=text,
                type_line="Enchantment",
                keywords=(),
            ),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )

    def test_rowen_and_primitive_etchings_are_exact_and_source_spanned(self):
        cases = (
            (
                "Rowen",
                "Reveal the first card you draw each turn. Whenever you reveal "
                "a basic land card this way, draw a card.",
                "draw-after-reveal-basic-land-v1",
            ),
            (
                "Primitive Etchings",
                "Reveal the first card you draw each turn. Whenever you reveal "
                "a creature card this way, draw a card.",
                "draw-after-reveal-creature-v1",
            ),
        )
        for name, text, rider_template in cases:
            with self.subTest(name=name):
                ir = self.compile(text, name=name)
                self.assertEqual("exact", ir.status)
                self.assertEqual(2, len(ir.faces[0].nodes))
                reveal, rider = ir.faces[0].nodes
                self.assertEqual("draw.reveal_as_drawn", reveal.event)
                self.assertEqual(DRAW_REVEAL_FIRST_HANDLER_ID, reveal.handlers[0]["handler_id"])
                self.assertEqual("card.draw.revealed_by_source", rider.event)
                self.assertEqual(rider_template, rider.template_id)
                self.assertEqual(
                    {
                        "trigger.placement.apnap",
                        "zone.draw.library_to_hand",
                        "zone.draw.reveal_as_drawn",
                    },
                    set(rider.capability_dependencies),
                )
                self.assertEqual(reveal.text, text[reveal.span.start : reveal.span.end])
                self.assertEqual(rider.text, text[rider.span.start : rider.span.end])

    def test_complex_linked_reveal_riders_remain_precise_residuals(self):
        text = (
            "You may reveal the first card you draw each turn as you draw it. "
            "Whenever you reveal an instant or sorcery card this way, copy "
            "that card and you may cast the copy. That copy costs {2} less to cast."
        )
        ir = self.compile(text, name="Optional Reveal Fixture")

        self.assertEqual("partial", ir.status)
        self.assertTrue(ir.faces[0].nodes[0].exact)
        self.assertEqual("draw.reveal_as_drawn", ir.faces[0].nodes[0].event)
        rider = ir.faces[0].nodes[1]
        self.assertFalse(rider.exact)
        self.assertEqual(rider.text, text[rider.span.start : rider.span.end])
        self.assertIn("instant or sorcery", rider.text)


class DrawRevealCoordinatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session_with_sources(
        self,
        *,
        count: int = 1,
        optional: bool = False,
        players: int = 2,
        qualifier: str = "creature",
        seed: int = 121900,
    ):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.pending_trigger_batches.clear()
        engine.state.stack.clear()
        engine.state.active_player = "A"
        engine.state.players["A"].stats.setdefault(
            "cards_drawn_by_turn", {}
        ).pop(str(engine.state.turn_sequence), None)
        sources = [
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Island"
        ][:count]
        self.assertEqual(count, len(sources))
        for source in sources:
            engine.move_card(
                source.object_id,
                "battlefield",
                controller="A",
                log=False,
                semantic_events=False,
            )
        oracle_id = sources[0].oracle_id
        engine.semantics.put(
            SemanticProgram(
                key=f"test:draw-reveal:{seed}",
                label="Reveal the first drawn card",
                oracle_id=oracle_id,
                ability_id="static:front:draw-reveal",
                active_zone="battlefield",
                event="draw.reveal_as_drawn",
                handlers=[reveal_descriptor(optional=optional)],
                trust_level="provisional",
            )
        )
        type_condition = (
            {
                "all": [
                    {
                        "field": "reveal_source_object_id",
                        "op": "eq",
                        "value": "$source.object_id",
                    },
                    {
                        "field": "revealed_card_types",
                        "op": "contains_any",
                        "value": ["land"],
                    },
                    {
                        "field": "revealed_card_supertypes",
                        "op": "contains_any",
                        "value": ["basic"],
                    },
                ]
            }
            if qualifier == "basic land"
            else {
                "all": [
                    {
                        "field": "reveal_source_object_id",
                        "op": "eq",
                        "value": "$source.object_id",
                    },
                    {
                        "field": "revealed_card_types",
                        "op": "contains_any",
                        "value": [qualifier],
                    },
                ]
            }
        )
        engine.semantics.put(
            SemanticProgram(
                key=f"test:draw-reveal-rider:{seed}",
                label="Draw for the source-linked reveal",
                oracle_id=oracle_id,
                ability_id="trigger:front:draw-reveal-rider",
                active_zone="battlefield",
                event="card.draw.revealed_by_source",
                effects=[
                    {
                        "op": "draw",
                        "player": "$controller",
                        "count": 1,
                        "private": True,
                    }
                ],
                event_condition=type_condition,
                trust_level="provisional",
            )
        )
        return session, sources

    @staticmethod
    def put_top(engine, quality: str) -> str:
        library = engine.state.players["A"].zones["library"]
        for object_id in tuple(library):
            card = engine.state.cards[object_id]
            record = engine.card_record(card)
            if record is None:
                continue
            type_line = (
                str(record.faces[0].get("type_line") or "")
                if record.faces
                else record.type_line
            )
            types, _, supertypes = engine._type_parts(type_line)
            matches = (
                "land" in types and "basic" in supertypes
                if quality == "basic land"
                else quality in types
            )
            if matches:
                library.remove(object_id)
                library.append(object_id)
                return object_id
        raise AssertionError(f"Fixture library lacks {quality}")

    @staticmethod
    def trigger_items(engine):
        return [
            *engine.state.stack,
            *(
                item
                for batch in engine.state.pending_trigger_batches
                for item in batch.items
            ),
        ]

    @staticmethod
    def trigger_source_object_id(item):
        if isinstance(item, Mapping):
            return item["source_object_id"]
        return item.source_object_id

    def test_mandatory_first_draw_reveals_and_dispatches_only_its_linked_trigger(self):
        session, sources = self.session_with_sources(
            qualifier="basic land", seed=121901
        )
        engine = session.engine
        object_id = self.put_top(engine, "basic land")
        revealed_from_zones: list[str] = []
        original_dispatch = engine._dispatch_semantic_event

        def observe_dispatch(event: str, context: dict):
            if event == "card.draw.revealed_by_source":
                revealed_from_zones.append(engine.state.cards[object_id].zone)
            return original_dispatch(event, context)

        with (
            mock.patch.object(
                CommanderEngine,
                "semantic_program_is_current_trusted",
                return_value=True,
            ),
            mock.patch.object(
                engine,
                "_dispatch_semantic_event",
                side_effect=observe_dispatch,
            ),
        ):
            engine._begin_draw_sequence(
                "A", 1, reason="mandatory first reveal", private=True
            )

        self.assertEqual(["library"], revealed_from_zones)
        self.assertIn(object_id, engine.state.players["A"].zones["hand"])
        self.assertEqual(sorted(engine.seats), engine.state.cards[object_id].revealed_to)
        triggers = self.trigger_items(engine)
        self.assertEqual(1, len(triggers))
        self.assertEqual(
            sources[0].object_id,
            self.trigger_source_object_id(triggers[0]),
        )

    def test_second_draw_and_non_draw_replacement_do_not_apply_reveal(self):
        session, _ = self.session_with_sources(seed=121902)
        engine = session.engine
        first = self.put_top(engine, "creature")
        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence("A", 1, reason="first draw", private=True)
        self.assertTrue(engine.state.cards[first].revealed_to)
        engine.state.pending_trigger_batches.clear()
        engine.state.stack.clear()

        second = self.put_top(engine, "creature")
        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence("A", 1, reason="second draw", private=True)
        self.assertFalse(engine.state.cards[second].revealed_to)
        self.assertFalse(self.trigger_items(engine))

        prevented_session, _ = self.session_with_sources(seed=121907)
        prevented_engine = prevented_session.engine
        prevented = self.put_top(prevented_engine, "creature")
        effect = ReplacementEffect(
            effect_id="prevent:draw-reveal",
            source_id="fixture:prevention",
            event_kind="draw",
            replacement_class=ReplacementClass.OTHER,
            conditions={"is_draw": {"eq": True}},
            operations=(PreventDraw(),),
        )
        with (
            mock.patch.object(
                CommanderEngine,
                "semantic_program_is_current_trusted",
                return_value=True,
            ),
            mock.patch(
                "mtg_commander_sim.drawing.coordinator._replacement_effects",
                return_value=(effect,),
            ),
        ):
            prevented_engine._begin_draw_sequence(
                "A", 1, reason="prevented reveal draw", private=True
            )
        self.assertIn(
            prevented,
            prevented_engine.state.players["A"].zones["library"],
        )
        self.assertFalse(prevented_engine.state.cards[prevented].revealed_to)
        self.assertIsNone(prevented_engine.state.pending_decision)

    def test_optional_reveal_is_seat_scoped_and_public_only_after_acceptance(self):
        session, _ = self.session_with_sources(
            optional=True, players=4, seed=121903
        )
        engine = session.engine
        object_id = self.put_top(engine, "creature")

        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence(
                "A", 1, reason="optional reveal", private=True
            )
            affected = session.packet("pilot:A", full=True)
            opponent = session.packet("pilot:B", full=True)
            self.assertEqual("draw.reveal", affected["decision"]["kind"])
            self.assertEqual(
                engine.state.cards[object_id].ref,
                affected["decision"]["ctx"]["card"]["id"],
            )
            self.assertIsNone(opponent["decision"])
            self.assertIn(object_id, engine.state.players["A"].zones["library"])
            result = session.act("pilot:A", {"action_id": "reveal"})

        self.assertTrue(result.ok, result.summary)
        self.assertIn(object_id, engine.state.players["A"].zones["hand"])
        for seat in ("B", "C", "D"):
            view = session.packet(f"pilot:{seat}", full=True)["state"]["players"]["A"]
            self.assertIn(
                engine.state.cards[object_id].ref,
                {card["id"] for card in view["known_hand"]},
            )

    def test_optional_sources_are_chosen_sequentially_and_linked_by_physical_source(self):
        session, _ = self.session_with_sources(
            count=2, optional=True, seed=121904
        )
        engine = session.engine
        object_id = self.put_top(engine, "creature")

        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence("A", 1, reason="two policies", private=True)
            first_source_ref = session.packet("pilot:A", full=True)["decision"]["ctx"]["source"]["id"]
            first = session.act("pilot:A", {"action_id": "reveal"})
            self.assertTrue(first.ok, first.summary)
            self.assertIn(object_id, engine.state.players["A"].zones["library"])
            second_packet = session.packet("pilot:A", full=True)
            self.assertEqual("draw.reveal", second_packet["decision"]["kind"])
            self.assertNotEqual(
                first_source_ref,
                second_packet["decision"]["ctx"]["source"]["id"],
            )
            second = session.act("pilot:A", {"action_id": "decline"})

        self.assertTrue(second.ok, second.summary)
        triggers = self.trigger_items(engine)
        self.assertEqual(1, len(triggers))
        source = next(card for card in engine.state.cards.values() if card.ref == first_source_ref)
        self.assertEqual(
            source.object_id,
            self.trigger_source_object_id(triggers[0]),
        )

    def test_source_change_rejects_choice_before_draw_mutation(self):
        session, sources = self.session_with_sources(
            optional=True, seed=121905
        )
        engine = session.engine
        object_id = self.put_top(engine, "creature")
        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence("A", 1, reason="stale source", private=True)
            engine.move_card(
                sources[0].object_id,
                "graveyard",
                log=False,
                semantic_events=False,
            )
            before = authoritative_state_hash(engine.state)
            result = session.act("pilot:A", {"action_id": "reveal"})

        self.assertFalse(result.ok)
        self.assertIn("policies changed", result.summary)
        self.assertEqual(before, authoritative_state_hash(engine.state))
        self.assertIn(object_id, engine.state.players["A"].zones["library"])

    def test_optional_reveal_choice_replays_exactly(self):
        session, _ = self.session_with_sources(optional=True, seed=121906)
        engine = session.engine
        object_id = self.put_top(engine, "creature")
        with mock.patch.object(
            CommanderEngine,
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            engine._begin_draw_sequence("A", 1, reason="replay reveal", private=True)
            session.initial_checkpoint = checkpoint_envelope(engine.state)
            session.commands.clear()
            session.decisions.clear()
            result = session.act("pilot:A", {"action_id": "reveal"})
            self.assertTrue(result.ok, result.summary)
            expected_hash = authoritative_state_hash(engine.state)
            with tempfile.TemporaryDirectory() as temporary:
                record_dir = Path(temporary) / "draw-reveal-replay"
                session.save(record_dir)
                replay = replay_record(record_dir, self.db, verify=True)

        self.assertIn(object_id, engine.state.players["A"].zones["hand"])
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    unittest.main()
