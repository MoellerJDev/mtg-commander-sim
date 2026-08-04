from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.semantics import SemanticProgram
from mtg_commander_sim.zone_trigger_events import (
    ZoneChangeOccurrence,
    ZoneTriggerEventError,
    normalized_zone_trigger_events,
)


def occurrence(**changes) -> ZoneChangeOccurrence:
    values = {
        "object_id": "object-1",
        "card_ref": "A01",
        "owner": "A",
        "origin": "hand",
        "destination": "battlefield",
        "previous_controller": "A",
        "current_controller": "A",
        "previous_logical_object_id": "object-1:0",
        "current_logical_object_id": "object-1:1",
        "zone_change_counter": 1,
        "token": False,
        "card_object": True,
        "previous_characteristics": {
            "type_line": "Creature — Human Cleric",
            "mana_value": 2,
        },
        "current_characteristics": {
            "type_line": "Creature — Human Cleric",
            "mana_value": 2,
        },
        "previous_attachments": (),
        "cause": "test",
    }
    values.update(changes)
    return ZoneChangeOccurrence(**values)


class ZoneTriggerEventModelTests(unittest.TestCase):
    def test_derives_exact_enter_and_death_events(self):
        entered = normalized_zone_trigger_events(occurrence())
        self.assertEqual(
            ["permanent.enter", "creature.enter"],
            [event.kind for event in entered],
        )
        self.assertTrue(all(event.source_timing == "after" for event in entered))

        died = normalized_zone_trigger_events(
            occurrence(
                origin="battlefield",
                destination="graveyard",
                previous_controller="B",
                current_controller="A",
                previous_characteristics={
                    "type_line": "Legendary Artifact Creature — Golem",
                    "mana_value": 4,
                },
            )
        )
        self.assertEqual(
            [
                "permanent.leave",
                "creature.dies",
                "artifact.graveyard",
                "permanent.graveyard",
            ],
            [event.kind for event in died],
        )
        self.assertTrue(all(event.source_timing == "before" for event in died))
        self.assertTrue(
            all(event.context["controller"] == "B" for event in died)
        )
        self.assertEqual(
            ["artifact", "creature"],
            list(died[0].context["types"]),
        )

    def test_occurrence_rejects_malformed_and_non_event_moves_are_empty(self):
        with self.assertRaisesRegex(
            ZoneTriggerEventError, "zone_change_counter"
        ):
            occurrence(zone_change_counter=True)
        with self.assertRaisesRegex(ZoneTriggerEventError, "nonempty string"):
            occurrence(previous_controller="")
        with self.assertRaisesRegex(ZoneTriggerEventError, "duplicates"):
            occurrence(previous_attachments=("A02", "A02"))
        with self.assertRaisesRegex(ZoneTriggerEventError, "must be an object"):
            occurrence(previous_characteristics=[])
        with self.assertRaisesRegex(ZoneTriggerEventError, "not canonical"):
            occurrence(current_characteristics={"invalid": {1, 2}})

        moved = occurrence(origin="library", destination="hand")
        self.assertEqual((), normalized_zone_trigger_events(moved))

    def test_occurrence_deep_freezes_input_and_has_canonical_fingerprint(self):
        previous = {
            "type_line": "Creature — Human",
            "colors": ["W"],
        }
        current = {
            "colors": ["W"],
            "type_line": "Creature — Human",
        }
        first = occurrence(
            previous_characteristics=previous,
            current_characteristics=current,
        )
        second = occurrence(
            previous_characteristics={
                "colors": ["W"],
                "type_line": "Creature — Human",
            },
            current_characteristics={
                "type_line": "Creature — Human",
                "colors": ["W"],
            },
        )
        previous["colors"].append("U")
        current["type_line"] = "Land"

        self.assertEqual(("W",), first.previous_characteristics["colors"])
        self.assertEqual("Creature — Human", first.current_characteristics["type_line"])
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_private_library_to_hand_move_produces_no_public_trigger_event(self):
        moved = occurrence(
            origin="library",
            destination="hand",
            previous_characteristics={"type_line": "Creature — Human"},
            current_characteristics={"type_line": "Creature — Human"},
        )

        self.assertEqual((), normalized_zone_trigger_events(moved))


class ZoneTriggerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_source_that_leaves_still_observes_simultaneous_death(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=6036001,
        )
        keep_all(session)
        engine = session.engine
        creatures = [
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and "creature"
            in engine._type_parts(
                str(engine._effective_card_data(card).get("type_line") or "")
            )[0]
            and not card.is_commander
        ][:2]
        self.assertEqual(2, len(creatures))
        source, other = creatures
        for card in creatures:
            engine.move_card(card.object_id, "battlefield", controller="A")
        engine.semantics.put(
            SemanticProgram(
                key=f"{source.oracle_id}:test:all-dies",
                label="Observe each death",
                oracle_id=source.oracle_id,
                ability_id="test:all-dies",
                active_zone="battlefield",
                event="creature.dies",
                effects=[],
            )
        )

        engine._move_cards_simultaneously(
            ((source.object_id, "graveyard"), (other.object_id, "graveyard")),
            reason="simultaneous death fixture",
        )

        items = [
            item
            for batch in engine.state.pending_trigger_batches
            for item in batch.items
            if item.label == "Observe each death"
        ]
        self.assertEqual(2, len(items))
        self.assertEqual(
            {source.ref, other.ref},
            {item["context"]["card"] for item in items},
        )


if __name__ == "__main__":
    unittest.main()
