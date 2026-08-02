from __future__ import annotations

import json
import random
import unittest

from mtg_commander_sim.replacement_effects import (
    AffectedObject,
    EntryReplacementScope,
    ReplaceableEvent,
    ReplacementClass,
    ReplacementEffect,
    ReplacementEventBatch,
    ReplacementSelection,
    apply_batch_replacement,
    apply_replacement,
    apply_tree_replacement,
    next_batch_replacement_choice,
    replacement_choice,
    replacement_choice_payload,
    replacement_tree_choice,
    resolve_replacement_batch,
    resolve_replacements,
)


def effect(
    effect_id: str,
    event_kind: str,
    *operations: dict,
    optional: bool = False,
    conditions: dict | None = None,
) -> ReplacementEffect:
    return ReplacementEffect(
        effect_id=effect_id,
        source_id=f"source:{effect_id}",
        event_kind=event_kind,
        replacement_class=ReplacementClass.OTHER,
        conditions=conditions or {},
        operations=tuple(operations),
        optional=optional,
        label=effect_id.replace("-", " ").title(),
    )


class ReplacementAffectedSubjectTests(unittest.TestCase):
    def test_affected_object_controller_chooses_before_owner(self):
        controlled = ReplaceableEvent(
            event_id="damage:controlled",
            kind="damage",
            affected_player=None,
            affected_object=AffectedObject(
                object_id="permanent:1",
                owner="A",
                controller="C",
            ),
            payload={"amount": 3},
        )
        owner_only = ReplaceableEvent(
            event_id="card:uncontrolled",
            kind="zone_change",
            affected_player=None,
            affected_object=AffectedObject(
                object_id="card:1",
                owner="A",
                controller=None,
            ),
            payload={"destination": "graveyard"},
        )

        self.assertEqual("C", controlled.chooser)
        self.assertEqual("A", owner_only.chooser)

    def test_event_requires_exactly_one_affected_subject(self):
        with self.assertRaisesRegex(ValueError, "exactly one affected subject"):
            ReplaceableEvent(
                event_id="invalid:none",
                kind="damage",
                affected_player=None,
                payload={"amount": 1},
            )
        with self.assertRaisesRegex(ValueError, "exactly one affected subject"):
            ReplaceableEvent(
                event_id="invalid:both",
                kind="damage",
                affected_player="A",
                affected_object=AffectedObject(
                    object_id="permanent:1",
                    owner="A",
                    controller="A",
                ),
                payload={"amount": 1},
            )


class ReplacementNestedEventTests(unittest.TestCase):
    def test_containing_event_is_replaced_before_nested_event(self):
        child = ReplaceableEvent(
            event_id="counter:1",
            kind="counter.add",
            affected_player=None,
            affected_object=AffectedObject(
                object_id="token:voice",
                owner="A",
                controller="A",
            ),
            payload={"amount": 1, "counter": "+1/+1"},
        )
        root = ReplaceableEvent(
            event_id="token:1",
            kind="token.create",
            affected_player="A",
            payload={"quantity": 1},
            children=(child,),
        )
        effects = (
            effect(
                "a-child-double",
                "counter.add",
                {"op": "multiply", "field": "amount", "factor": 2},
            ),
            effect(
                "z-outer-double",
                "token.create",
                {"op": "multiply", "field": "quantity", "factor": 2},
            ),
        )

        first = replacement_tree_choice(root, effects)
        self.assertEqual((), first.path)
        self.assertEqual(("z-outer-double",), first.choice.options)

        after_outer = apply_tree_replacement(
            root, effects, first, "z-outer-double"
        )
        second = replacement_tree_choice(after_outer, effects)
        self.assertEqual((0,), second.path)
        self.assertEqual(("a-child-double",), second.choice.options)

    def test_nested_event_operation_creates_replayable_child(self):
        root = ReplaceableEvent(
            event_id="token:1",
            kind="token.create",
            affected_player="A",
            payload={"quantity": 1},
        )
        nested = effect(
            "make-counter-event",
            "token.create",
            {
                "op": "nested_event",
                "event": {
                    "kind": "counter.add",
                    "affected_object": {
                        "object_id": "token:1",
                        "owner": "A",
                        "controller": "A",
                    },
                    "payload": {"counter": "+1/+1", "amount": 1},
                },
            },
        )

        choice = replacement_choice(root, (nested,))
        changed = apply_replacement(choice, (nested,), nested.effect_id)

        self.assertEqual(1, len(changed.children))
        self.assertEqual("token:1/0", changed.children[0].event_id)
        self.assertEqual(
            changed,
            ReplaceableEvent.from_dict(changed.to_dict()),
        )

    def test_nested_event_rejects_nonobject_children(self):
        root = ReplaceableEvent(
            event_id="token:malformed",
            kind="token.create",
            affected_player="A",
            payload={"quantity": 1},
        )
        malformed = effect(
            "malformed-child",
            "token.create",
            {
                "op": "nested_event",
                "event": {
                    "kind": "counter.add",
                    "affected_player": "A",
                    "payload": {"amount": 1},
                    "children": [42],
                },
            },
        )

        with self.assertRaisesRegex(ValueError, "contain only objects"):
            apply_replacement(
                replacement_choice(root, (malformed,)),
                (malformed,),
                malformed.effect_id,
            )

    def test_replacement_created_token_and_counter_events_remain_replaceable(self):
        root = ReplaceableEvent(
            event_id="effect:1",
            kind="effect",
            affected_player="A",
            payload={"resolved": False},
        )
        creates_nested_events = effect(
            "create-token-and-counter",
            "effect",
            {
                "op": "nested_event",
                "event": {
                    "kind": "token.create",
                    "affected_player": "A",
                    "payload": {"quantity": 1},
                    "children": [
                        {
                            "kind": "counter.add",
                            "affected_object": {
                                "object_id": "token:1",
                                "owner": "A",
                                "controller": "A",
                            },
                            "payload": {"counter": "+1/+1", "amount": 1},
                        }
                    ],
                },
            },
        )
        token_double = effect(
            "double-token",
            "token.create",
            {"op": "multiply", "field": "quantity", "factor": 2},
        )
        counter_double = effect(
            "double-counter",
            "counter.add",
            {"op": "multiply", "field": "amount", "factor": 2},
        )
        resolved = resolve_replacement_batch(
            ReplacementEventBatch(
                batch_id="batch:614.16",
                events=(root,),
                apnap_order=("A", "B", "C", "D"),
            ),
            (creates_nested_events, token_double, counter_double),
            selections=(
                ReplacementSelection(
                    event_id="effect:1",
                    path=(),
                    chooser="A",
                    effect_id="create-token-and-counter",
                ),
                ReplacementSelection(
                    event_id="effect:1",
                    path=(0,),
                    chooser="A",
                    effect_id="double-token",
                ),
                ReplacementSelection(
                    event_id="effect:1",
                    path=(0, 0),
                    chooser="A",
                    effect_id="double-counter",
                ),
            ),
        )

        token_event = resolved.events[0].children[0]
        self.assertEqual(2, token_event.payload["quantity"])
        self.assertEqual(2, token_event.children[0].payload["amount"])


class ReplacementEntryScopeTests(unittest.TestCase):
    def test_entering_objects_and_reserved_objects_cannot_change_zones(self):
        scope = EntryReplacementScope(
            entering_objects=("ghoul", "elder"),
            entering_from_library=("elder",),
        )

        self.assertEqual(
            ("bear", "wurm"),
            scope.eligible_zone_choices(("ghoul", "bear", "elder", "wurm")),
        )
        reserved = scope.reserve_zone_changes(("bear",))
        self.assertEqual(
            ("wurm",),
            reserved.eligible_zone_choices(
                ("ghoul", "bear", "elder", "wurm")
            ),
        )
        with self.assertRaisesRegex(ValueError, "not eligible"):
            reserved.reserve_zone_changes(("elder",))
        with self.assertRaisesRegex(ValueError, "not eligible"):
            reserved.reserve_zone_changes(("bear",))

    def test_library_top_ignores_cards_entering_from_library(self):
        scope = EntryReplacementScope(
            entering_objects=("pool", "companion"),
            entering_from_library=("pool", "companion"),
        )

        self.assertEqual(
            ("next-card", "following-card"),
            scope.library_order_for_replacement(
                ("pool", "next-card", "companion", "following-card")
            ),
        )
        self.assertEqual(
            scope,
            EntryReplacementScope.from_dict(scope.to_dict()),
        )


class ReplacementBatchTests(unittest.TestCase):
    def setUp(self):
        self.effects = tuple(
            effect(
                f"replace-{seat}",
                "damage",
                {"op": "set", "field": "prevented_by", "value": seat},
                conditions={"affected_player": seat},
            )
            for seat in "ABCD"
        )

    @staticmethod
    def event(seat: str) -> ReplaceableEvent:
        return ReplaceableEvent(
            event_id=f"damage:{seat}",
            kind="damage",
            affected_player=seat,
            payload={"amount": 1},
        )

    def test_simultaneous_choices_are_collected_in_apnap_order(self):
        batch = ReplacementEventBatch(
            batch_id="damage:simultaneous",
            events=(self.event("A"), self.event("C"), self.event("B")),
            apnap_order=("B", "C", "D", "A"),
        )

        expected = ("B", "C", "A")
        for seat in expected:
            pending = next_batch_replacement_choice(batch, self.effects)
            self.assertEqual(seat, pending.choice.chooser)
            batch = apply_batch_replacement(
                batch,
                self.effects,
                pending,
                f"replace-{seat}",
            )

        self.assertIsNone(next_batch_replacement_choice(batch, self.effects))
        self.assertEqual(expected, tuple(item.chooser for item in batch.journal))

    def test_batch_round_trip_and_path_checked_replay_are_exact(self):
        initial = ReplacementEventBatch(
            batch_id="damage:replay",
            events=(self.event("A"), self.event("B")),
            apnap_order=("A", "B", "C", "D"),
        )
        selections = (
            ReplacementSelection(
                event_id="damage:A",
                path=(),
                chooser="A",
                effect_id="replace-A",
            ),
            ReplacementSelection(
                event_id="damage:B",
                path=(),
                chooser="B",
                effect_id="replace-B",
            ),
        )

        first = resolve_replacement_batch(
            initial, self.effects, selections=selections
        )
        restored = ReplacementEventBatch.from_dict(first.to_dict())
        replayed = resolve_replacement_batch(
            initial, self.effects, selections=selections
        )

        self.assertEqual(first, restored)
        self.assertEqual(first, replayed)

    def test_choice_payload_does_not_expose_authoritative_event_payload(self):
        event = ReplaceableEvent(
            event_id="library:SECRET-OBJECT",
            kind="damage",
            affected_player="A",
            payload={"amount": 1, "top_library_object": "SECRET-OBJECT"},
        )
        batch = ReplacementEventBatch(
            batch_id="hidden:SECRET-OBJECT",
            events=(event,),
            apnap_order=("A", "B", "C", "D"),
            journal=(
                ReplacementSelection(
                    event_id="prior:SECRET-OBJECT",
                    path=(4, 2),
                    chooser="B",
                    effect_id="prior-secret-effect",
                ),
            ),
        )
        pending = next_batch_replacement_choice(batch, self.effects)

        payload = replacement_choice_payload(pending, self.effects)

        self.assertNotIn("SECRET-OBJECT", json.dumps(payload))
        self.assertEqual("A", payload["chooser"])
        self.assertEqual(
            {"chooser", "prompt", "options", "legal_actions"},
            set(payload),
        )
        self.assertEqual({"replace-A"}, {row["id"] for row in payload["options"]})

    def test_declining_one_optional_effect_does_not_decline_the_others(self):
        event = self.event("A")
        optional = (
            effect(
                "optional-one",
                "damage",
                {"op": "set", "field": "one", "value": True},
                optional=True,
            ),
            effect(
                "optional-two",
                "damage",
                {"op": "set", "field": "two", "value": True},
                optional=True,
            ),
        )
        first = replacement_choice(event, optional)
        declined = apply_replacement(
            first, optional, "decline:optional-one"
        )
        second = replacement_choice(declined, optional)

        self.assertEqual(("optional-one",), declined.applied_effects)
        self.assertEqual(("optional-two",), second.options)

    def test_duplicate_effect_ids_fail_closed(self):
        duplicates = (
            effect(
                "duplicate",
                "damage",
                {"op": "set", "field": "first", "value": True},
            ),
            effect(
                "duplicate",
                "damage",
                {"op": "set", "field": "second", "value": True},
            ),
        )

        with self.assertRaisesRegex(ValueError, "must be unique"):
            replacement_choice(self.event("A"), duplicates)

    def test_three_thousand_permuted_transitions_are_deterministic(self):
        randomizer = random.Random(616_001)
        effects = (
            effect(
                "add-three",
                "damage",
                {"op": "add", "field": "amount", "amount": 3},
            ),
            effect(
                "double",
                "damage",
                {"op": "multiply", "field": "amount", "factor": 2},
            ),
            effect(
                "add-five",
                "damage",
                {"op": "add", "field": "amount", "amount": 5},
            ),
        )
        for example in range(1_000):
            supplied = list(effects)
            selected = [value.effect_id for value in effects]
            randomizer.shuffle(supplied)
            randomizer.shuffle(selected)
            initial_amount = randomizer.randint(0, 20)
            expected = initial_amount
            by_id = {value.effect_id: value for value in effects}
            for effect_id in selected:
                operation = by_id[effect_id].operations[0]
                if operation["op"] == "add":
                    expected += int(operation["amount"])
                else:
                    expected *= int(operation["factor"])
            resolved = resolve_replacements(
                ReplaceableEvent(
                    event_id=f"fuzz:{example}",
                    kind="damage",
                    affected_player="A",
                    payload={"amount": initial_amount},
                ),
                supplied,
                selections=selected,
            )
            self.assertEqual(expected, resolved.payload["amount"])
            self.assertEqual(tuple(selected), resolved.applied_effects)
            self.assertIsNone(replacement_choice(resolved, supplied))


if __name__ == "__main__":
    unittest.main()
