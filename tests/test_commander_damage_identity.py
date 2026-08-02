from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
import uuid

from common import keep_all, load_assets, make_session
from mtg_commander_sim.damage import (
    commit_prepared_damage_batch,
    damage_proposal,
    prepare_damage_batch,
    resolve_damage_batch,
)
from mtg_commander_sim.deck import DeckDefinition, DeckEntry
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.model import CardInstance, CombatState, GameConfig, GameState
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class CommanderDamageIdentityTests(unittest.TestCase):
    """CR 903.3/903.10a uses a designated physical commander card."""

    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session(self, seed: int = 903_100_001):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.priority_player = None
        return session

    @staticmethod
    def commander(engine: CommanderEngine, seat: str) -> CardInstance:
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.is_commander
        )

    @staticmethod
    def put_on_battlefield(
        engine: CommanderEngine,
        card: CardInstance,
        *,
        controller: str | None = None,
    ) -> None:
        engine.move_card(
            card.object_id,
            "battlefield",
            controller=controller or card.owner,
            reason="commander identity test setup",
            log=False,
            semantic_events=False,
        )

    @staticmethod
    def deal_combat_damage(
        engine: CommanderEngine,
        source: CardInstance,
        target: str,
        amount: int,
        *,
        suffix: str,
    ) -> None:
        resolve_damage_batch(
            engine,
            (
                damage_proposal(
                    engine,
                    proposal_id=f"commander-damage:{suffix}",
                    actor=source.controller,
                    source_ref=source.ref,
                    target=target,
                    amount=amount,
                    combat=True,
                    reason="CR 903.10a identity test",
                ),
            ),
        )

    def test_same_named_commanders_remain_separate_and_drive_four_player_sba(self):
        session = self.session()
        engine = session.engine
        first = self.commander(engine, "A")
        second = self.commander(engine, "C")
        self.assertEqual(first.oracle_id, second.oracle_id)
        self.assertNotEqual(
            first.commander_designation_id,
            second.commander_designation_id,
        )
        self.put_on_battlefield(engine, first)
        self.put_on_battlefield(engine, second)

        self.deal_combat_damage(engine, first, "B", 10, suffix="A-1")
        self.deal_combat_damage(engine, second, "B", 10, suffix="C-1")

        received = engine.state.players["B"].commander_damage_received
        self.assertEqual(
            {
                first.commander_designation_id: 10,
                second.commander_designation_id: 10,
            },
            received,
        )
        self.assertFalse(engine._stabilize())
        self.assertTrue(engine.state.players["B"].in_game)

        self.deal_combat_damage(engine, first, "B", 11, suffix="A-2")
        engine._stabilize()
        self.assertFalse(engine.state.players["B"].in_game)
        self.assertTrue(engine.state.players["A"].in_game)
        self.assertTrue(engine.state.players["C"].in_game)
        self.assertTrue(engine.state.players["D"].in_game)

    def test_designation_survives_zone_and_control_changes(self):
        engine = self.session(903_100_002).engine
        commander = self.commander(engine, "A")
        designation = commander.commander_designation_id
        self.put_on_battlefield(engine, commander)
        self.deal_combat_damage(engine, commander, "B", 4, suffix="before")

        engine.move_card(
            commander.object_id,
            "graveyard",
            reason="commander identity leaves",
            log=False,
            semantic_events=False,
        )
        engine.move_card(
            commander.object_id,
            "battlefield",
            controller="C",
            reason="commander identity returns under new control",
            log=False,
            semantic_events=False,
        )
        self.assertEqual(designation, commander.commander_designation_id)
        self.assertEqual("C", commander.controller)
        self.deal_combat_damage(engine, commander, "B", 5, suffix="after")

        self.assertEqual(
            {designation: 9},
            engine.state.players["B"].commander_damage_received,
        )

    def test_prepared_damage_uses_source_snapshot_after_source_leaves(self):
        engine = self.session(903_100_007).engine
        commander = self.commander(engine, "A")
        designation = commander.commander_designation_id
        self.put_on_battlefield(engine, commander)
        prepared = prepare_damage_batch(
            engine,
            (
                damage_proposal(
                    engine,
                    proposal_id="commander-damage:lki",
                    actor="A",
                    source_ref=commander.ref,
                    target="B",
                    amount=6,
                    combat=True,
                    reason="CR 903.10a source snapshot test",
                ),
            ),
        )

        engine.move_card(
            commander.object_id,
            "graveyard",
            reason="source leaves after the damage event was prepared",
            log=False,
            semantic_events=False,
        )
        commander.controller = "C"
        result = commit_prepared_damage_batch(engine, prepared)

        self.assertEqual(6, result.dealt_amount)
        self.assertEqual(
            {designation: 6},
            engine.state.players["B"].commander_damage_received,
        )
        self.assertEqual("A", result.events[0].source_controller)

    def test_ordinary_copy_of_commander_has_no_designation(self):
        engine = self.session(903_100_003).engine
        original = self.commander(engine, "A")
        copy_id = uuid.uuid4().hex
        copied = CardInstance(
            object_id=copy_id,
            ref="A-copy-commander",
            oracle_id=original.oracle_id,
            printed_name=original.printed_name,
            owner="A",
            controller="A",
            zone="battlefield",
            object_kind="card_copy",
            is_commander=False,
        )
        engine.state.cards[copy_id] = copied
        engine.state.players["A"].zones["battlefield"].append(copy_id)

        self.assertIsNone(copied.commander_designation_id)
        self.deal_combat_damage(engine, copied, "B", 5, suffix="copy")
        self.assertEqual(
            {}, engine.state.players["B"].commander_damage_received
        )

    def test_two_commander_setup_assigns_two_distinct_designations(self):
        two_commanders = DeckDefinition(
            name="Two-commanders identity fixture",
            entries=[
                DeckEntry("Mishra, Eminent One", board="commander"),
                DeckEntry("Zimone and Dina", board="commander"),
            ],
            commanders=["Mishra, Eminent One", "Zimone and Dina"],
        )
        engine = CommanderEngine.create(
            self.db,
            {"A": two_commanders, "B": two_commanders},
            first_player="A",
            config=GameConfig(seed=903_100_004),
        )

        designated = sorted(
            (
                card.commander_designation_id,
                card.oracle_id,
            )
            for card in engine.state.cards.values()
            if card.owner == "A" and card.is_commander
        )
        self.assertEqual(2, len(designated))
        self.assertEqual(2, len({value[0] for value in designated}))
        self.assertTrue(all(value[0] for value in designated))

    def test_save_load_preserves_new_identity_and_legacy_state_is_explicit(self):
        state = self.session(903_100_005).state
        restored = GameState.from_dict(copy.deepcopy(state.to_dict()))
        self.assertEqual(state.to_dict(), restored.to_dict())
        self.assertEqual(2, restored.commander_damage_identity_version)

        legacy = copy.deepcopy(state.to_dict())
        legacy.pop("commander_damage_identity_version")
        for card in legacy["cards"].values():
            card.pop("commander_designation_id", None)
        restored_legacy = GameState.from_dict(legacy)
        self.assertIsNone(restored_legacy.commander_damage_identity_version)
        self.assertNotIn(
            "commander_damage_identity_version", restored_legacy.to_dict()
        )
        self.assertTrue(
            all(
                "commander_designation_id" not in value
                for value in restored_legacy.to_dict()["cards"].values()
            )
        )

    def test_command_replay_preserves_designation_damage_key(self):
        session = self.session(903_100_006)
        engine = session.engine
        commander = self.commander(engine, "A")
        self.put_on_battlefield(engine, commander)
        commander.temporary_keywords.append("Trample")
        blocker_ref = engine.create_token(
            "B",
            name="Replay Blocker",
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "0",
                "toughness": "1",
            },
        )[0]
        blocker = next(
            card
            for card in engine.state.cards.values()
            if card.ref == blocker_ref
        )
        commander.attacking = "B"
        blocker.blocking = commander.object_id
        engine.state.active_player = "A"
        engine.state.phase_index = 7
        engine.state.phase = "combat"
        engine.state.step = "combat_damage"
        engine.state.combat = CombatState(
            attackers_declared=True,
            blockers_declared=True,
            had_attacking_creature=True,
            attackers={commander.object_id: "B"},
            defending_players=["B"],
            blockers={commander.object_id: [blocker.object_id]},
        )
        engine._begin_combat_damage()
        self.assertEqual("combat.damage", engine.state.pending_decision.kind)
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        result = session.act(
            "pilot:A",
            {
                "a": "dmg",
                "assignments": [
                    {
                        "source": commander.ref,
                        "target": blocker.ref,
                        "amount": 1,
                    },
                    {
                        "source": commander.ref,
                        "target": "B",
                        "amount": 4,
                    }
                ],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(
            {commander.commander_designation_id: 4},
            engine.state.players["B"].commander_damage_received,
        )
        expected_hash = authoritative_state_hash(engine.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "commander-identity-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(1, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])


if __name__ == "__main__":
    unittest.main()
