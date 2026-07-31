from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import GameRuleError, TURN_STEPS
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import checkpoint_envelope, replay_record


class MainPhaseRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
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
    def card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def enter_main(session, phase: str, *, active: str = "A") -> None:
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.active_player = active
        engine.state.phase_index = TURN_STEPS.index((phase, "main"))
        engine._enter_step()

    def test_contract_traces_every_cr_505_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "main-phase.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {
                "505",
                "505.1",
                "505.1a",
                "505.1b",
                "505.2",
                "505.3",
                "505.4",
                "505.5",
                "505.6",
                "505.6a",
                "505.6b",
            },
            set(contract["rule_references"]),
        )

    def test_ordinary_turn_has_two_main_boundaries_separated_by_combat(self):
        precombat = TURN_STEPS.index(("precombat_main", "main"))
        combat_start = TURN_STEPS.index(("combat", "beginning_combat"))
        combat_end = TURN_STEPS.index(("combat", "end_combat"))
        postcombat = TURN_STEPS.index(("postcombat_main", "main"))

        self.assertLess(precombat, combat_start)
        self.assertLess(combat_start, combat_end)
        self.assertLess(combat_end, postcombat)
        self.assertEqual(
            [("precombat_main", "main"), ("postcombat_main", "main")],
            [
                boundary
                for boundary in TURN_STEPS
                if boundary[0] in {"precombat_main", "postcombat_main"}
            ],
        )

    def test_main_phase_ends_only_after_empty_stack_passes_and_replays(self):
        session = self.make_session(50502)
        engine = session.engine
        self.enter_main(session, "postcombat_main")
        engine.pump()
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for seat in ("A", "B"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass the empty postcombat main phase.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual(
            ("ending", "end_step"),
            (engine.state.phase, engine.state.step),
        )
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "main-phase"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_resolving_stack_does_not_end_main_phase(self):
        session = self.make_session(50503)
        engine = session.engine
        ring = self.card(engine, "A", "Sol Ring")
        engine.move_card(ring.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["C"] = 1
        self.enter_main(session, "precombat_main")

        engine._cast("A", {"card": ring.ref, "pay": "auto"})
        self.assertTrue(engine.state.stack)
        engine._pass_priority("A")
        engine._pass_priority("B")
        engine.pump()

        self.assertFalse(engine.state.stack)
        self.assertEqual(
            ("precombat_main", "main"),
            (engine.state.phase, engine.state.step),
        )
        self.assertEqual("A", engine.state.priority_player)

    def test_saga_lore_precedes_main_phase_priority(self):
        session = self.make_session(50504)
        engine = session.engine
        saga = self.card(engine, "A", "Urza's Saga")
        engine.move_card(
            saga.object_id,
            "battlefield",
            controller="A",
            log=False,
            semantic_events=False,
        )
        saga.counters["lore"] = 1
        engine.state.stack.clear()
        engine.state.pending_trigger_batches.clear()

        self.enter_main(session, "precombat_main", active="A")
        engine.pump()

        self.assertEqual(2, saga.counters["lore"])
        self.assertTrue(engine.state.stack)
        self.assertEqual("A", engine.state.priority_player)
        self.assertIn("chapter II", engine.state.stack[-1].label)

    def test_active_player_gets_main_priority_and_sorcery_timing_is_exact(
        self,
    ):
        session = self.make_session(50505)
        engine = session.engine
        ring = self.card(engine, "A", "Sol Ring")
        engine.move_card(ring.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["C"] = 1
        self.enter_main(session, "precombat_main")

        self.assertEqual("A", engine.state.priority_player)
        hints = engine._priority_action_hints("A")
        self.assertIn(ring.ref, hints["cast"])

        other_ring = self.card(engine, "B", "Sol Ring")
        engine.move_card(other_ring.object_id, "hand", log=False)
        engine.state.players["B"].mana_pool["C"] = 1
        engine.state.priority_player = "B"
        with self.assertRaisesRegex(GameRuleError, "active player"):
            engine._cast("B", {"card": other_ring.ref, "pay": "auto"})

        engine.state.priority_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "main"
        hints = engine._priority_action_hints("A")
        self.assertNotIn(ring.ref, hints["cast"])
        with self.assertRaisesRegex(GameRuleError, "main phase"):
            engine._cast("A", {"card": ring.ref, "pay": "auto"})

        engine.state.phase = "precombat_main"
        engine.state.stack.append(
            StackItem(
                stack_id="cr505-stack",
                ref="S505",
                kind="spell",
                controller="B",
                label="CR 505 stack witness",
            )
        )
        hints = engine._priority_action_hints("A")
        self.assertNotIn(ring.ref, hints["cast"])
        with self.assertRaisesRegex(GameRuleError, "empty stack"):
            engine._cast("A", {"card": ring.ref, "pay": "auto"})

    def test_land_play_is_stackless_atomic_and_uses_allowance(self):
        session = self.make_session(50506)
        engine = session.engine
        lands = [
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and card.zone in {"hand", "library"}
            and engine.card_record(card)
            and engine.card_record(card).is_land
        ][:2]
        self.assertEqual(2, len(lands))
        for land in lands:
            if land.zone != "hand":
                engine.move_card(land.object_id, "hand", log=False)
        engine.state.players["A"].land_plays_remaining = 2
        self.enter_main(session, "precombat_main")

        engine._play_land("A", {"card": lands[0].ref})
        self.assertEqual("battlefield", lands[0].zone)
        self.assertFalse(engine.state.stack)
        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual(
            1,
            engine.state.players["A"].land_plays_remaining,
        )

        engine._play_land("A", {"card": lands[1].ref})
        self.assertEqual("battlefield", lands[1].zone)
        self.assertEqual(
            0,
            engine.state.players["A"].land_plays_remaining,
        )
        with self.assertRaisesRegex(GameRuleError, "No land plays remain"):
            engine._play_land("A", {"card": lands[0].ref})

    def test_land_hints_require_the_actual_active_main_phase(self):
        session = self.make_session(50507)
        engine = session.engine
        land = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and engine.card_record(card)
            and engine.card_record(card).is_land
        )
        if land.zone != "hand":
            engine.move_card(land.object_id, "hand", log=False)
        engine.state.active_player = "A"
        engine.state.priority_player = "A"
        engine.state.players["A"].land_plays_remaining = 1
        engine.state.phase = "combat"
        engine.state.step = "main"

        self.assertNotIn(
            land.ref,
            engine._priority_action_hints("A")["lands"],
        )
        engine.state.phase = "precombat_main"
        self.assertIn(
            land.ref,
            engine._priority_action_hints("A")["lands"],
        )

        engine.state.stack.append(
            StackItem(
                stack_id="cr505-land-stack",
                ref="S506",
                kind="spell",
                controller="B",
                label="CR 505 land stack witness",
            )
        )
        self.assertNotIn(
            land.ref,
            engine._priority_action_hints("A")["lands"],
        )
        with self.assertRaisesRegex(GameRuleError, "empty stack"):
            engine._play_land("A", {"card": land.ref})

        engine.state.stack.clear()
        other_land = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and engine.card_record(card)
            and engine.card_record(card).is_land
        )
        if other_land.zone != "hand":
            engine.move_card(other_land.object_id, "hand", log=False)
        engine.state.priority_player = "B"
        with self.assertRaisesRegex(GameRuleError, "active player"):
            engine._play_land("B", {"card": other_land.ref})


if __name__ == "__main__":
    unittest.main()
