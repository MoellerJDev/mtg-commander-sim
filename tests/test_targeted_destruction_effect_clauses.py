from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from common import ROOT
from mtg_commander_sim.carddb import CardDatabase
from mtg_commander_sim.compiler.destruction_templates import (
    DestructionTarget,
    TargetedDestructionEffectTemplate,
    targeted_destruction_effect_template,
)
from mtg_commander_sim.oracle_ir import (
    compile_oracle_card,
    register_generated_programs,
)
from mtg_commander_sim.rules.capabilities import (
    capability_dependencies_for_node,
    load_default_capability_registry,
)
from mtg_commander_sim.semantics import SemanticRegistry
from scripts.build_test_database import build_fixture_database


def focused_card_database(directory: str) -> CardDatabase:
    database = Path(directory) / "targeted-destruction.sqlite3"
    build_fixture_database(
        [
            ROOT / "tests" / "fixtures" / "scryfall-exact-lists.json",
            ROOT / "tests" / "fixtures" / "targeted-destruction-cards.json",
        ],
        database,
    )
    return CardDatabase(database)


class TargetedDestructionTemplateTests(unittest.TestCase):
    def test_targeted_destruction_template_is_immutable_and_copy_isolated(self):
        template = TargetedDestructionEffectTemplate(
            DestructionTarget.CREATURE
        )

        self.assertEqual("destroy-target-creature-v2", template.template_id)
        self.assertEqual(
            ({"op": "destroy", "card": "$target.0"},),
            template.effects,
        )
        schema = template.target_schema
        schema["types_any"].append("artifact")
        effects = template.effects
        effects[0]["op"] = "exile"
        self.assertEqual(["creature"], template.target_schema["types_any"])
        self.assertEqual("destroy", template.effects[0]["op"])
        with self.assertRaisesRegex(ValueError, "target"):
            TargetedDestructionEffectTemplate(  # type: ignore[arg-type]
                "creature"
            )

    def test_whole_clause_parser_accepts_only_closed_direct_targets(self):
        for target in DestructionTarget:
            with self.subTest(target=target):
                template = targeted_destruction_effect_template(
                    f"Destroy target {target.value}."
                )
                self.assertIsNotNone(template)
                assert template is not None
                self.assertEqual(target, template.target)
        for text in (
            "Destroy up to one target creature.",
            "You may destroy target creature.",
            "Destroy another target creature.",
            "Destroy target tapped creature.",
            "Destroy target nonland permanent.",
            "Destroy target creature. It can't be regenerated.",
            "Destroy target creature or planeswalker.",
            "Destroy all creatures.",
            "Sacrifice target creature.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(
                    targeted_destruction_effect_template(text)
                )


class TargetedDestructionCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.db = focused_card_database(cls.temporary.name)
        cls.base = cls.db.lookup("Lightning Greaves")
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.temporary.cleanup()

    def compile(self, oracle_text: str, *, type_line: str = "Instant"):
        return compile_oracle_card(
            replace(
                self.base,
                name="Fixture",
                oracle_text=oracle_text,
                type_line=type_line,
                keywords=(),
                faces=(),
            ),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )

    def test_spell_trigger_and_activated_contexts_share_targeted_destruction_lowering(self):
        contexts = (
            (
                "Destroy target creature.",
                "Instant",
                "spell_ability",
                "destroy-target-creature-v2",
            ),
            (
                "When this creature enters, destroy target artifact.",
                "Creature — Test",
                "triggered_ability",
                "destroy-target-artifact-v2",
            ),
            (
                "{2}{B}, {T}: Destroy target creature.",
                "Creature — Test",
                "activated_ability",
                "destroy-target-creature-v2",
            ),
        )
        for text, type_line, kind, template_id in contexts:
            with self.subTest(kind=kind, text=text):
                ir = self.compile(text, type_line=type_line)
                node = ir.faces[0].nodes[0]
                self.assertEqual("exact", ir.status)
                self.assertTrue(node.exact)
                self.assertEqual(kind, node.kind)
                self.assertEqual(template_id, node.template_id)
                self.assertEqual(
                    {
                        "permanent.destroy.effect",
                        "target.revalidate_resolution",
                    },
                    set(node.capability_dependencies)
                    - {
                        "trigger.event.normalized_zone_change",
                        "trigger.placement.apnap",
                    },
                )
                self.assertEqual(text, text[node.span.start : node.span.end])

    def test_unsupported_destruction_variants_remain_material_residuals(self):
        for text in (
            "Destroy up to one target creature.",
            "You may destroy target creature.",
            "Destroy another target creature.",
            "Destroy target tapped creature.",
            "Destroy target nonland permanent.",
            "Destroy target creature. It can't be regenerated.",
            "Destroy all creatures.",
        ):
            with self.subTest(text=text):
                ir = self.compile(text)
                self.assertNotEqual("exact", ir.status)
                self.assertTrue(ir.material_residuals)

    def test_targeted_destruction_shape_mutants_fail_closed(self):
        template = TargetedDestructionEffectTemplate(
            DestructionTarget.CREATURE
        )
        self.assertEqual(
            {
                "permanent.destroy.effect",
                "target.revalidate_resolution",
            },
            set(
                capability_dependencies_for_node(
                    effects=template.effects,
                    target_schema=template.target_schema,
                    mechanic_ids=template.mechanics,
                )
            ),
        )
        malformed_effects = (
            ({"op": "destroy", "card": "$target.1"},),
            ({"op": "destroy", "card": "$source"},),
            (
                {
                    "op": "destroy",
                    "card": "$target.0",
                    "reason": "open grammar",
                },
            ),
            ({"op": "move", "card": "$target.0"},),
        )
        for effects in malformed_effects:
            with self.subTest(effects=effects):
                self.assertFalse(
                    capability_dependencies_for_node(
                        effects=effects,
                        target_schema=template.target_schema,
                        mechanic_ids=template.mechanics,
                    )
                )
        malformed_schemas = (
            {**template.target_schema, "zones": ["graveyard"]},
            {**template.target_schema, "count": 2},
            {**template.target_schema, "types_any": ["noncreature"]},
            {**template.target_schema, "controller": "opponent"},
        )
        for schema in malformed_schemas:
            with self.subTest(schema=schema):
                self.assertFalse(
                    capability_dependencies_for_node(
                        effects=template.effects,
                        target_schema=schema,
                        mechanic_ids=template.mechanics,
                    )
                )
        self.assertFalse(
            capability_dependencies_for_node(
                effects=template.effects,
                target_schema=template.target_schema,
                mechanic_ids=("cr-115-targets",),
            )
        )

    def test_generated_direct_target_program_is_capability_closed(self):
        registry = SemanticRegistry(include_builtin_packs=False)
        result = register_generated_programs(
            self.db,
            registry,
            (self.db.lookup("Murder"),),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            promote_exact_effect_programs=True,
        )
        programs = [program for program in registry.programs() if program.effects]
        self.assertEqual(1, result["exact_effect_programs_promoted"])
        self.assertEqual(1, len(programs))
        self.assertEqual("trusted", programs[0].trust_level)
        self.assertTrue(
            {
                "permanent.destroy.effect",
                "target.revalidate_resolution",
            }.issubset(programs[0].capability_dependencies)
        )


if __name__ == "__main__":
    unittest.main()
