from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session, pass_current
from mtg_commander_sim.combat import (
    DOUBLE_STRIKE,
    FIRST_STRIKE,
    assigns_in_damage_step,
    ordinary_second_step_combatants,
)
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class CombatDamageStepUnitTests(unittest.TestCase):
    def test_keyword_contracts_trace_the_pinned_rules(self):
        root = Path(__file__).resolve().parents[1]
        expected = {
            "defender": {"702.3", "702.3a", "702.3b", "702.3c"},
            "double-strike": {
                "702.4",
                "702.4a",
                "702.4b",
                "702.4c",
                "702.4d",
                "702.4e",
            },
            "first-strike": {
                "702.7",
                "702.7a",
                "702.7b",
                "702.7c",
                "702.7d",
            },
            "lifelink": {
                "702.15",
                "702.15a",
                "702.15b",
                "702.15c",
                "702.15d",
                "702.15e",
                "702.15f",
            },
            "trample": {
                "702.19",
                "702.19a",
                "702.19b",
                "702.19c",
                "702.19d",
                "702.19e",
                "702.19f",
                "702.19g",
            },
            "menace": {
                "702.111",
                "702.111a",
                "702.111b",
                "702.111c",
            },
        }
        for mechanic_id, references in expected.items():
            with self.subTest(mechanic_id=mechanic_id):
                contract = json.loads(
                    (
                        root
                        / "mechanics"
                        / "contracts"
                        / f"{mechanic_id}.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(references, set(contract["rule_references"]))

    def test_second_step_uses_the_first_step_snapshot_and_current_double_strike(self):
        beginning = {
            "ordinary": frozenset(),
            "first": frozenset({FIRST_STRIKE}),
            "double": frozenset({DOUBLE_STRIKE}),
        }
        ordinary = ordinary_second_step_combatants(beginning)

        # Gaining first strike after the first step does not remove an
        # ordinary combatant from the second step (CR 510.4).
        self.assertTrue(
            assigns_in_damage_step(
                object_id="ordinary",
                current_keywords=frozenset({FIRST_STRIKE}),
                step_index=1,
                first_strike_step=True,
                ordinary_second_step=ordinary,
            )
        )
        # A first striker does not deal twice merely by retaining or losing
        # first strike after it dealt damage in the first step.
        for current in (frozenset({FIRST_STRIKE}), frozenset()):
            self.assertFalse(
                assigns_in_damage_step(
                    object_id="first",
                    current_keywords=current,
                    step_index=1,
                    first_strike_step=True,
                    ordinary_second_step=ordinary,
                )
            )
        # Double strike is checked again as the second step begins.
        self.assertTrue(
            assigns_in_damage_step(
                object_id="first",
                current_keywords=frozenset({DOUBLE_STRIKE}),
                step_index=1,
                first_strike_step=True,
                ordinary_second_step=ordinary,
            )
        )
        self.assertFalse(
            assigns_in_damage_step(
                object_id="double",
                current_keywords=frozenset(),
                step_index=1,
                first_strike_step=True,
                ordinary_second_step=ordinary,
            )
        )


class CombatKeywordRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int, *, step: str = "combat_damage"):
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
        engine.state.phase_index = 7 if step == "combat_damage" else 6
        engine.state.phase = "combat"
        engine.state.step = step
        engine.state.combat = CombatState()
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def token(
        engine,
        controller: str,
        name: str,
        *,
        power: int = 2,
        toughness: int = 2,
        keywords: tuple[str, ...] = (),
        colors: tuple[str, ...] = (),
        oracle_text: str = "",
    ):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": str(power),
                "toughness": str(toughness),
                "keywords": list(keywords),
                "colors": list(colors),
                "oracle_text": oracle_text,
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    @staticmethod
    def set_combat(engine, attacker, *blockers):
        attacker.attacking = "B"
        for blocker in blockers:
            blocker.blocking = attacker.object_id
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
            blockers=(
                {attacker.object_id: [b.object_id for b in blockers]}
                if blockers
                else {}
            ),
        )

    @staticmethod
    def submit_damage(session, seat: str, assignments):
        result = session.act(
            f"pilot:{seat}",
            {"a": "dmg", "assignments": assignments},
        )
        return result

    def test_first_strike_destroys_blocker_before_ordinary_damage(self):
        session = self.make_session(51040)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "First striker",
            keywords=("First strike",),
        )
        blocker = self.token(engine, "B", "Ordinary blocker")
        self.set_combat(engine, attacker, blocker)

        engine._enter_step()

        self.assertTrue(engine.state.combat.first_strike_step)
        self.assertEqual("outside", blocker.zone)
        self.assertEqual(0, attacker.marked_damage)
        projected_combat = session.packet("pilot:A", full=True)["state"]["combat"]
        self.assertEqual(1, projected_combat["damage_step"])
        self.assertNotIn(
            "ordinary_second_damage_combatants", projected_combat
        )
        self.assertNotIn(attacker.object_id, json.dumps(projected_combat))

        self.assertIsNotNone(session.next_task())
        pass_current(session)
        pass_current(session)

        self.assertEqual(1, engine.state.combat.damage_step_index)
        self.assertEqual(0, attacker.marked_damage)
        self.assertEqual(
            2,
            session.packet("pilot:A", full=True)["state"]["combat"]["damage_step"],
        )

    def test_double_strike_creates_two_real_damage_steps_and_replays(self):
        session = self.make_session(51041)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Double striker",
            keywords=("Double strike",),
        )
        self.set_combat(engine, attacker)

        engine._enter_step()
        self.assertEqual(38, engine.state.players["B"].life)
        self.assertEqual(0, engine.state.combat.damage_step_index)
        self.assertIsNotNone(session.next_task())
        session.initial_checkpoint = checkpoint_envelope(session.state)

        pass_current(session)
        pass_current(session)

        self.assertEqual(36, engine.state.players["B"].life)
        self.assertEqual(1, engine.state.combat.damage_step_index)
        begins = [
            event
            for event in engine.state.events
            if event.code == "step.begin"
            and event.phase == "combat"
            and event.step == "combat_damage"
        ]
        self.assertEqual(2, len(begins))
        damage_events = [
            event
            for event in engine.state.events
            if event.code == "combat.damage"
            and event.details.get("first_strike_step") is True
        ]
        self.assertEqual(
            [1, 2],
            [event.details["damage_step"] for event in damage_events],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "double-strike"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])

    def test_double_strike_does_not_hit_player_after_its_blocker_dies(self):
        session = self.make_session(51048)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Blocked double striker",
            keywords=("Double strike",),
        )
        blocker = self.token(engine, "B", "First-step blocker")
        self.set_combat(engine, attacker, blocker)
        life_before = engine.state.players["B"].life

        engine._enter_step()
        self.assertEqual("outside", blocker.zone)
        self.assertIsNotNone(session.next_task())
        pass_current(session)
        pass_current(session)

        self.assertEqual(life_before, engine.state.players["B"].life)
        self.assertEqual(1, engine.state.combat.damage_step_index)

    def test_lifelink_counts_only_damage_not_prevented_by_protection(self):
        session = self.make_session(51042)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Green trampling lifelinker",
            power=5,
            toughness=5,
            keywords=("Trample", "Lifelink"),
            colors=("G",),
        )
        blocker = self.token(
            engine,
            "B",
            "Protected blocker",
            oracle_text="Protection from green",
        )
        self.set_combat(engine, attacker, blocker)
        life_a = engine.state.players["A"].life
        life_b = engine.state.players["B"].life
        engine._begin_combat_damage()

        result_a = self.submit_damage(
            session,
            "A",
            [
                {"source": attacker.ref, "target": blocker.ref, "amount": 2},
                {"source": attacker.ref, "target": "B", "amount": 3},
            ],
        )
        self.assertTrue(result_a.ok, result_a.summary)
        result_b = self.submit_damage(
            session,
            "B",
            [{"source": blocker.ref, "target": attacker.ref, "amount": 2}],
        )

        self.assertTrue(result_b.ok, result_b.summary)
        self.assertEqual(life_a + 3, engine.state.players["A"].life)
        self.assertEqual(life_b - 3, engine.state.players["B"].life)
        self.assertEqual(0, blocker.marked_damage)

    def test_trample_rejects_spill_before_lethal_atomically(self):
        session = self.make_session(51043)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Trampler",
            power=5,
            toughness=5,
            keywords=("Trample",),
        )
        blocker = self.token(engine, "B", "Blocker")
        self.set_combat(engine, attacker, blocker)
        engine._begin_combat_damage()
        first = self.submit_damage(
            session,
            "A",
            [
                {"source": attacker.ref, "target": blocker.ref, "amount": 1},
                {"source": attacker.ref, "target": "B", "amount": 4},
            ],
        )
        self.assertTrue(first.ok, first.summary)
        before = authoritative_state_hash(session.state)

        result = self.submit_damage(
            session,
            "B",
            [{"source": blocker.ref, "target": attacker.ref, "amount": 2}],
        )

        self.assertFalse(result.ok)
        self.assertIn("until", result.summary)
        self.assertIn("lethal damage", result.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual(40, engine.state.players["B"].life)
        self.assertEqual(0, blocker.marked_damage)

    def test_trample_accepts_lethal_then_spill(self):
        session = self.make_session(51044)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Trampler",
            power=5,
            toughness=5,
            keywords=("Trample",),
        )
        blocker = self.token(engine, "B", "Blocker")
        self.set_combat(engine, attacker, blocker)
        engine._begin_combat_damage()

        self.assertTrue(
            self.submit_damage(
                session,
                "A",
                [
                    {"source": attacker.ref, "target": blocker.ref, "amount": 2},
                    {"source": attacker.ref, "target": "B", "amount": 3},
                ],
            ).ok
        )
        result = self.submit_damage(
            session,
            "B",
            [{"source": blocker.ref, "target": attacker.ref, "amount": 2}],
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual(37, engine.state.players["B"].life)
        self.assertEqual("outside", blocker.zone)

    def test_deathtouch_and_marked_damage_each_reduce_trample_lethal(self):
        for seed, blocker_toughness, marked, keywords, lethal in (
            (51045, 5, 0, ("Trample", "Deathtouch"), 1),
            (51046, 4, 2, ("Trample",), 2),
        ):
            with self.subTest(seed=seed):
                session = self.make_session(seed)
                engine = session.engine
                attacker = self.token(
                    engine,
                    "A",
                    "Lethal calculator",
                    power=5,
                    toughness=6,
                    keywords=keywords,
                )
                blocker = self.token(
                    engine,
                    "B",
                    "Damaged blocker",
                    power=1,
                    toughness=blocker_toughness,
                )
                blocker.marked_damage = marked
                self.set_combat(engine, attacker, blocker)
                engine._begin_combat_damage()
                self.assertTrue(
                    self.submit_damage(
                        session,
                        "A",
                        [
                            {
                                "source": attacker.ref,
                                "target": blocker.ref,
                                "amount": lethal,
                            },
                            {
                                "source": attacker.ref,
                                "target": "B",
                                "amount": 5 - lethal,
                            },
                        ],
                    ).ok
                )
                result = self.submit_damage(
                    session,
                    "B",
                    [{"source": blocker.ref, "target": attacker.ref, "amount": 1}],
                )
                self.assertTrue(result.ok, result.summary)
                self.assertEqual(35 + lethal, engine.state.players["B"].life)

    def test_trample_deals_to_defender_after_all_blockers_leave(self):
        session = self.make_session(51047)
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Persistent trampler",
            power=4,
            toughness=4,
            keywords=("Trample",),
        )
        blocker = self.token(engine, "B", "Departing blocker")
        self.set_combat(engine, attacker, blocker)
        engine.move_card(blocker.object_id, "graveyard")

        engine._begin_combat_damage()

        self.assertEqual(36, engine.state.players["B"].life)
        self.assertEqual(
            [{"source": attacker.ref, "target": "B", "amount": 4}],
            engine.state.combat.damage_assignments,
        )

    def test_menace_requires_zero_or_two_blockers_and_projects_the_minimum(self):
        session = self.make_session(50940, step="declare_blockers")
        engine = session.engine
        attacker = self.token(
            engine,
            "A",
            "Menacing attacker",
            keywords=("Menace",),
        )
        first = self.token(engine, "B", "First blocker")
        second = self.token(engine, "B", "Second blocker")
        attacker.attacking = "B"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={attacker.object_id: "B"},
            defending_players=["B"],
        )
        engine._begin_blocker_decisions()
        packet = session.packet("pilot:B", full=True)
        self.assertEqual(
            {attacker.ref: 2},
            packet["decision"]["ctx"]["minimum_blockers"],
        )
        field = packet["decision"]["legal_actions"][0]["form"]["fields"][0]
        self.assertEqual(
            {attacker.ref: 2}, field["minimum_group_sizes"]
        )
        before = authoritative_state_hash(session.state)

        rejected = session.act(
            "pilot:B",
            {"a": "block", "blk": {first.ref: attacker.ref}},
        )

        self.assertFalse(rejected.ok)
        self.assertIn("menace", rejected.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))

        accepted_session = self.make_session(50941, step="declare_blockers")
        accepted_engine = accepted_session.engine
        accepted_attacker = self.token(
            accepted_engine,
            "A",
            "Menacing attacker",
            keywords=("Menace",),
        )
        accepted_first = self.token(accepted_engine, "B", "First blocker")
        accepted_second = self.token(accepted_engine, "B", "Second blocker")
        accepted_attacker.attacking = "B"
        accepted_engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={accepted_attacker.object_id: "B"},
            defending_players=["B"],
        )
        accepted_engine._begin_blocker_decisions()
        accepted = accepted_session.act(
            "pilot:B",
            {
                "a": "block",
                "blk": {
                    accepted_first.ref: accepted_attacker.ref,
                    accepted_second.ref: accepted_attacker.ref,
                },
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)

    def test_defender_is_not_offered_and_cannot_be_injected_as_an_attacker(self):
        session = self.make_session(50840, step="declare_blockers")
        engine = session.engine
        engine.state.phase_index = 5
        engine.state.step = "declare_attackers"
        defender = self.token(
            engine,
            "A",
            "Wall",
            keywords=("Defender", "Haste"),
        )
        ordinary = self.token(
            engine,
            "A",
            "Ordinary attacker",
            keywords=("Haste",),
        )
        engine._issue_attackers()
        candidates = {
            row["id"]
            for row in engine.state.pending_decision.payload_by_actor["A"]["candidates"]
        }
        self.assertNotIn(defender.ref, candidates)
        self.assertIn(ordinary.ref, candidates)
        before = authoritative_state_hash(session.state)

        result = session.act(
            "pilot:A",
            {"a": "attack", "atk": {defender.ref: "B"}},
        )

        self.assertFalse(result.ok)
        self.assertIn("defender", result.summary)
        self.assertEqual(before, authoritative_state_hash(session.state))


if __name__ == "__main__":
    unittest.main()
