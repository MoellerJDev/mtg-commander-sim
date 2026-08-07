from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest

from common import ROOT, keep_all, make_session
from quorune.carddb import CardDatabase
from quorune.deck import DeckLoader
from quorune.destruction import (
    commit_destruction_plan,
    DestructionCause,
    DestructionDisposition,
    DestructionError,
    destroy_permanent_refs,
    prepare_destructions,
    request_for_card,
)
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from quorune.replacement.immutable import thaw_value
from quorune.semantic_runtime import (
    DestroyPermanentIntent,
    ReadOnlyHandlerContext,
    ReadOnlyRulesQuery,
)
from quorune.semantic_runtime.context import SemanticNodeError
from quorune.semantic_runtime.destruction_handlers import (
    DestroyPermanentHandler,
)
from scripts.build_test_database import build_fixture_database


def focused_card_database(directory: str) -> CardDatabase:
    database = Path(directory) / "destruction-rules.sqlite3"
    build_fixture_database(
        [
            ROOT / "tests" / "fixtures" / "scryfall-exact-lists.json",
            ROOT / "tests" / "fixtures" / "targeted-destruction-cards.json",
        ],
        database,
    )
    return CardDatabase(database)


class DestructionRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.db = focused_card_database(cls.temporary.name)
        loader = DeckLoader(cls.db)
        cls.mishra = loader.load(
            ROOT / "examples" / "mishra-eminent-one.txt",
            commander="Mishra, Eminent One",
            deck_name="Mishra",
        )
        cls.zimone = loader.load(
            ROOT / "examples" / "zimone-and-dina.txt",
            commander="Zimone and Dina",
            deck_name="Zimone",
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.temporary.cleanup()

    def session(self, seed: int, *, players: int = 4, murder: bool = False):
        mishra = copy.deepcopy(self.mishra)
        if murder:
            next(
                entry for entry in mishra.entries if entry.board == "mainboard"
            ).name = "Murder"
        session = make_session(
            self.db,
            mishra,
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
    def permanent(engine, seat: str, *, card_type: str = "creature"):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat
            and card.zone != "command"
            and (record := engine.card_record(card)) is not None
            and card_type in record.type_line.casefold().split(" — ", 1)[0].split()
        )

    @staticmethod
    def put_on_battlefield(engine, card, *, controller: str | None = None):
        engine.move_card(
            card.object_id,
            "battlefield",
            controller=controller or card.owner,
            tapped=False,
            log=False,
        )
        return card

    @staticmethod
    def pass_stack(session):
        while session.state.stack:
            principals = session.pending_principals()
            if not principals:
                raise AssertionError("Stack resolution stopped without priority")
            result = session.act(principals[0], {"action_id": "pass"})
            if not result.ok:
                raise AssertionError(result.summary)

    def assert_replays(self, session, label: str):
        expected_hash = authoritative_state_hash(session.state)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / label
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_plan_is_immutable_canonical_and_caller_copy_isolated(self):
        session = self.session(7010801, players=3)
        engine = session.engine
        first = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        second = self.put_on_battlefield(
            engine, self.permanent(engine, "C")
        )
        forward = prepare_destructions(
            engine,
            (request_for_card(first), request_for_card(second)),
            cause=DestructionCause.EFFECT,
            actor="A",
            reason="canonical batch",
        )
        reverse = prepare_destructions(
            engine,
            (request_for_card(second), request_for_card(first)),
            cause=DestructionCause.EFFECT,
            actor="A",
            reason="canonical batch",
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(
            sorted((first.object_id, second.object_id)),
            [entry.object_id for entry in forward.entries],
        )
        with self.assertRaises(FrozenInstanceError):
            forward.reason = "mutated"  # type: ignore[misc]

        selection = {"event_path": [0], "selection": "replacement-a"}
        isolated = prepare_destructions(
            engine,
            (request_for_card(first),),
            cause=DestructionCause.EFFECT,
            actor="A",
            reason="copy isolation",
            replacement_selections=(selection,),
        )
        selection["event_path"].append(9)
        selection["selection"] = "replacement-b"
        self.assertEqual(
            {"event_path": [0], "selection": "replacement-a"},
            thaw_value(isolated.replacement_selections[0]),
        )

    def test_handler_lowers_one_strict_typed_intent(self):
        context = ReadOnlyHandlerContext(
            actor="A",
            default_reason="destroy fixture",
            query=ReadOnlyRulesQuery(
                seats=("A", "B", "C", "D"),
                active_seats=("A", "B", "C", "D"),
                apnap_order=("B", "C", "D", "A"),
            ),
        )
        plan = DestroyPermanentHandler().lower(
            {"op": "destroy", "card": "B01"},
            context,
        )
        self.assertEqual("generic.destroy-permanent.v1", plan.handler_id)
        self.assertEqual(
            (
                DestroyPermanentIntent(
                    actor="A",
                    object_ref="B01",
                    reason="destroy fixture",
                ),
            ),
            plan.intents,
        )
        for malformed in (
            {"op": "destroy", "card": ""},
            {"op": "destroy", "card": "B01", "reason": 4},
            {
                "op": "destroy",
                "card": "B01",
                "_replacement_selections": "replacement-a",
            },
            {"op": "destroy", "card": "B01", "destination": "exile"},
        ):
            with self.subTest(effect=malformed):
                with self.assertRaises(SemanticNodeError):
                    DestroyPermanentHandler().lower(malformed, context)

    def test_effect_destruction_consumes_shield_instead(self):
        session = self.session(7010802, players=2)
        engine = session.engine
        target = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        target.counters["shield"] = 2

        result = destroy_permanent_refs(
            engine,
            (target.ref,),
            actor="A",
            reason="shield replacement witness",
        )

        self.assertEqual((), result.destroyed_object_ids)
        self.assertEqual((target.object_id,), result.shielded_object_ids)
        self.assertEqual("battlefield", target.zone)
        self.assertEqual(1, target.counters["shield"])
        self.assertIn(
            "permanent.destroy.replaced",
            [event.code for event in engine.state.events],
        )

    def test_state_based_destruction_ignores_shield_counter(self):
        session = self.session(7010803, players=2)
        engine = session.engine
        target = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        target.counters["shield"] = 1
        plan = prepare_destructions(
            engine,
            (request_for_card(target),),
            cause=DestructionCause.STATE_BASED_ACTION,
            actor=None,
            reason="lethal damage state-based action",
        )
        self.assertEqual(
            DestructionDisposition.DESTROY,
            plan.entries[0].disposition,
        )
        self.assertFalse(plan.shield_counter_plan.transitions)

        result = commit_destruction_plan(engine, plan)

        self.assertEqual((target.object_id,), result.destroyed_object_ids)
        self.assertEqual("graveyard", target.zone)
        self.assertNotIn("permanent.destroy.replaced", [
            event.code for event in engine.state.events
        ])

    def test_indestructible_and_phased_objects_are_not_destroyed(self):
        session = self.session(7010804, players=2)
        engine = session.engine
        citadel = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Darksteel Citadel"
        )
        self.put_on_battlefield(engine, citadel)
        citadel.counters["shield"] = 1

        result = destroy_permanent_refs(
            engine,
            (citadel.ref,),
            actor="B",
            reason="Indestructible witness",
        )

        self.assertEqual((citadel.object_id,), result.indestructible_object_ids)
        self.assertEqual("battlefield", citadel.zone)
        self.assertEqual(1, citadel.counters["shield"])

        phased = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        phased.phased_out = True
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(DestructionError, "phased-in"):
            prepare_destructions(
                engine,
                (request_for_card(phased),),
                cause=DestructionCause.EFFECT,
                actor="A",
                reason="phasing witness",
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))

    def test_indestructible_can_move_for_a_nondestruction_companion_sba(self):
        session = self.session(7010808, players=2)
        engine = session.engine
        citadel = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Darksteel Citadel"
        )
        self.put_on_battlefield(engine, citadel)
        plan = prepare_destructions(
            engine,
            (request_for_card(citadel),),
            cause=DestructionCause.STATE_BASED_ACTION,
            actor=None,
            reason="overlapping state-based actions",
        )

        result = commit_destruction_plan(
            engine,
            plan,
            companion_changes=((citadel.object_id, "graveyard"),),
        )

        self.assertEqual((citadel.object_id,), result.indestructible_object_ids)
        self.assertEqual("graveyard", citadel.zone)

    def test_stale_destruction_plan_rolls_back_without_mutation(self):
        session = self.session(7010805, players=2)
        engine = session.engine
        target = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        plan = prepare_destructions(
            engine,
            (request_for_card(target),),
            cause=DestructionCause.EFFECT,
            actor="A",
            reason="stale plan witness",
        )
        target.counters["shield"] = 1
        before = authoritative_state_hash(engine.state)

        with self.assertRaisesRegex(DestructionError, "stale"):
            commit_destruction_plan(engine, plan)

        self.assertEqual(before, authoritative_state_hash(engine.state))
        self.assertEqual("battlefield", target.zone)
        self.assertEqual(1, target.counters["shield"])

    def test_simultaneous_multiplayer_batch_has_disjoint_results(self):
        session = self.session(7010806, players=4)
        engine = session.engine
        ordinary = self.put_on_battlefield(
            engine, self.permanent(engine, "B")
        )
        shielded = self.put_on_battlefield(
            engine, self.permanent(engine, "D")
        )
        shielded.counters["shield"] = 1
        citadel = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "C" and card.printed_name == "Darksteel Citadel"
        )
        self.put_on_battlefield(engine, citadel)

        result = destroy_permanent_refs(
            engine,
            (shielded.ref, citadel.ref, ordinary.ref),
            actor="A",
            reason="four-player batch witness",
        )

        self.assertEqual((ordinary.object_id,), result.destroyed_object_ids)
        self.assertEqual((shielded.object_id,), result.shielded_object_ids)
        self.assertEqual((citadel.object_id,), result.indestructible_object_ids)
        self.assertEqual("graveyard", ordinary.zone)
        self.assertEqual("battlefield", shielded.zone)
        self.assertNotIn("shield", shielded.counters)
        self.assertEqual("battlefield", citadel.zone)

    def test_effect_destruction_uses_typed_owner_and_replays(self):
        session = self.session(7010807, players=4, murder=True)
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Murder"
        )
        target = self.put_on_battlefield(
            engine, self.permanent(engine, "C")
        )
        engine.move_card(source.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["B"] = 3
        engine.state.priority_player = "A"
        hints = engine._priority_action_hints("A")
        action = next(
            row for row in hints["actions"] if row.get("card") == source.ref
        )
        self.assertEqual("cast", action["action"])
        self.assertIn(target.ref, action["target_schema"]["legal_refs"])
        self.assertFalse(
            {"A", "B", "C", "D"}.intersection(
                action["target_schema"]["legal_refs"]
            )
        )
        engine._issue_priority("A", hints)
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        before = authoritative_state_hash(engine.state)
        rejected = session.act(
            "pilot:A",
            {
                "action_id": action["id"],
                "targets": ["C"],
                "pay": "manual",
                "payment": {"B": 3},
            },
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(before, authoritative_state_hash(engine.state))
        source = engine.state.cards[source.object_id]
        target = engine.state.cards[target.object_id]

        accepted = session.act(
            "pilot:A",
            {
                "action_id": action["id"],
                "targets": [target.ref],
                "pay": "manual",
                "payment": {"B": 3},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.pass_stack(session)

        self.assertEqual("graveyard", target.zone)
        self.assertEqual("graveyard", source.zone)
        self.assertIn(
            "permanent.destroyed",
            [event.code for event in engine.state.events],
        )
        self.assert_replays(session, "targeted-destruction-record")


if __name__ == "__main__":
    unittest.main()
