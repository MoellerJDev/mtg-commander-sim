from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from common import keep_all, load_assets, make_session
from mtg_commander_sim.engine import CommanderEngine
from mtg_commander_sim.model import StackItem
from mtg_commander_sim.record import checkpoint_envelope, replay_record
from mtg_commander_sim.semantics import SemanticProgram


class SemanticChoiceCharacterizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def _session(self, seed: int = 68001):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
            auto_pass_empty=True,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.priority_player = None
        return session

    @staticmethod
    def _card(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def _begin_choice(
        self,
        session,
        effect,
        *,
        seat: str = "A",
        expect_decision: bool = True,
    ):
        engine = session.engine
        card = next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat
            and card.is_card_object
            and card.zone not in {"command", "outside"}
        )
        engine._remove_from_zone(card)
        engine._reset_zone_change(card, "stack")
        card.zone = "stack"
        card.controller = seat
        card.known_to = list(engine.seats)
        card.revealed_to = list(engine.seats)
        key = f"test:semantic-choice:{effect['op']}"
        program = SemanticProgram(
            key=key,
            label=f"Characterize {effect['op']}",
            effects=[dict(effect)],
            destination="graveyard",
        )
        engine.semantics.put(program)
        item = StackItem(
            stack_id=uuid.uuid4().hex,
            ref=f"S-{effect['op']}",
            kind="spell",
            controller=seat,
            label=program.label,
            card_object_id=card.object_id,
            semantic_key=key,
            default_destination="graveyard",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)
        engine._begin_resolve_item(
            item,
            program.effects,
            program.destination,
            note="choice characterization",
        )
        if expect_decision:
            self.assertEqual(
                "semantic.choice", engine.state.pending_decision.kind
            )
        session.commands.clear()
        session.decisions.clear()
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        return card, item

    def test_scalar_mana_choice_preserves_action_shape_and_replays(self):
        session = self._session()
        _card, item = self._begin_choice(
            session,
            {
                "op": "choose_mana",
                "player": "A",
                "colors": ["G", "U"],
                "amount": 2,
            },
        )
        decision = session.state.pending_decision
        payload = decision.payload_by_actor["A"]
        self.assertEqual(item.ref, payload["stack"])
        self.assertEqual("choose_mana", payload["operation"])
        self.assertEqual(["G", "U"], payload["options"])
        self.assertEqual(
            ["G", "U"],
            payload["legal_actions"][0]["choice_schema"]["legal_values"],
        )
        self.assertEqual(2, decision.continuation["schema_version"])
        self.assertEqual(
            "choice.scalar.mana.v1",
            decision.continuation["handler_id"],
        )

        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choice": "G",
                "plan": "DEVELOP_MANA",
                "reason": "Choose the required green mana.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual(2, session.state.players["A"].mana_pool["G"])
        self.assertFalse(session.state.stack)

        with tempfile.TemporaryDirectory() as temporary:
            record = Path(temporary) / "scalar-choice"
            session.save(record)
            replay = replay_record(record, self.db, verify=True)
            self.assertTrue(replay["ok"], replay)

    def test_card_name_choice_rejects_malformed_response_without_mutation(self):
        session = self._session(68002)
        card, _item = self._begin_choice(
            session,
            {"op": "choose_card_name", "player": "A"},
        )
        before = session.state.to_dict()
        rejected = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "card_name": "Definitely Not A Magic Card",
                "plan": "NAME_CARD",
                "reason": "Exercise strict card-name validation.",
            },
        )
        self.assertFalse(rejected.ok)
        self.assertNotIn("chosen_name", card.annotations)
        self.assertEqual(before, session.state.to_dict())

        accepted = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "card_name": "sol ring",
                "plan": "NAME_CARD",
                "reason": "Choose a canonical card name.",
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        event = next(
            event
            for event in session.state.events
            if event.code == "card.name.chosen"
        )
        self.assertEqual("Sol Ring", event.details["card_name"])

    def test_creature_type_choice_survives_checkpoint_restart(self):
        session = self._session(68003)
        card, _item = self._begin_choice(
            session,
            {"op": "choose_creature_type", "player": "A"},
        )
        with tempfile.TemporaryDirectory() as temporary:
            checkpoint = Path(temporary) / "choice-state.json"
            session.engine.save(str(checkpoint))
            restored = CommanderEngine.load(
                self.db,
                str(checkpoint),
                semantics=session.engine.semantics,
            )
            restored.permissions.reissue_pending()
            decision = restored.state.pending_decision
            capability = restored.permissions.capability_for("pilot:A")
            result = restored.try_submit(
                token=capability.token,
                principal="pilot:A",
                action="choose",
                payload={"creature_type": "time lord"},
            )
        self.assertTrue(result.ok, result.summary)
        event = next(
            event
            for event in restored.state.events
            if event.code == "creature_type.chosen"
        )
        self.assertEqual(
            "Time Lord",
            event.details["creature_type"],
        )

    def test_scalar_option_choice_prepend_effects_resume_once(self):
        session = self._session(68004)
        self._begin_choice(
            session,
            {
                "op": "choose_option",
                "player": "A",
                "prompt": "Choose a mana bundle.",
                "options": [
                    {"id": "green", "label": "Add green"},
                    {"id": "blue", "label": "Add blue"},
                ],
                "then_by_choice": {
                    "green": [
                        {
                            "op": "mana",
                            "player": "A",
                            "color": "G",
                            "amount": 1,
                        }
                    ],
                    "blue": [
                        {
                            "op": "mana",
                            "player": "A",
                            "color": "U",
                            "amount": 1,
                        }
                    ],
                },
            },
        )
        decision = session.state.pending_decision
        self.assertEqual(
            ["green", "blue"],
            decision.payload_by_actor["A"]["legal_actions"][0][
                "choice_schema"
            ]["legal_values"],
        )
        accepted = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choice": "blue",
                "plan": "DEVELOP_MANA",
                "reason": "Choose blue for the test.",
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        self.assertEqual(1, session.state.players["A"].mana_pool["U"])
        events = [
            event
            for event in session.state.events
            if event.code == "semantic.option.chosen"
        ]
        self.assertEqual(1, len(events))

    def test_private_hand_object_choice_moves_only_the_selected_land(self):
        session = self._session(68005)
        engine = session.engine
        land = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and engine.card_record(card)
            and engine.card_record(card).is_land
        )
        engine.move_card(land.object_id, "hand", log=False)
        self._begin_choice(
            session,
            {"op": "put_land_from_hand", "player": "A"},
        )
        payload = session.state.pending_decision.payload_by_actor["A"]
        legal = payload["legal_actions"][0]["choice_schema"]["legal_refs"]
        self.assertIn(land.ref, legal)
        self.assertNotIn(land.ref, str(session.packet("pilot:B", full=True)))

        accepted = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "card": land.ref,
                "plan": "DEVELOP_MANA",
                "reason": "Put the selected land onto the battlefield.",
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        current = session.state.cards[land.object_id]
        self.assertEqual("battlefield", current.zone)
        event = next(
            event for event in session.state.events if event.code == "land.put"
        )
        self.assertEqual(current.tapped, event.details["tapped"])

    def test_private_hand_object_choice_auto_continues_when_empty(self):
        session = self._session(68006)
        engine = session.engine
        for card in list(engine.state.cards.values()):
            if card.owner != "A" or card.zone != "hand":
                continue
            record = engine.card_record(card)
            if record is not None and record.is_land:
                engine.move_card(card.object_id, "library", log=False)
        _source, _item = self._begin_choice(
            session,
            {"op": "put_land_from_hand", "player": "A"},
            expect_decision=False,
        )
        self.assertIsNone(session.state.pending_decision)
        self.assertFalse(session.state.stack)

    def test_private_library_ordering_uses_one_typed_choice_lifecycle(self):
        session = self._session(68007)
        engine = session.engine
        library = engine.state.players["A"].zones["library"]
        expected = [
            engine.state.cards[object_id].ref
            for object_id in reversed(library[-2:])
        ]
        self._begin_choice(
            session,
            {"op": "scry", "player": "A", "count": 2},
        )
        decision = session.state.pending_decision
        schema = decision.payload_by_actor["A"]["legal_actions"][0][
            "choice_schema"
        ]
        self.assertEqual(expected, schema["legal_refs"])
        self.assertEqual("library_bottom", schema["destination"])
        self.assertNotIn(expected[0], str(session.packet("pilot:B", full=True)))

        accepted = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "cards": [expected[0]],
                "plan": "FILTER_DRAW",
                "reason": "Put the first looked-at card on the bottom.",
            },
        )
        self.assertTrue(accepted.ok, accepted.summary)
        bottom = engine.state.cards[
            session.state.players["A"].zones["library"][0]
        ].ref
        self.assertEqual(expected[0], bottom)
        self.assertEqual(
            1,
            len(
                [
                    event
                    for event in session.state.events
                    if event.code == "library.scry"
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
