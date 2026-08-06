from __future__ import annotations

import unittest

from mtg_commander_sim.combat_damage_assignment import DamageAssignment
from mtg_commander_sim.combat_damage_sequence import (
    CombatDamageAssignmentSequence,
    CombatDamageSequenceError,
)


class CombatDamageSequenceTests(unittest.TestCase):
    def test_apnap_announcements_are_typed_canonical_and_round_trip(self):
        sequence = CombatDamageAssignmentSequence(actors=("A", "B", "D"))
        sequence = sequence.announce(
            actor="A",
            proposal_id="proposal:a",
            assignments=(DamageAssignment("A1", "B1", 2),),
            automatic=False,
        )
        sequence = sequence.announce(
            actor="B",
            proposal_id="proposal:b",
            assignments=(),
            automatic=True,
        )

        self.assertEqual("D", sequence.pending_actor)
        self.assertEqual(
            (DamageAssignment("A1", "B1", 2),),
            sequence.collected_assignments,
        )
        self.assertEqual(
            sequence,
            CombatDamageAssignmentSequence.from_dict(sequence.to_dict()),
        )

    def test_sequence_rejects_wrong_actor_zero_rows_and_tampering(self):
        sequence = CombatDamageAssignmentSequence(actors=("A", "B"))
        with self.assertRaises(CombatDamageSequenceError):
            sequence.announce(
                actor="B",
                proposal_id="proposal:b",
                assignments=(),
                automatic=False,
            )
        with self.assertRaises(CombatDamageSequenceError):
            sequence.announce(
                actor="A",
                proposal_id="proposal:a",
                assignments=(DamageAssignment("A1", "B", 0),),
                automatic=False,
            )
        with self.assertRaises(CombatDamageSequenceError):
            CombatDamageAssignmentSequence.from_dict(
                {
                    "version": 1,
                    "actors": ["A"],
                    "cursor": True,
                    "announcements": [],
                }
            )
        with self.assertRaises(CombatDamageSequenceError):
            CombatDamageAssignmentSequence.from_dict(
                {
                    "version": 1,
                    "actors": ["A"],
                    "cursor": 0,
                    "announcements": [],
                    "unknown": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
