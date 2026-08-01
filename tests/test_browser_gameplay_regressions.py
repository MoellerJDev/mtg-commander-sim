from __future__ import annotations

import unittest
import uuid

from common import keep_all, load_assets, make_session
from mtg_commander_sim.model import CardInstance, StackItem


class BrowserGameplayRegressionTests(unittest.TestCase):
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
            auto_pass_empty=True,
        )
        keep_all(session)
        session.state.config.semantic_policy = "trusted_only"
        session.engine.permissions.invalidate_current()
        session.state.pending_decision = None
        session.state.priority_player = None
        session.state.stack = []
        return session

    def add_card(self, engine, seat: str, name: str, zone: str) -> CardInstance:
        record = self.db.lookup(name, fuzzy=False)
        ref = f"X{len(engine.state.cards) + 1}"
        card = CardInstance(
            object_id=uuid.uuid4().hex,
            ref=ref,
            oracle_id=record.oracle_id,
            printed_name=record.name,
            owner=seat,
            controller=seat,
            zone=zone,
            known_to=[seat] if zone == "hand" else list(engine.seats),
            revealed_to=(list(engine.seats) if zone != "hand" else []),
        )
        engine.state.cards[card.object_id] = card
        engine.state.players[seat].zones[zone].append(card.object_id)
        return card

    @staticmethod
    def choose_targets(engine, seat: str, *targets: str) -> None:
        capability = engine.permissions.capability_for(f"pilot:{seat}")
        assert capability is not None
        result = engine.submit(
            token=capability.token,
            principal=f"pilot:{seat}",
            action="choose",
            payload={"targets": list(targets)},
        )
        assert result.ok, result.summary

    @staticmethod
    def resolve_top(engine) -> None:
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        engine._prepare_stack_resolution()

    def test_active_player_must_explicitly_end_each_main_phase(self):
        session = self.make_session(9101)
        engine = session.engine
        engine.state.config.manual_active_main_phase = True
        engine.state.started = True
        engine.state.turn_sequence = 3
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        engine.state.players["A"].land_plays_remaining = 0
        for object_id in list(engine.state.players["A"].zones["hand"]):
            engine.move_card(object_id, "library", log=False)

        engine._grant_priority("A")
        engine.pump()

        self.assertEqual("priority", engine.state.pending_decision.kind)
        self.assertEqual(["A"], engine.state.pending_decision.actors)
        capability = engine.permissions.capability_for("pilot:A")
        self.assertIsNotNone(capability)
        result = engine.submit(
            token=capability.token,
            principal="pilot:A",
            action="pass",
            payload={},
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("postcombat_main", engine.state.phase)
        self.assertEqual("priority", engine.state.pending_decision.kind)
        self.assertEqual(["A"], engine.state.pending_decision.actors)

    def test_rules_boundary_changes_session_lifecycle_to_paused(self):
        session = self.make_session(9105)
        engine = session.engine
        engine.state.started = True
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine.pump()
        engine.state.annotations.append(
            {
                "kind": "semantic_unsupported",
                "active": True,
                "label": "Unsupported Test Card",
                "semantic_key": "test:unsupported",
                "semantic_policy": "trusted_only",
            }
        )

        result = session.act("pilot:A", {"action_id": "pass"})

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("paused", session.record_status)
        self.assertEqual(
            "semantic_unsupported", session.pause_reason["kind"]
        )

    def test_sunscorched_desert_prompts_for_target_and_deals_damage(self):
        session = self.make_session(9102)
        engine = session.engine
        desert = self.add_card(engine, "B", "Sunscorched Desert", "hand")

        engine.move_card(
            desert.object_id,
            "battlefield",
            controller="B",
            reason="land play",
            semantic_events=True,
        )
        engine._stabilize()

        self.assertEqual("semantic.target", engine.state.pending_decision.kind)
        self.assertEqual(["B"], engine.state.pending_decision.actors)
        schema = engine.state.pending_decision.payload_by_actor["B"][
            "target_schema"
        ]
        self.assertEqual(["A", "B"], schema["legal_refs"])
        self.choose_targets(engine, "B", "A")
        self.resolve_top(engine)

        self.assertEqual(39, engine.state.players["A"].life)
        self.assertEqual("battlefield", desert.zone)

    def test_orcish_bowmasters_resolves_then_damages_and_amasses(self):
        session = self.make_session(9103)
        engine = session.engine
        bowmasters = self.add_card(engine, "A", "Orcish Bowmasters", "hand")
        engine._remove_from_zone(bowmasters)
        bowmasters.zone = "stack"
        bowmasters.known_to = list(engine.seats)
        bowmasters.revealed_to = list(engine.seats)
        item = StackItem(
            stack_id=uuid.uuid4().hex,
            ref="SX1",
            kind="spell",
            controller="A",
            label="Orcish Bowmasters",
            card_object_id=bowmasters.object_id,
            semantic_key=(f"{bowmasters.oracle_id}:spell:front"),
            default_destination="battlefield",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)

        engine._prepare_stack_resolution()

        self.assertEqual("battlefield", bowmasters.zone)
        self.assertEqual("semantic.target", engine.state.pending_decision.kind)
        self.choose_targets(engine, "A", "B")
        self.resolve_top(engine)

        self.assertEqual(39, engine.state.players["B"].life)
        armies = [
            card
            for card in engine.state.cards.values()
            if card.controller == "A"
            and card.is_token
            and "army"
            in engine._type_parts(
                str(engine._effective_card_data(card)["type_line"])
            )[1]
        ]
        self.assertEqual(1, len(armies))
        self.assertEqual(1, armies[0].counters["+1/+1"])
        self.assertIn(
            "orc",
            engine._type_parts(
                str(engine._effective_card_data(armies[0])["type_line"])
            )[1],
        )

    def test_orcish_bowmasters_tracks_each_qualifying_opponent_draw(self):
        session = self.make_session(9104)
        engine = session.engine
        bowmasters = self.add_card(
            engine, "A", "Orcish Bowmasters", "battlefield"
        )
        engine.state.turn_sequence = 20
        engine.state.active_player = "B"
        engine.state.phase = "beginning"
        engine.state.step = "draw"

        engine.draw("B", 1, reason="turn-based draw")
        self.assertEqual([], engine.state.pending_trigger_batches)
        engine.draw("B", 2, reason="additional draw")

        triggered = [
            item
            for batch in engine.state.pending_trigger_batches
            for group in batch["groups"]
            for item in group["items"]
            if item["source_object_id"] == bowmasters.object_id
        ]
        self.assertEqual(2, len(triggered))


if __name__ == "__main__":
    unittest.main()
