from __future__ import annotations

import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from quorune.life_change import (
    commit_life_change_batch,
    LifeChangeError,
    LifeChangeRequest,
    prepare_life_change_batch,
    summarize_life_change_batch,
)
from quorune.replacement import (
    AddAmount,
    MultiplyAmount,
    ReplacementClass,
    ReplacementEffect,
)


def replacement(
    effect_id: str,
    operation: AddAmount | MultiplyAmount,
) -> ReplacementEffect:
    return ReplacementEffect(
        effect_id=effect_id,
        source_id=f"source:{effect_id}",
        event_kind="life.change",
        replacement_class=ReplacementClass.OTHER,
        conditions={"direction": {"eq": "gain"}},
        operations=(operation,),
        label=effect_id,
    )


class LifeChangeTransactionTests(DamageReplacementPipelineBase):
    def test_life_gain_replacement_uses_typed_precommit_plan(self):
        engine = self.session(119_100_001).engine
        engine.state.players["B"].life = 20
        prepared = prepare_life_change_batch(
            engine,
            (
                LifeChangeRequest(
                    event_id="life:test:double",
                    player="B",
                    amount=3,
                    source="fixture:gain",
                ),
            ),
            effects=(
                replacement(
                    "double-life",
                    MultiplyAmount(field="amount", factor=2),
                ),
            ),
        )

        self.assertEqual(20, engine.state.players["B"].life)
        self.assertEqual(6, prepared.records[0].amount)
        result = commit_life_change_batch(engine, prepared)

        self.assertEqual(26, engine.state.players["B"].life)
        self.assertEqual(("B",), result.changed_players)

    def test_life_replacement_choice_and_replay_are_canonical(self):
        engine = self.session(119_100_002).engine
        request = LifeChangeRequest(
            event_id="life:test:order",
            player="B",
            amount=3,
        )
        effects = (
            replacement("add-life", AddAmount(field="amount", amount=1)),
            replacement(
                "double-life", MultiplyAmount(field="amount", factor=2)
            ),
        )

        pending = prepare_life_change_batch(
            engine,
            (request,),
            effects=effects,
            require_all_selections=False,
        )
        self.assertIsNotNone(pending.pending)
        complete = prepare_life_change_batch(
            engine,
            (request,),
            effects=effects,
            selections=("add-life",),
        )
        replayed = prepare_life_change_batch(
            engine,
            (request,),
            effects=tuple(reversed(effects)),
            selections=("add-life",),
        )

        self.assertEqual(8, complete.records[0].amount)
        self.assertEqual(complete.events, replayed.events)
        self.assertEqual(complete.journal, replayed.journal)

    def test_stale_life_plan_rolls_back_without_additional_mutation(self):
        engine = self.session(119_100_003).engine
        prepared = prepare_life_change_batch(
            engine,
            (
                LifeChangeRequest(
                    event_id="life:test:stale",
                    player="B",
                    amount=4,
                ),
            ),
        )
        engine.state.players["B"].life -= 1
        stale_life = engine.state.players["B"].life

        with self.assertRaisesRegex(LifeChangeError, "stale"):
            commit_life_change_batch(engine, prepared)
        self.assertEqual(stale_life, engine.state.players["B"].life)

    def test_simultaneous_four_player_life_gain_uses_one_typed_batch(self):
        engine = self.session(119_100_004, players=4).engine
        requests = tuple(
            LifeChangeRequest(
                event_id=f"life:test:multiplayer:{seat}",
                player=seat,
                amount=index,
            )
            for index, seat in enumerate(engine.active_seats, start=1)
        )
        prepared = prepare_life_change_batch(
            engine,
            requests,
            effects=(
                replacement(
                    "double-every-gain",
                    MultiplyAmount(field="amount", factor=2),
                ),
            ),
        )

        self.assertEqual((2, 4, 6, 8), tuple(
            record.amount for record in prepared.records
        ))
        commit_life_change_batch(engine, prepared)
        self.assertEqual(
            {"A": 42, "B": 44, "C": 46, "D": 48},
            {
                seat: engine.state.players[seat].life
                for seat in engine.active_seats
            },
        )

    def test_duplicate_life_event_ids_fail_before_mutation(self):
        engine = self.session(119_100_005).engine
        before = engine.state.players["B"].life

        with self.assertRaisesRegex(LifeChangeError, "must be unique"):
            prepare_life_change_batch(
                engine,
                (
                    LifeChangeRequest(
                        event_id="life:test:duplicate",
                        player="A",
                        amount=1,
                    ),
                    LifeChangeRequest(
                        event_id="life:test:duplicate",
                        player="B",
                        amount=2,
                    ),
                ),
            )

        self.assertEqual(before, engine.state.players["B"].life)

    def test_life_summary_separates_requested_and_replacement_adjusted_results(self):
        engine = self.session(119_100_006, players=4).engine
        prepared = prepare_life_change_batch(
            engine,
            (
                LifeChangeRequest("life:summary:B", "B", -2),
                LifeChangeRequest("life:summary:C", "C", -2),
                LifeChangeRequest("life:summary:A", "A", 2),
            ),
            effects=(
                ReplacementEffect(
                    effect_id="prevent-b-loss",
                    source_id="source:prevent-b-loss",
                    event_kind="life.change",
                    replacement_class=ReplacementClass.OTHER,
                    conditions={
                        "affected_player": {"eq": "B"},
                        "direction": {"eq": "loss"},
                    },
                    operations=(MultiplyAmount(field="amount", factor=0),),
                ),
                ReplacementEffect(
                    effect_id="double-a-gain",
                    source_id="source:double-a-gain",
                    event_kind="life.change",
                    replacement_class=ReplacementClass.OTHER,
                    conditions={
                        "affected_player": {"eq": "A"},
                        "direction": {"eq": "gain"},
                    },
                    operations=(MultiplyAmount(field="amount", factor=2),),
                ),
            ),
        )

        summary = summarize_life_change_batch(prepared)

        self.assertEqual(-2, summary.for_player("B").requested_delta)
        self.assertEqual(0, summary.for_player("B").delta)
        self.assertEqual(-2, summary.for_player("C").delta)
        self.assertEqual(4, summary.for_player("A").delta)
        self.assertEqual(("A", "C"), summary.changed_players)
        self.assertEqual(0, summary.to_dict()["life_players"][0]["delta"])


if __name__ == "__main__":
    unittest.main()
