from __future__ import annotations

import unittest

from damage_replacement_support import DamageReplacementPipelineBase
from mtg_commander_sim.life_change import (
    commit_life_change_batch,
    LifeChangeError,
    LifeChangeRequest,
    prepare_life_change_batch,
)
from mtg_commander_sim.replacement import (
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


if __name__ == "__main__":
    unittest.main()
