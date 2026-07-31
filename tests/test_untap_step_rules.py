from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import TURN_STEPS
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticProgram


class UntapStepRuleTests(unittest.TestCase):
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
    def token(
        engine,
        controller: str,
        name: str,
        *,
        tapped: bool = False,
        oracle_text: str = "",
        keywords: list[str] | None = None,
    ):
        ref = engine.create_token(
            controller,
            name=name,
            tapped=tapped,
            characteristics={
                "type_line": "Token Creature — Construct",
                "oracle_text": oracle_text,
                "power": "2",
                "toughness": "2",
                "keywords": list(keywords or []),
            },
        )[0]
        return next(
            card
            for card in engine.state.cards.values()
            if card.ref == ref
        )

    @staticmethod
    def enter_untap(session) -> None:
        engine = session.engine
        engine.state.phase_index = TURN_STEPS.index(
            ("beginning", "untap")
        )
        engine._enter_step()

    def test_contract_traces_every_cr_502_rule(self):
        root = Path(__file__).resolve().parents[1]
        contract = json.loads(
            (
                root
                / "mechanics"
                / "contracts"
                / "untap-step.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            {
                "502",
                "502.1",
                "502.2",
                "502.2a",
                "502.3",
                "502.4",
            },
            set(contract["rule_references"]),
        )

    def test_ordinary_untap_is_stackless_and_advances_directly_to_upkeep(
        self,
    ):
        session = self.make_session(50201)
        engine = session.engine
        first = self.token(engine, "A", "First Untap Witness", tapped=True)
        second = self.token(
            engine,
            "A",
            "Second Untap Witness",
            tapped=True,
        )
        before_event = engine.state.event_sequence
        before_priority_epoch = engine.state.priority_epoch

        self.enter_untap(session)

        self.assertFalse(first.tapped)
        self.assertFalse(second.tapped)
        self.assertEqual(
            ("beginning", "upkeep"),
            (engine.state.phase, engine.state.step),
        )
        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual(
            before_priority_epoch + 1,
            engine.state.priority_epoch,
        )
        self.assertFalse(engine.state.stack)
        events = [
            event
            for event in engine.state.events
            if event.event_id > before_event
        ]
        self.assertEqual(
            ["step.begin", "permanent.untap", "step.begin"],
            [event.code for event in events],
        )
        self.assertEqual(
            {first.ref, second.ref},
            set(events[1].details["objects"]),
        )

    def test_stun_and_next_untap_restrictions_precede_the_untap_batch(
        self,
    ):
        session = self.make_session(50202)
        engine = session.engine
        stunned = self.token(engine, "A", "Stunned Witness", tapped=True)
        delayed = self.token(
            engine,
            "A",
            "Next-Untap Witness",
            tapped=True,
        )
        ordinary = self.token(
            engine,
            "A",
            "Ordinary Witness",
            tapped=True,
        )
        stunned.counters["stun"] = 1
        delayed.annotations["does_not_untap_next"] = True

        self.enter_untap(session)

        self.assertTrue(stunned.tapped)
        self.assertNotIn("stun", stunned.counters)
        self.assertTrue(delayed.tapped)
        self.assertNotIn("does_not_untap_next", delayed.annotations)
        self.assertFalse(ordinary.tapped)

        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        self.enter_untap(session)

        self.assertFalse(stunned.tapped)
        self.assertFalse(delayed.tapped)

    def test_phasing_turn_action_fails_closed_before_untap_mutation(
        self,
    ):
        session = self.make_session(50203)
        engine = session.engine
        phasing = self.token(
            engine,
            "A",
            "Phasing Witness",
            tapped=True,
            keywords=["Phasing"],
        )
        ordinary = self.token(
            engine,
            "A",
            "Unaffected Witness",
            tapped=True,
        )

        self.enter_untap(session)

        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertEqual("untap.phasing", pause["event"])
        self.assertEqual("Phasing Witness", pause["label"])
        self.assertEqual(
            ("beginning", "untap"),
            (engine.state.phase, engine.state.step),
        )
        self.assertTrue(phasing.tapped)
        self.assertTrue(ordinary.tapped)
        self.assertIsNone(engine.state.priority_player)
        self.assertFalse(engine.state.stack)

    def test_global_untap_limit_fails_closed_instead_of_untapping_all(
        self,
    ):
        session = self.make_session(50204, players=4)
        engine = session.engine
        limiter = self.token(
            engine,
            "C",
            "Untap Limit Witness",
            oracle_text=(
                "As long as this artifact is untapped, players can't untap "
                "more than two permanents during their untap steps."
            ),
        )
        limiter.annotations["token_characteristics"]["type_line"] = (
            "Token Artifact"
        )
        tapped = [
            self.token(
                engine,
                "A",
                f"Limited Permanent {index}",
                tapped=True,
            )
            for index in range(3)
        ]

        self.enter_untap(session)

        pause = engine._semantic_pause_annotation()
        self.assertIsNotNone(pause)
        self.assertEqual(
            "untap.selection_restriction",
            pause["event"],
        )
        self.assertEqual("Untap Limit Witness", pause["label"])
        self.assertTrue(all(card.tapped for card in tapped))
        self.assertIsNone(engine.state.priority_player)

        inactive_session = self.make_session(50206, players=4)
        inactive_engine = inactive_session.engine
        inactive_limiter = self.token(
            inactive_engine,
            "C",
            "Inactive Untap Limit Witness",
            tapped=True,
            oracle_text=(
                "As long as this artifact is untapped, players can't untap "
                "more than two permanents during their untap steps."
            ),
        )
        inactive_limiter.annotations["token_characteristics"][
            "type_line"
        ] = "Token Artifact"
        unrestricted = [
            self.token(
                inactive_engine,
                "A",
                f"Unrestricted Permanent {index}",
                tapped=True,
            )
            for index in range(3)
        ]

        self.enter_untap(inactive_session)

        self.assertIsNone(inactive_engine._semantic_pause_annotation())
        self.assertTrue(inactive_limiter.tapped)
        self.assertTrue(all(not card.tapped for card in unrestricted))

    def test_untap_trigger_waits_for_upkeep_priority_and_replays(
        self,
    ):
        session = self.make_session(50205)
        engine = session.engine
        source = self.card(session, "A", "Sai, Master Thopterist")
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        source.tapped = True
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:cr502-untapped",
                label="CR 502 held untap trigger",
                oracle_id=source.oracle_id,
                ability_id="test:cr502-untapped",
                active_zone="battlefield",
                event="permanent.untap.self",
                effects=[],
            )
        )
        before_priority_epoch = engine.state.priority_epoch

        self.enter_untap(session)

        self.assertEqual(
            ("beginning", "upkeep"),
            (engine.state.phase, engine.state.step),
        )
        self.assertEqual(
            ["CR 502 held untap trigger"],
            [item.label for item in engine.state.stack],
        )
        self.assertEqual("A", engine.state.priority_player)
        self.assertEqual(
            before_priority_epoch + 1,
            engine.state.priority_epoch,
        )

        engine.pump()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        for seat in ("A", "B"):
            result = session.act(
                f"pilot:{seat}",
                {
                    "a": "pass",
                    "reason": "Pass priority over the held untap trigger.",
                },
            )
            self.assertTrue(result.ok, result.summary)
        self.assertFalse(engine.state.stack)
        self.assertEqual("A", engine.state.priority_player)

        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "untap-held-trigger"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)
            self.assertEqual(2, replay["commands"])


if __name__ == "__main__":
    unittest.main()
