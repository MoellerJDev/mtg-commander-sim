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
from tests.common import keep_all, load_assets, make_session


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


class ExploreEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def _session(self, seed: int):
        session = make_session(
            self.database,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.stack.clear()
        engine.semantics.put(
            SemanticProgram(
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
        )
        return session

    @staticmethod
    def _card(engine, owner: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == owner and card.printed_name == name
        )

    @staticmethod
    def _put_on_top(engine, card) -> None:
        engine.move_card(card.object_id, "library", log=False)
        library = engine.state.players[card.owner].zones["library"]
        library.remove(card.object_id)
        library.append(card.object_id)

    @staticmethod
    def _stack_explore(engine, source, controller: str) -> None:
        ref = engine._next_ref("S")
        engine.state.stack.append(
            StackItem(
                stack_id=engine._stable_runtime_id("stack", ref),
                ref=ref,
                kind="triggered_ability",
                controller=controller,
                label="Explore fixture",
                source_object_id=source.object_id,
                semantic_key="fixture:explore",
                visibility=list(engine.seats),
                context={
                    "source_logical_object_id": source.logical_object_id,
                },
            )
        )

    def test_nonland_explore_uses_current_controller_and_completes(self):
        session = self._session(7014401)
        engine = session.engine
        explorer = self._card(engine, "A", "Goblin Engineer")
        top = self._card(engine, "A", "Sol Ring")
        engine.move_card(explorer.object_id, "battlefield", controller="A")
        self._put_on_top(engine, top)
        self._stack_explore(engine, explorer, "A")

        engine._prepare_stack_resolution()
        self.assertEqual("semantic.choice", engine.state.pending_decision.kind)
        self.assertEqual(1, explorer.counters.get("+1/+1"))
        result = session.act(
            "pilot:A",
            {
                "action_id": "choose",
                "choice": "top",
                "plan": "KEEP_TOP",
                "reason": "Keep the nonland card on top.",
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertEqual("library", top.zone)
        self.assertTrue(
            any(event.code == "explore.complete" for event in engine.state.events)
        )

    def test_departed_explorer_uses_lki_controller_without_countering_return(self):
        session = self._session(7014402)
        engine = session.engine
        explorer = self._card(engine, "A", "Goblin Engineer")
        top = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and not self.database.lookup(card.printed_name).is_land
            and card.object_id != explorer.object_id
        )
        engine.move_card(explorer.object_id, "battlefield", controller="A")
        self._stack_explore(engine, explorer, "A")
        engine.change_control(explorer.object_id, "B", reason="Explore LKI")
        engine.move_card(explorer.object_id, "graveyard", reason="Explore LKI")
        self._put_on_top(engine, top)

        engine._prepare_stack_resolution()
        self.assertEqual("semantic.choice", engine.state.pending_decision.kind)
        self.assertEqual(["B"], engine.state.pending_decision.actors)
        self.assertNotIn("+1/+1", explorer.counters)
        result = session.act(
            "pilot:B",
            {
                "action_id": "choose",
                "choice": "top",
                "plan": "KEEP_TOP",
                "reason": "Complete the LKI Explore instruction.",
            },
        )
        self.assertTrue(result.ok, result.summary)


if __name__ == "__main__":
    unittest.main()
