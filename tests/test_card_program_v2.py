from __future__ import annotations

from dataclasses import replace
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import jsonschema

from common import DB_PATH
from mtg_commander_sim.card_programs import CardProgram, CardProgramError
from mtg_commander_sim.card_programs.commands import (
    _compile_best_available,
    audit_card_program,
    explain_card_program,
)
from mtg_commander_sim.card_programs.adapters import (
    card_program_from_semantic_programs,
    card_programs_from_semantic_programs,
    compile_card_program,
)
from mtg_commander_sim.carddb import CardDatabase, CardRecord
from mtg_commander_sim.cli import main as cli_main
from mtg_commander_sim.rules.capabilities import (
    load_default_capability_registry,
)
from mtg_commander_sim.card_programs.validation import (
    canonical_program_fingerprint,
)
from mtg_commander_sim.semantics import SemanticRegistry


ROOT = Path(__file__).resolve().parents[1]


def _bolt() -> CardRecord:
    return CardRecord(
        oracle_id="00000000-0000-4000-8000-00000000b017",
        name="Lightning Bolt",
        mana_cost="{R}",
        mana_value=1.0,
        type_line="Instant",
        oracle_text="Lightning Bolt deals 3 damage to any target.",
        power=None,
        toughness=None,
        loyalty=None,
        defense=None,
        colors=("R",),
        color_identity=("R",),
        keywords=(),
        produced_mana=(),
        layout="normal",
        released_at="1993-08-05",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class CardProgramV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.capabilities = load_default_capability_registry()
        cls.schema = json.loads(
            (ROOT / "schemas" / "card-program-v2.schema.json").read_text(
                encoding="utf-8"
            )
        )

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_generated_program_is_deterministic_typed_and_schema_valid(self):
        first = compile_card_program(
            self.db,
            _bolt(),
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )
        second = compile_card_program(
            self.db,
            _bolt(),
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(2, first.schema_version)
        self.assertEqual("Lightning Bolt", first.card_name)
        self.assertTrue(first.trust_closure["trusted"])
        self.assertIn(
            "damage.result.player_life", first.capability_dependencies
        )
        ability = first.to_dict()["abilities"][0]
        self.assertEqual("spell", ability["kind"])
        self.assertEqual(["stack"], ability["active_zones"])
        self.assertEqual("resolve", ability["timing_permissions"]["event"])
        self.assertEqual("damage", ability["effect_nodes"][0]["op"])
        self.assertEqual("damageable", ability["targets"]["predicate"])
        self.assertEqual("front", ability["face_id"])
        self.assertTrue(ability["source_span"])
        jsonschema.Draft202012Validator(self.schema).validate(first.to_dict())
        restored = CardProgram.from_dict(first.to_dict())
        self.assertEqual(first.to_dict(), restored.to_dict())

    def test_tampered_projection_hash_and_closure_fail_closed(self):
        program = compile_card_program(
            self.db,
            _bolt(),
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )
        changed = program.to_dict()
        changed["abilities"][0]["kind"] = "activated"
        with self.assertRaisesRegex(CardProgramError, "does not match"):
            CardProgram.from_dict(changed)

        changed = program.to_dict()
        changed["fingerprint"] = "0" * 64
        with self.assertRaisesRegex(CardProgramError, "fingerprint"):
            CardProgram.from_dict(changed)

        changed = program.to_dict()
        changed["trust_closure"]["trusted"] = False
        with self.assertRaisesRegex(CardProgramError, "trust_closure"):
            CardProgram.from_dict(changed)

    def test_unparsed_material_text_is_preserved_as_residual(self):
        changed = replace(
            _bolt(),
            oracle_text=(
                "Lightning Bolt deals 3 damage to any target. "
                "Then copy this spell."
            ),
        )
        program = compile_card_program(
            self.db,
            changed,
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
        )
        self.assertTrue(program.residuals)
        self.assertFalse(program.trust_closure["trusted"])
        self.assertTrue(
            any(
                value.startswith("residual:")
                for value in program.trust_closure["blockers"]
            )
        )

    def test_every_builtin_semantic_pack_adapts_to_one_canonical_group(self):
        registry = SemanticRegistry()
        values = registry.programs()
        adapted = card_programs_from_semantic_programs(reversed(values))
        expected_oracle_ids = {
            program.oracle_id for program in values if program.oracle_id
        }
        self.assertEqual(expected_oracle_ids, set(adapted))
        self.assertEqual(
            len(values), sum(len(program.abilities) for program in adapted.values())
        )
        for oracle_id, program in adapted.items():
            with self.subTest(oracle_id):
                jsonschema.Draft202012Validator(self.schema).validate(
                    program.to_dict()
                )
                self.assertEqual(
                    program.to_dict(),
                    CardProgram.from_dict(program.to_dict()).to_dict(),
                )

    def test_registry_snapshot_roundtrips_canonical_and_legacy_views(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "semantics.json"
            registry = SemanticRegistry(path)
            registry.save()
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(2, raw["card_program_schema_version"])
            self.assertEqual(
                registry.card_program_fingerprints(),
                {
                    oracle_id: value["fingerprint"]
                    for oracle_id, value in raw["card_programs"].items()
                },
            )
            restored = SemanticRegistry(path)
            self.assertEqual(
                registry.card_program_fingerprints(),
                restored.card_program_fingerprints(),
            )
            self.assertEqual(
                [program.to_dict() for program in registry.programs()],
                [program.to_dict() for program in restored.programs()],
            )

            program = restored.programs()[0]
            self.assertIsNotNone(
                canonical_program_fingerprint(restored, program)
            )
            program.label += " mutated after pin"
            self.assertIsNone(
                canonical_program_fingerprint(restored, program)
            )

            key = next(iter(raw["programs"]))
            raw["programs"][key]["label"] += " tampered"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "views disagree"):
                SemanticRegistry(path)

    def test_semantic_adapter_rejects_cross_card_or_source_hash_mix(self):
        values = SemanticRegistry().programs()
        first = values[0]
        second = next(
            program for program in values if program.oracle_id != first.oracle_id
        )
        with self.assertRaisesRegex(CardProgramError, "one oracle_id"):
            card_program_from_semantic_programs([first, second])

        grouped = card_programs_from_semantic_programs(values)
        multi = next(
            program for program in grouped.values() if len(program.abilities) > 1
        )
        same_card = list(multi.abilities)
        stale = replace(
            same_card[0],
            provenance={
                **same_card[0].provenance,
                "source_oracle_hash": "0" * 64,
            },
        )
        with self.assertRaisesRegex(CardProgramError, "Oracle hashes"):
            card_program_from_semantic_programs([stale, *same_card[1:]])

    def test_current_card_program_blocks_stale_reviewed_source(self):
        generated = compile_card_program(
            self.db,
            _bolt(),
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )
        reviewed = replace(
            generated.abilities[0],
            provenance={
                **generated.abilities[0].provenance,
                "source_oracle_hash": "0" * 64,
            },
        )
        registry = SemanticRegistry(include_builtin_packs=False)
        registry.put(reviewed)
        current = compile_card_program(
            self.db,
            _bolt(),
            semantic_registry=registry,
            capability_registry=self.capabilities,
            capability_profile="commander_duel",
            trust_level="trusted",
        )
        self.assertFalse(current.trust_closure["trusted"])
        self.assertTrue(
            any(
                blocker.endswith("stale_oracle_source")
                for blocker in current.trust_closure["blockers"]
            )
        )

    def test_card_cli_compile_explain_audit_diff_overrides_and_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "mishra.card-program.json"
            invocations = (
                [
                    "card",
                    "compile",
                    "Mishra, Eminent One",
                    "--db",
                    str(DB_PATH),
                    "--output",
                    str(snapshot),
                ],
                [
                    "card",
                    "explain",
                    "Mishra, Eminent One",
                    "--db",
                    str(DB_PATH),
                ],
                [
                    "card",
                    "audit",
                    "Mishra, Eminent One",
                    "--db",
                    str(DB_PATH),
                ],
                [
                    "card",
                    "diff",
                    "Mishra, Eminent One",
                    "--db",
                    str(DB_PATH),
                    "--against",
                    str(snapshot),
                ],
                ["card", "overrides", "--db", str(DB_PATH)],
                [
                    "card",
                    "coverage",
                    "--db",
                    str(DB_PATH),
                    "--limit",
                    "2",
                ],
            )
            results = []
            for args in invocations:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(0, cli_main(args))
                results.append(json.loads(output.getvalue()))
            self.assertEqual(2, results[0]["schema_version"])
            self.assertTrue(results[1]["abilities"])
            self.assertTrue(results[2]["deterministic_roundtrip"])
            self.assertFalse(results[3]["changed"])
            self.assertIn("overrides", results[4])
            self.assertEqual(2, results[5]["cards_considered"])

    def test_explain_and_audit_identify_registered_typed_handlers(self):
        program = next(
            card_program
            for card_program in SemanticRegistry().card_programs()
            if any(
                effect.get("op") == "draw"
                for ability in card_program.abilities
                for effect in ability.effects
            )
        )
        explained = explain_card_program(program)
        mappings = [
            handler
            for ability in explained["abilities"]
            for handler in ability["runtime_handler_mapping"][
                "typed_handlers"
            ]
        ]
        self.assertTrue(
            any(handler["handler_id"] == "generic.draw.v1" for handler in mappings)
        )
        audited = audit_card_program(program)
        audit_mappings = [
            handler
            for ability in audited["runtime_handler_mapping"].values()
            for handler in ability["typed_handlers"]
        ]
        self.assertTrue(
            any(
                handler["capability_dependencies"]
                == ["zone.draw.library_to_hand"]
                for handler in audit_mappings
            )
        )

        runtime_programs = [
            card_program
            for card_program in SemanticRegistry().card_programs()
            if any(ability.handlers for ability in card_program.abilities)
        ]
        event_handlers = [
            handler
            for runtime_program in runtime_programs
            for ability in explain_card_program(runtime_program)["abilities"]
            for handler in ability["runtime_handler_mapping"][
                "event_handlers"
            ]
        ]
        self.assertEqual(
            {
                "continuous.anthem.power_toughness.v1": [
                    "continuous.power_toughness.fixed_anthem"
                ],
                "prevention.damage.fixed.v1": [
                    "damage.prevention.static_fixed"
                ],
                "replacement.counter.quantity.v1": [
                    "counter.placement.quantity_replacement"
                ],
                "replacement.damage.quantity.v1": [
                    "damage.replacement.static_quantity"
                ],
                "replacement.token.additional.v1": [
                    "token.creation.additional_replacement"
                ],
                "replacement.zone.destination.v1": [
                    "zone.change.destination_replacement"
                ],
            },
            {
                handler["handler_id"]: handler["registry"][
                    "capability_dependencies"
                ]
                for handler in event_handlers
            },
        )
        self.assertTrue(
            all(
                any(
                    mapping["event_handlers"]
                    for mapping in audit_card_program(runtime_program)[
                        "runtime_handler_mapping"
                    ].values()
                )
                for runtime_program in runtime_programs
            )
        )

    def test_cli_does_not_downgrade_unexpected_compiler_errors(self):
        with patch(
            "mtg_commander_sim.card_programs.commands.compile_card_program",
            side_effect=ValueError("broken CardProgram structure"),
        ) as compile_program:
            with self.assertRaisesRegex(ValueError, "broken CardProgram"):
                _compile_best_available(
                    self.db,
                    self.db.lookup("Mishra, Eminent One"),
                    registry=SemanticRegistry(),
                    profile="traditional",
                )
        compile_program.assert_called_once()


if __name__ == "__main__":
    unittest.main()
