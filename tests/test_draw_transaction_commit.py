from __future__ import annotations

import unittest

from common import keep_all, load_assets, make_session
from mtg_commander_sim.drawing import (
    DrawError,
    DrawEventRequest,
    commit_prepared_draw,
    prepare_draw_event,
)
from mtg_commander_sim.replacement import (
    DredgeDraw,
    PreventDraw,
    ReplacementClass,
    ReplacementEffect,
)


class DrawTransactionCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_engine(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        return session.engine

    @staticmethod
    def request(engine, seat: str, suffix: str) -> DrawEventRequest:
        return DrawEventRequest(
            event_id=f"draw:test:{suffix}",
            player=seat,
            library_size=len(engine.state.players[seat].zones["library"]),
            reason="CR 121 test",
        )

    def test_ordinary_draw_commits_zone_history_and_events_once(self):
        engine = self.make_engine(12101)
        player = engine.state.players["A"]
        top = player.zones["library"][-1]
        history_before = len(player.draw_history)
        prepared = prepare_draw_event(
            self.request(engine, "A", "ordinary"),
            apnap_order=engine.apnap_order(),
        )

        result = commit_prepared_draw(engine, prepared)

        self.assertEqual((top,), result)
        self.assertEqual("hand", engine.state.cards[top].zone)
        self.assertEqual(history_before + 1, len(player.draw_history))
        self.assertEqual("CR 121 test", player.draw_history[-1]["reason"])
        self.assertEqual("card.draw", engine.state.events[-2].code)
        self.assertEqual("card.draw.private", engine.state.events[-1].code)

    def test_prevented_empty_draw_does_not_mark_empty_library_loss(self):
        engine = self.make_engine(12102)
        player = engine.state.players["A"]
        for object_id in list(player.zones["library"]):
            engine.move_card(
                object_id,
                "exile",
                log=False,
                semantic_events=False,
            )
        effect = ReplacementEffect(
            effect_id="prevent:draw:test",
            source_id="fixture:prevention",
            event_kind="draw",
            replacement_class=ReplacementClass.OTHER,
            conditions={"is_draw": {"eq": True}},
            operations=(PreventDraw(),),
        )
        prepared = prepare_draw_event(
            self.request(engine, "A", "prevented-empty"),
            apnap_order=engine.apnap_order(),
            effects=(effect,),
        )

        self.assertEqual((), commit_prepared_draw(engine, prepared))
        self.assertFalse(player.attempted_empty_draw)
        self.assertEqual("card.draw.prevented", engine.state.events[-1].code)

    def test_dredge_mills_top_cards_and_returns_the_pinned_source(self):
        engine = self.make_engine(12103)
        player = engine.state.players["B"]
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B" and card.printed_name == "Life from the Loam"
        )
        engine.move_card(
            source.object_id,
            "graveyard",
            log=False,
            semantic_events=False,
        )
        top_three = tuple(reversed(player.zones["library"][-3:]))
        effect = ReplacementEffect(
            effect_id="dredge:loam:test",
            source_id=source.logical_object_id,
            event_kind="draw",
            replacement_class=ReplacementClass.OTHER,
            conditions={
                "affected_player": {"eq": "B"},
                "is_draw": {"eq": True},
                "library_size": {"gte": 3},
            },
            operations=(
                DredgeDraw(
                    source_ref=source.ref,
                    source_object_id=source.object_id,
                    source_zone_change_counter=source.zone_change_counter,
                    mill_count=3,
                ),
            ),
            optional=True,
        )
        prepared = prepare_draw_event(
            self.request(engine, "B", "dredge"),
            apnap_order=engine.apnap_order(),
            effects=(effect,),
            selections=(effect.effect_id,),
        )

        self.assertEqual(
            (source.object_id,), commit_prepared_draw(engine, prepared)
        )
        self.assertEqual("hand", source.zone)
        self.assertTrue(
            all(engine.state.cards[value].zone == "graveyard" for value in top_three)
        )
        self.assertEqual("draw.replaced.dredge", engine.state.events[-1].code)
        self.assertNotIn(
            "CR 121 test", [entry["reason"] for entry in player.draw_history]
        )

    def test_changed_library_or_source_fails_before_draw_mutation(self):
        engine = self.make_engine(12104)
        prepared = prepare_draw_event(
            self.request(engine, "A", "stale-library"),
            apnap_order=engine.apnap_order(),
        )
        top = engine.state.players["A"].zones["library"][-1]
        engine.move_card(top, "exile", log=False, semantic_events=False)
        hand_before = tuple(engine.state.players["A"].zones["hand"])

        with self.assertRaisesRegex(DrawError, "library size changed"):
            commit_prepared_draw(engine, prepared)
        self.assertEqual(hand_before, tuple(engine.state.players["A"].zones["hand"]))


if __name__ == "__main__":
    unittest.main()
