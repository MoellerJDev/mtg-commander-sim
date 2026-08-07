from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session, pass_current
from quorune.ability_fragments import (
    CombatKeywordTriggerKind,
    CombatKeywordTriggerSpec,
    ability_fragment_to_dict,
)
from quorune.model import CombatState
from quorune.errors import StateInvariantError
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class BlockKeywordTriggerIntegrationTests(unittest.TestCase):
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
            players=4,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine.state.phase_index = 6
        engine.state.phase = "combat"
        engine.state.step = "declare_blockers"
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def trigger_fragment(
        kind: CombatKeywordTriggerKind,
        amount: int = 1,
    ) -> dict:
        return ability_fragment_to_dict(
            CombatKeywordTriggerSpec(kind=kind, amount=amount)
        )

    @staticmethod
    def creature(
        engine,
        controller: str,
        name: str,
        *,
        fragments: tuple[dict, ...] = (),
    ):
        ref = engine.create_token(
            controller,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "3",
                "toughness": "4",
                "ability_fragments": list(fragments),
            },
        )[0]
        return engine._resolve_object(
            controller,
            ref,
            zones={"battlefield"},
        )

    def prepare_multiplayer_transition(self, session):
        engine = session.engine
        flanking = self.trigger_fragment(CombatKeywordTriggerKind.FLANKING)
        bushido_one = self.trigger_fragment(
            CombatKeywordTriggerKind.BUSHIDO,
            1,
        )
        bushido_two = self.trigger_fragment(
            CombatKeywordTriggerKind.BUSHIDO,
            2,
        )
        attacker_b = self.creature(
            engine,
            "A",
            "Flanking Bushido attacker",
            fragments=(flanking, flanking, bushido_one),
        )
        attacker_c = self.creature(
            engine,
            "A",
            "Bushido attacker",
            fragments=(bushido_one,),
        )
        blocker_b = self.creature(
            engine,
            "B",
            "Bushido two blocker",
            fragments=(bushido_two,),
        )
        blocker_c = self.creature(
            engine,
            "C",
            "Flanking Bushido blocker",
            fragments=(flanking, bushido_one),
        )
        attacker_b.attacking = "B"
        attacker_c.attacking = "C"
        engine.state.combat = CombatState(
            attackers_declared=True,
            had_attacking_creature=True,
            attackers={
                attacker_b.object_id: "B",
                attacker_c.object_id: "C",
            },
            defending_players=["B", "C"],
        )
        engine._begin_blocker_decisions()
        return attacker_b, attacker_c, blocker_b, blocker_c

    @staticmethod
    def submit_block(session, seat: str, blocker, attacker):
        return session.act(
            f"pilot:{seat}",
            {"a": "block", "blk": {blocker.ref: attacker.ref}},
        )

    def test_four_player_block_declarations_finish_before_apnap_trigger_placement(self):
        session = self.make_session(702_025_001)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )

        first = self.submit_block(session, "B", blocker_b, attacker_b)
        self.assertTrue(first.ok, first.summary)
        decision = session.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual(["C"], decision.actors)
        self.assertEqual("combat.blockers", decision.kind)
        self.assertEqual([], session.state.pending_trigger_batches)
        self.assertFalse(
            any(
                event.code == "combat.block_transition"
                for event in session.state.events
            )
        )

        second = self.submit_block(session, "C", blocker_c, attacker_c)
        self.assertTrue(second.ok, second.summary)
        decision = session.state.pending_decision
        self.assertIsNotNone(decision)
        self.assertEqual(["A"], decision.actors)
        self.assertEqual("trigger.order", decision.kind)
        self.assertEqual(1, len(session.state.pending_trigger_batches))
        batch = session.state.pending_trigger_batches[0]
        self.assertEqual(
            ["A", "B", "C"],
            [group.controller for group in batch.groups],
        )
        self.assertTrue(batch.placement_started)

    def test_flanking_and_bushido_share_one_sealed_apnap_batch(self):
        session = self.make_session(702_045_001)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )
        self.assertTrue(
            self.submit_block(session, "B", blocker_b, attacker_b).ok
        )
        self.assertTrue(
            self.submit_block(session, "C", blocker_c, attacker_c).ok
        )

        batch = session.state.pending_trigger_batches[0]
        by_controller = {
            group.controller: tuple(group.items) for group in batch.groups
        }
        self.assertEqual(4, len(by_controller["A"]))
        self.assertEqual(1, len(by_controller["B"]))
        self.assertEqual(1, len(by_controller["C"]))
        a_labels = [item.label for item in by_controller["A"]]
        self.assertEqual(2, sum("Flanking" in label for label in a_labels))
        self.assertEqual(2, sum("Bushido" in label for label in a_labels))
        self.assertTrue(
            all(
                item["context"]["event"] == "combat.block_transition"
                for item in batch.items
            )
        )
        transition_ids = {
            item["context"]["block_keyword_trigger"]["transition_id"]
            for item in batch.items
        }
        self.assertEqual(1, len(transition_ids))
        transition_event = next(
            event
            for event in session.state.events
            if event.code == "combat.block_transition"
        )
        self.assertEqual(
            transition_ids,
            {transition_event.details["transition"]["transition_id"]},
        )

    def test_four_player_block_transition_is_public_without_hidden_cards(self):
        session = self.make_session(702_045_002)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )
        self.assertTrue(
            self.submit_block(session, "B", blocker_b, attacker_b).ok
        )
        self.assertTrue(
            self.submit_block(session, "C", blocker_c, attacker_c).ok
        )

        for seat in session.state.players:
            packet = session.packet(f"pilot:{seat}", full=True)
            event = next(
                row
                for row in packet["events"]
                if row["c"] == "combat.block_transition"
            )
            self.assertIn("represented trigger", event["s"])
            for other_seat in session.state.players:
                if other_seat == seat:
                    continue
                opposing = packet["state"]["players"][other_seat]
                self.assertNotIn("hand", opposing)
                self.assertEqual(
                    len(
                        session.state.players[other_seat].zones["hand"]
                    ),
                    opposing["hand_n"],
                )

    def test_four_player_block_transition_replays_exactly(self):
        session = self.make_session(702_045_003)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )
        session.initial_checkpoint = checkpoint_envelope(session.state)
        self.assertTrue(
            self.submit_block(session, "B", blocker_b, attacker_b).ok
        )
        self.assertTrue(
            self.submit_block(session, "C", blocker_c, attacker_c).ok
        )
        expected_hash = authoritative_state_hash(session.state)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "block-keyword-trigger"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(2, replay["commands"])
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_malformed_transition_rolls_back_final_block_declaration(self):
        session = self.make_session(702_045_004)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )
        self.assertTrue(
            self.submit_block(session, "B", blocker_b, attacker_b).ok
        )
        before = authoritative_state_hash(session.state)

        with patch(
            (
                "quorune.block_transition_engine_adapter."
                "enqueue_block_transition_triggers"
            ),
            side_effect=StateInvariantError("malformed transition"),
        ):
            with self.assertRaisesRegex(
                StateInvariantError,
                "malformed transition",
            ):
                self.submit_block(
                    session,
                    "C",
                    blocker_c,
                    attacker_c,
                )

        self.assertEqual(before, authoritative_state_hash(session.state))
        self.assertEqual(["C"], session.state.pending_decision.actors)
        self.assertNotIn(
            blocker_c.object_id,
            session.state.combat.blockers.get(attacker_c.object_id, []),
        )

    def test_block_keyword_stack_resolution_updates_current_characteristics(self):
        session = self.make_session(702_045_005)
        attacker_b, attacker_c, blocker_b, blocker_c = (
            self.prepare_multiplayer_transition(session)
        )
        self.assertTrue(
            self.submit_block(session, "B", blocker_b, attacker_b).ok
        )
        self.assertTrue(
            self.submit_block(session, "C", blocker_c, attacker_c).ok
        )
        decision = session.state.pending_decision
        trigger_refs = [
            row["id"]
            for row in decision.payload_by_actor["A"]["triggers"]
        ]

        ordered = session.act(
            "pilot:A",
            {"a": "order", "triggers": trigger_refs},
        )
        self.assertTrue(ordered.ok, ordered.summary)
        self.assertEqual(6, len(session.state.stack))
        self.assertIn("Bushido 1", session.state.stack[-1].label)

        for _seat in session.engine.active_seats:
            pass_current(session)

        self.assertEqual(5, len(session.state.stack))
        current = session.engine._effective_card_data(blocker_c)
        self.assertEqual("4", current["power"])
        self.assertEqual("5", current["toughness"])


if __name__ == "__main__":
    unittest.main()
