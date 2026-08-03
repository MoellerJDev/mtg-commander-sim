from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim import CommanderSession, GameConfig
from mtg_commander_sim.model import YieldPolicy
from mtg_commander_sim.pilot import PilotResponse
from mtg_commander_sim.report import derive_review


class DecisionOpportunityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    @staticmethod
    def _card(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    @staticmethod
    def _reset_priority(engine, seat: str) -> None:
        engine.permissions.invalidate_current()
        engine.state.priority_player = seat
        engine.state.priority_passes = []
        engine.state.priority_epoch += 1

    def test_beginning_phase_yield_expires_before_own_main(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=20260730,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        land = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and engine.card_record(card)
            and engine.card_record(card).is_land
        )
        if land.zone != "hand":
            engine.move_card(land.object_id, "hand", log=False)
        engine.permissions.invalidate_current()
        engine.state.turn_sequence = 3
        engine.state.active_player = "A"
        engine.state.phase = "beginning"
        engine.state.step = "draw"
        engine.state.phase_index = 2
        engine.state.priority_player = "A"
        engine.state.priority_epoch += 1
        engine._set_yield("A", "until_public_change")

        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        engine.state.priority_epoch += 1
        engine.pump()

        self.assertEqual(["pilot:A"], session.pending_principals())
        legal = session.packet("pilot:A")["decision"]["ctx"]["legal"]
        self.assertIn(land.ref, legal["lands"])
        self.assertEqual(
            1,
            engine.state.players["A"]
            .stats["decision_optimization"]["yields_invalidated_by_phase"],
        )
        self.assertFalse(
            engine.state.action_opportunities[-1]["incorrectly_suppressed"]
        )

    def test_private_draw_invalidates_yield(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=301,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self._reset_priority(engine, "B")
        engine._set_yield("B", "until_public_change")

        engine.draw("B", 1, reason="yield invalidation regression")
        hints = engine._priority_action_hints("B")
        allowed, reason = engine._can_auto_pass(
            "B",
            action_signature=engine.meaningful_action_signature("B", hints),
            meaningful=engine._signature_has_actions("B", hints),
        )

        self.assertFalse(allowed)
        self.assertEqual("draw", reason)
        self.assertEqual("none", engine.state.players["B"].yield_policy.mode)
        self.assertEqual(
            1,
            engine.state.players["B"]
            .stats["decision_optimization"]["yields_invalidated_by_draw"],
        )

    def test_meaningful_action_signature_change_invalidates_yield(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=302,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        top = self._card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id, "battlefield", controller="A", log=False
        )
        engine.permissions.invalidate_current()
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self._reset_priority(engine, "A")
        engine._set_yield("A", "until_public_change")
        before = engine.state.players["A"].yield_policy.action_signature

        engine.state.players["A"].mana_pool["U"] = 1
        hints = engine._priority_action_hints("A")
        after = engine.meaningful_action_signature("A", hints)
        allowed, reason = engine._can_auto_pass(
            "A",
            action_signature=after,
            meaningful=engine._signature_has_actions("A", hints),
        )

        self.assertNotEqual(before, after)
        self.assertFalse(allowed)
        self.assertEqual("action_change", reason)

    def test_unchanged_nonactive_response_window_remains_safely_yielded(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=303,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        top = self._card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id, "battlefield", controller="A", log=False
        )
        engine.state.players["A"].mana_pool["U"] = 1
        engine.permissions.invalidate_current()
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self._reset_priority(engine, "A")
        engine._set_yield("A", "until_public_change")
        hints = engine._priority_action_hints("A")

        allowed, reason = engine._can_auto_pass(
            "A",
            action_signature=engine.meaningful_action_signature("A", hints),
            meaningful=engine._signature_has_actions("A", hints),
        )

        self.assertTrue(allowed)
        self.assertIsNone(reason)
        self.assertEqual(
            "until_public_change",
            engine.state.players["A"].yield_policy.mode,
        )

    def test_offer_revision_metadata_does_not_invalidate_unchanged_yield(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=304,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        top = self._card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id, "battlefield", controller="A", log=False
        )
        engine.state.players["A"].mana_pool["U"] = 1
        engine.permissions.invalidate_current()
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self._reset_priority(engine, "A")
        engine._set_yield("A", "until_public_change")
        before = engine.state.players["A"].yield_policy.action_signature

        engine.state.revision += 1
        hints = engine._priority_action_hints("A")
        after = engine.meaningful_action_signature("A", hints)
        allowed, reason = engine._can_auto_pass(
            "A",
            action_signature=after,
            meaningful=engine._signature_has_actions("A", hints),
        )

        self.assertEqual(before, after)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    def test_yield_invalidation_survives_standard_trace_reload(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=308,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        top = self._card(engine, "A", "Sensei's Divining Top")
        engine.move_card(
            top.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.state.players["A"].mana_pool["U"] = 1
        engine.permissions.invalidate_current()
        engine.state.active_player = "B"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        self._reset_priority(engine, "A")
        engine._set_yield("A", "until_public_change")
        engine._log(
            "B",
            "permanent.untap",
            "B untapped a permanent.",
            {"object": "regression"},
            importance=0,
            changed_players=["B"],
        )

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "record"
            session.save(record)
            self.assertNotIn(
                '"code":"permanent.untap"',
                (record / "events.jsonl").read_text(encoding="utf-8"),
            )
            loaded = CommanderSession.load(
                self.db,
                record,
                semantics_path=record / "semantics.json",
            )
            hints = loaded.engine._priority_action_hints("A")
            allowed, reason = loaded.engine._can_auto_pass(
                "A",
                action_signature=(
                    loaded.engine.meaningful_action_signature("A", hints)
                ),
                meaningful=loaded.engine._signature_has_actions("A", hints),
            )

        self.assertFalse(allowed)
        self.assertEqual("public_change", reason)
        self.assertEqual(
            "none",
            loaded.state.players["A"].yield_policy.mode,
        )

    def test_fidelity_fails_if_meaningful_window_is_suppressed(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=304,
            auto_pass_empty=True,
        )
        keep_all(session)
        state = session.state
        state.players["A"].stats.setdefault(
            "decision_optimization", {}
        )["suppressed_meaningful_windows"] = 1
        state.action_opportunities.append(
            {
                "sequence": 1,
                "seat": "A",
                "turn_sequence": 3,
                "phase": "precombat_main",
                "step": "main",
                "action_signature": "regression",
                "meaningful_actions_exist": True,
                "meaningful_action_ids": ["play-land:A01"],
                "incorrectly_suppressed": True,
                "outcome": "incorrectly_suppressed",
            }
        )

        review = derive_review(session.engine, decisions=[])

        self.assertEqual(
            "rules_test", review["fidelity"]["classification"]
        )
        self.assertEqual(
            "fail",
            review["fidelity"]["dimensions"]["legal_action_exposure"],
        )
        self.assertEqual(
            1, review["pilot_audit"]["suppressed_meaningful_windows"]
        )
        self.assertFalse(review["suspected_pilot_mistakes"])
        self.assertTrue(
            review["suspected_rules_or_semantics_failures"][
                "decision_opportunity_infrastructure"
            ]
        )

    def test_legacy_inactivity_is_not_attributed_to_pilot(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=305,
            auto_pass_empty=True,
        )
        keep_all(session)
        session.state.action_opportunities = []
        session.state.players["A"].stats["decision_optimization"] = {
            "yield_covered_windows": 101
        }
        session.engine._log(
            "A",
            "cleanup.discard",
            "A discarded for cleanup.",
            {"objects": ["A01"]},
        )

        review = derive_review(
            session.engine,
            decisions=[
                {
                    "accepted": True,
                    "action": "pass",
                    "decision_id": "legacy",
                    "legal_alternatives": [{"id": "pass"}],
                    "reason": "Yield through unchanged windows.",
                }
            ],
        )

        self.assertFalse(review["suspected_pilot_mistakes"])
        self.assertEqual(
            "unavailable",
            review["interaction_opportunities"]["status"],
        )
        self.assertIn(
            "infrastructure-unverified",
            review["interaction_opportunities"]["note"],
        )

    def test_illegal_target_advertisement_fails_exposure_dimension(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=306,
            auto_pass_empty=True,
        )
        keep_all(session)
        session.state.players["A"].stats.setdefault(
            "decision_optimization", {}
        ).update(
            {
                "illegal_target_actions_advertised": 1,
                "illegal_target_actions_prevented": 4,
            }
        )

        review = derive_review(session.engine, decisions=[])

        self.assertEqual(
            "rules_test", review["fidelity"]["classification"]
        )
        self.assertEqual(
            "fail",
            review["fidelity"]["dimensions"]["legal_action_exposure"],
        )
        target_audit = review["pilot_audit"]["target_action_audit"]
        self.assertEqual(1, target_audit["illegal_target_actions_advertised"])
        self.assertGreaterEqual(
            target_audit["illegal_target_actions_prevented"], 4
        )
        self.assertTrue(
            any(
                "advertised without a legal mandatory target" in failure
                for failure in review["fidelity"]["failures"]
            )
        )

    def test_fetch_untapped_and_cast_accelerator_ordered_plan(self):
        session = CommanderSession.create(
            self.db,
            {"A": self.zimone, "B": self.mishra},
            first_player="A",
            seed=20260730,
            config=GameConfig(
                seed=20260730,
                profile="commander_duel",
                auto_pass_empty_priority=True,
            ),
        )
        keep_all(session)
        engine = session.engine
        flooded = self._card(engine, "A", "Flooded Strand")
        breeding_pool = self._card(engine, "A", "Breeding Pool")
        elves = self._card(engine, "A", "Elves of Deep Shadow")
        for object_id in list(engine.state.players["A"].zones["hand"]):
            engine.move_card(object_id, "library", log=False)
        engine.move_card(flooded.object_id, "hand", log=False)
        engine.move_card(elves.object_id, "hand", log=False)
        if breeding_pool.zone != "library":
            engine.move_card(breeding_pool.object_id, "library", log=False)
        engine.permissions.invalidate_current()
        engine.state.started = True
        engine.state.turn_sequence = 1
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.phase_index = 3
        engine.state.players["A"].land_plays_remaining = 1
        engine.state.stack = []
        engine._grant_priority("A")
        engine.pump()

        fetch_ability = next(
            ability
            for ability in engine._activated_abilities(flooded)
            if engine._fetch_land_types(ability.effect_text)
        )
        response = PilotResponse.from_mapping(
            {
                "actions": [
                    {"action_id": f"play-land:{flooded.ref}"},
                    {
                        "action_id": (
                            f"activate:{flooded.ref}:"
                            f"{fetch_ability.ability_id}"
                        )
                    },
                    {
                        "action_id": "choose",
                        "choices": {
                            "search_card": breeding_pool.ref,
                            "entry_pay_life": True,
                        },
                    },
                    {"action_id": f"cast:{elves.ref}"},
                ],
                "plan": "DEVELOP_MANA",
                "reason": "Fetch untapped green and deploy Elves before passing.",
                "confidence": 0.95,
                "memory_update": (
                    "One accelerator established; next priority is B/U access."
                ),
            }
        ).engine_response()
        result = session.act("pilot:A", response)
        self.assertTrue(result.ok, result.summary)
        session.next_task()

        self.assertEqual("battlefield", breeding_pool.zone)
        search_event = next(
            event
            for event in engine.state.events
            if event.code == "library.search"
            and event.details.get("object") == breeding_pool.ref
        )
        self.assertFalse(search_event.details["tapped"])
        self.assertEqual(2, search_event.details["life_paid"])
        self.assertEqual(37, engine.state.players["A"].life)
        self.assertEqual("battlefield", elves.zone)
        command_templates = [
            row["action_template_id"] for row in session.commands[-4:]
        ]
        self.assertEqual(
            [
                f"play-land:{flooded.ref}",
                f"activate:{flooded.ref}:{fetch_ability.ability_id}",
                "choose",
                f"cast:{elves.ref}",
            ],
            command_templates,
        )
        self.assertEqual(
            ["external_decision", "planned_automatic", "planned_automatic", "planned_automatic"],
            [row["execution"] for row in session.commands[-4:]],
        )

    def test_ordered_plan_stops_when_another_principal_receives_task(self):
        session = make_session(
            self.db, self.mishra, self.zimone, players=2, seed=306
        )
        response = PilotResponse.from_mapping(
            {
                "actions": [
                    {"action_id": "keep"},
                    {"action_id": "pass"},
                ],
                "plan": "MULLIGAN",
                "reason": "Keep, with no authority to precommit another seat's window.",
                "confidence": 0.8,
            }
        ).engine_response()
        result = session.act("pilot:A", response)
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(["pilot:B"], session.pending_principals())
        self.assertNotIn("pilot:A", session.plans)

    def test_ordered_plan_stops_on_private_mulligan_draw(self):
        session = CommanderSession.create(
            self.db,
            {"B": self.mishra, "A": self.zimone},
            first_player="B",
            seed=307,
            config=GameConfig(
                seed=307,
                profile="commander_duel",
            ),
        )
        kept = session.act(
            "pilot:B",
            PilotResponse.from_mapping(
                {
                    "action_id": "keep",
                    "plan": "MULLIGAN",
                    "reason": "Keep a functional hand.",
                    "confidence": 0.8,
                }
            ).engine_response(),
        )
        self.assertTrue(kept.ok, kept.summary)
        redraw = session.act(
            "pilot:A",
            PilotResponse.from_mapping(
                {
                    "actions": [
                        {
                            "action_id": "mulligan",
                            "choices": {
                                "override_reason": (
                                    "Exercise the private-draw plan-stop regression."
                                )
                            },
                        },
                        {"action_id": "keep"},
                    ],
                    "plan": "MULLIGAN",
                    "reason": "Take the free redraw and reassess the hidden hand.",
                    "confidence": 0.8,
                }
            ).engine_response(),
        )

        self.assertTrue(redraw.ok, redraw.summary)
        self.assertNotIn("pilot:A", session.plans)
        self.assertTrue(
            any(
                event.code == "card.draw.private"
                and event.actor == "A"
                for event in session.state.events
            )
        )


if __name__ == "__main__":
    unittest.main()
