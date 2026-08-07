from __future__ import annotations

import unittest

from quorune.combat_damage_assignment import (
    build_combat_damage_assignment_proposal,
    CombatDamageAssignmentError,
    CombatDamageParticipant,
    CombatDamageAssignmentProposal,
    CombatDamageSourceSpec,
    CreatureDamageState,
    TrampleDamageSpec,
)
from quorune.combat_damage_snapshot import (
    CombatAttackRelationship,
    CombatBlockRelationship,
    CombatDamageRecipient,
    CombatDamageSnapshot,
    CombatDamageSnapshotError,
)


class CombatDamageAssignmentProposalTests(unittest.TestCase):
    def test_typed_snapshot_builder_owns_offer_and_trample_inputs(self) -> None:
        attacker = CombatDamageParticipant(
            object_id="attacker-id",
            reference="attacker",
            controller="A",
            power=5,
            toughness=5,
            marked_damage=0,
            keywords=frozenset({"trample"}),
            assigns_damage=True,
        )
        blocker = CombatDamageParticipant(
            object_id="blocker-id",
            reference="blocker",
            controller="B",
            power=2,
            toughness=3,
            marked_damage=1,
            keywords=frozenset(),
            assigns_damage=True,
        )

        proposal = build_combat_damage_assignment_proposal(
            seat="A",
            snapshot=CombatDamageSnapshot(
                damage_step_id="combat-damage:1:0:0",
                damage_step_index=0,
                first_strike_step=False,
                active_player="A",
                participants=(attacker, blocker),
                attacks=(
                    CombatAttackRelationship(
                        attacker.object_id,
                        CombatDamageRecipient(
                            reference="B",
                            logical_object_id="player:B",
                            controller="B",
                            kind="player",
                            legal=True,
                        ),
                    ),
                ),
                blocks=(
                    CombatBlockRelationship(
                        attacker.object_id,
                        blocker.object_id,
                    ),
                ),
                was_blocked=frozenset({attacker.object_id}),
            ),
        )

        self.assertEqual(
            {"attacker": {"power": 5, "targets": ["blocker", "B"]}},
            proposal.projected_options(),
        )
        blocker_state = proposal.trample_sources[0].blockers[0][1]
        self.assertEqual(3, blocker_state.toughness)
        self.assertEqual(1, blocker_state.marked_damage)

        with self.assertRaisesRegex(
            CombatDamageSnapshotError,
            "object identities must be unique",
        ):
            CombatDamageSnapshot(
                damage_step_id="combat-damage:1:0:0",
                damage_step_index=0,
                first_strike_step=False,
                active_player="A",
                participants=(attacker, attacker),
                attacks=(),
                blocks=(),
                was_blocked=frozenset(),
            )

    def proposal(
        self,
        *,
        power: int = 5,
        blocker_toughness: int = 3,
        marked_damage: int = 0,
        deathtouch_sources: frozenset[str] = frozenset(),
        extra_sources: tuple[CombatDamageSourceSpec, ...] = (),
    ) -> CombatDamageAssignmentProposal:
        return CombatDamageAssignmentProposal(
            damage_step_id="combat-damage:1:0:0",
            actor="A",
            sources=(
                CombatDamageSourceSpec(
                    source="attacker",
                    controller="A",
                    logical_object_id="attacker@1",
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
                                toughness=blocker_toughness,
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

    def test_lethal_then_spill_holds_across_power_and_damage_grid(self) -> None:
        for toughness in range(1, 7):
            for marked_damage in range(toughness + 1):
                lethal = max(0, toughness - marked_damage)
                power = lethal + 2
                with self.subTest(
                    toughness=toughness,
                    marked_damage=marked_damage,
                    power=power,
                ):
                    proposal = self.proposal(
                        power=power,
                        blocker_toughness=toughness,
                        marked_damage=marked_damage,
                    )
                    accepted = []
                    if lethal:
                        accepted.append(
                            {
                                "source": "attacker",
                                "target": "blocker",
                                "amount": lethal,
                            }
                        )
                    accepted.append(
                        {
                            "source": "attacker",
                            "target": "B",
                            "amount": power - lethal,
                        }
                    )
                    self.assertEqual(
                        power,
                        sum(
                            item.amount
                            for item in proposal.validate(accepted)
                        ),
                    )

                    if lethal:
                        with self.assertRaises(CombatDamageAssignmentError):
                            proposal.validate(
                                [
                                    {
                                        "source": "attacker",
                                        "target": "blocker",
                                        "amount": lethal - 1,
                                    },
                                    {
                                        "source": "attacker",
                                        "target": "B",
                                        "amount": power - lethal + 1,
                                    },
                                ]
                            )

    def test_deathtouch_damage_from_another_attacker_is_lethal(self) -> None:
        helper = CombatDamageSourceSpec(
            source="helper",
            controller="A",
            logical_object_id="helper@1",
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
            controller="A",
            logical_object_id="helper@1",
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
            damage_step_id="combat-damage:1:0:0",
            actor="A",
            sources=(
                CombatDamageSourceSpec(
                    source="stranded",
                    controller="A",
                    logical_object_id="stranded@1",
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
            controller="A",
            logical_object_id="attacker@1",
            power=1,
            targets=("B",),
        )
        with self.assertRaises(CombatDamageAssignmentError):
            CombatDamageAssignmentProposal(
                damage_step_id="combat-damage:1:0:0",
                actor="A",
                sources=(source,),
                attacking_sources=frozenset({"unknown"}),
                deathtouch_sources=frozenset(),
                trample_sources=(),
            )
        with self.assertRaises(CombatDamageAssignmentError):
            CombatDamageAssignmentProposal(
                damage_step_id="combat-damage:1:0:0",
                actor="A",
                sources=(source,),
                attacking_sources=frozenset({"attacker"}),
                deathtouch_sources=frozenset({"unknown"}),
                trample_sources=(),
            )


if __name__ == "__main__":
    unittest.main()
