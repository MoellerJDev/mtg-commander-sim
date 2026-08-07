from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from quorune.engine import TURN_STEPS
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)


class CleanupStepRuleTests(unittest.TestCase):
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
    def card(session, owner: str, name: str):
        return next(
            card
            for card in session.state.cards.values()
            if card.owner == owner
            and card.is_card_object
            and card.printed_name == name
        )

    @staticmethod
    def enter_cleanup(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("ending", "cleanup")
        )
        engine._enter_step()

    def test_contract_traces_every_cr_514_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "cleanup-step.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "514",
                "514.1",
                "514.2",
                "514.3",
                "514.3a",
            },
            set(contract["rule_references"]),
        )

    def test_cleanup_discard_is_exact_simultaneous_private_and_replayable(
        self,
    ):
        session = self.make_session(51401)
        engine = session.engine
        player = engine.state.players["A"]
        player.max_hand_size = len(player.zones["hand"]) - 2

        self.enter_cleanup(session)

        self.assertEqual("cleanup.discard", engine.state.pending_decision.kind)
        self.assertEqual(["pilot:A"], session.pending_principals())
        context = engine.state.pending_decision.payload_by_actor["A"]
        self.assertEqual(2, context["count"])
        chosen = [
            context["hand"][0]["id"],
            context["hand"][1]["id"],
        ]
        session.initial_checkpoint = checkpoint_envelope(engine.state)

        result = session.act(
            "pilot:A",
            {
                "a": "discard",
                "cards": chosen,
                "reason": "Discard exactly to maximum hand size.",
            },
        )

        self.assertTrue(result.ok, result.summary)
        discarded = [
            card
            for card in engine.state.cards.values()
            if card.ref in chosen
        ]
        self.assertEqual(
            {"graveyard"},
            {card.zone for card in discarded},
        )
        self.assertEqual(
            1,
            len({card.zone_timestamp for card in discarded}),
        )
        self.assertEqual(player.max_hand_size, len(player.zones["hand"]))
        self.assertFalse(engine.state.stack)
        self.assertEqual("B", engine.state.active_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "cleanup-discard"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(1, replay["commands"])

    def test_invalid_cleanup_discard_rolls_back_capability_and_state(self):
        session = self.make_session(51402)
        engine = session.engine
        player = engine.state.players["A"]
        player.max_hand_size = len(player.zones["hand"]) - 2
        self.enter_cleanup(session)
        context = engine.state.pending_decision.payload_by_actor["A"]
        first = context["hand"][0]["id"]
        before_hash = authoritative_state_hash(engine.state)

        wrong_count = session.act(
            "pilot:A",
            {"a": "discard", "cards": [first]},
        )
        self.assertFalse(wrong_count.ok)
        self.assertEqual(before_hash, authoritative_state_hash(engine.state))

        duplicate = session.act(
            "pilot:A",
            {"a": "discard", "cards": [first, first]},
        )
        self.assertFalse(duplicate.ok)
        self.assertEqual(before_hash, authoritative_state_hash(engine.state))
        capability = engine.permissions.capability_for("pilot:A")
        self.assertIsNotNone(capability)
        self.assertFalse(capability.consumed)

    def test_ordinary_cleanup_grants_no_priority(self):
        session = self.make_session(51403)
        engine = session.engine
        turn = engine.state.turn_sequence

        self.enter_cleanup(session)

        self.assertEqual(turn + 1, engine.state.turn_sequence)
        self.assertEqual("B", engine.state.active_player)
        self.assertEqual("B", engine.state.priority_player)
        self.assertFalse(
            any(
                event.code == "cleanup.priority_required"
                and event.turn_sequence == turn
                for event in engine.state.events
            )
        )

    def test_cleanup_state_action_grants_priority_then_repeats_cleanup(self):
        session = self.make_session(51404)
        engine = session.engine
        creature = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            creature.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        creature.annotations["copy_overrides"] = {
            "name": creature.printed_name,
            "type_line": "Creature — Human Artificer",
            "power": "1",
            "toughness": "0",
        }
        creature.annotations["until_end_of_turn"] = {
            "toughness": 1,
        }
        turn = engine.state.turn_sequence

        self.enter_cleanup(session)

        self.assertEqual("graveyard", creature.zone)
        self.assertEqual("A", engine.state.active_player)
        self.assertEqual("ending", engine.state.phase)
        self.assertEqual("cleanup", engine.state.step)
        self.assertEqual("A", engine.state.priority_player)
        exception = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "cleanup.priority_required"
        )
        self.assertIn(
            "state_based_action",
            exception.details["reasons"],
        )

        engine._pass_priority("A")
        engine._pass_priority("B")

        self.assertEqual("B", engine.state.active_player)
        self.assertEqual(turn + 1, engine.state.turn_sequence)
        self.assertEqual(
            2,
            sum(
                event.code == "turn.cleanup"
                and event.turn_sequence == turn
                for event in engine.state.events
            ),
        )
        self.assertEqual(
            2,
            sum(
                event.code == "step.begin"
                and event.turn_sequence == turn
                and event.phase == "ending"
                and event.step == "cleanup"
                for event in engine.state.events
            ),
        )

    def test_next_cleanup_trigger_waits_until_cleanup_actions_finish(self):
        session = self.make_session(51405)
        engine = session.engine
        permanent = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            permanent.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        permanent.marked_damage = 2
        permanent.temporary_keywords.append("Haste")
        engine.schedule_delayed_trigger(
            controller="A",
            label="Next cleanup witness",
            event_kind="step.begin",
            condition={
                "phase": "ending",
                "step": "cleanup",
                "player": "A",
            },
            stack_template={
                "label": "Next cleanup witness",
                "context": {"test": "CR 514.3a"},
            },
        )

        self.enter_cleanup(session)

        self.assertEqual(0, permanent.marked_damage)
        self.assertEqual([], permanent.temporary_keywords)
        self.assertEqual(
            "Next cleanup witness",
            engine.state.stack[-1].label,
        )
        self.assertEqual("A", engine.state.priority_player)
        cleanup_event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "turn.cleanup"
        )
        trigger_event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "stack.trigger"
            and event.details.get("trigger")
        )
        self.assertLess(cleanup_event.event_id, trigger_event.event_id)

    def test_cleanup_clears_damage_and_represented_turn_effects_together(
        self,
    ):
        session = self.make_session(51406)
        engine = session.engine
        permanent = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            permanent.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        permanent.phased_out = True
        permanent.marked_damage = 3
        permanent.deathtouch_damage = True
        permanent.temporary_keywords.extend(["Haste", "Flying"])
        permanent.annotations["until_end_of_turn"] = {
            "power": 2,
            "toughness": 2,
        }
        player = engine.state.players["A"]
        player.stats["next_spell_improvise"] = True
        player.stats["spells_cant_be_countered_until_end"] = True

        self.enter_cleanup(session)

        self.assertEqual(0, permanent.marked_damage)
        self.assertFalse(permanent.deathtouch_damage)
        self.assertEqual([], permanent.temporary_keywords)
        self.assertNotIn("until_end_of_turn", permanent.annotations)
        self.assertNotIn("next_spell_improvise", player.stats)
        self.assertNotIn(
            "spells_cant_be_countered_until_end",
            player.stats,
        )


if __name__ == "__main__":
    unittest.main()
