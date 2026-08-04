from __future__ import annotations

import unittest
import uuid

from common import keep_all, load_assets, make_session, set_fixture_turn
from mtg_commander_sim import CommanderSession, GameConfig
from mtg_commander_sim.deck import DeckDefinition, DeckEntry
from mtg_commander_sim.model import CardInstance, StackItem


class CommanderDuelTurnStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_duel(self) -> CommanderSession:
        spire = DeckDefinition(
            name="Spire Garden turn-state fixture",
            commanders=["Saskia the Unyielding"],
            entries=[
                DeckEntry("Saskia the Unyielding", 1, "commander"),
                DeckEntry("Spire Garden"),
                DeckEntry("Forest", 49),
                DeckEntry("Mountain", 49),
            ],
        )
        islands = DeckDefinition(
            name="Island turn-state fixture",
            commanders=["Mishra, Eminent One"],
            entries=[
                DeckEntry("Mishra, Eminent One", 1, "commander"),
                DeckEntry("Island", 99),
            ],
        )
        session = CommanderSession.create(
            self.db,
            {"A": spire, "B": islands},
            first_player="A",
            seed=1,
            config=GameConfig(
                seed=1,
                profile="commander_duel",
                auto_pass_empty_priority=False,
            ),
        )
        keep_all(session)
        return session

    @staticmethod
    def hand_count(session: CommanderSession, seat: str) -> int:
        return sum(
            card.owner == seat and card.zone == "hand"
            for card in session.state.cards.values()
        )

    @staticmethod
    def legal_actions(session: CommanderSession, seat: str) -> list[dict]:
        decision = session.state.pending_decision
        if decision is None:
            return []
        return list(
            (decision.payload_by_actor.get(seat, {}).get("legal") or {}).get(
                "actions", []
            )
        )

    def advance_until(self, session: CommanderSession, predicate) -> None:
        for _ in range(80):
            if predicate(session.state):
                return
            principals = session.pending_principals()
            if not principals:
                session.engine.pump()
                continue
            result = session.act(principals[0], {"a": "pass"})
            self.assertTrue(result.ok, result.summary)
        self.fail("Turn-state fixture did not reach the requested boundary")

    def play_first_land(self, session: CommanderSession, seat: str) -> None:
        action = next(
            action
            for action in self.legal_actions(session, seat)
            if str(action["id"]).startswith("play-land:")
        )
        result = session.act(f"pilot:{seat}", {"action_id": action["id"]})
        self.assertTrue(result.ok, result.summary)

    def test_full_control_exposes_upkeep_priority_without_advancing_turn(self):
        session = self.make_duel()

        self.assertEqual(1, session.state.turn_sequence)
        self.assertEqual("A", session.state.active_player)
        self.assertEqual("A", session.state.priority_player)
        self.assertEqual("beginning", session.state.phase)
        self.assertEqual("upkeep", session.state.step)
        self.assertEqual(["pilot:A"], session.pending_principals())

    def test_spire_garden_is_offered_in_own_duel_main_phase(self):
        session = self.make_duel()
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 1
            and state.phase == "precombat_main"
            and state.priority_player == "A",
        )

        spire = next(
            card
            for card in session.state.cards.values()
            if card.printed_name == "Spire Garden"
        )
        self.assertIn(
            f"play-land:{spire.ref}",
            {action["id"] for action in self.legal_actions(session, "A")},
        )

    def test_spire_garden_enters_tapped_with_one_opponent(self):
        session = self.make_duel()
        self.advance_until(
            session,
            lambda state: state.phase == "precombat_main"
            and state.priority_player == "A",
        )
        spire = next(
            card
            for card in session.state.cards.values()
            if card.printed_name == "Spire Garden"
        )

        result = session.act(
            "pilot:A", {"action_id": f"play-land:{spire.ref}"}
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("battlefield", spire.zone)
        self.assertTrue(spire.tapped)

    def test_nonactive_player_cannot_play_land_while_holding_priority(self):
        session = self.make_duel()
        self.advance_until(
            session,
            lambda state: state.phase == "precombat_main"
            and state.priority_player == "B",
        )

        self.assertEqual("A", session.state.active_player)
        self.assertEqual("B", session.state.priority_player)
        self.assertFalse(
            any(
                str(action["id"]).startswith("play-land:")
                for action in self.legal_actions(session, "B")
            )
        )

    def test_projection_explains_own_land_without_exposing_it_publicly(self):
        session = self.make_duel()
        engine = session.engine
        spire = next(
            card
            for card in session.state.cards.values()
            if card.printed_name == "Spire Garden"
        )
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"

        projected = session.projector._snapshot("pilot:A")
        explanation = projected["action_explanations"][spire.ref]

        self.assertEqual("not_active_player", explanation["reason"])
        self.assertIn("Seat B is the active player", explanation["message"])
        self.assertNotIn(
            "action_explanations",
            session.projector._snapshot("spectator"),
        )
        self.assertNotIn(
            spire.ref,
            session.projector._snapshot("pilot:B").get(
                "action_explanations", {}
            ),
        )

    def test_land_explanation_codes_cover_safe_unavailable_boundaries(self):
        session = self.make_duel()
        engine = session.engine
        spire = next(
            card
            for card in session.state.cards.values()
            if card.printed_name == "Spire Garden"
        )

        def reason() -> str:
            return session.projector._snapshot("pilot:A")[
                "action_explanations"
            ][spire.ref]["reason"]

        engine.state.active_player = "A"
        engine.state.priority_player = "A"
        engine.state.phase = "beginning"
        engine.state.step = "upkeep"
        self.assertEqual("not_main_phase", reason())

        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.stack.append(
            StackItem(
                stack_id=uuid.uuid4().hex,
                ref="S-safe-explanation",
                kind="spell",
                controller="B",
                label="Public stack object",
            )
        )
        self.assertEqual("stack_not_empty", reason())
        engine.state.stack.clear()

        engine.state.players["A"].land_plays_remaining = 0
        self.assertEqual("no_land_play_remaining", reason())
        engine.state.players["A"].land_plays_remaining = 1
        engine.state.priority_player = "B"
        self.assertEqual("not_priority_player", reason())

        engine.move_card(spire.object_id, "graveyard", log=False)
        self.assertEqual("unsupported_face_or_zone_permission", reason())

    def test_duel_first_player_skips_only_turn_one_draw(self):
        session = self.make_duel()
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 1
            and state.step == "draw"
            and state.priority_player == "A",
        )
        self.assertEqual(7, self.hand_count(session, "A"))

        self.advance_until(
            session,
            lambda state: state.turn_sequence == 1
            and state.phase == "precombat_main"
            and state.priority_player == "A",
        )
        self.play_first_land(session, "A")
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 2
            and state.phase == "precombat_main"
            and state.priority_player == "B",
        )
        self.play_first_land(session, "B")
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 3
            and state.step == "draw"
            and state.priority_player == "A",
        )
        self.assertEqual(7, self.hand_count(session, "A"))

    def test_duel_second_player_draws_on_turn_two(self):
        session = self.make_duel()
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 2
            and state.step == "draw"
            and state.priority_player == "B",
        )

        self.assertEqual(8, self.hand_count(session, "B"))

    def test_three_player_commander_starting_player_draws_on_turn_one(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=3,
            seed=9107,
            auto_pass_empty=False,
        )
        keep_all(session)
        self.assertTrue(
            session.state.config.effective_first_player_draws(3)
        )
        self.advance_until(
            session,
            lambda state: state.turn_sequence == 1
            and state.step == "draw"
            and state.priority_player == "A",
        )
        self.assertEqual(8, self.hand_count(session, "A"))


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
        set_fixture_turn(engine, 3)
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

    def test_land_play_command_stabilizes_enter_trigger_before_priority(self):
        session = self.make_session(9106)
        engine = session.engine
        desert = self.add_card(engine, "A", "Sunscorched Desert", "hand")
        engine.state.started = True
        set_fixture_turn(engine, 3)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        engine.state.players["A"].land_plays_remaining = 1
        engine._grant_priority("A")
        engine.pump()

        result = session.act(
            "pilot:A",
            {"action_id": f"play-land:{desert.ref}"},
        )

        self.assertTrue(result.ok, result.summary)
        self.assertEqual("precombat_main", engine.state.phase)
        self.assertEqual("main", engine.state.step)
        self.assertEqual("semantic.target", engine.state.pending_decision.kind)
        self.assertEqual(["A"], engine.state.pending_decision.actors)
        self.assertEqual(1, len(engine.state.stack))
        self.assertEqual(
            "Sunscorched Desert enters", engine.state.stack[-1].label
        )
        self.assertIsNone(engine.state.priority_player)

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
        set_fixture_turn(engine, 20)
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
