from __future__ import annotations

import unittest

from mtg_commander_sim.combat_damage_assignment import (
    CombatDamageAssignmentError,
    CombatDamageAssignmentProposal,
    CombatDamageSourceSpec,
    CreatureDamageState,
    TrampleDamageSpec,
)


class CombatDamageAssignmentProposalTests(unittest.TestCase):
    def proposal(
        self,
        *,
        power: int = 5,
        marked_damage: int = 0,
        deathtouch_sources: frozenset[str] = frozenset(),
        extra_sources: tuple[CombatDamageSourceSpec, ...] = (),
    ) -> CombatDamageAssignmentProposal:
        return CombatDamageAssignmentProposal(
            sources=(
                CombatDamageSourceSpec(
                    source="attacker",
                    power=power,
                    targets=("blocker", "B"),
                ),
                *extra_sources,
            ),
            attacking_sources=frozenset(
                {"attacker", *(source.source for source in extra_sources)}
            ),
            deathtouch_sources=deathtouch_sources,
            trample_sources=(
                TrampleDamageSpec(
                    attacker="attacker",
                    spill_target="B",
                    blockers=(
                        (
                            "blocker",
                            CreatureDamageState(
                                toughness=3,
                                marked_damage=marked_damage,
                            ),
                        ),
                    ),
                ),
            ),
        )

    def test_projected_options_and_validation_share_one_proposal(self) -> None:
        proposal = self.proposal()

        self.assertEqual(
            proposal.projected_options(),
            {
                "attacker": {
                    "power": 5,
                    "targets": ["blocker", "B"],
                }
            },
        )
        assignments = proposal.validate(
            [
                {"source": "attacker", "target": "blocker", "amount": 3},
                {"source": "attacker", "target": "B", "amount": 2},
            ]
        )

        self.assertEqual(
            [assignment.to_dict() for assignment in assignments],
            [
                {"source": "attacker", "target": "blocker", "amount": 3},
                {"source": "attacker", "target": "B", "amount": 2},
            ],
        )

    def test_trample_rejects_spill_before_lethal(self) -> None:
        with self.assertRaisesRegex(
            CombatDamageAssignmentError,
            "until blocker has lethal damage assigned",
        ):
            self.proposal().validate(
                [
                    {
                        "source": "attacker",
                        "target": "blocker",
                        "amount": 2,
                    },
                    {"source": "attacker", "target": "B", "amount": 3},
                ]
            )

    def test_marked_damage_reduces_lethal_assignment(self) -> None:
        assignments = self.proposal(marked_damage=2).validate(
            [
                {"source": "attacker", "target": "blocker", "amount": 1},
                {"source": "attacker", "target": "B", "amount": 4},
            ]
        )

        self.assertEqual(sum(item.amount for item in assignments), 5)

    def test_deathtouch_damage_from_another_attacker_is_lethal(self) -> None:
        helper = CombatDamageSourceSpec(
            source="helper",
            power=1,
            targets=("blocker", "C"),
        )
        assignments = self.proposal(
            deathtouch_sources=frozenset({"helper"}),
            extra_sources=(helper,),
        ).validate(
            [
                {"source": "helper", "target": "blocker", "amount": 1},
                {"source": "attacker", "target": "B", "amount": 5},
            ]
        )

        self.assertEqual(len(assignments), 2)

    def test_zero_deathtouch_assignment_is_not_lethal(self) -> None:
        helper = CombatDamageSourceSpec(
            source="helper",
            power=1,
            targets=("blocker", "C"),
        )
        with self.assertRaisesRegex(
            CombatDamageAssignmentError,
            "until blocker has lethal damage assigned",
        ):
            self.proposal(
                deathtouch_sources=frozenset({"helper"}),
                extra_sources=(helper,),
            ).validate(
                [
                    {"source": "helper", "target": "blocker", "amount": 0},
                    {"source": "attacker", "target": "B", "amount": 5},
                    {"source": "helper", "target": "C", "amount": 1},
                ]
            )

    def test_source_must_assign_exactly_its_power(self) -> None:
        with self.assertRaisesRegex(
            CombatDamageAssignmentError,
            "must assign exactly 5 combat damage, not 4",
        ):
            self.proposal().validate(
                [
                    {
                        "source": "attacker",
                        "target": "blocker",
                        "amount": 4,
                    }
                ]
            )

    def test_source_without_targets_assigns_zero(self) -> None:
        proposal = CombatDamageAssignmentProposal(
            sources=(
                CombatDamageSourceSpec(
                    source="stranded",
                    power=4,
                    targets=(),
                ),
            ),
            attacking_sources=frozenset({"stranded"}),
            deathtouch_sources=frozenset(),
            trample_sources=(),
        )

        self.assertEqual(proposal.validate([]), ())

    def test_malformed_and_noncanonical_assignments_fail_closed(self) -> None:
        proposal = self.proposal()
        cases = (
            None,
            "attacker",
            [{"source": "attacker", "target": "blocker"}],
            [
                {
                    "source": "attacker",
                    "target": "blocker",
                    "amount": 5,
                    "extra": True,
                }
            ],
            [{"source": "unknown", "target": "blocker", "amount": 5}],
            [{"source": "attacker", "target": "unknown", "amount": 5}],
            [{"source": "attacker", "target": "blocker", "amount": True}],
            [{"source": "attacker", "target": "blocker", "amount": -1}],
            [
                {"source": "attacker", "target": "blocker", "amount": 3},
                {"source": "attacker", "target": "blocker", "amount": 2},
            ],
        )
        for submitted in cases:
            with self.subTest(submitted=submitted):
                with self.assertRaises(CombatDamageAssignmentError):
                    proposal.validate(submitted)  # type: ignore[arg-type]

    def test_invalid_proposal_relationships_fail_closed(self) -> None:
        source = CombatDamageSourceSpec(
            source="attacker",
            power=1,
            targets=("B",),
        )
        with self.assertRaises(CombatDamageAssignmentError):
            CombatDamageAssignmentProposal(
                sources=(source,),
                attacking_sources=frozenset({"unknown"}),
                deathtouch_sources=frozenset(),
                trample_sources=(),
            )
        with self.assertRaises(CombatDamageAssignmentError):
            CombatDamageAssignmentProposal(
                sources=(source,),
                attacking_sources=frozenset({"attacker"}),
                deathtouch_sources=frozenset({"unknown"}),
                trample_sources=(),
            )


if __name__ == "__main__":
    unittest.main()
