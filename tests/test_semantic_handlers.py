from __future__ import annotations

from dataclasses import FrozenInstanceError
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import GameRuleError
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.semantic_runtime import (
    BecomeMonarchIntent,
    DrawCardsIntent,
    ReadOnlyHandlerContext,
    ReadOnlyRulesQuery,
    SemanticHandlerRegistry,
    SemanticHandlerRegistryError,
    default_semantic_handler_registry,
)
from mtg_commander_sim.semantic_runtime.generic import (
    BecomeMonarchHandler,
    DrawEachPlayerHandler,
    DrawHandler,
)
from mtg_commander_sim.semantics import SemanticProgram


class TypedSemanticHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int, *, players: int = 3):
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
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def context(*, actor: str = "A") -> ReadOnlyHandlerContext:
        return ReadOnlyHandlerContext(
            actor=actor,
            default_reason="test effect",
            query=ReadOnlyRulesQuery(
                seats=("A", "B", "C"),
                active_seats=("A", "B", "C"),
                apnap_order=("B", "C", "A"),
            ),
        )

    def test_registry_is_deterministic_and_rejects_duplicate_ownership(self):
        first = default_semantic_handler_registry()
        second = SemanticHandlerRegistry(reversed((
            DrawHandler(),
            BecomeMonarchHandler(),
        )))
        reordered = SemanticHandlerRegistry((
            BecomeMonarchHandler(),
            DrawHandler(),
        ))
        self.assertEqual(second.inventory(), reordered.inventory())
        self.assertEqual(second.fingerprint, reordered.fingerprint)
        self.assertEqual(3, len(first.inventory()))
        with self.assertRaisesRegex(
            SemanticHandlerRegistryError, "Duplicate semantic operation"
        ):
            SemanticHandlerRegistry((DrawHandler(), DrawHandler()))
        with self.assertRaisesRegex(
            SemanticHandlerRegistryError, "registry is frozen"
        ):
            first.register(DrawHandler())

    def test_draw_handler_lowers_typed_intent_through_read_only_context(self):
        context = self.context()
        plan = DrawHandler().lower(
            {"op": "draw", "player": "B", "count": 2},
            context,
        )
        self.assertEqual("generic.draw.v1", plan.handler_id)
        self.assertEqual(
            (
                DrawCardsIntent(
                    player="B",
                    count=2,
                    reason="test effect",
                ),
            ),
            plan.intents,
        )
        self.assertFalse(hasattr(context, "state"))
        with self.assertRaises(FrozenInstanceError):
            context.actor = "C"  # type: ignore[misc]
        private_plan = DrawHandler().lower(
            {"op": "draw", "player": "B", "private": True},
            context,
        )
        self.assertTrue(private_plan.intents[0].private)

    def test_draw_each_player_uses_apnap_order_and_exact_engine_path(self):
        session = self.session(1210401)
        engine = session.engine
        engine.state.active_player = "B"
        before = {
            seat: len(engine.state.players[seat].zones["hand"])
            for seat in engine.active_seats
        }

        result = engine.apply_effect(
            {"op": "draw_each_player", "count": 1},
            actor="A",
        )

        self.assertEqual(["B", "C", "A"], list(result))
        self.assertTrue(all(len(cards) == 1 for cards in result.values()))
        for seat in engine.active_seats:
            self.assertEqual(
                before[seat] + 1,
                len(engine.state.players[seat].zones["hand"]),
            )

    def test_monarch_handler_uses_canonical_engine_mutation_path(self):
        session = self.session(7250401)
        engine = session.engine
        result = engine.apply_effect(
            {"op": "become_monarch", "player": "B"},
            actor="A",
        )
        self.assertEqual("B", result)
        self.assertEqual("B", engine.state.monarch)
        self.assertIsInstance(
            BecomeMonarchHandler().lower(
                {"op": "become_monarch", "player": "C"},
                self.context(),
            ).intents[0],
            BecomeMonarchIntent,
        )
        self.assertEqual(
            "monarch.change",
            [event for event in engine.state.events if event.code == "monarch.change"][-1].code,
        )

    def test_registered_node_validation_fails_before_mutation(self):
        session = self.session(1210402)
        engine = session.engine
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(
            GameRuleError, "Draw count must be a nonnegative integer"
        ):
            engine.apply_effect(
                {"op": "draw", "count": "2"},
                actor="A",
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_unmigrated_operation_retains_legacy_dispatch(self):
        session = self.session(1190401)
        engine = session.engine
        before = engine.state.players["A"].life
        result = engine.apply_effect(
            {"op": "life", "player": "A", "delta": 2},
            actor="A",
        )
        self.assertEqual(before + 2, result)
        self.assertEqual(before + 2, engine.state.players["A"].life)

    def test_migrated_semantic_effect_replays_exactly(self):
        session = self.session(1210403, players=2)
        engine = session.engine
        program = SemanticProgram(
            key="test:typed-draw",
            label="Typed draw",
            effects=[
                {
                    "op": "draw",
                    "player": "$controller",
                    "count": 1,
                    "private": True,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="typed-draw",
                ref="S-typed-draw",
                kind="triggered_ability",
                controller="A",
                label=program.label,
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
        hand_before = len(engine.state.players["A"].zones["hand"])

        original_lower = DrawHandler.lower
        with patch.object(
            DrawHandler,
            "lower",
            autospec=True,
            side_effect=original_lower,
        ) as lower:
            for principal in ("pilot:A", "pilot:B"):
                result = session.act(principal, {"action_id": "pass"})
                self.assertTrue(result.ok, result.summary)
        self.assertGreaterEqual(lower.call_count, 1)
        self.assertEqual(
            hand_before + 1,
            len(engine.state.players["A"].zones["hand"]),
        )
        private_draw = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "card.draw.private" and event.actor == "A"
        )
        self.assertEqual(0, private_draw.importance)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "typed-draw-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])

    def test_stack_draw_node_validation_rolls_back_before_resolution(self):
        session = self.session(1210404, players=2)
        engine = session.engine
        program = SemanticProgram(
            key="test:invalid-typed-draw",
            label="Invalid typed draw",
            effects=[
                {"op": "draw", "player": "$controller", "count": "1"}
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="invalid-typed-draw",
                ref="S-invalid-typed-draw",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")

        first = session.act("pilot:A", {"action_id": "pass"})
        self.assertTrue(first.ok, first.summary)
        before = authoritative_state_hash(engine.state)
        second = session.act("pilot:B", {"action_id": "pass"})

        self.assertFalse(second.ok)
        self.assertIn(
            "Draw count must be a nonnegative integer", second.summary
        )
        self.assertEqual(before, authoritative_state_hash(engine.state))
        self.assertEqual(
            ["S-invalid-typed-draw"],
            [item.ref for item in engine.state.stack],
        )

    def test_stack_draw_each_routes_through_handler_in_apnap_order(self):
        session = self.session(1210405)
        engine = session.engine
        program = SemanticProgram(
            key="test:typed-draw-each",
            label="Typed table draw",
            effects=[{"op": "draw_each_player", "count": 1}],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="typed-draw-each",
                ref="S-typed-draw-each",
                kind="triggered_ability",
                controller="A",
                label=program.label,
                semantic_key=program.key,
                visibility=["A", "B", "C"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        before = {
            seat: len(engine.state.players[seat].zones["hand"])
            for seat in engine.active_seats
        }

        original_lower = DrawEachPlayerHandler.lower
        with patch.object(
            DrawEachPlayerHandler,
            "lower",
            autospec=True,
            side_effect=original_lower,
        ) as lower:
            for principal in ("pilot:A", "pilot:B", "pilot:C"):
                result = session.act(principal, {"action_id": "pass"})
                self.assertTrue(result.ok, result.summary)

        self.assertGreaterEqual(lower.call_count, 1)
        self.assertEqual(
            {seat: count + 1 for seat, count in before.items()},
            {
                seat: len(engine.state.players[seat].zones["hand"])
                for seat in engine.active_seats
            },
        )


if __name__ == "__main__":
    unittest.main()
