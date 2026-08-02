from __future__ import annotations

import unittest

from mtg_commander_sim.object_query import (
    ObjectQueryResult,
    ObjectQuerySpec,
    query_objects,
)


class ObjectQueryTests(unittest.TestCase):
    def setUp(self):
        self.rows = (
            ObjectQueryResult(
                object_id="one",
                ref="C1",
                printed_name="Citadel",
                owner="A",
                controller="A",
                zone="battlefield",
                types=("artifact", "land"),
                subtypes=("swamp",),
                supertypes=(),
                colors=(),
                keywords=("indestructible",),
            ),
            ObjectQueryResult(
                object_id="two",
                ref="C2",
                printed_name="Familiar",
                owner="A",
                controller="B",
                zone="graveyard",
                types=("creature",),
                subtypes=("cat",),
                supertypes=(),
                colors=("B",),
                keywords=(),
                tapped=True,
            ),
        )

    def test_query_composes_zone_relation_and_effective_characteristics(self):
        self.assertEqual(
            ("C1",),
            tuple(
                row.ref
                for row in query_objects(
                    self.rows,
                    ObjectQuerySpec(
                        zones=("battlefield",),
                        controller="A",
                        types_all=("land",),
                        subtypes_all=("swamp",),
                        keywords_all=("indestructible",),
                    ),
                )
            ),
        )

    def test_non_target_query_preserves_owner_controller_distinction(self):
        self.assertEqual(
            ("C2",),
            tuple(
                row.ref
                for row in query_objects(
                    self.rows,
                    ObjectQuerySpec(
                        zones=("graveyard",),
                        owner="A",
                        controller="B",
                        types_all=("creature",),
                        tapped=True,
                    ),
                )
            ),
        )

    def test_inputs_and_results_are_immutable(self):
        original = list(self.rows)
        result = query_objects(original, ObjectQuerySpec(types_all=("land",)))
        original.clear()
        self.assertEqual(("C1",), tuple(row.ref for row in result))
