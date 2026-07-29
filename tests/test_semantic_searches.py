from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim import CommanderSession, GameConfig, PilotResponse
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticProgram


class SemanticPrivateSearchTests(unittest.TestCase):
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

    def _session(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=606,
            auto_pass_empty=True,
        )
        keep_all(session)
        return session

    def _begin_spell(
        self,
        session,
        *,
        seat: str,
        name: str,
        program: SemanticProgram | None = None,
    ):
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.priority_player = None
        card = self._card(engine, seat, name)
        if card.zone != "hand":
            engine.move_card(card.object_id, "hand", log=False)
        engine._remove_from_zone(card)
        card.zone = "stack"
        card.known_to = list(engine.seats)
        card.revealed_to = list(engine.seats)
        if program is not None:
            engine.semantics.put(program)
            semantic_key = program.key
        else:
            semantic_key = f"{card.oracle_id}:spell:front"
        item = StackItem(
            stack_id=uuid.uuid4().hex,
            ref="S-search-test",
            kind="spell",
            controller=seat,
            label=name,
            card_object_id=card.object_id,
            semantic_key=semantic_key,
            default_destination="graveyard",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)
        engine._prepare_stack_resolution()
        self.assertEqual(
            "semantic.search", engine.state.pending_decision.kind
        )
        session.commands.clear()
        session.decisions.clear()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        return card, item

    def test_entomb_private_search_continuation_and_exact_replay(self):
        session = self._session()
        entomb, item = self._begin_spell(
            session, seat="B", name="Entomb"
        )
        bloodghast = self._card(
            session.engine, "B", "Bloodghast"
        )
        task = session.packet("pilot:B", full=True)
        candidates = task["decision"]["ctx"]["search_cards"]
        self.assertIn(
            bloodghast.ref, {item["id"] for item in candidates}
        )
        serialized_other = json.dumps(
            session.packet("pilot:A", full=True)
        )
        self.assertNotIn(bloodghast.ref, serialized_other)
        self.assertNotIn("search_cards", serialized_other)
        arbiter = json.dumps(session.packet("arbiter", full=True))
        self.assertNotIn(bloodghast.ref, arbiter)

        frame = session.state.pending_decision.continuation[
            "semantic_frame"
        ]
        self.assertEqual(item.ref, frame["stack_object"])
        self.assertEqual(
            item.semantic_key, frame["semantic_program_id"]
        )
        self.assertEqual(
            session.state.pending_decision.decision_id,
            frame["pending_choice_id"],
        )
        before_shuffle = session.state.players["B"].stats.get(
            "shuffle_count", 0
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "search_card": bloodghast.ref,
                "plan": "DEVELOP_ENGINE",
                "reason": "Put Bloodghast into the graveyard for landfall recursion.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("graveyard", bloodghast.zone)
        self.assertEqual("graveyard", entomb.zone)
        self.assertFalse(session.state.stack)
        self.assertEqual(
            before_shuffle + 1,
            session.state.players["B"].stats["shuffle_count"],
        )
        public_search = next(
            event
            for event in session.state.events
            if event.code == "library.search"
        )
        self.assertEqual(bloodghast.ref, public_search.details["object"])
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "entomb"
            session.save(record)
            replay = replay_record(record, self.db, verify=True)
            self.assertTrue(replay["ok"])

    def _three_visits(
        self,
        land_name: str,
        *,
        pay_life: bool = False,
    ):
        session = self._session()
        spell, _ = self._begin_spell(
            session, seat="B", name="Three Visits"
        )
        land = self._card(session.engine, "B", land_name)
        if land.zone != "library":
            session.engine.move_card(
                land.object_id, "library", log=False
            )
        # Reissue after making the deterministic candidate fixture.
        session.engine.permissions.invalidate_current()
        session.engine.state.pending_decision = None
        session.engine._prepare_stack_resolution()
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "search_card": land.ref,
                "entry_pay_life": pay_life,
                "plan": "FIX_COLORS",
                "reason": f"Find {land_name} with the Forest search.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("graveyard", spell.zone)
        return session, land

    def test_three_visits_to_bayou_and_natures_lore_template(self):
        session, bayou = self._three_visits("Bayou")
        self.assertEqual("battlefield", bayou.zone)
        self.assertFalse(bayou.tapped)
        three = session.engine.semantics.get(
            "1b882a0e-0ede-4d1a-bd1a-9b7cffbcde8e:spell:front"
        )
        lore = session.engine.semantics.get(
            "78826359-fe63-44ad-adc4-a17ffcd710e4:spell:front"
        )
        self.assertEqual(three.effects, lore.effects)

    def test_three_visits_shockland_tapped_and_untapped(self):
        declined, tapped_pool = self._three_visits(
            "Breeding Pool", pay_life=False
        )
        self.assertTrue(tapped_pool.tapped)
        self.assertEqual(40, declined.state.players["B"].life)

        paid, untapped_pool = self._three_visits(
            "Breeding Pool", pay_life=True
        )
        self.assertFalse(untapped_pool.tapped)
        self.assertEqual(38, paid.state.players["B"].life)

    def test_restrictive_hidden_search_may_fail_to_find(self):
        session = self._session()
        spell, _ = self._begin_spell(
            session, seat="B", name="Three Visits"
        )
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "search_cards": [],
                "plan": "FIX_COLORS",
                "reason": "Exercise the rules-permitted hidden-zone failure to find.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("graveyard", spell.zone)

    def test_private_and_revealed_hand_search_visibility(self):
        for reveal in (False, True):
            with self.subTest(reveal=reveal):
                session = self._session()
                key = f"test:hand-search:{reveal}"
                program = SemanticProgram(
                    key=key,
                    label="Hand search",
                    effects=[
                        {
                            "op": "search",
                            "searching_player": "$controller",
                            "zone": "library",
                            "selector": {"types": ["Artifact"]},
                            "count": {"minimum": 1, "maximum": 1},
                            "destination": "hand",
                            "reveal": reveal,
                            "shuffle_after": True,
                        }
                    ],
                    destination="graveyard",
                )
                self._begin_spell(
                    session,
                    seat="B",
                    name="Entomb",
                    program=program,
                )
                option = session.packet("pilot:B", full=True)[
                    "decision"
                ]["ctx"]["search_cards"][0]
                result = session.act(
                    "pilot:B",
                    {
                        "action_id": "choose",
                        "search_card": option["id"],
                        "plan": "DEVELOP_ENGINE",
                        "reason": "Choose the artifact for the visibility test.",
                    },
                )
                self.assertTrue(result.ok, result.summary)
                opposing = json.dumps(
                    session.packet("pilot:A", full=True)
                )
                if reveal:
                    self.assertIn(option["id"], opposing)
                    self.assertIn(option["name"], opposing)
                else:
                    self.assertNotIn(option["id"], opposing)
                    self.assertNotIn(option["name"], opposing)
                public_event = next(
                    event
                    for event in session.state.events
                    if event.code == "library.search"
                )
                self.assertEqual(
                    reveal, "object" in public_event.details
                )

    def test_ordered_plan_spans_fetch_entomb_and_private_search(self):
        session = CommanderSession.create(
            self.db,
            {"A": self.zimone, "B": self.mishra},
            first_player="A",
            seed=20260736,
            config=GameConfig(
                seed=20260736,
                profile="commander_duel",
                auto_pass_empty_priority=True,
            ),
        )
        keep_all(session)
        engine = session.engine
        foothills = self._card(engine, "A", "Wooded Foothills")
        bayou = self._card(engine, "A", "Bayou")
        entomb = self._card(engine, "A", "Entomb")
        bloodghast = self._card(engine, "A", "Bloodghast")
        for object_id in list(engine.state.players["A"].zones["hand"]):
            engine.move_card(object_id, "library", log=False)
        for card in (foothills, entomb):
            engine.move_card(card.object_id, "hand", log=False)
        for card in (bayou, bloodghast):
            engine.move_card(card.object_id, "library", log=False)
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
        fetch = next(
            ability
            for ability in engine._activated_abilities(foothills)
            if engine._fetch_land_types(ability.effect_text)
        )
        session.commands.clear()
        session.decisions.clear()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        result = session.act(
            "pilot:A",
            PilotResponse.from_mapping({
                "actions": [
                    {"action_id": f"play-land:{foothills.ref}"},
                    {
                        "action_id": (
                            f"activate:{foothills.ref}:{fetch.ability_id}"
                        ),
                        "future_choices": {
                            "search_card_name": "Bayou",
                            "entry_pay_life": False,
                        },
                    },
                    {
                        "action_id": f"cast:{entomb.ref}",
                        "future_choices": {
                            "search_card_name": "Bloodghast"
                        },
                    },
                ],
                "plan": "DEVELOP_ENGINE",
                "reason": "Fetch Bayou, Entomb Bloodghast, and preserve blue access.",
                "confidence": 0.95,
            }).engine_response(),
        )
        self.assertTrue(result.ok, result.summary)
        session.next_task()
        self.assertNotIn("pilot:A", session.plans)
        self.assertEqual("battlefield", bayou.zone)
        self.assertEqual("graveyard", bloodghast.zone)
        self.assertEqual("graveyard", entomb.zone)
        self.assertGreaterEqual(
            sum(
                row["execution"] == "planned_automatic"
                for row in session.commands
            ),
            4,
        )
        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "ordered-search"
            session.save(record)
            self.assertTrue(
                replay_record(record, self.db, verify=True)["ok"]
            )


if __name__ == "__main__":
    unittest.main()
