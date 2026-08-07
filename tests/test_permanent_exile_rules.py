from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import ROOT, keep_all, make_session
from mtg_commander_sim import permanent_exile as exile_module
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.deck import DeckLoader
from mtg_commander_sim.permanent_exile import (
    commit_permanent_exile,
    exile_permanent,
    PermanentExileError,
    prepare_permanent_exile,
    request_for_card,
)
from mtg_commander_sim.projection import StateProjector
from mtg_commander_sim.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from mtg_commander_sim.replacement.immutable import thaw_value
from mtg_commander_sim.semantic_runtime import (
    ExilePermanentIntent,
    ReadOnlyHandlerContext,
    ReadOnlyRulesQuery,
)
from mtg_commander_sim.semantic_runtime.context import SemanticNodeError
from mtg_commander_sim.semantic_runtime.permanent_exile_handlers import (
    ExilePermanentHandler,
)
from mtg_commander_sim.semantics import SemanticProgram
from scripts.build_test_database import build_fixture_database


def focused_card_database(directory: str) -> CardDatabase:
    database = Path(directory) / "permanent-exile.sqlite3"
    build_fixture_database(
        [
            ROOT / "tests" / "fixtures" / "scryfall-exact-lists.json",
            ROOT / "tests" / "fixtures" / "targeted-exile-cards.json",
        ],
        database,
    )
    return CardDatabase(database)


class PermanentExileRuleTests(unittest.TestCase):
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

    def session(self, seed: int, *, players: int = 4, scour: bool = False):
        mishra = copy.deepcopy(self.mishra)
        if scour:
            next(
                entry for entry in mishra.entries if entry.board == "mainboard"
            ).name = "Scour from Existence"
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
            and card_type
            in record.type_line.casefold().split(" — ", 1)[0].split()
        )

    @staticmethod
    def put_on_battlefield(engine, card, *, controller: str | None = None):
        return engine.move_card(
            card.object_id,
            "battlefield",
            controller=controller or card.owner,
            tapped=False,
            log=False,
        )

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

    def test_exile_model_is_immutable_canonical_and_caller_copy_isolated(self):
        session = self.session(7011001, players=3)
        engine = session.engine
        target = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
            controller="C",
        )
        selection = {
            "selection": "replacement-a",
            "event_path": [0],
        }
        plan = prepare_permanent_exile(
            engine,
            request_for_card(target),
            actor="A",
            reason="copy isolation",
            replacement_selections=(selection,),
        )
        equivalent = prepare_permanent_exile(
            engine,
            request_for_card(target),
            actor="A",
            reason="copy isolation",
            replacement_selections=(
                {"event_path": [0], "selection": "replacement-a"},
            ),
        )
        selection["event_path"].append(9)
        selection["selection"] = "replacement-b"

        self.assertEqual(plan, equivalent)
        self.assertEqual(
            {"event_path": [0], "selection": "replacement-a"},
            thaw_value(plan.replacement_selections[0]),
        )
        with self.assertRaises(FrozenInstanceError):
            plan.reason = "mutated"  # type: ignore[misc]

    def test_handler_lowers_one_strict_typed_exile_intent(self):
        context = ReadOnlyHandlerContext(
            actor="A",
            default_reason="exile fixture",
            query=ReadOnlyRulesQuery(
                seats=("A", "B", "C", "D"),
                active_seats=("A", "B", "C", "D"),
                apnap_order=("B", "C", "D", "A"),
            ),
        )
        plan = ExilePermanentHandler().lower(
            {"op": "exile_permanent", "card": "B01"},
            context,
        )
        self.assertEqual("generic.exile-permanent.v1", plan.handler_id)
        self.assertEqual(
            (
                ExilePermanentIntent(
                    actor="A",
                    object_ref="B01",
                    reason="exile fixture",
                ),
            ),
            plan.intents,
        )
        for malformed in (
            {"op": "exile_permanent", "card": ""},
            {"op": "exile_permanent", "card": "B01", "reason": 4},
            {
                "op": "exile_permanent",
                "card": "B01",
                "_replacement_selections": "replacement-a",
            },
            {
                "op": "exile_permanent",
                "card": "B01",
                "destination": "exile",
            },
        ):
            with self.subTest(effect=malformed):
                with self.assertRaises(SemanticNodeError):
                    ExilePermanentHandler().lower(malformed, context)

    def test_control_changed_permanent_exiles_to_owner_public_zone(self):
        session = self.session(7011002)
        engine = session.engine
        target = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
            controller="C",
        )
        previous_logical_id = target.logical_object_id

        result = exile_permanent(
            engine,
            target.ref,
            actor="A",
            reason="control-change witness",
        )

        self.assertEqual("B", result.owner)
        self.assertEqual("C", result.origin_controller)
        self.assertTrue(result.exiled)
        self.assertEqual("exile", target.zone)
        self.assertEqual("B", target.controller)
        self.assertIn(target.object_id, engine.state.players["B"].zones["exile"])
        self.assertNotIn(
            target.object_id,
            engine.state.players["C"].zones["battlefield"],
        )
        self.assertNotEqual(previous_logical_id, target.logical_object_id)
        self.assertEqual(
            1,
            sum(
                event.code == "permanent.exile"
                for event in engine.state.events
            ),
        )

    def test_exile_destination_replacement_preserves_typed_result(self):
        session = self.session(7011003)
        engine = session.engine
        target = self.put_on_battlefield(
            engine,
            self.permanent(engine, "A"),
        )
        source = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
        )
        engine.semantics.put(
            SemanticProgram(
                key="test:exile-destination-replacement",
                label="Replace exile destination",
                oracle_id=source.oracle_id,
                ability_id="static:front:exile-destination",
                active_zone="battlefield",
                event="zone.change",
                trust_level="provisional",
                handlers=[
                    {
                        "handler_id": "replacement.zone.destination.v1",
                        "schema_version": 1,
                        "event": "zone.change",
                        "condition": {
                            "destination": "exile",
                            "object_kind": "card",
                            "owner_relation": "opponent",
                        },
                        "destination": "graveyard",
                        "counters": {"exile-replacement": 1},
                    }
                ],
            )
        )

        with patch.object(
            type(engine),
            "semantic_program_is_current_trusted",
            return_value=True,
        ):
            result = exile_permanent(
                engine,
                target.ref,
                actor="B",
                reason="destination replacement witness",
            )

        self.assertFalse(result.exiled)
        self.assertEqual("graveyard", result.destination)
        self.assertEqual("graveyard", target.zone)
        self.assertEqual(1, target.counters["exile-replacement"])
        event = next(
            event
            for event in reversed(engine.state.events)
            if event.code == "permanent.exile"
        )
        self.assertEqual("graveyard", event.details["destination"])
        self.assertEqual("exile", event.details["requested_destination"])

    def test_indestructible_and_shield_do_not_prevent_exile(self):
        session = self.session(7011004, players=2)
        engine = session.engine
        citadel = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Darksteel Citadel"
        )
        self.put_on_battlefield(engine, citadel)
        citadel.counters["shield"] = 1

        result = exile_permanent(
            engine,
            citadel.ref,
            actor="B",
            reason="nondestruction interaction witness",
        )

        self.assertTrue(result.exiled)
        self.assertEqual("exile", citadel.zone)
        self.assertNotIn(
            "permanent.destroy.replaced",
            [event.code for event in engine.state.events],
        )
        self.assertNotIn(
            "permanent.destroy.prohibited",
            [event.code for event in engine.state.events],
        )

    def test_exile_phased_and_stale_permanents_fail_before_mutation(self):
        session = self.session(7011005)
        engine = session.engine
        phased = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
        )
        phased.phased_out = True
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(PermanentExileError, "phased-in"):
            prepare_permanent_exile(
                engine,
                request_for_card(phased),
                actor="A",
                reason="phasing witness",
            )
        self.assertEqual(before, authoritative_state_hash(engine.state))

        phased.phased_out = False
        plan = prepare_permanent_exile(
            engine,
            request_for_card(phased),
            actor="A",
            reason="stale control witness",
        )
        phased.controller = "C"
        before = authoritative_state_hash(engine.state)
        with self.assertRaisesRegex(PermanentExileError, "stale"):
            commit_permanent_exile(engine, plan)
        self.assertEqual(before, authoritative_state_hash(engine.state))
        self.assertEqual("battlefield", phased.zone)

    def test_compiled_exile_is_multiplayer_public_and_replays(self):
        session = self.session(7011006, scour=True)
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Scour from Existence"
        )
        target = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
        )
        engine.move_card(source.object_id, "hand", log=False)
        engine.state.players["A"].mana_pool["C"] = 7
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
                "targets": ["B"],
                "pay": "manual",
                "payment": {"C": 7},
            },
        )
        self.assertFalse(rejected.ok)
        self.assertEqual(before, authoritative_state_hash(engine.state))

        accepted = session.act(
            "pilot:A",
            {
                "action_id": action["id"],
                "targets": [target.ref],
                "pay": "manual",
                "payment": {"C": 7},
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.pass_stack(session)

        committed_target = engine.state.cards[target.object_id]
        committed_source = engine.state.cards[source.object_id]
        self.assertEqual("exile", committed_target.zone)
        self.assertEqual("B", committed_target.owner)
        self.assertEqual("graveyard", committed_source.zone)
        self.assertIn(
            "permanent.exile",
            [event.code for event in engine.state.events],
        )
        for seat in ("A", "B", "C", "D"):
            projected = StateProjector(self.db, engine.state)._snapshot(
                f"pilot:{seat}"
            )
            self.assertIn(
                committed_target.ref,
                {
                    row["id"]
                    for row in projected["players"]["B"]["ex"]
                },
            )
        projected_d = StateProjector(self.db, engine.state)._snapshot(
            "pilot:D"
        )
        private_refs = {
            engine.state.cards[object_id].ref
            for object_id in engine.state.players["B"].zones["hand"]
        }
        serialized_d = json.dumps(projected_d, sort_keys=True)
        self.assertTrue(all(ref not in serialized_d for ref in private_refs))
        self.assert_replays(session, "targeted-permanent-exile-record")

    def test_permanent_exile_transaction_mutant_is_killed(self):
        session = self.session(7011007)
        engine = session.engine
        target = self.put_on_battlefield(
            engine,
            self.permanent(engine, "B"),
        )
        plan = prepare_permanent_exile(
            engine,
            request_for_card(target),
            actor="A",
            reason="stale-validation mutation witness",
        )
        target.controller = "C"

        def assert_stale_rejected() -> None:
            before = authoritative_state_hash(engine.state)
            with self.assertRaises(PermanentExileError):
                commit_permanent_exile(engine, plan)
            self.assertEqual(before, authoritative_state_hash(engine.state))

        assert_stale_rejected()
        with patch.object(
            exile_module,
            "validate_permanent_exile_plan",
            lambda _host, _plan: None,
        ):
            with self.assertRaises(AssertionError):
                assert_stale_rejected()


if __name__ == "__main__":
    unittest.main()
