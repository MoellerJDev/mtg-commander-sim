from __future__ import annotations

import unittest
from types import SimpleNamespace

from quorune.object_query import ObjectQueryResult
from quorune.replacement.immutable import FrozenMap
from quorune.semantic_choices.context import (
    SemanticChoiceContext,
    SnapshotSemanticChoiceQuery,
)
from quorune.semantic_choices.library_and_hand import ExploreChoiceHandler
from quorune.semantic_runtime.intents import (
    ExploreCompletedIntent,
    PlaceCountersIntent,
    RevealLibraryCardsIntent,
    ZoneMoveIntent,
)
from quorune.semantic_runtime.explore import (
    capture_explore_source_departure,
    explore_source_controller,
)
from quorune.semantics import SemanticProgram, SemanticRegistry
from quorune.model import StackItem


def _row(
    ref: str,
    *,
    zone: str,
    logical: str,
    controller: str = "A",
    owner: str = "A",
    types: tuple[str, ...] = (),
    phased_out: bool = False,
) -> ObjectQueryResult:
    return ObjectQueryResult(
        object_id=f"object:{ref}",
        logical_object_id=logical,
        ref=ref,
        printed_name=ref,
        owner=owner,
        controller=controller,
        zone=zone,
        types=types,
        phased_out=phased_out,
    )


def _context(
    explorer: ObjectQueryResult,
    top: ObjectQueryResult | None,
    *,
    pinned_logical: str = "logical:explorer",
) -> SemanticChoiceContext:
    rows = (explorer,) if top is None else (explorer, top)
    library = () if top is None else (top.ref,)
    return SemanticChoiceContext(
        actor="A",
        stack_ref="S1",
        stack_controller="A",
        stack_label="Explore fixture",
        source_ref=explorer.ref,
        card_ref=None,
        semantic_program_id="fixture:explore",
        semantic_program_version=1,
        query=SnapshotSemanticChoiceQuery(
            seat_order=("A", "B"),
            active_order=("A", "B"),
            object_rows=rows,
            libraries_by_seat=FrozenMap({"A": library}),
        ),
        source_logical_object_id=pinned_logical,
    )


class ExploreRuleTests(unittest.TestCase):
    def setUp(self):
        self.handler = ExploreChoiceHandler()

    def test_nonland_reveal_places_counter_before_request(self):
        explorer = _row(
            "P1",
            zone="battlefield",
            logical="logical:explorer",
            types=("creature",),
        )
        top = _row(
            "C1",
            zone="library",
            logical="logical:top",
            types=("instant",),
        )
        preparation = self.handler.prepare(
            {"op": "explore", "player": "A", "card": "P1"},
            _context(explorer, top),
        )
        self.assertIsNotNone(preparation.request)
        self.assertEqual(
            (RevealLibraryCardsIntent, PlaceCountersIntent),
            tuple(type(intent) for intent in preparation.preparation_intents),
        )

    def test_old_or_phased_incarnation_cannot_receive_explore_counter(self):
        top = _row(
            "C1",
            zone="library",
            logical="logical:top",
            types=("instant",),
        )
        for explorer in (
            _row(
                "P1",
                zone="graveyard",
                logical="logical:new-zone",
                types=("creature",),
            ),
            _row(
                "P1",
                zone="battlefield",
                logical="logical:explorer",
                types=("creature",),
                phased_out=True,
            ),
        ):
            with self.subTest(zone=explorer.zone, phased=explorer.phased_out):
                preparation = self.handler.prepare(
                    {"op": "explore", "player": "A", "card": "P1"},
                    _context(explorer, top),
                )
                self.assertEqual(
                    (RevealLibraryCardsIntent,),
                    tuple(
                        type(intent)
                        for intent in preparation.preparation_intents
                    ),
                )

    def test_empty_library_still_completes_explore(self):
        explorer = _row(
            "P1",
            zone="battlefield",
            logical="logical:explorer",
            types=("creature",),
        )
        preparation = self.handler.prepare(
            {"op": "explore", "player": "A", "card": "P1"},
            _context(explorer, None),
        )
        self.assertEqual(1, len(preparation.preparation_intents))
        completed = preparation.preparation_intents[0]
        self.assertIsInstance(completed, ExploreCompletedIntent)
        self.assertEqual("empty_library", completed.result)

    def test_land_reveal_moves_to_hand_then_marks_explored(self):
        explorer = _row(
            "P1",
            zone="battlefield",
            logical="logical:explorer",
            types=("creature",),
        )
        top = _row(
            "C1",
            zone="library",
            logical="logical:top",
            types=("land",),
        )
        preparation = self.handler.prepare(
            {"op": "explore", "player": "A", "card": "P1"},
            _context(explorer, top),
        )
        self.assertEqual(
            (
                RevealLibraryCardsIntent,
                ZoneMoveIntent,
                ExploreCompletedIntent,
            ),
            tuple(type(intent) for intent in preparation.preparation_intents),
        )

    def test_source_controller_uses_current_then_departure_lki(self):
        registry = SemanticRegistry(include_builtin_packs=False)
        registry._programs["fixture:explore"] = SemanticProgram(
            key="fixture:explore",
            label="Explore fixture",
            effects=[
                {
                    "op": "explore",
                    "player": "$source.controller",
                    "card": "$source",
                }
            ],
        )
        card = SimpleNamespace(
            object_id="object:P1",
            logical_object_id="logical:one",
            ref="P1",
            controller="B",
            zone="battlefield",
        )
        item = StackItem(
            stack_id="stack:S1",
            ref="S1",
            kind="triggered_ability",
            controller="A",
            label="Explore fixture",
            source_object_id=card.object_id,
            semantic_key="fixture:explore",
            context={"source_logical_object_id": card.logical_object_id},
        )
        host = SimpleNamespace(
            semantics=registry,
            state=SimpleNamespace(
                stack=[item],
                pending_trigger_batches=[],
            ),
        )
        cards = {card.object_id: card}
        self.assertEqual("B", explore_source_controller(item, cards))
        self.assertEqual(1, capture_explore_source_departure(host, card))
        card.zone = "graveyard"
        card.controller = "A"
        card.logical_object_id = "logical:two"
        self.assertEqual("B", explore_source_controller(item, cards))


if __name__ == "__main__":
    unittest.main()
