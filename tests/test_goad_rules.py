from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import GameRuleError
from quorune.model import CombatState, TurnEntry
from quorune.oracle_ir import (
    compile_oracle_card,
    generated_programs,
)
from quorune.projection import StateProjector
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class GoadRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_combat_session(self, seed: int, *, players: int = 4):
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
        engine.state.phase_index = 5
        engine.state.phase = "combat"
        engine.state.step = "declare_attackers"
        engine.state.combat = CombatState()
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def attacker(engine, name: str = "Goaded Attacker"):
        ref = engine.create_token(
            "A",
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
            },
            temporary_keywords=["Haste"],
        )[0]
        return engine._resolve_object("A", ref, zones={"battlefield"})

    def test_contract_traces_every_goad_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (root / "mechanics" / "contracts" / "goad.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {"701.15", "701.15a", "701.15b", "701.15c", "701.15d"},
            set(contract["rule_references"]),
        )

    def test_single_goad_requires_another_player_when_available_and_replays(self):
        session = self.make_combat_session(7011501)
        engine = session.engine
        attacker = self.attacker(engine)
        engine.apply_effect(
            {"op": "goad", "card": attacker.ref},
            actor="B",
        )
        engine._issue_attackers()
        session.initial_checkpoint = checkpoint_envelope(session.state)

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(2, constraints["maximum_requirements"])
        other = next(
            requirement
            for requirement in constraints["requirements"]
            if requirement["kind"] == "choose_option_in"
        )
        self.assertEqual(["C", "D"], other["options"])
        self.assertEqual(
            ["B"],
            StateProjector(self.db, engine.state)._obj(
                attacker,
                "pilot:A",
            )["goad"],
        )

        before = authoritative_state_hash(session.state)
        rejected = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "B"}},
        )
        self.assertFalse(rejected.ok)
        self.assertIn("possible 2 requirements", rejected.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

        accepted = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "C"}},
        )
        self.assertTrue(accepted.ok, accepted.summary)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "goaded-attack"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_goad_in_duel_still_requires_attacking_the_goader(self):
        session = self.make_combat_session(7011502, players=2)
        engine = session.engine
        attacker = self.attacker(engine)
        engine.apply_effect(
            {"op": "goad", "card": attacker.ref},
            actor="B",
        )
        problem = engine._attack_declaration_problem("A")

        self.assertEqual(1, problem.maximum_satisfied_requirements())
        engine._issue_attackers()
        result = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "B"}},
        )
        self.assertTrue(result.ok, result.summary)

    def test_multiple_goaders_create_independent_maximized_requirements(self):
        session = self.make_combat_session(7011503)
        engine = session.engine
        attacker = self.attacker(engine)
        for player in ("B", "C"):
            engine.apply_effect(
                {"op": "goad", "card": attacker.ref},
                actor=player,
            )
        engine._issue_attackers()

        constraints = engine.state.pending_decision.payload_by_actor["A"][
            "declaration_constraints"
        ]
        self.assertEqual(4, constraints["maximum_requirements"])
        rejected = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "B"}},
        )
        self.assertFalse(rejected.ok)
        accepted = session.act(
            "pilot:A",
            {"a": "attack", "atk": {attacker.ref: "D"}},
        )
        self.assertTrue(accepted.ok, accepted.summary)

    def test_goaded_by_every_opponent_accepts_any_maximal_attack(self):
        session = self.make_combat_session(7011504)
        engine = session.engine
        attacker = self.attacker(engine)
        for player in ("B", "C", "D"):
            engine.apply_effect(
                {"op": "goad", "card": attacker.ref},
                actor=player,
            )
        problem = engine._attack_declaration_problem("A")

        self.assertEqual(5, problem.maximum_satisfied_requirements())
        for defender in ("B", "C", "D"):
            self.assertTrue(
                problem.evaluate({attacker.ref: defender}).legal,
                defender,
            )

    def test_same_player_goad_is_redundant_and_expires_on_their_next_turn(self):
        session = self.make_combat_session(7011505)
        engine = session.engine
        attacker = self.attacker(engine)
        public_epoch = engine._yield_change_epoch("public")
        for _ in range(2):
            engine.apply_effect(
                {"op": "goad", "card": attacker.ref},
                actor="B",
            )

        self.assertEqual(1, len(attacker.goaded_by))
        self.assertEqual(
            public_epoch + 1,
            engine._yield_change_epoch("public"),
        )
        self.assertEqual(2, engine._attack_declaration_problem("A").maximum_satisfied_requirements())
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine._begin_turn(
            TurnEntry(
                turn_id="goad-expiration-turn",
                player="B",
                extra=True,
                created_sequence=engine.state.turn_sequence,
            )
        )

        self.assertEqual([], attacker.goaded_by)
        self.assertEqual(
            public_epoch + 2,
            engine._yield_change_epoch("public"),
        )
        self.assertTrue(
            any(
                event.code == "permanent.goad.expire"
                for event in engine.state.events
            )
        )

    def test_zone_change_removes_the_noncopiable_designation(self):
        session = self.make_combat_session(7011506)
        engine = session.engine
        attacker = self.attacker(engine)
        engine.apply_effect(
            {"op": "goad", "card": attacker.ref},
            actor="B",
        )

        engine.move_card(attacker.object_id, "exile", reason="goad witness")

        self.assertEqual([], attacker.goaded_by)

    def test_goad_rejects_a_noncreature(self):
        session = self.make_combat_session(7011507)
        engine = session.engine
        ref = engine.create_token(
            "A",
            name="Test Rock",
            characteristics={"type_line": "Token Artifact"},
        )[0]

        with self.assertRaisesRegex(GameRuleError, "Only a creature"):
            engine.apply_effect({"op": "goad", "card": ref}, actor="B")

    def test_goad_accepts_a_permanent_that_is_both_creature_and_battle(self):
        session = self.make_combat_session(7011509)
        engine = session.engine
        ref = engine.create_token(
            "A",
            name="Animated Siege",
            battle_protector="B",
            characteristics={
                "type_line": "Token Creature Battle — Siege",
                "power": "3",
                "toughness": "3",
                "defense": "4",
            },
        )[0]

        result = engine.apply_effect(
            {"op": "goad", "card": ref},
            actor="B",
        )

        card = engine._resolve_object("A", ref, zones={"battlefield"})
        self.assertEqual(ref, result)
        self.assertEqual(["B"], [value.player for value in card.goaded_by])

    def test_exact_static_prohibition_makes_goad_have_no_effect(self):
        session = self.make_combat_session(7011508)
        engine = session.engine
        attacker = self.attacker(engine)
        engine.create_token(
            "A",
            name="Goad Ward",
            characteristics={
                "type_line": "Token Enchantment",
                "oracle_text": "Creatures you control can't be goaded.",
            },
        )

        result = engine.apply_effect(
            {"op": "goad", "card": attacker.ref},
            actor="B",
        )

        self.assertEqual(attacker.ref, result)
        self.assertEqual([], attacker.goaded_by)
        self.assertEqual(
            "permanent.goad.prevented",
            engine.state.events[-1].code,
        )

    def test_oracle_compiler_lowers_only_anchored_target_goad_templates(self):
        # Use a card in the compact CI fixture as the immutable record shell;
        # this test replaces its Oracle text and does not depend on its rules.
        base = self.db.lookup("Arcum Dagsson")
        ordinary = replace(base, oracle_text="{2}: Goad target creature.")
        opponent = replace(
            base,
            oracle_text=(
                "{2}: Goad target creature an opponent controls."
            ),
        )

        ordinary_program = generated_programs(self.db, ordinary)[0]
        opponent_program = generated_programs(self.db, opponent)[0]
        self.assertEqual(
            [{"op": "goad", "card": "$target.0"}],
            ordinary_program.effects,
        )
        self.assertNotIn(
            "controller_relation",
            ordinary_program.target_schema,
        )
        self.assertEqual(
            "opponent",
            opponent_program.target_schema["controller_relation"],
        )
        self.assertIn("goad", opponent_program.coverage)

        mutated = replace(
            base,
            oracle_text=(
                "{2}: Goad target creature, then draw a card."
            ),
        )
        ir = compile_oracle_card(mutated)
        self.assertTrue(ir.material_residuals)
        self.assertNotEqual("exact", ir.status)


if __name__ == "__main__":
    unittest.main()
