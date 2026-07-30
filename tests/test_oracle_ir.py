from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
import random
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from common import DB_PATH
from mtg_commander_sim import (
    CardDatabase,
    CommanderSession,
    GameConfig,
)
from mtg_commander_sim.cli import main
from mtg_commander_sim.deck import DeckDefinition, DeckEntry
from mtg_commander_sim.mechanic_contracts import (
    MechanicContractError,
    apply_contracts_to_registry,
    load_mechanic_contracts,
    validate_mechanic_contract,
)
from mtg_commander_sim.oracle_ir import (
    ORACLE_COMPILER_VERSION,
    compile_oracle_card,
    generated_programs,
    oracle_corpus_coverage,
)
from mtg_commander_sim.rules_corpus import verify_rules_corpus
from mtg_commander_sim.util import normalize_card_name


ROOT = Path(__file__).resolve().parents[1]


class MechanicContractTests(unittest.TestCase):
    def test_partial_contracts_overlay_without_claiming_trust(self):
        registry = json.loads(
            (ROOT / "mechanics" / "registry.json").read_text(
                encoding="utf-8"
            )
        )
        contracts = load_mechanic_contracts(
            ROOT,
            expected_effective_date=registry["effective_date"],
            expected_source_sha256=registry["source_sha256"],
            known_rule_ids={
                row["rule_id"]
                for row in json.loads(
                    (ROOT / "rules" / "rule-index.json").read_text(
                        encoding="utf-8"
                    )
                )["rules"]
            },
        )
        self.assertEqual(
            {
                "cr-613-interaction-of-continuous-effects",
                "cr-616-interaction-of-replacement-and-or-prevention-effects",
                "deathtouch",
                "flying",
                "protection",
            },
            {contract["mechanic_id"] for contract in contracts},
        )
        overlaid = apply_contracts_to_registry(registry, contracts)
        flying = next(
            row
            for row in overlaid["mechanics"]
            if row["mechanic_id"] == "flying"
        )
        self.assertEqual("partial", flying["coverage_status"])
        self.assertEqual("untrusted", flying["trust_level"])
        self.assertTrue(flying["known_blockers"])
        self.assertTrue(verify_rules_corpus(ROOT)["ok"])

    def test_trusted_contract_cannot_retain_known_blockers(self):
        contract = json.loads(
            (
                ROOT
                / "mechanics"
                / "contracts"
                / "flying.json"
            ).read_text(encoding="utf-8")
        )
        contract["coverage_status"] = "trusted"
        contract["trust_level"] = "trusted"
        contract["review_status"] = "reviewed"
        with self.assertRaises(MechanicContractError):
            validate_mechanic_contract(contract)


class OracleIRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temporary_directory = tempfile.TemporaryDirectory()
        cls.db_path = (
            Path(cls._temporary_directory.name)
            / "oracle-ir-test.sqlite3"
        )
        shutil.copy2(DB_PATH, cls.db_path)
        cls._insert_synthetic_cards(cls.db_path)
        cls.db = CardDatabase(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls._temporary_directory.cleanup()

    @staticmethod
    def _insert_synthetic_cards(path: Path) -> None:
        cards = [
            {
                "oracle_id": "00000000-0000-4000-8000-000000000001",
                "name": "Lightning Bolt",
                "mana_cost": "{R}",
                "mana_value": 1.0,
                "type_line": "Instant",
                "oracle_text": (
                    "Lightning Bolt deals 3 damage to any target."
                ),
                "colors": ["R"],
                "color_identity": ["R"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000002",
                "name": "Rest in Peace",
                "mana_cost": "{1}{W}",
                "mana_value": 2.0,
                "type_line": "Enchantment",
                "oracle_text": (
                    "When Rest in Peace enters, exile all graveyards.\n"
                    "If a card or token would be put into a graveyard "
                    "from anywhere, exile it instead."
                ),
                "colors": ["W"],
                "color_identity": ["W"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000003",
                "name": "Divination",
                "mana_cost": "{2}{U}",
                "mana_value": 3.0,
                "type_line": "Sorcery",
                "oracle_text": "Draw two cards.",
                "colors": ["U"],
                "color_identity": ["U"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000004",
                "name": "Grizzly Bears",
                "mana_cost": "{1}{G}",
                "mana_value": 2.0,
                "type_line": "Creature — Bear",
                "oracle_text": "",
                "power": "2",
                "toughness": "2",
                "colors": ["G"],
                "color_identity": ["G"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000005",
                "name": "Flying Men",
                "mana_cost": "{U}",
                "mana_value": 1.0,
                "type_line": "Creature — Human",
                "oracle_text": "Flying",
                "power": "1",
                "toughness": "1",
                "colors": ["U"],
                "color_identity": ["U"],
                "keywords": ["Flying"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000006",
                "name": "Llanowar Elves",
                "mana_cost": "{G}",
                "mana_value": 1.0,
                "type_line": "Creature — Elf Druid",
                "oracle_text": "{T}: Add {G}.",
                "power": "1",
                "toughness": "1",
                "colors": ["G"],
                "color_identity": ["G"],
                "keywords": ["Mana Ability"],
                "produced_mana": ["G"],
            },
        ]
        with sqlite3.connect(path) as connection:
            for card in cards:
                raw = {
                    "object": "card",
                    "id": card["oracle_id"],
                    **card,
                    "layout": "normal",
                    "released_at": "2026-01-01",
                    "legalities": {"commander": "legal"},
                }
                connection.execute(
                    """
                    INSERT INTO cards (
                        oracle_id, name, normalized_name, mana_cost,
                        mana_value, type_line, oracle_text, power,
                        toughness, loyalty, defense, colors_json,
                        color_identity_json, keywords_json,
                        produced_mana_json, layout, released_at,
                        legalities_json, faces_json, raw_json
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?,
                        ?, ?, 'normal', '2026-01-01', ?, '[]', ?
                    )
                    """,
                    (
                        card["oracle_id"],
                        card["name"],
                        normalize_card_name(card["name"]),
                        card["mana_cost"],
                        card["mana_value"],
                        card["type_line"],
                        card["oracle_text"],
                        card.get("power"),
                        card.get("toughness"),
                        json.dumps(card.get("colors", [])),
                        json.dumps(card.get("color_identity", [])),
                        json.dumps(card.get("keywords", [])),
                        json.dumps(card.get("produced_mana", [])),
                        json.dumps({"commander": "legal"}),
                        json.dumps(raw),
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO aliases (
                        normalized_alias, alias, oracle_id, priority
                    ) VALUES (?, ?, ?, 100)
                    """,
                    (
                        normalize_card_name(card["name"]),
                        card["name"],
                        card["oracle_id"],
                    ),
                )

    def test_simple_spell_compiles_with_exact_source_span(self):
        record = self.db.lookup("Lightning Bolt")
        ir = compile_oracle_card(record)
        self.assertEqual("partial", ir.status)
        self.assertEqual(1, len(ir.material_residuals))
        node = ir.faces[0].nodes[0]
        self.assertEqual("damage-any-target-v1", node.template_id)
        self.assertTrue(node.lowerable)
        self.assertFalse(node.exact)
        self.assertEqual(record.oracle_text, record.oracle_text[
            node.span.start : node.span.end
        ])
        self.assertEqual(
            {
                "zones": ["player", "battlefield"],
                "categories": ["player", "permanent"],
                "predicate": "damageable",
                "count": 1,
            },
            node.target_schema,
        )

    def test_vanilla_keyword_and_mana_cards_compile_without_name_branches(self):
        self.assertEqual("exact", compile_oracle_card(
            self.db.lookup("Grizzly Bears")
        ).status)
        flying = compile_oracle_card(self.db.lookup("Flying Men"))
        self.assertEqual("partial", flying.status)
        self.assertEqual(
            ("flying",), flying.faces[0].nodes[0].mechanics
        )
        elf = compile_oracle_card(self.db.lookup("Llanowar Elves"))
        self.assertEqual("partial", elf.status)
        self.assertEqual("mana_ability", elf.faces[0].nodes[0].kind)

    def test_trusted_dependency_set_promotes_only_the_matching_template(self):
        bolt = compile_oracle_card(
            self.db.lookup("Lightning Bolt"),
            trusted_mechanics={"damage", "target"},
        )
        self.assertEqual("exact", bolt.status)
        self.assertEqual(0, len(bolt.material_residuals))

    def test_material_unknowns_fail_closed_with_specific_residuals(self):
        rest = compile_oracle_card(self.db.lookup("Rest in Peace"))
        self.assertEqual("unresolved", rest.status)
        kinds = {residual.kind for residual in rest.material_residuals}
        self.assertIn("trigger", kinds)
        self.assertIn("replacement_effect", kinds)
        self.assertTrue(
            all(residual.reason for residual in rest.material_residuals)
        )

    def test_generated_program_is_provisional_and_requires_arbiter(self):
        record = self.db.lookup("Lightning Bolt")
        programs = generated_programs(self.db, record)
        self.assertEqual(1, len(programs))
        program = programs[0]
        self.assertEqual(
            f"{record.oracle_id}:spell:front", program.key
        )
        self.assertEqual("provisional", program.trust_level)
        self.assertTrue(program.requires_arbiter)
        self.assertEqual(
            ORACLE_COMPILER_VERSION,
            program.provenance["authored_by"],
        )
        self.assertEqual(
            "pending_mechanic_contracts",
            program.provenance["dependency_trust"],
        )

    def test_template_mutation_cannot_be_silently_discarded(self):
        record = self.db.lookup("Lightning Bolt")
        mutated = replace(
            record,
            oracle_text=(
                record.oracle_text
                + " Then that player discards a card."
            ),
        )
        ir = compile_oracle_card(
            mutated,
            trusted_mechanics={"damage", "target"},
        )
        self.assertNotEqual("exact", ir.status)
        self.assertTrue(ir.material_residuals)
        self.assertFalse(generated_programs(self.db, mutated))

    def test_unrecognized_oracle_fuzz_always_leaves_material_residual(self):
        base = self.db.lookup("Lightning Bolt")
        randomizer = random.Random(701)
        words = [
            "choose",
            "exchange",
            "outside",
            "perpetually",
            "unless",
            "instead",
            "owner",
            "copy",
        ]
        for index in range(250):
            text = " ".join(
                randomizer.choice(words)
                for _ in range(randomizer.randint(3, 12))
            ) + f" {index}."
            ir = compile_oracle_card(
                replace(base, oracle_text=text)
            )
            self.assertTrue(ir.material_residuals, text)
            self.assertNotEqual("exact", ir.status)

    def test_semantic_hash_is_stable_and_source_sensitive(self):
        record = self.db.lookup("Divination")
        first = compile_oracle_card(record)
        second = compile_oracle_card(record)
        changed = compile_oracle_card(
            replace(record, oracle_text=record.oracle_text + " ")
        )
        self.assertEqual(first.semantic_hash, second.semantic_hash)
        self.assertNotEqual(first.semantic_hash, changed.semantic_hash)

    def test_session_registers_generated_program_for_new_deck_card(self):
        deck_a = DeckDefinition(
            name="A",
            commanders=["Zimone and Dina"],
            entries=[
                DeckEntry(
                    "Zimone and Dina",
                    board="commander",
                ),
                DeckEntry("Lightning Bolt"),
            ],
        )
        deck_b = DeckDefinition(
            name="B",
            commanders=["Mishra, Eminent One"],
            entries=[
                DeckEntry(
                    "Mishra, Eminent One",
                    board="commander",
                ),
                DeckEntry("Island"),
            ],
        )
        session = CommanderSession.create(
            self.db,
            {"A": deck_a, "B": deck_b},
            first_player="A",
            seed=9191,
        )
        bolt = self.db.lookup("Lightning Bolt")
        program = session.engine.semantics.get(
            f"{bolt.oracle_id}:spell:front"
        )
        self.assertIsNotNone(program)
        self.assertEqual("provisional", program.trust_level)
        self.assertTrue(program.requires_arbiter)

    def _generated_spell_session(self, *, trusted_only=False):
        deck_a = DeckDefinition(
            name="A",
            commanders=["Zimone and Dina"],
            entries=[
                DeckEntry("Zimone and Dina", board="commander"),
                DeckEntry("Lightning Bolt"),
            ],
        )
        deck_b = DeckDefinition(
            name="B",
            commanders=["Mishra, Eminent One"],
            entries=[
                DeckEntry("Mishra, Eminent One", board="commander"),
                DeckEntry("Island"),
            ],
        )
        session = CommanderSession.create(
            self.db,
            {"A": deck_a, "B": deck_b},
            first_player="A",
            seed=9292,
            config=GameConfig(
                seed=9292,
                profile="commander_duel",
                semantic_policy=(
                    "trusted_only"
                    if trusted_only
                    else "arbitrate_or_pause"
                ),
            ),
        )
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        bolt = next(
            card
            for card in engine.state.cards.values()
            if card.printed_name == "Lightning Bolt"
        )
        engine.move_card(bolt.object_id, "hand")
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"
        engine.state.players["A"].mana_pool["R"] = 1
        return session, bolt

    def test_generated_spell_routes_to_arbiter_in_default_policy(self):
        session, bolt = self._generated_spell_session()
        engine = session.engine
        engine._cast(
            "A",
            {
                "card": bolt.ref,
                "targets": ["B"],
                "auto_pay": True,
            },
        )
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine._prepare_stack_resolution()
        self.assertEqual(
            "arbiter.resolve",
            engine.state.pending_decision.kind,
        )
        self.assertEqual(
            ["arbiter"], session.pending_principals()
        )

    def test_generated_spell_is_withheld_under_trusted_only(self):
        session, bolt = self._generated_spell_session(
            trusted_only=True
        )
        hints = session.engine._priority_action_hints("A")
        self.assertFalse(
            any(
                action.get("card") == bolt.ref
                for action in hints["actions"]
            )
        )
        self.assertTrue(
            any(
                row.get("card") == bolt.ref
                and row.get("reason")
                == "semantic_policy_requires_trusted"
                for row in hints["diagnostic"][
                    "unresolved_cost_semantics"
                ]
            )
        )

    def test_limited_corpus_coverage_is_measured_not_claimed(self):
        coverage = oracle_corpus_coverage(self.db, limit=25)
        self.assertEqual(25, coverage["total_oracle_ids"])
        self.assertTrue(coverage["limited"])
        self.assertFalse(coverage["current_snapshot_complete"])
        self.assertEqual(
            25, sum(coverage["status_counts"].values())
        )

    def test_oracle_cli_parse_explain_and_coverage(self):
        for args in (
            [
                "oracle",
                "parse",
                "Lightning Bolt",
                "--db",
                str(self.db_path),
            ],
            [
                "oracle",
                "explain",
                "Rest in Peace",
                "--db",
                str(self.db_path),
            ],
            [
                "oracle",
                "coverage",
                "--db",
                str(self.db_path),
                "--limit",
                "5",
            ],
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0, main(args))
            self.assertIsInstance(json.loads(output.getvalue()), dict)


if __name__ == "__main__":
    unittest.main()
