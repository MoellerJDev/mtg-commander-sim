from __future__ import annotations

from dataclasses import replace
import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.declaration_restrictions import (
    parse_declaration_restriction_line,
)
from mtg_commander_sim.model import CombatState, GameState
from mtg_commander_sim.oracle_ir import compile_oracle_card
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class MonarchRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int, *, players: int = 4):
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
    def creature(
        engine,
        seat: str,
        name: str,
        *,
        oracle_text: str = "",
        power: str = "2",
    ):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "oracle_text": oracle_text,
                "power": power,
                "toughness": "2",
                "keywords": ["Haste"],
            },
            temporary_keywords=("Haste",),
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    @staticmethod
    def static_source(engine, seat: str, oracle_text: str):
        ref = engine.create_token(
            seat,
            name="Player-state restriction",
            characteristics={
                "type_line": "Token Enchantment",
                "oracle_text": oracle_text,
            },
        )[0]
        return engine._resolve_object(seat, ref, zones={"battlefield"})

    def test_contract_traces_every_cr_725_rule(self):
        contract = json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "mechanics"
                / "contracts"
                / "monarch.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            {"725", "725.1", "725.2", "725.3", "725.4", "725.5"},
            set(contract["rule_references"]),
        )

    def test_designation_is_public_serialized_and_unique(self):
        session = self.session(7250101, players=3)
        engine = session.engine

        engine.become_monarch("B", reason="test designation")
        engine.become_monarch("C", reason="test transfer")

        self.assertEqual("C", engine.state.monarch)
        self.assertEqual(
            "C",
            StateProjector(self.db, engine.state)._snapshot("pilot:A")[
                "game"
            ]["monarch"],
        )
        restored = GameState.from_dict(engine.state.to_dict())
        self.assertEqual("C", restored.monarch)
        self.assertEqual(
            ["B", "C"],
            [
                event.actor
                for event in engine.state.events
                if event.code == "monarch.change"
            ],
        )

    def test_null_designation_preserves_additive_v3_hash_compatibility(self):
        session = self.session(7250109, players=3)
        payload = session.state.to_dict()
        payload.pop("monarch")

        self.assertEqual(
            authoritative_state_hash(session.state),
            authoritative_state_hash(payload),
        )

    def test_monarch_draws_from_inherent_end_step_trigger(self):
        session = self.session(7250102, players=3)
        engine = session.engine
        engine.become_monarch("B", reason="test designation")
        hand_before = len(engine.state.players["B"].zones["hand"])
        engine.state.active_player = "B"
        engine.state.phase_index = 10
        engine.state.phase = "ending"
        engine.state.step = "end_step"

        engine._enter_step()

        self.assertEqual(
            ["The monarch — draw a card"],
            [item.label for item in engine.state.stack],
        )
        self.assertEqual(hand_before, len(engine.state.players["B"].zones["hand"]))
        engine.state.priority_player = None
        engine._prepare_stack_resolution()
        self.assertEqual(
            hand_before + 1,
            len(engine.state.players["B"].zones["hand"]),
        )
        self.assertEqual([], engine.state.stack)

    def test_other_players_end_steps_do_not_trigger_the_monarch_draw(self):
        session = self.session(7250108, players=3)
        engine = session.engine
        engine.become_monarch("B", reason="test designation")
        hand_before = len(engine.state.players["B"].zones["hand"])
        engine.state.active_player = "A"
        engine.state.phase_index = 10
        engine.state.phase = "ending"
        engine.state.step = "end_step"

        engine._enter_step()

        self.assertEqual([], engine.state.stack)
        self.assertEqual(hand_before, len(engine.state.players["B"].zones["hand"]))

    def test_creature_combat_damage_transfers_only_on_trigger_resolution(self):
        session = self.session(7250103, players=3)
        engine = session.engine
        attacker = self.creature(engine, "A", "Monarch attacker")
        engine.become_monarch("B", reason="test designation")
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B", "C"],
        )

        interrupted = engine._apply_combat_assignments(
            [{"source": attacker.ref, "target": "B", "amount": 2}]
        )

        self.assertFalse(interrupted)
        self.assertEqual("B", engine.state.monarch)
        self.assertEqual(
            ["The monarch — A becomes the monarch"],
            [item.label for item in engine.state.stack],
        )
        engine.state.priority_player = None
        engine._prepare_stack_resolution()
        self.assertEqual("A", engine.state.monarch)

    def test_nonqualifying_damage_does_not_create_a_transfer_trigger(self):
        session = self.session(7250110, players=3)
        engine = session.engine
        attacker = self.creature(engine, "A", "Nonqualifying attacker")
        engine.become_monarch("B", reason="test designation")
        engine.state.active_player = "A"
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "C"},
            attackers_declared=True,
            defending_players=["B", "C"],
        )

        engine._apply_combat_assignments(
            [{"source": attacker.ref, "target": "C", "amount": 2}]
        )
        self.assertEqual("B", engine.state.monarch)
        self.assertFalse(
            any(item.label.startswith("The monarch") for item in engine.state.stack)
        )

        engine.state.players["B"].stats[
            "protection_from_everything_until_next_turn"
        ] = True
        engine.state.combat.attackers = {attacker.object_id: "B"}
        engine._apply_combat_assignments(
            [{"source": attacker.ref, "target": "B", "amount": 2}]
        )
        self.assertEqual("B", engine.state.monarch)
        self.assertFalse(
            any(item.label.startswith("The monarch") for item in engine.state.stack)
        )

    def test_departing_monarch_passes_to_active_or_next_player(self):
        session = self.session(7250104, players=4)
        engine = session.engine
        engine.state.active_player = "A"
        engine.become_monarch("B", reason="test designation")

        engine._eliminate_players(["B"], reason="test loss")
        self.assertEqual("A", engine.state.monarch)

        engine._eliminate_players(["A"], reason="test active-player loss")
        self.assertEqual("C", engine.state.monarch)

    def test_player_state_declaration_predicates_and_exact_replay(self):
        session = self.session(7250105, players=3)
        engine = session.engine
        poisoned_only = self.creature(
            engine,
            "A",
            "Chained condition",
            oracle_text=(
                "This creature can't attack unless defending player is "
                "poisoned."
            ),
        )
        monarch_only = self.creature(
            engine,
            "A",
            "Crown condition",
            oracle_text=(
                "This creature can't attack unless defending player is "
                "the monarch."
            ),
        )
        engine.state.players["B"].poison = 1
        engine.become_monarch("C", reason="test designation")
        engine.state.phase_index = 5
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine.state.combat = CombatState(defending_players=["B", "C"])

        domains = engine._attack_declaration_problem("A").domains
        self.assertEqual(("B",), domains[poisoned_only.ref])
        self.assertEqual(("C",), domains[monarch_only.ref])

        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)
        result = session.act(
            "pilot:A",
            {
                "a": "attack",
                "atk": {
                    poisoned_only.ref: "B",
                    monarch_only.ref: "C",
                },
            },
        )
        self.assertTrue(result.ok, result.summary)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "player-state-declarations"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_monarch_controller_evasion_and_conditional_defense(self):
        session = self.session(7250106, players=3)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Fleet evasion",
            oracle_text=(
                "This creature can't be blocked by creatures the monarch "
                "controls."
            ),
        )
        blocker = self.creature(engine, "B", "Blocker")
        engine.state.phase_index = 6
        engine.state.phase = "combat"
        engine.state.step = "declare_blockers"
        engine.state.combat = CombatState(
            attackers={attacker.object_id: "B"},
            attackers_declared=True,
            defending_players=["B", "C"],
        )
        attacker.attacking = "B"

        engine.become_monarch("B", reason="test designation")
        self.assertFalse(engine._can_block(attacker, blocker)[0])
        engine.become_monarch("C", reason="test transfer")
        self.assertTrue(engine._can_block(attacker, blocker)[0])

        attack_session = self.session(7250107, players=3)
        attack_engine = attack_session.engine
        small = self.creature(attack_engine, "A", "Small", power="2")
        large = self.creature(attack_engine, "A", "Large", power="3")
        self.static_source(
            attack_engine,
            "B",
            (
                "As long as you're the monarch, creatures with power 2 or "
                "less can't attack you."
            ),
        )
        domains_without_monarch = attack_engine._attack_declaration_problem(
            "A"
        ).domains
        self.assertEqual(("B", "C"), domains_without_monarch[small.ref])
        attack_engine.become_monarch("B", reason="test designation")
        domains = attack_engine._attack_declaration_problem("A").domains
        self.assertEqual(("C",), domains[small.ref])
        self.assertEqual(("B", "C"), domains[large.ref])

    def test_oracle_templates_lower_monarch_effects_and_restrictions(self):
        for text in (
            "This creature can't attack unless defending player is poisoned.",
            "This creature can't attack unless defending player is the monarch.",
            "This creature can't be blocked by creatures the monarch controls.",
            (
                "As long as you're the monarch, creatures with power 2 or "
                "less can't attack you."
            ),
        ):
            with self.subTest(text=text):
                parsed = parse_declaration_restriction_line(text)
                self.assertTrue(parsed.exact, parsed)

        base = self.db.lookup("Arcum Dagsson")
        card = replace(
            base,
            oracle_text="When this creature enters, you become the monarch.",
            type_line="Creature — Test",
        )
        ir = compile_oracle_card(
            card,
            trusted_mechanics={
                "cr-603-handling-triggered-abilities",
                "cr-725-the-monarch",
                "trigger-event-normalized-zone-change",
            },
        )
        self.assertEqual("exact", ir.status)
        self.assertEqual(
            "become-monarch-controller-v1",
            ir.faces[0].nodes[0].template_id,
        )
        self.assertEqual(
            "become_monarch",
            ir.faces[0].nodes[0].effects[0]["op"],
        )


if __name__ == "__main__":
    unittest.main()
