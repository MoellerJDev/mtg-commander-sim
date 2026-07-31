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
    register_generated_programs,
)
from mtg_commander_sim.rules_corpus import verify_rules_corpus
from mtg_commander_sim.semantics import (
    SemanticProgram,
    SemanticRegistry,
)
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
                "cr-111-tokens",
                "cr-120-damage",
                "cr-122-counters",
                "cr-210-defense",
                "cr-310-battles",
                "cr-400-general",
                "cr-504-draw-step",
                "cr-506-combat-phase",
                "cr-505-main-phase",
                "cr-507-beginning-of-combat-step",
                "cr-508-declare-attackers-step",
                "cr-509-declare-blockers-step",
                "cr-510-combat-damage-step",
                "cr-511-end-of-combat-step",
                "cr-512-ending-phase",
                "cr-513-end-step",
                "cr-514-cleanup-step",
                "cr-600-general",
                "cr-601-casting-spells",
                "cr-602-activating-activated-abilities",
                "cr-603-handling-triggered-abilities",
                "cr-604-handling-static-abilities",
                "cr-605-mana-abilities",
                "cr-606-loyalty-abilities",
                "cr-607-linked-abilities",
                "cr-608-resolving-spells-and-abilities",
                "cr-609-effects",
                "cr-611-continuous-effects",
                "cr-614-replacement-effects",
                "cr-615-prevention-effects",
                "cr-704-state-based-actions",
                "cr-707-copying-objects",
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
            {
                "oracle_id": "00000000-0000-4000-8000-000000000007",
                "name": "Elvish Visionary",
                "mana_cost": "{1}{G}",
                "mana_value": 2.0,
                "type_line": "Creature — Elf Shaman",
                "oracle_text": (
                    "When this creature enters, draw a card."
                ),
                "power": "1",
                "toughness": "1",
                "colors": ["G"],
                "color_identity": ["G"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000008",
                "name": "Kingfisher",
                "mana_cost": "{3}{U}",
                "mana_value": 4.0,
                "type_line": "Creature — Bird",
                "oracle_text": (
                    "Flying\nWhen this creature dies, draw a card."
                ),
                "power": "2",
                "toughness": "2",
                "colors": ["U"],
                "color_identity": ["U"],
                "keywords": ["Flying"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000009",
                "name": "Moss Diamond",
                "mana_cost": "{2}",
                "mana_value": 2.0,
                "type_line": "Artifact",
                "oracle_text": (
                    "This artifact enters tapped.\n{T}: Add {G}."
                ),
                "produced_mana": ["G"],
                "color_identity": ["G"],
                "keywords": ["Mana Ability"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000010",
                "name": "Sprout",
                "mana_cost": "{G}",
                "mana_value": 1.0,
                "type_line": "Instant",
                "oracle_text": (
                    "Create a 1/1 green Saproling creature token."
                ),
                "colors": ["G"],
                "color_identity": ["G"],
            },
            {
                "oracle_id": "00000000-0000-4000-8000-000000000011",
                "name": "Whispering Shade",
                "mana_cost": "{3}{B}",
                "mana_value": 4.0,
                "type_line": "Creature — Shade",
                "oracle_text": (
                    "{B}: This creature gets +1/+1 until end of turn."
                ),
                "power": "1",
                "toughness": "1",
                "colors": ["B"],
                "color_identity": ["B"],
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
            trusted_mechanics={
                "cr-120-damage",
                "cr-115-targets",
            },
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

    def test_simple_self_trigger_compiles_to_normalized_engine_event(self):
        record = self.db.lookup("Elvish Visionary")
        ir = compile_oracle_card(record)
        node = ir.faces[0].nodes[0]
        self.assertEqual("triggered_ability", node.kind)
        self.assertEqual("permanent.enter.self", node.event)
        self.assertEqual("draw-controller-v1", node.template_id)
        self.assertTrue(node.lowerable)
        self.assertFalse(node.exact)
        self.assertEqual(
            (
                "cr-603-handling-triggered-abilities",
                "cr-121-drawing-a-card",
            ),
            node.mechanics,
        )
        programs = generated_programs(self.db, record)
        self.assertEqual(1, len(programs))
        self.assertEqual("permanent.enter.self", programs[0].event)
        self.assertEqual(
            [{"op": "draw", "player": "$controller", "count": 1,
              "private": True}],
            programs[0].effects,
        )

    def test_trigger_with_uncompiled_condition_remains_residual(self):
        record = replace(
            self.db.lookup("Elvish Visionary"),
            oracle_text=(
                "When this creature enters, if you control an Elf, "
                "draw a card."
            ),
        )
        ir = compile_oracle_card(record)
        self.assertEqual("unresolved", ir.status)
        self.assertEqual("trigger", ir.material_residuals[0].kind)
        self.assertFalse(generated_programs(self.db, record))

    def test_self_pump_and_basic_token_creation_lower_generically(self):
        shade_program = generated_programs(
            self.db,
            self.db.lookup("Whispering Shade"),
        )[0]
        self.assertEqual(
            [
                {
                    "op": "modify_stats_until_end_of_turn",
                    "card": "$source",
                    "power": 1,
                    "toughness": 1,
                }
            ],
            shade_program.effects,
        )
        sprout_program = generated_programs(
            self.db,
            self.db.lookup("Sprout"),
        )[0]
        token = sprout_program.effects[0]
        self.assertEqual("create_token", token["op"])
        self.assertEqual("Saproling", token["name"])
        self.assertEqual(
            "Token Creature — Saproling",
            token["characteristics"]["type_line"],
        )
        self.assertEqual(["G"], token["characteristics"]["colors"])
        counter_record = replace(
            self.db.lookup("Whispering Shade"),
            oracle_text=(
                "{T}: Put a +1/+1 counter on target creature."
            ),
        )
        counter_program = generated_programs(
            self.db,
            counter_record,
        )[0]
        self.assertEqual(
            {
                "op": "add_counter_selected",
                "cards": ["$target.0"],
                "counter": "+1/+1",
                "amount": 1,
            },
            counter_program.effects[0],
        )
        self.assertEqual(
            ["creature"],
            counter_program.target_schema["types_any"],
        )

    def test_new_templates_remain_whole_text_anchored(self):
        cases = [
            (
                self.db.lookup("Sprout"),
                (
                    "Create a 1/1 green Saproling creature token "
                    "with flying."
                ),
            ),
            (
                self.db.lookup("Whispering Shade"),
                (
                    "{B}: This creature gets +1/+1 until end of turn. "
                    "Activate only once each turn."
                ),
            ),
            (
                self.db.lookup("Moss Diamond"),
                (
                    "This artifact enters tapped unless you control "
                    "a Forest.\n{T}: Add {G}."
                ),
            ),
        ]
        for base, oracle_text in cases:
            with self.subTest(base.name):
                ir = compile_oracle_card(
                    replace(base, oracle_text=oracle_text)
                )
                self.assertTrue(ir.material_residuals)
                self.assertNotEqual("exact", ir.status)

    def test_generated_trust_cannot_bypass_material_residuals(self):
        with self.assertRaisesRegex(
            ValueError,
            "material Oracle residuals remain",
        ):
            generated_programs(
                self.db,
                self.db.lookup("Lightning Bolt"),
                trust_level="trusted",
            )

    def test_reviewed_trigger_shadows_equivalent_generated_event(self):
        record = self.db.lookup("Elvish Visionary")
        registry = SemanticRegistry(include_builtin_packs=False)
        reviewed = SemanticProgram(
            key=f"{record.oracle_id}:reviewed:enter",
            label="Reviewed Elvish Visionary trigger",
            effects=[
                {
                    "op": "draw",
                    "player": "$controller",
                    "count": 1,
                }
            ],
            oracle_id=record.oracle_id,
            ability_id="reviewed:enter",
            active_zone="battlefield",
            event="permanent.enter.self",
            trust_level="trusted",
            provenance={
                "source_oracle_hash": "reviewed-oracle-hash",
                "source_rulings_hash": "reviewed-rulings-hash",
                "authored_by": "test",
                "review_status": "reviewed",
            },
            tests=["test_reviewed_trigger"],
        )
        registry.put(reviewed)
        result = register_generated_programs(
            self.db,
            registry,
            [record],
        )
        self.assertEqual(0, result["programs_generated"])
        self.assertEqual(1, result["programs_skipped_existing"])
        self.assertEqual(
            [reviewed.key],
            [program.key for program in registry.programs()],
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
            trusted_mechanics={
                "cr-120-damage",
                "cr-115-targets",
            },
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

    def _trigger_session(self):
        deck_a = DeckDefinition(
            name="A",
            commanders=["Zimone and Dina"],
            entries=[
                DeckEntry("Zimone and Dina", board="commander"),
                DeckEntry("Elvish Visionary"),
                DeckEntry("Kingfisher"),
                DeckEntry("Moss Diamond"),
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
            seed=9393,
        )
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        for player in engine.state.players.values():
            player.attempted_empty_draw = False
        return session

    def test_generated_enters_trigger_reaches_arbiter_fail_closed(self):
        session = self._trigger_session()
        engine = session.engine
        visionary = next(
            card
            for card in engine.state.cards.values()
            if card.printed_name == "Elvish Visionary"
        )
        engine.move_card(
            visionary.object_id,
            "battlefield",
            controller="A",
            semantic_events=True,
        )
        self.assertTrue(engine.state.pending_trigger_batches)
        self.assertFalse(engine._stabilize())
        trigger = engine.state.stack[-1]
        self.assertEqual("A", trigger.controller)
        self.assertEqual(
            "permanent.enter",
            trigger.context["event"],
        )
        engine._prepare_stack_resolution()
        self.assertEqual(
            "arbiter.resolve",
            engine.state.pending_decision.kind,
        )

    def test_self_dies_trigger_uses_last_known_controller(self):
        session = self._trigger_session()
        engine = session.engine
        kingfisher = next(
            card
            for card in engine.state.cards.values()
            if card.printed_name == "Kingfisher"
        )
        engine.move_card(
            kingfisher.object_id,
            "battlefield",
            controller="B",
        )
        engine.move_card(
            kingfisher.object_id,
            "graveyard",
            semantic_events=True,
        )
        self.assertTrue(engine.state.pending_trigger_batches)
        self.assertFalse(engine._stabilize())
        trigger = engine.state.stack[-1]
        self.assertEqual("B", trigger.controller)
        self.assertEqual("creature.dies", trigger.context["event"])
        self.assertEqual("A", kingfisher.controller)

    def test_unconditional_entry_tapped_is_engine_derived(self):
        session = self._trigger_session()
        engine = session.engine
        diamond = next(
            card
            for card in engine.state.cards.values()
            if card.printed_name == "Moss Diamond"
        )
        ir = compile_oracle_card(self.db.lookup("Moss Diamond"))
        entry = next(
            node
            for node in ir.faces[0].nodes
            if node.template_id == "enters-tapped-self-v1"
        )
        self.assertTrue(entry.lowerable)
        engine.move_card(
            diamond.object_id,
            "battlefield",
            controller="A",
        )
        self.assertTrue(diamond.tapped)
        engine.move_card(diamond.object_id, "hand")
        engine.move_card(
            diamond.object_id,
            "battlefield",
            controller="A",
            tapped=False,
        )
        self.assertFalse(diamond.tapped)

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
        # This deliberately tiny compiler fixture exhausts both libraries
        # during setup. Clear that unrelated loss marker before exercising
        # post-cast semantic arbitration.
        for player in engine.state.players.values():
            player.attempted_empty_draw = False
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
