from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import unittest

from quorune.replacement.immutable import thaw_value
from quorune.rules.single_object_zone_transition import (
    SingleObjectDestination,
    SingleObjectZoneTransitionError,
    SingleObjectZoneTransitionPlan,
    commit_prevalidated_single_object_zone_transition,
    prepare_single_object_zone_transition,
    request_for_card,
    validate_single_object_zone_transition_plan,
)


@dataclass
class FakeCard:
    object_id: str = "object-1"
    ref: str = "A01"
    logical_object_id: str = "object-1:0"
    owner: str = "A"
    controller: str = "B"
    zone: str = "battlefield"
    phased_out: bool = False


class FakeHost:
    def __init__(self) -> None:
        self.card = FakeCard()
        self.state = SimpleNamespace(cards={self.card.object_id: self.card})
        self.replacement_destination: str | None = None
        self.last_move: dict[str, object] | None = None

    def move_card(self, object_id: str, destination: str, **kwargs):
        self.last_move = {
            "object_id": object_id,
            "destination": destination,
            **kwargs,
        }
        self.card.zone = self.replacement_destination or destination
        self.card.logical_object_id = "object-1:1"
        return self.card


class SingleObjectZoneTransitionTests(unittest.TestCase):
    def plan(
        self,
        host: FakeHost,
        destination: SingleObjectDestination = SingleObjectDestination.EXILE,
        *,
        replacement_selections=(),
    ) -> SingleObjectZoneTransitionPlan:
        return prepare_single_object_zone_transition(
            host,
            request_for_card(host.card),
            actor="A",
            reason="typed transition fixture",
            requested_destination=destination,
            replacement_selections=replacement_selections,
        )

    def test_destination_vocabulary_is_closed(self):
        host = FakeHost()

        with self.assertRaisesRegex(
            SingleObjectZoneTransitionError, "supported typed value"
        ):
            prepare_single_object_zone_transition(
                host,
                request_for_card(host.card),
                actor="A",
                reason="malformed destination",
                requested_destination="graveyard",
            )

        self.assertEqual(
            {"hand", "exile"},
            {destination.value for destination in SingleObjectDestination},
        )

    def test_plan_deep_freezes_replacement_selections(self):
        host = FakeHost()
        selection = {
            "effect_id": "replace-1",
            "event_path": [0, 2],
        }

        plan = self.plan(host, replacement_selections=[selection])
        selection["effect_id"] = "tampered"
        selection["event_path"].append(9)

        self.assertEqual(
            {"effect_id": "replace-1", "event_path": [0, 2]},
            thaw_value(plan.replacement_selections[0]),
        )

    def test_prepare_and_commit_reject_stale_or_phased_permanents(self):
        phased = FakeHost()
        phased.card.phased_out = True
        with self.assertRaisesRegex(
            SingleObjectZoneTransitionError, "phased-in battlefield"
        ):
            self.plan(phased)

        stale = FakeHost()
        plan = self.plan(stale)
        stale.card.controller = "C"
        with self.assertRaisesRegex(SingleObjectZoneTransitionError, "stale"):
            validate_single_object_zone_transition_plan(stale, plan)

    def test_commit_reports_replaced_destination_and_new_incarnation(self):
        host = FakeHost()
        host.replacement_destination = "graveyard"
        plan = self.plan(host, SingleObjectDestination.OWNER_HAND)
        validate_single_object_zone_transition_plan(host, plan)

        result = commit_prevalidated_single_object_zone_transition(host, plan)

        self.assertEqual(SingleObjectDestination.OWNER_HAND, result.requested_destination)
        self.assertEqual("graveyard", result.actual_destination)
        self.assertEqual("object-1:0", plan.entry.logical_object_id)
        self.assertEqual("object-1:1", result.logical_object_id)
        self.assertEqual("hand", host.last_move["destination"])
        self.assertTrue(host.last_move["semantic_events"])


if __name__ == "__main__":
    unittest.main()
