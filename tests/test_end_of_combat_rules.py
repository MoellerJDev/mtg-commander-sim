from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import TURN_STEPS
from quorune.model import CombatState
from quorune.record import checkpoint_envelope, replay_record
from quorune.semantics import SemanticProgram


class EndOfCombatRuleTests(unittest.TestCase):
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
    def enter_end_of_combat(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("combat", "end_combat")
        )
        engine._enter_step()

    @staticmethod
    def add_end_of_combat_program(engine, source) -> None:
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr511-end-combat",
                label="CR 511 permanent end-of-combat trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr511-end-combat",
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
                            "value": "end_combat",
                        },
                    ]
                },
                effects=[],
            )
        )

    def test_contract_traces_every_cr_511_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "end-of-combat.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {"511", "511.1", "511.2", "511.3"},
            set(contract["rule_references"]),
        )

    def test_end_of_combat_has_no_turn_action_then_active_gets_priority(
        self,
    ):
        session = self.make_session(51101)
        engine = session.engine
        before_event = engine.state.event_sequence

        self.enter_end_of_combat(session)

        events = [
            event
            for event in engine.state.events
            if event.event_id > before_event
        ]
        self.assertEqual(["step.begin"], [event.code for event in events])
        self.assertEqual("A", engine.state.priority_player)
        self.assertFalse(engine.state.stack)

    def test_permanent_and_delayed_end_of_combat_triggers_precede_priority(
        self,
    ):
        session = self.make_session(51102)
        engine = session.engine
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        self.add_end_of_combat_program(engine, source)
        delayed = engine.schedule_delayed_trigger(
            controller="B",
            label="CR 511 delayed end-of-combat trigger",
            event_kind="step.begin",
            condition={
                "phase": "combat",
                "step": "end_combat",
            },
            stack_template={
                "label": "CR 511 delayed end-of-combat trigger",
                "context": {"test": "CR 511.2"},
            },
        )

        self.enter_end_of_combat(session)

        self.assertEqual(
            {
                "CR 511 permanent end-of-combat trigger",
                "CR 511 delayed end-of-combat trigger",
            },
            {item.label for item in engine.state.stack},
        )
        self.assertFalse(delayed.active)
        self.assertEqual("A", engine.state.priority_player)

    def test_objects_leave_combat_only_after_step_ends_and_replay_exactly(
        self,
    ):
        session = self.make_session(51103, players=4)
        engine = session.engine
        attacker = self.card(session, "A", "Goblin Engineer")
        blocker = self.card(session, "B", "Birds of Paradise")
        attacked = self.card(session, "B", "Tyvar, Jubilant Brawler")
        for card, controller in (
            (attacker, "A"),
            (blocker, "B"),
            (attacked, "B"),
        ):
            engine.move_card(
                card.object_id,
                "battlefield",
                controller=controller,
                log=False,
            )
        attacker.attacking = attacked.ref
        blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            attackers={attacker.object_id: attacked.ref},
            defending_players=["B"],
            blocker_cursor=1,
            blockers={attacker.object_id: [blocker.object_id]},
            damage_assignments=[],
        )

        self.enter_end_of_combat(session)
        engine.pump()

        self.assertEqual(attacked.ref, attacker.attacking)
        self.assertEqual(attacker.object_id, blocker.blocking)
        self.assertTrue(engine.state.combat.attackers)
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        for seat in ("A", "B", "C", "D"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass end-of-combat priority.",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual(("postcombat_main", "main"), (
            engine.state.phase,
            engine.state.step,
        ))
        self.assertIsNone(attacker.attacking)
        self.assertIsNone(blocker.blocking)
        self.assertEqual(CombatState(), engine.state.combat)
        self.assertEqual(
            ["combat.end", "step.begin"],
            [
                event.code
                for event in engine.state.events
                if event.code in {"combat.end", "step.begin"}
            ][-2:],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "end-of-combat"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(4, replay["commands"])


if __name__ == "__main__":
    unittest.main()
