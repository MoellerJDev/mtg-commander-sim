from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim import CommanderEngine, GameConfig
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticProgram


class BeginningOfCombatRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, players: int = 2):
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
    def card(session, owner: str, name: str):
        return next(
            card
            for card in session.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def enter_beginning_of_combat(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("combat", "beginning_combat")
        )
        engine._enter_step()

    @staticmethod
    def add_beginning_of_combat_program(engine, source) -> None:
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr507-begin-combat",
                label="CR 507 permanent beginning-of-combat trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr507-begin-combat",
                active_zone="battlefield",
                event="step.begin",
                event_condition={
                    "all": [
                        {
                            "field": "phase",
                            "op": "eq",
                            "value": "combat",
                        },
                        {
                            "field": "step",
                            "op": "eq",
                            "value": "beginning_combat",
                        },
                    ]
                },
                effects=[],
            )
        )

    def test_contract_traces_every_cr_507_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "beginning-of-combat.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"507", "507.1", "507.2"},
            set(contract["rule_references"]),
        )

    def test_supported_commander_profiles_have_no_defender_choice(
        self,
    ):
        session = self.make_session(50701, players=4)
        engine = session.engine

        self.enter_beginning_of_combat(session)
        engine.pump()

        self.assertEqual(["B", "C", "D"], engine.state.combat.defending_players)
        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual("priority", engine.state.pending_decision.kind)
        self.assertEqual(["A"], engine.state.pending_decision.actors)

        engine._eliminate_players(["C"], reason="CR 507 test")
        self.assertEqual(["B", "D"], engine.state.combat.defending_players)

    def test_single_defender_multiplayer_variants_fail_closed(
        self,
    ):
        with self.assertRaisesRegex(
            ValueError,
            "Unsupported Commander format profile",
        ):
            CommanderEngine.create(
                self.db,
                {
                    "A": self.mishra,
                    "B": self.zimone,
                    "C": self.mishra,
                },
                first_player="A",
                config=GameConfig(profile="attack_left"),
            )

    def test_permanent_and_delayed_triggers_precede_active_priority(
        self,
    ):
        session = self.make_session(50702)
        engine = session.engine
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.add_beginning_of_combat_program(engine, source)
        delayed = engine.schedule_delayed_trigger(
            controller="B",
            label="CR 507 delayed beginning-of-combat trigger",
            event_kind="step.begin",
            condition={
                "phase": "combat",
                "step": "beginning_combat",
            },
            stack_template={
                "label": "CR 507 delayed beginning-of-combat trigger",
                "context": {"test": "CR 507.2"},
            },
        )

        self.enter_beginning_of_combat(session)

        self.assertEqual(
            {
                "CR 507 permanent beginning-of-combat trigger",
                "CR 507 delayed beginning-of-combat trigger",
            },
            {item.label for item in engine.state.stack},
        )
        self.assertFalse(delayed.active)
        self.assertEqual("A", engine.state.priority_player)

    def test_priority_round_advances_to_attackers_and_replays_exactly(
        self,
    ):
        session = self.make_session(50703, players=4)
        engine = session.engine

        self.enter_beginning_of_combat(session)
        engine.pump()
        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual(["B", "C", "D"], engine.state.combat.defending_players)
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for seat in ("A", "B", "C", "D"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass beginning-of-combat priority.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual(
            ("combat", "declare_attackers"),
            (engine.state.phase, engine.state.step),
        )
        self.assertTrue(engine.state.combat.attackers_declared)
        self.assertEqual(
            ["B", "C", "D"],
            engine.state.combat.defending_players,
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "beginning-of-combat"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(4, replay["commands"])


if __name__ == "__main__":
    unittest.main()
