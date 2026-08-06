from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session, pass_current
from mtg_commander_sim.combat_damage_assignment import (
    CombatDamageAssignmentError,
)
from mtg_commander_sim.combat_damage_projection import (
    project_combat_damage_assignment,
)
from mtg_commander_sim.model import CombatState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class TrampleAssignmentIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.db.close()

    def session(self, seed: int, *, players: int = 2):
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
        engine.state.phase_index = 7
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def creature(
        engine,
        controller: str,
        name: str,
        *,
        power: int,
        toughness: int,
        keywords=(),
    ):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": str(power),
                "toughness": str(toughness),
            },
            temporary_keywords=tuple(keywords),
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    @staticmethod
    def combat(
        engine,
        attackers,
        blockers,
        *,
        target_context=None,
    ) -> None:
        defending_players = sorted(
            {
                str(context.get("defending_player"))
                for context in (target_context or {}).values()
            }
            | {
                str(target)
                for target in attackers.values()
                if str(target) in engine.state.players
            }
        )
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers=dict(attackers),
            attack_target_context=dict(target_context or {}),
            defending_players=defending_players,
            blockers={key: list(value) for key, value in blockers.items()},
        )

    def assert_replay(self, session, name: str, commands: int) -> None:
        expected_hash = authoritative_state_hash(session.state)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / name
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(commands, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])

    @staticmethod
    def damage_sources(packet):
        form = packet["decision"]["legal_actions"][0]["form"]
        return form["fields"][0]["combat"]["damage_sources"]

    def test_trample_to_attacked_permanent_never_spills_to_controller(self) -> None:
        for seed, kind in ((70219001, "planeswalker"), (70219002, "battle")):
            with self.subTest(kind=kind):
                session = self.session(seed, players=3)
                engine = session.engine
                attacker = self.creature(
                    engine,
                    "A",
                    f"{kind.title()} Trampler",
                    power=5,
                    toughness=5,
                    keywords=("Trample",),
                )
                blocker = self.creature(
                    engine,
                    "B",
                    f"{kind.title()} Blocker",
                    power=1,
                    toughness=2,
                )
                if kind == "planeswalker":
                    target_ref = engine.create_token(
                        "B",
                        name="Trample Target Walker",
                        characteristics={
                            "type_line": "Token Planeswalker — Test",
                            "loyalty": "5",
                        },
                    )[0]
                    counter = "loyalty"
                else:
                    target_ref = engine.create_token(
                        "C",
                        name="Trample Target Battle",
                        battle_protector="B",
                        characteristics={
                            "type_line": "Token Battle — Siege",
                            "defense": "5",
                        },
                    )[0]
                    counter = "defense"
                target = engine._resolve_object(
                    "A", target_ref, zones={"battlefield"}
                )
                attacker.attacking = target.ref
                blocker.blocking = attacker.object_id
                self.combat(
                    engine,
                    {attacker.object_id: target.ref},
                    {attacker.object_id: [blocker.object_id]},
                    target_context={
                        attacker.object_id: {
                            "target": target.ref,
                            "kind": kind,
                            "defending_player": "B",
                        }
                    },
                )
                engine._begin_combat_damage()
                sources = self.damage_sources(
                    session.packet("pilot:A", full=True)
                )
                self.assertEqual(
                    {blocker.ref, target.ref},
                    set(sources[attacker.ref]["targets"]),
                )
                self.assertNotIn("B", sources[attacker.ref]["targets"])
                session.initial_checkpoint = checkpoint_envelope(session.state)

                before = authoritative_state_hash(session.state)
                rejected = session.act(
                    "pilot:A",
                    {
                        "a": "dmg",
                        "assignments": [
                            {
                                "source": attacker.ref,
                                "target": blocker.ref,
                                "amount": 2,
                            },
                            {
                                "source": attacker.ref,
                                "target": "B",
                                "amount": 3,
                            },
                        ],
                    },
                )
                self.assertFalse(rejected.ok)
                self.assertEqual(before, authoritative_state_hash(session.state))

                accepted = session.act(
                    "pilot:A",
                    {
                        "a": "dmg",
                        "assignments": [
                            {
                                "source": attacker.ref,
                                "target": blocker.ref,
                                "amount": 2,
                            },
                            {
                                "source": attacker.ref,
                                "target": target.ref,
                                "amount": 3,
                            },
                        ],
                    },
                )
                self.assertTrue(accepted.ok, accepted.summary)
                current_target = engine._resolve_object(
                    "A", target.ref, zones={"battlefield"}
                )
                self.assertEqual(
                    2,
                    current_target.counters[counter],
                    [event.to_dict() for event in engine.state.events[-5:]],
                )
                self.assertEqual(40, engine.state.players["B"].life)
                self.assert_replay(session, f"trample-{kind}", 1)

    def test_four_player_trample_task_is_seat_scoped_and_replays(self) -> None:
        session = self.session(70219003, players=4)
        engine = session.engine
        first = self.creature(
            engine,
            "A",
            "First Trampler",
            power=5,
            toughness=5,
            keywords=("Trample", "Trample"),
        )
        second = self.creature(
            engine,
            "A",
            "Second Trampler",
            power=4,
            toughness=4,
            keywords=("Trample",),
        )
        blocker_b = self.creature(
            engine, "B", "B Blocker", power=1, toughness=2
        )
        blocker_c = self.creature(
            engine, "C", "C Blocker", power=1, toughness=3
        )
        first.attacking = "B"
        second.attacking = "C"
        blocker_b.blocking = first.object_id
        blocker_c.blocking = second.object_id
        self.combat(
            engine,
            {first.object_id: "B", second.object_id: "C"},
            {
                first.object_id: [blocker_b.object_id],
                second.object_id: [blocker_c.object_id],
            },
        )
        engine._begin_combat_damage()

        packet_a = session.packet("pilot:A", full=True)
        self.assertEqual(
            {first.ref, second.ref},
            set(self.damage_sources(packet_a)),
        )
        for seat in ("B", "C", "D"):
            self.assertIsNone(session.packet(f"pilot:{seat}", full=True)["decision"])
        session.initial_checkpoint = checkpoint_envelope(session.state)
        accepted = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {"source": first.ref, "target": blocker_b.ref, "amount": 2},
                    {"source": first.ref, "target": "B", "amount": 3},
                    {"source": second.ref, "target": blocker_c.ref, "amount": 3},
                    {"source": second.ref, "target": "C", "amount": 1},
                ],
            },
        )

        self.assertTrue(accepted.ok, accepted.summary)
        self.assertEqual(37, engine.state.players["B"].life)
        self.assertEqual(39, engine.state.players["C"].life)
        self.assertEqual(40, engine.state.players["D"].life)
        self.assertEqual(
            ["A", "B", "C"],
            [
                event.actor
                for event in engine.state.events
                if event.code == "combat.damage.assigned"
            ],
        )
        self.assert_replay(session, "four-player-trample", 1)

    def test_trample_does_not_change_a_blockers_damage_recipient(self) -> None:
        session = self.session(70219005)
        engine = session.engine
        attacker = self.creature(
            engine, "A", "Ordinary Attacker", power=4, toughness=4
        )
        blocker = self.creature(
            engine,
            "B",
            "Trampling Blocker",
            power=3,
            toughness=3,
            keywords=("Trample",),
        )
        attacker.attacking = "B"
        blocker.blocking = attacker.object_id
        self.combat(
            engine,
            {attacker.object_id: "B"},
            {attacker.object_id: [blocker.object_id]},
        )

        proposal = project_combat_damage_assignment(engine, "B")

        self.assertEqual(
            {blocker.ref: {"power": 3, "targets": [attacker.ref]}},
            proposal.projected_options(),
        )
        self.assertEqual((), proposal.trample_sources)

    def test_removed_attack_target_is_not_replaced_by_controller(self) -> None:
        session = self.session(70219006, players=3)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Stranded Trampler",
            power=5,
            toughness=5,
            keywords=("Trample",),
        )
        blocker = self.creature(
            engine, "B", "Remaining Blocker", power=1, toughness=2
        )
        target_ref = engine.create_token(
            "B",
            name="Departing Walker",
            characteristics={
                "type_line": "Token Planeswalker — Test",
                "loyalty": "5",
            },
        )[0]
        target = engine._resolve_object("A", target_ref, zones={"battlefield"})
        attacker.attacking = target.ref
        blocker.blocking = attacker.object_id
        self.combat(
            engine,
            {attacker.object_id: target.ref},
            {attacker.object_id: [blocker.object_id]},
            target_context={
                attacker.object_id: {
                    "target": target.ref,
                    "kind": "planeswalker",
                    "defending_player": "B",
                }
            },
        )
        engine.move_card(target.object_id, "graveyard")

        proposal = project_combat_damage_assignment(engine, "A")

        self.assertEqual(
            {attacker.ref: {"power": 5, "targets": [blocker.ref]}},
            proposal.projected_options(),
        )
        self.assertEqual(
            5,
            proposal.validate(
                [
                    {
                        "source": attacker.ref,
                        "target": blocker.ref,
                        "amount": 5,
                    }
                ]
            )[0].amount,
        )
        with self.assertRaisesRegex(
            CombatDamageAssignmentError,
            "illegal combat-damage target",
        ):
            proposal.validate(
                [
                    {
                        "source": attacker.ref,
                        "target": blocker.ref,
                        "amount": 2,
                    },
                    {"source": attacker.ref, "target": "B", "amount": 3},
                ]
            )

    def test_double_strike_trample_recomputes_after_blocker_leaves(self) -> None:
        session = self.session(70219004)
        engine = session.engine
        attacker = self.creature(
            engine,
            "A",
            "Double Trampler",
            power=4,
            toughness=4,
            keywords=("Double strike", "Trample"),
        )
        blocker = self.creature(
            engine, "B", "First Step Blocker", power=0, toughness=2
        )
        attacker.attacking = "B"
        blocker.blocking = attacker.object_id
        self.combat(
            engine,
            {attacker.object_id: "B"},
            {attacker.object_id: [blocker.object_id]},
        )
        engine._begin_combat_damage()
        session.initial_checkpoint = checkpoint_envelope(session.state)
        accepted = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {"source": attacker.ref, "target": blocker.ref, "amount": 2},
                    {"source": attacker.ref, "target": "B", "amount": 2},
                ],
            },
        )

        self.assertTrue(accepted.ok, accepted.summary)
        self.assertEqual(
            "outside",
            engine.state.cards[blocker.object_id].zone,
        )
        passed_by: list[str] = []
        for _attempt in range(8):
            if engine.state.combat.damage_step_index == 1:
                break
            passed_by.append(pass_current(session))
        self.assertEqual(34, engine.state.players["B"].life)
        self.assertEqual(
            1,
            engine.state.combat.damage_step_index,
            passed_by,
        )
        self.assert_replay(
            session,
            "double-strike-trample",
            len(session.commands),
        )


if __name__ == "__main__":
    unittest.main()
