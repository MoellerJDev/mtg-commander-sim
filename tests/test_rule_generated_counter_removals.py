from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from common import keep_all, load_assets, make_session
from quorune.counter_removal import (
    commit_counter_removals,
    CounterRemoval,
    CounterRemovalError,
    plan_counter_removals,
)
from quorune.model import CardInstance, StackItem
from quorune.record import checkpoint_envelope, replay_record
from quorune.semantics import SemanticProgram
from quorune.state_based_actions import StateBasedActionBatch
from quorune.state_based_execution import (
    commit_state_based_counter_removals,
    prepare_state_based_execution,
    StateBasedExecutionError,
)
from quorune.tap_state import TapStateError, untap_permanent


class CounterRemovalTransactionTests(unittest.TestCase):
    @staticmethod
    def host(*counter_sets: dict[str, int]):
        cards = {}
        for index, counters in enumerate(counter_sets, start=1):
            card = CardInstance(
                object_id=f"permanent:{index}",
                ref=f"A{index:02d}",
                oracle_id=f"oracle:{index}",
                printed_name=f"Counter Fixture {index}",
                owner="A",
                controller="A",
                zone="battlefield",
                counters=dict(counters),
            )
            cards[card.object_id] = card
        return SimpleNamespace(state=SimpleNamespace(cards=cards)), tuple(
            cards.values()
        )

    def test_removals_are_canonical_and_commit_exactly(self):
        host, (first, second) = self.host(
            {"charge": 3}, {"stun": 2}
        )
        plan = plan_counter_removals(
            host,
            (
                CounterRemoval(
                    second.object_id,
                    "Stun",
                    1,
                    expected_logical_object_id=(
                        second.logical_object_id
                    ),
                ),
                CounterRemoval(
                    first.object_id,
                    " Charge ",
                    2,
                    expected_logical_object_id=(
                        first.logical_object_id
                    ),
                ),
            ),
        )

        self.assertEqual(
            (
                (first.object_id, "charge"),
                (second.object_id, "stun"),
            ),
            tuple(value.key for value in plan.removals),
        )
        self.assertEqual({"charge": 3}, first.counters)
        self.assertEqual({"stun": 2}, second.counters)

        transitions = commit_counter_removals(host, plan)

        self.assertEqual({"charge": 1}, first.counters)
        self.assertEqual({"stun": 1}, second.counters)
        self.assertEqual((-2, -1), tuple(
            value.applied_delta for value in transitions
        ))

    def test_malformed_or_unpayable_removal_fails_before_mutation(self):
        host, (card,) = self.host({"charge": 1})
        for amount in (0, -1, True, 1.5):
            with self.subTest(amount=amount):
                with self.assertRaises(CounterRemovalError):
                    CounterRemoval(
                        card.object_id,
                        "charge",
                        amount,  # type: ignore[arg-type]
                    )
        with self.assertRaisesRegex(
            CounterRemovalError, "enough counters"
        ):
            plan_counter_removals(
                host,
                (CounterRemoval(card.object_id, "charge", 2),),
            )
        with self.assertRaisesRegex(
            CounterRemovalError, "one request"
        ):
            plan_counter_removals(
                host,
                (
                    CounterRemoval(card.object_id, "charge", 1),
                    CounterRemoval(card.object_id, "CHARGE", 1),
                ),
            )
        self.assertEqual({"charge": 1}, card.counters)

        for field, value in (
            ("object_id", True),
            ("counter_name", True),
            ("expected_zone", True),
            ("expected_logical_object_id", ""),
        ):
            with self.subTest(field=field):
                values = {
                    "object_id": card.object_id,
                    "counter_name": "charge",
                    "amount": 1,
                    "expected_zone": "battlefield",
                    "expected_logical_object_id": card.logical_object_id,
                }
                values[field] = value
                with self.assertRaises(CounterRemovalError):
                    CounterRemoval(**values)

    def test_stale_identity_rolls_back_the_whole_removal_batch(self):
        host, (first, second) = self.host(
            {"charge": 2}, {"stun": 2}
        )
        plan = plan_counter_removals(
            host,
            tuple(
                CounterRemoval(
                    card.object_id,
                    next(iter(card.counters)),
                    1,
                    expected_logical_object_id=card.logical_object_id,
                )
                for card in (first, second)
            ),
        )
        second.zone_change_counter += 1

        with self.assertRaisesRegex(
            CounterRemovalError, "changed object identity"
        ):
            commit_counter_removals(host, plan)

        self.assertEqual({"charge": 2}, first.counters)
        self.assertEqual({"stun": 2}, second.counters)

    def test_stun_replacement_uses_the_counter_removal_owner(self):
        host, (card,) = self.host({"stun": 2})
        card.tapped = True
        events = []
        host._log = lambda *args, **kwargs: events.append((args, kwargs))

        self.assertFalse(
            untap_permanent(host, card, actor="A", reason="untap step")
        )
        self.assertTrue(card.tapped)
        self.assertEqual(1, card.counters["stun"])
        self.assertEqual("permanent.untap.replaced", events[0][0][1])

        with patch(
            "quorune.counter_removal.commit_counter_changes",
            return_value=(),
        ):
            with self.assertRaises(AssertionError):
                untap_permanent(
                    host, card, actor="A", reason="mutant"
                )
                self.assertNotIn("stun", card.counters)

    def test_stun_replacement_rejects_malformed_public_state(self):
        for value in (True, 1.0, "1", -1):
            with self.subTest(value=value):
                host, (card,) = self.host({"stun": value})
                card.tapped = True
                host._log = lambda *args, **kwargs: None

                with self.assertRaisesRegex(
                    TapStateError,
                    "Stun-counter state",
                ):
                    untap_permanent(
                        host, card, actor="A", reason="untap step"
                    )

                self.assertTrue(card.tapped)
                self.assertEqual(value, card.counters["stun"])


class StateBasedCounterRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def engine(self, seed: int):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            seed=seed,
        )
        keep_all(session)
        session.engine.permissions.invalidate_current()
        session.engine.state.priority_player = None
        return session.engine

    @staticmethod
    def counter_token(engine, seat: str, name: str, counters):
        ref = engine.create_token(
            seat,
            name=name,
            characteristics={
                "type_line": "Token Creature — Test",
                "power": "2",
                "toughness": "2",
            },
        )[0]
        card = next(
            value
            for value in engine.state.cards.values()
            if value.ref == ref
        )
        card.counters.update(counters)
        return card

    def test_overlapping_sba_removals_share_one_atomic_plan(self):
        engine = self.engine(7045101)
        card = self.counter_token(
            engine,
            "A",
            "Limited Counter Fixture",
            {"+1/+1": 10, "-1/-1": 4},
        )
        batch = StateBasedActionBatch(
            counter_pairs_to_remove=((card.object_id, 4),),
            counter_maximums_to_remove=(
                (card.object_id, "+1/+1", 8),
            ),
        )

        execution = prepare_state_based_execution(engine, batch)
        self.assertEqual(2, len(
            execution.counter_removals.counters.removals
        ))
        self.assertEqual(
            {"+1/+1": 10, "-1/-1": 4}, card.counters
        )

        result = commit_state_based_counter_removals(
            engine, execution.counter_removals
        )

        self.assertEqual({"+1/+1": 2}, card.counters)
        self.assertEqual(4, result.pairs[0].pairs_removed)
        self.assertEqual(10, result.maximums[0].before)
        self.assertEqual(2, result.maximums[0].after)

    def test_sba_removal_order_is_canonical_across_permutations(self):
        engine = self.engine(7045102)
        first = self.counter_token(
            engine,
            "A",
            "First Counter Fixture",
            {"stun": 2, "+1/+1": 1, "-1/-1": 1},
        )
        second = self.counter_token(
            engine,
            "B",
            "Second Counter Fixture",
            {"charge": 3, "+1/+1": 2, "-1/-1": 2},
        )
        left = StateBasedActionBatch(
            counter_pairs_to_remove=(
                (second.object_id, 1),
                (first.object_id, 1),
            ),
            counter_maximums_to_remove=(
                (second.object_id, "charge", 1),
                (first.object_id, "stun", 1),
            )
        )
        right = StateBasedActionBatch(
            counter_pairs_to_remove=tuple(
                reversed(left.counter_pairs_to_remove)
            ),
            counter_maximums_to_remove=tuple(
                reversed(left.counter_maximums_to_remove)
            )
        )

        left_plan = prepare_state_based_execution(engine, left)
        right_plan = prepare_state_based_execution(engine, right)

        self.assertEqual(
            left_plan.counter_removals.counters.removals,
            right_plan.counter_removals.counters.removals,
        )
        self.assertEqual(
            left_plan.counter_removals.counters.counter_plan,
            right_plan.counter_removals.counters.counter_plan,
        )
        self.assertEqual(
            left_plan.counter_removals.pairs,
            right_plan.counter_removals.pairs,
        )
        self.assertEqual(
            left_plan.counter_removals.maximums,
            right_plan.counter_removals.maximums,
        )

    def test_moving_permanent_skips_redundant_counter_removal(self):
        engine = self.engine(7045103)
        card = self.counter_token(
            engine,
            "A",
            "Departing Counter Fixture",
            {"+1/+1": 1, "-1/-1": 1},
        )
        execution = prepare_state_based_execution(
            engine,
            StateBasedActionBatch(
                put_in_graveyard=(card.object_id,),
                counter_pairs_to_remove=((card.object_id, 1),),
            ),
        )

        self.assertEqual((), execution.counter_removals.counters.removals)

    def test_malformed_sba_removal_fails_before_mutation(self):
        engine = self.engine(7045104)
        card = self.counter_token(
            engine, "A", "Malformed Counter Fixture", {"charge": 2}
        )

        malformed_batches = (
            StateBasedActionBatch(
                counter_maximums_to_remove=(
                    (card.object_id, "charge", True),
                )
            ),
            StateBasedActionBatch(
                counter_maximums_to_remove=(
                    (card.object_id, True, 1),
                )
            ),
            StateBasedActionBatch(
                counter_pairs_to_remove=(
                    (card.object_id, 1),
                    (card.object_id, 1),
                )
            ),
            StateBasedActionBatch(
                counter_maximums_to_remove=(
                    (card.object_id, "charge", 1),
                    (card.object_id, "CHARGE", 1),
                )
            ),
        )
        for batch in malformed_batches:
            with self.subTest(batch=batch):
                with self.assertRaises(StateBasedExecutionError):
                    prepare_state_based_execution(engine, batch)
        self.assertEqual({"charge": 2}, card.counters)

    def test_opposing_counter_removal_replays_in_four_player_game(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=7045105,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        card = self.counter_token(
            engine,
            "A",
            "Replay Counter Fixture",
            {"+1/+1": 3},
        )
        program = SemanticProgram(
            key="test:opposing-counter-removal-replay",
            label="Put two -1/-1 counters on the fixture",
            effects=[
                {
                    "op": "counter",
                    "card": card.ref,
                    "counter": "-1/-1",
                    "delta": 2,
                }
            ],
            trust_level="provisional",
        )
        engine.semantics.put(program)
        engine.state.stack.append(
            StackItem(
                stack_id="opposing-counter-removal-replay",
                ref="S-opposing-counter-removal-replay",
                kind="triggered",
                controller="A",
                label=program.label,
                source_object_id=card.object_id,
                semantic_key=program.key,
                visibility=["A", "B", "C", "D"],
            )
        )
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        for principal in ("pilot:A", "pilot:B", "pilot:C", "pilot:D"):
            result = session.act(
                principal,
                {
                    "action_id": "pass",
                    "reason": "Allow the counter fixture to resolve.",
                    "plan": "HOLD",
                },
            )
            self.assertTrue(result.ok, result.summary)

        self.assertEqual({"+1/+1": 1}, card.counters)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "opposing-counter-removal-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)


if __name__ == "__main__":
    unittest.main()
