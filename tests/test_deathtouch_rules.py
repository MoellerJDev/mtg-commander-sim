from __future__ import annotations

import unittest
from types import SimpleNamespace

from mtg_commander_sim.damage_results import (
    consume_deathtouch_damage_checks,
    DamageResultError,
)
from mtg_commander_sim.deathtouch import (
    deathtouch_assignment_is_lethal,
    deathtouch_damage_result_applies,
    DeathtouchError,
)
from mtg_commander_sim.model import CardInstance
from mtg_commander_sim.state_based_actions import (
    evaluate_permanent_state_based_actions,
    PermanentSnapshot,
)


class DeathtouchValueTests(unittest.TestCase):
    def test_nonzero_assignment_is_lethal_and_instances_are_redundant(self):
        self.assertTrue(
            deathtouch_assignment_is_lethal(
                source="snake",
                amount=1,
                deathtouch_sources=("snake", "snake"),
            )
        )
        self.assertFalse(
            deathtouch_assignment_is_lethal(
                source="snake",
                amount=0,
                deathtouch_sources=("snake",),
            )
        )
        self.assertFalse(
            deathtouch_assignment_is_lethal(
                source="bear",
                amount=1,
                deathtouch_sources=("snake",),
            )
        )
        self.assertFalse(
            deathtouch_assignment_is_lethal(
                source="SNAKE",
                amount=1,
                deathtouch_sources=("snake",),
            )
        )

    def test_malformed_amounts_and_keyword_values_fail_closed(self):
        with self.assertRaisesRegex(DeathtouchError, "nonnegative integer"):
            deathtouch_assignment_is_lethal(
                source="snake",
                amount=True,
                deathtouch_sources=("snake",),
            )
        with self.assertRaisesRegex(DeathtouchError, "nonempty strings"):
            deathtouch_damage_result_applies(
                amount=1,
                source_keywords=("Deathtouch", ""),
                target_types=("Creature",),
            )
        with self.assertRaisesRegex(DeathtouchError, "must be a collection"):
            deathtouch_assignment_is_lethal(
                source="snake",
                amount=1,
                deathtouch_sources=None,
            )
        with self.assertRaisesRegex(DeathtouchError, "must be a collection"):
            deathtouch_damage_result_applies(
                amount=1,
                source_keywords={"Deathtouch": True},
                target_types=("Creature",),
            )

    def test_result_requires_positive_damage_to_a_creature(self):
        self.assertTrue(
            deathtouch_damage_result_applies(
                amount=1,
                source_keywords=("Deathtouch", "DEATHTOUCH"),
                target_types=("Battle", "Creature"),
            )
        )
        self.assertFalse(
            deathtouch_damage_result_applies(
                amount=0,
                source_keywords=("Deathtouch",),
                target_types=("Creature",),
            )
        )
        self.assertFalse(
            deathtouch_damage_result_applies(
                amount=1,
                source_keywords=("Deathtouch",),
                target_types=("Planeswalker",),
            )
        )

    def test_assignment_and_result_predicates_hold_across_bounded_grid(self):
        for amount in range(8):
            for source in ("snake", "bear"):
                with self.subTest(amount=amount, source=source):
                    self.assertEqual(
                        amount > 0 and source == "snake",
                        deathtouch_assignment_is_lethal(
                            source=source,
                            amount=amount,
                            deathtouch_sources=("snake",),
                        ),
                    )
            for keywords in ((), ("Flying",), ("Deathtouch",)):
                for target_types in (("Creature",), ("Planeswalker",)):
                    with self.subTest(
                        amount=amount,
                        keywords=keywords,
                        target_types=target_types,
                    ):
                        self.assertEqual(
                            amount > 0
                            and "Deathtouch" in keywords
                            and target_types == ("Creature",),
                            deathtouch_damage_result_applies(
                                amount=amount,
                                source_keywords=keywords,
                                target_types=target_types,
                            ),
                        )


class DeathtouchStateBasedActionTests(unittest.TestCase):
    def test_persisted_marker_and_check_collection_fail_closed(self):
        payload = CardInstance(
            object_id="creature",
            ref="A01",
            oracle_id="oracle:creature",
            printed_name="Creature",
            owner="A",
            controller="A",
            zone="battlefield",
        ).to_dict()
        payload["deathtouch_damage"] = 1
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            CardInstance.from_dict(payload)

        host = SimpleNamespace(state=SimpleNamespace(cards={}))
        with self.assertRaisesRegex(DamageResultError, "must be a collection"):
            consume_deathtouch_damage_checks(host, "creature")

    def test_check_proposes_destruction_before_typed_prohibitions(self):
        batch = evaluate_permanent_state_based_actions(
            (
                PermanentSnapshot(
                    object_id="ordinary",
                    card_types=frozenset({"creature"}),
                    toughness=8,
                    marked_damage=1,
                    deathtouch_damage=True,
                ),
                PermanentSnapshot(
                    object_id="indestructible",
                    card_types=frozenset({"creature"}),
                    toughness=8,
                    marked_damage=1,
                    deathtouch_damage=True,
                    indestructible=True,
                ),
                PermanentSnapshot(
                    object_id="zero-toughness",
                    card_types=frozenset({"creature"}),
                    toughness=0,
                    deathtouch_damage=True,
                ),
            )
        )

        self.assertEqual(("indestructible", "ordinary"), batch.destroy)
        self.assertEqual(("zero-toughness",), batch.put_in_graveyard)
        self.assertEqual(
            ("indestructible", "ordinary", "zero-toughness"),
            batch.deathtouch_checks,
        )

    def test_noncreature_and_phased_markers_are_consumed_by_this_check(self):
        batch = evaluate_permanent_state_based_actions(
            (
                PermanentSnapshot(
                    object_id="former-creature",
                    card_types=frozenset({"artifact"}),
                    deathtouch_damage=True,
                ),
                PermanentSnapshot(
                    object_id="phased-creature",
                    card_types=frozenset(),
                    deathtouch_damage=True,
                    phased_out=True,
                ),
            )
        )

        self.assertEqual((), batch.destroy)
        self.assertEqual(
            ("former-creature", "phased-creature"),
            batch.deathtouch_checks,
        )

    def test_stale_check_batch_rolls_back_without_consuming_any_marker(self):
        current = SimpleNamespace(
            zone="battlefield",
            phased_out=False,
            deathtouch_damage=True,
        )
        stale = SimpleNamespace(
            zone="graveyard",
            phased_out=False,
            deathtouch_damage=True,
        )
        host = SimpleNamespace(
            state=SimpleNamespace(cards={"current": current, "stale": stale})
        )

        with self.assertRaisesRegex(
            DamageResultError,
            "changed before consumption",
        ):
            consume_deathtouch_damage_checks(
                host,
                ("current", "stale"),
            )

        self.assertTrue(current.deathtouch_damage)
        self.assertTrue(stale.deathtouch_damage)

    def test_phased_battlefield_marker_is_consumed_transactionally(self):
        phased = SimpleNamespace(
            zone="battlefield",
            phased_out=True,
            deathtouch_damage=True,
        )
        host = SimpleNamespace(state=SimpleNamespace(cards={"phased": phased}))

        self.assertEqual(
            ("phased",),
            consume_deathtouch_damage_checks(host, ("phased",)),
        )
        self.assertFalse(phased.deathtouch_damage)


if __name__ == "__main__":
    unittest.main()
