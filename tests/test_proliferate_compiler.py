from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from quorune.carddb import CardDatabase, CardRecord
from quorune.compiler.proliferate_templates import (
    single_proliferate_effect_template,
)
from quorune.oracle_ir import compile_oracle_card, generated_programs
from quorune.rules.capabilities import (
    CapabilityRegistry,
    load_default_capability_registry,
)
from quorune.rules.node_capability_shapes import (
    single_proliferate_node_capabilities,
)
from tests.common import DB_PATH


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "quorune" / "rules" / "capability-registry.json"


def proliferate_record(
    text: str,
    *,
    suffix: int,
    type_line: str = "Sorcery",
) -> CardRecord:
    return CardRecord(
        oracle_id=f"00000000-0000-4000-9000-{suffix:012d}",
        name=f"Generic Proliferate Fixture {suffix}",
        mana_cost="{2}",
        mana_value=2.0,
        type_line=type_line,
        oracle_text=text,
        power="2" if "Creature" in type_line else None,
        toughness="2" if "Creature" in type_line else None,
        loyalty=None,
        defense=None,
        colors=(),
        color_identity=(),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class ProliferateCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry_value = json.loads(
            REGISTRY_PATH.read_text(encoding="utf-8")
        )
        cls.capabilities = load_default_capability_registry()
        cls.database = CardDatabase(DB_PATH)

    @classmethod
    def tearDownClass(cls):
        cls.database.close()

    def test_generic_proliferate_program_is_source_spanned_and_capability_closed(
        self,
    ):
        fixtures = (
            proliferate_record("Proliferate.", suffix=1),
            proliferate_record(
                "When this creature enters, proliferate.",
                suffix=2,
                type_line="Creature — Phyrexian",
            ),
            proliferate_record(
                "{2}: Proliferate.",
                suffix=3,
                type_line="Artifact",
            ),
        )
        expected_kinds = (
            "spell_ability",
            "triggered_ability",
            "activated_ability",
        )
        for record, expected_kind in zip(fixtures, expected_kinds, strict=True):
            with self.subTest(kind=expected_kind):
                ir = compile_oracle_card(
                    record,
                    capability_registry=self.capabilities,
                    capability_profile="commander_review",
                )
                nodes = [node for face in ir.faces for node in face.nodes]
                node = next(
                    value
                    for value in nodes
                    if value.template_id == "proliferate-once-v1"
                )
                self.assertEqual("exact", ir.status)
                self.assertEqual(expected_kind, node.kind)
                self.assertEqual(({"op": "proliferate"},), node.effects)
                self.assertIn(
                    "counter.producer.proliferate",
                    node.capability_dependencies,
                )
                if expected_kind == "triggered_ability":
                    self.assertTrue(
                        {
                            "trigger.event.normalized_zone_change",
                            "trigger.placement.apnap",
                        }.issubset(node.capability_dependencies)
                    )
                self.assertEqual(
                    record.oracle_text,
                    record.oracle_text[node.span.start : node.span.end],
                )
                program = next(
                    value
                    for value in generated_programs(
                        self.database,
                        record,
                        trust_level="trusted",
                        capability_registry=self.capabilities,
                        capability_profile="commander_review",
                    )
                    if value.provenance.get("template_id")
                    == "proliferate-once-v1"
                )
                self.assertTrue(program.capability_closure["trusted"])
                self.assertEqual(
                    {
                        "line": 1,
                        "start": 0,
                        "end": len(record.oracle_text),
                    },
                    program.provenance["source_span"],
                )

    def test_unsupported_proliferate_variants_remain_material_residuals(self):
        for suffix, text in enumerate(
            (
                "Proliferate twice.",
                "Proliferate, then proliferate again.",
                "Target player proliferates.",
                "If you would proliferate, proliferate twice instead.",
                "Proliferate X times.",
            ),
            start=10,
        ):
            with self.subTest(text=text):
                self.assertIsNone(single_proliferate_effect_template(text))
                ir = compile_oracle_card(
                    proliferate_record(text, suffix=suffix),
                    capability_registry=self.capabilities,
                    capability_profile="commander_review",
                )
                self.assertNotEqual("exact", ir.status)
                self.assertTrue(ir.material_residuals)

    def test_representative_commander_cards_use_the_generic_family(self):
        expected = {
            "Contentious Plan": "spell_ability",
            "Kiora's Dambreaker": "triggered_ability",
            "Viral Drake": "activated_ability",
        }
        for name, kind in expected.items():
            with self.subTest(name=name):
                ir = compile_oracle_card(
                    self.database.lookup(name),
                    capability_registry=self.capabilities,
                    capability_profile="commander_review",
                )
                node = next(
                    node
                    for face in ir.faces
                    for node in face.nodes
                    if node.template_id == "proliferate-once-v1"
                )
                self.assertEqual("exact", ir.status)
                self.assertEqual(kind, node.kind)
                self.assertEqual(
                    ({"op": "proliferate"},),
                    node.effects,
                )

    def test_proliferate_capability_shape_rejects_mutations(self):
        for effects, target_schema, mechanics in (
            (({"op": "proliferate", "times": 2},), None, ("proliferate",)),
            (({"op": "proliferate"},), {"count": 1}, ("proliferate",)),
            (({"op": "proliferate"},), None, ()),
            (({"op": "proliferate"}, {"op": "draw", "count": 1}), None, ("proliferate",)),
        ):
            with self.subTest(effects=effects):
                self.assertEqual(
                    (),
                    single_proliferate_node_capabilities(
                        effects=effects,
                        target_schema=target_schema,
                        mechanic_ids=mechanics,
                    ),
                )

    def test_proliferate_dependency_mutation_fails_closed(self):
        value = json.loads(json.dumps(self.registry_value))
        dependency = next(
            row
            for row in value["capabilities"]
            if row["id"] == "counter.placement.quantity_replacement"
        )
        dependency["status"] = "blocked"
        dependency["blockers"] = ["test mutation"]
        ir = compile_oracle_card(
            proliferate_record("Proliferate.", suffix=20),
            capability_registry=CapabilityRegistry(value),
            capability_profile="commander_review",
        )
        self.assertNotEqual("exact", ir.status)
        self.assertTrue(
            any(
                "counter.placement.quantity_replacement" in blocker
                for residual in ir.material_residuals
                for blocker in residual.blockers
            )
        )

    def test_proliferate_compiler_mutant_is_killed(self):
        record = proliferate_record("Proliferate.", suffix=30)

        def assert_exact() -> None:
            ir = compile_oracle_card(
                record,
                capability_registry=self.capabilities,
                capability_profile="commander_review",
            )
            self.assertEqual("exact", ir.status)

        assert_exact()
        with patch(
            "quorune.compiler.resolution_effect_templates."
            "single_proliferate_effect_template",
            return_value=None,
        ):
            with self.assertRaises(AssertionError):
                assert_exact()


if __name__ == "__main__":
    unittest.main()
