from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common import DB_PATH, keep_all, load_assets, make_session
from quorune.carddb import CardDatabase
from quorune.compiler.damage_templates import (
    FixedDamageEffectTemplate,
    FixedDamageRecipient,
    fixed_damage_effect_template,
)
from quorune.compiler import damage_templates
from quorune.oracle_ir import (
    compile_oracle_card,
    register_generated_programs,
)
from quorune.model import StackItem
from quorune.record import (
    authoritative_state_hash,
    checkpoint_envelope,
    replay_record,
)
from quorune.rules.capabilities import (
    capability_dependencies_for_node,
    load_default_capability_registry,
)
from quorune.rules import node_capability_shapes
from quorune.semantics import SemanticRegistry


class FixedDamageEffectTemplateTests(unittest.TestCase):
    def test_typed_template_is_immutable_canonical_and_copy_isolated(self):
        template = FixedDamageEffectTemplate(
            amount=3,
            recipient=FixedDamageRecipient.CREATURE_OR_PLANESWALKER,
            source_kind="spell",
        )

        self.assertEqual("damage-creature-or-planeswalker-v1", template.template_id)
        self.assertEqual(
            (
                {
                    "op": "damage",
                    "source": "$source",
                    "target": "$target.0",
                    "amount": 3,
                },
            ),
            template.effects,
        )
        schema = template.target_schema
        self.assertIsNotNone(schema)
        schema["types_any"].append("battle")
        self.assertEqual(
            ["creature", "planeswalker"],
            template.target_schema["types_any"],
        )
        with self.assertRaisesRegex(ValueError, "positive"):
            FixedDamageEffectTemplate(
                amount=0,
                recipient=FixedDamageRecipient.CREATURE,
            )
        with self.assertRaisesRegex(ValueError, "source kind"):
            FixedDamageEffectTemplate(
                amount=1,
                recipient=FixedDamageRecipient.CREATURE,
                source_kind="arbitrary",
            )

    def test_whole_clause_parser_rejects_riders_and_open_grammar(self):
        accepted = fixed_damage_effect_template(
            "This land deals 2 damage to target opponent or planeswalker.",
            card_name="Fixture Land",
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(
            FixedDamageRecipient.OPPONENT_OR_PLANESWALKER,
            accepted.recipient,
        )
        for text in (
            "Fixture deals 0 damage to target creature.",
            "Fixture deals X damage to target creature.",
            "Fixture deals 3 damage divided as you choose among two targets.",
            "Fixture deals 3 damage to target creature and you gain 3 life.",
            "If you control a Mountain, Fixture deals 3 damage to any target.",
            "Deal 3 damage to target creature.",
        ):
            with self.subTest(text=text):
                self.assertIsNone(
                    fixed_damage_effect_template(text, card_name="Fixture")
                )

    def test_recipient_and_positive_amount_mutants_are_killed(self):
        def assert_creature_recipient() -> None:
            template = fixed_damage_effect_template(
                "Fixture deals 2 damage to target creature.",
                card_name="Fixture",
            )
            self.assertIsNotNone(template)
            self.assertEqual(FixedDamageRecipient.CREATURE, template.recipient)

        assert_creature_recipient()
        mutated_recipients = tuple(
            (
                phrase,
                (
                    FixedDamageRecipient.PLAYER
                    if phrase == "target creature"
                    else recipient
                ),
            )
            for phrase, recipient in damage_templates._FIXED_DAMAGE_RECIPIENTS
        )
        with patch.object(
            damage_templates,
            "_FIXED_DAMAGE_RECIPIENTS",
            mutated_recipients,
        ):
            with self.assertRaises(AssertionError):
                assert_creature_recipient()

        effect = {
            "op": "damage",
            "source": "$source",
            "target": "$target.0",
            "amount": 0,
        }
        schema = FixedDamageEffectTemplate(
            amount=1,
            recipient=FixedDamageRecipient.CREATURE,
        ).target_schema

        def assert_zero_is_untrusted() -> None:
            dependencies = capability_dependencies_for_node(
                effects=(effect,),
                target_schema=schema,
                mechanic_ids=("cr-120-damage", "cr-115-targets"),
            )
            self.assertNotIn("damage.amount.positive", dependencies)

        assert_zero_is_untrusted()
        with patch.object(
            node_capability_shapes,
            "_positive_int",
            lambda _value: True,
        ):
            with self.assertRaises(AssertionError):
                assert_zero_is_untrusted()


class FixedDamageEffectCompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = CardDatabase(DB_PATH)
        cls.base = cls.db.lookup("Lightning Bolt")
        cls.capabilities = load_default_capability_registry()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def compile(self, oracle_text: str, *, type_line: str = "Instant"):
        record = replace(
            self.base,
            name="Fixture",
            oracle_text=oracle_text,
            type_line=type_line,
            keywords=(),
        )
        return compile_oracle_card(
            record,
            capability_registry=self.capabilities,
            capability_profile="commander_review",
        )

    def test_closed_target_domains_lower_with_precise_capabilities(self):
        cases = {
            "target creature": (
                "damage-creature-v1",
                {
                    "zones": ["battlefield"],
                    "categories": ["permanent"],
                    "types_any": ["creature"],
                    "count": 1,
                },
                {
                    "damage.amount.positive",
                    "damage.result.multitype_permanent",
                    "target.revalidate_resolution",
                },
            ),
            "target creature or planeswalker": (
                "damage-creature-or-planeswalker-v1",
                {
                    "zones": ["battlefield"],
                    "categories": ["permanent"],
                    "types_any": ["creature", "planeswalker"],
                    "count": 1,
                },
                {
                    "damage.amount.positive",
                    "damage.result.multitype_permanent",
                    "target.revalidate_resolution",
                },
            ),
            "target player or planeswalker": (
                "damage-player-or-planeswalker-v1",
                {
                    "zones": ["player", "battlefield"],
                    "categories": ["player", "permanent"],
                    "predicate": "player_or_planeswalker",
                    "count": 1,
                },
                {
                    "damage.amount.positive",
                    "damage.result.multitype_permanent",
                    "damage.result.player_life",
                    "target.revalidate_resolution",
                },
            ),
            "target opponent or planeswalker": (
                "damage-opponent-or-planeswalker-v1",
                {
                    "zones": ["player", "battlefield"],
                    "categories": ["player", "permanent"],
                    "predicate": "player_or_planeswalker",
                    "count": 1,
                    "player_relation": "opponent",
                },
                {
                    "damage.amount.positive",
                    "damage.result.multitype_permanent",
                    "damage.result.player_life",
                    "target.revalidate_resolution",
                },
            ),
            "target player": (
                "damage-player-v1",
                {
                    "zones": ["player"],
                    "categories": ["player"],
                    "count": 1,
                },
                {
                    "damage.amount.positive",
                    "damage.result.player_life",
                    "target.revalidate_resolution",
                },
            ),
            "target opponent": (
                "damage-opponent-v1",
                {
                    "zones": ["player"],
                    "categories": ["player"],
                    "count": 1,
                    "player_relation": "opponent",
                },
                {
                    "damage.amount.positive",
                    "damage.result.player_life",
                    "target.revalidate_resolution",
                },
            ),
        }
        for phrase, (template_id, schema, dependencies) in cases.items():
            text = f"Fixture deals 3 damage to {phrase}."
            with self.subTest(phrase=phrase):
                ir = self.compile(text)
                node = ir.faces[0].nodes[0]
                self.assertEqual("exact", ir.status)
                self.assertTrue(node.exact)
                self.assertEqual(template_id, node.template_id)
                self.assertEqual(schema, node.target_schema)
                self.assertEqual(dependencies, set(node.capability_dependencies))
                self.assertEqual(
                    text,
                    ir.faces[0].oracle_text[node.span.start : node.span.end],
                )

    def test_each_opponent_is_untargeted_and_capability_closed(self):
        text = "Fixture deals 3 damage to each opponent."
        ir = self.compile(text)
        node = ir.faces[0].nodes[0]

        self.assertEqual("exact", ir.status)
        self.assertEqual("damage-each-opponent-v1", node.template_id)
        self.assertIsNone(node.target_schema)
        self.assertEqual(
            (
                {
                    "op": "damage_each_opponent",
                    "source": "$source",
                    "amount": 3,
                },
            ),
            node.effects,
        )
        self.assertEqual(
            {"damage.amount.positive", "damage.result.player_life"},
            set(node.capability_dependencies),
        )

    def test_spell_trigger_and_activated_contexts_share_one_lowering(self):
        contexts = (
            (
                "Fixture deals 2 damage to target creature.",
                "Instant",
                "spell_ability",
            ),
            (
                "When this creature enters, this creature deals 2 damage "
                "to target creature.",
                "Creature — Test",
                "triggered_ability",
            ),
            (
                "{1}, {T}: This creature deals 2 damage to target creature.",
                "Creature — Test",
                "activated_ability",
            ),
        )
        for text, type_line, kind in contexts:
            with self.subTest(kind=kind):
                ir = self.compile(text, type_line=type_line)
                node = ir.faces[0].nodes[0]
                self.assertEqual("exact", ir.status)
                self.assertEqual(kind, node.kind)
                self.assertEqual("damage-creature-v1", node.template_id)
                self.assertEqual(
                    {
                        "damage.amount.positive",
                        "damage.result.multitype_permanent",
                        "target.revalidate_resolution",
                    },
                    set(node.capability_dependencies)
                    - {
                        "trigger.event.normalized_zone_change",
                        "trigger.placement.apnap",
                    },
                )

    def test_unsupported_damage_variants_remain_material_residuals(self):
        for text in (
            "Fixture deals 0 damage to target creature.",
            "Fixture deals X damage to target creature.",
            "Fixture deals 3 damage divided as you choose among two targets.",
            "Fixture deals 3 damage to target creature and you gain 3 life.",
            "If you control a Mountain, Fixture deals 3 damage to any target.",
        ):
            with self.subTest(text=text):
                ir = self.compile(text)
                node = ir.faces[0].nodes[0]
                self.assertNotEqual("exact", ir.status)
                self.assertIsNone(node.template_id)
                self.assertTrue(ir.material_residuals)

    def test_capability_shape_matching_fails_closed(self):
        template = FixedDamageEffectTemplate(
            amount=3,
            recipient=FixedDamageRecipient.CREATURE,
            source_kind="named",
        )
        mechanics = template.mechanics
        schema = template.target_schema
        expected = {
            "damage.amount.positive",
            "damage.result.multitype_permanent",
            "target.revalidate_resolution",
        }
        self.assertEqual(
            expected,
            set(
                capability_dependencies_for_node(
                    effects=template.effects,
                    target_schema=schema,
                    mechanic_ids=mechanics,
                )
            ),
        )
        malformed_effects = (
            ({**template.effects[0], "amount": 0},),
            ({**template.effects[0], "amount": True},),
            ({**template.effects[0], "target": "$target.1"},),
            ({**template.effects[0], "unknown": 1},),
        )
        for effects in malformed_effects:
            with self.subTest(effects=effects):
                dependencies = capability_dependencies_for_node(
                    effects=effects,
                    target_schema=schema,
                    mechanic_ids=mechanics,
                )
                self.assertNotIn("damage.amount.positive", dependencies)
        self.assertNotIn(
            "damage.amount.positive",
            capability_dependencies_for_node(
                effects=template.effects,
                target_schema={**schema, "zones": ["hand"]},
                mechanic_ids=mechanics,
            ),
        )

    def test_exact_effect_promotion_is_unique_key_and_fail_closed(self):
        registry = SemanticRegistry(include_builtin_packs=False)
        result = register_generated_programs(
            self.db,
            registry,
            (self.db.lookup("Flame Slash"), self.db.lookup("Blood Cultist")),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            promote_exact_effect_programs=True,
        )
        effect_programs = [
            program
            for program in registry.programs()
            if program.effects
        ]
        self.assertEqual(
            2,
            result["exact_fixed_damage_programs_promoted"],
        )
        self.assertEqual(
            {"trusted"},
            {program.trust_level for program in effect_programs},
        )
        self.assertEqual(
            {"spell:front", "ability:ab1"},
            {program.ability_id for program in effect_programs},
        )

        duplicate_registry = SemanticRegistry(include_builtin_packs=False)
        duplicate = register_generated_programs(
            self.db,
            duplicate_registry,
            (self.db.lookup("Resupply"),),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            promote_exact_effect_programs=True,
        )
        self.assertEqual(
            0,
            duplicate["exact_fixed_damage_programs_promoted"],
        )
        duplicate_programs = duplicate_registry.programs()
        self.assertEqual(1, len(duplicate_programs))
        self.assertEqual("provisional", duplicate_programs[0].trust_level)
        self.assertTrue(duplicate_programs[0].requires_arbiter)

        unrelated_record = replace(
            self.base,
            name="Unrelated Fixture",
            oracle_text="Destroy target creature.",
            type_line="Instant",
            keywords=(),
        )
        unrelated_registry = SemanticRegistry(include_builtin_packs=False)
        unrelated = register_generated_programs(
            self.db,
            unrelated_registry,
            (unrelated_record,),
            capability_registry=self.capabilities,
            capability_profile="commander_review",
            promote_exact_effect_programs=True,
        )
        self.assertEqual(
            0,
            unrelated["exact_fixed_damage_programs_promoted"],
        )
        self.assertEqual(
            {"trusted"},
            {
                program.trust_level
                for program in unrelated_registry.programs()
            },
        )
        self.assertFalse(unrelated_registry.programs()[0].requires_arbiter)


class FixedDamageEffectRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def session_with_card(self, card_name: str, *, players: int, seed: int):
        deck = copy.deepcopy(self.mishra)
        replaceable_entry = next(
            entry for entry in deck.entries if entry.board == "mainboard"
        )
        replaceable_entry.name = card_name
        session = make_session(
            self.db,
            deck,
            self.zimone,
            players=players,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.priority_player = None
        engine.state.priority_passes = []
        session.commands.clear()
        session.decisions.clear()
        return session

    @staticmethod
    def stage_spell(session, source, program, *, targets=()):
        engine = session.engine
        engine._remove_from_zone(source)
        engine._reset_zone_change(source, "stack")
        source.zone = "stack"
        source.controller = "A"
        engine.state.stack.append(
            StackItem(
                stack_id=f"stack:{source.ref}",
                ref=f"S-{source.ref}",
                kind="spell",
                controller="A",
                label=source.printed_name,
                card_object_id=source.object_id,
                source_object_id=source.object_id,
                semantic_key=program.key,
                targets=list(targets),
                default_destination="graveyard",
                visibility=list(engine.seats),
                context={"targets_chosen_at_creation": True},
            )
        )
        engine.state.active_player = "A"
        engine.state.started = True
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine._grant_priority("A")
        engine._issue_priority("A")
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

    @staticmethod
    def pass_stack(session):
        while session.state.stack:
            principals = session.pending_principals()
            if not principals:
                raise AssertionError("Stack resolution stopped without priority")
            result = session.act(principals[0], {"action_id": "pass"})
            if not result.ok:
                raise AssertionError(result.summary)

    def assert_replays(self, session):
        expected_hash = authoritative_state_hash(session.state)
        with tempfile.TemporaryDirectory() as temporary:
            record_dir = Path(temporary) / "fixed-damage-effect-record"
            session.save(record_dir)
            replay = replay_record(record_dir, self.db, verify=True)
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(expected_hash, replay["final_state_hash"])

    def test_compiled_target_offer_resolves_and_replays_exactly(self):
        session = self.session_with_card(
            "Flame Slash",
            players=2,
            seed=12011501,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Flame Slash"
        )
        target = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and (
                record := engine.card_record(card)
            ) is not None
            and "creature" in record.type_line.casefold()
        )
        engine.move_card(
            target.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        target.counters["+1/+1"] = 10
        program = next(
            candidate
            for candidate in engine.semantics.programs_for_oracle(
                source.oracle_id
            )
            if candidate.event == "resolve"
        )

        self.assertEqual("trusted", program.trust_level)
        self.assertFalse(program.requires_arbiter)
        public_schema = engine._public_target_schema(
            "A",
            program.target_schema,
            source_ref=source.ref,
        )
        self.assertIn(target.ref, public_schema["legal_refs"])
        self.assertNotIn("B", public_schema["legal_refs"])

        self.stage_spell(session, source, program, targets=(target.ref,))
        self.pass_stack(session)

        self.assertEqual(4, target.marked_damage)
        self.assertEqual("graveyard", source.zone)
        self.assert_replays(session)

    def test_compiled_each_opponent_is_simultaneous_and_replays(self):
        session = self.session_with_card(
            "Breath of Malfegor",
            players=4,
            seed=12011502,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A"
            and card.printed_name == "Breath of Malfegor"
        )
        program = next(
            candidate
            for candidate in engine.semantics.programs_for_oracle(
                source.oracle_id
            )
            if candidate.event == "resolve"
        )
        self.assertEqual("trusted", program.trust_level)
        self.assertIsNone(program.target_schema)

        self.stage_spell(session, source, program)
        self.pass_stack(session)

        self.assertEqual(40, engine.state.players["A"].life)
        self.assertEqual(
            {"B": 35, "C": 35, "D": 35},
            {
                seat: engine.state.players[seat].life
                for seat in ("B", "C", "D")
            },
        )
        damage_events = [
            event
            for event in engine.state.events
            if event.code == "effect.damage"
        ]
        self.assertTrue(damage_events)
        self.assertEqual(
            ["B", "C", "D"],
            damage_events[-1].details["opponents"],
        )
        self.assert_replays(session)

    def test_compiled_activation_offer_executes_and_replays(self):
        session = self.session_with_card(
            "Blood Cultist",
            players=2,
            seed=12011504,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Blood Cultist"
        )
        target = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and (
                record := engine.card_record(card)
            ) is not None
            and "creature" in record.type_line.casefold()
        )
        engine.move_card(
            source.object_id,
            "battlefield",
            controller="A",
            tapped=False,
            log=False,
        )
        engine.move_card(
            target.object_id,
            "battlefield",
            controller="B",
            tapped=False,
            log=False,
        )
        target.counters["+1/+1"] = 10
        engine.state.players["A"].turns_begun = 1
        source.acquired_control_turn_count = 0
        engine._grant_priority("A")
        engine.pump()
        packet = session.packet("pilot:A", full=True)
        action = next(
            row
            for row in packet["decision"]["ctx"]["legal"]["actions"]
            if row["id"] == f"activate:{source.ref}:ab1"
        )
        session.initial_checkpoint = checkpoint_envelope(engine.state)
        session.commands.clear()
        session.decisions.clear()

        self.assertIn(target.ref, action["target_schema"]["legal_refs"])
        self.assertNotIn("B", action["target_schema"]["legal_refs"])
        before_rejection = authoritative_state_hash(engine.state)
        rejected = session.act(
            "pilot:A",
            {
                "action_id": action["id"],
                "targets": ["B"],
            },
        )
        self.assertFalse(rejected.ok)
        self.assertFalse(source.tapped)
        self.assertFalse(engine.state.stack)
        self.assertEqual(before_rejection, authoritative_state_hash(engine.state))
        source = engine.state.cards[source.object_id]
        target = engine.state.cards[target.object_id]

        result = session.act(
            "pilot:A",
            {
                "action_id": action["id"],
                "targets": [target.ref],
            },
        )
        self.assertTrue(result.ok, result.summary)
        self.assertTrue(source.tapped)
        self.assertEqual(source.object_id, engine.state.stack[-1].source_object_id)

        self.pass_stack(session)

        self.assertEqual(1, target.marked_damage)
        self.assert_replays(session)

    def test_opponent_or_planeswalker_relation_is_multiplayer_exact(self):
        session = self.session_with_card(
            "Burning Fields",
            players=4,
            seed=12011503,
        )
        engine = session.engine
        source = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "A" and card.printed_name == "Burning Fields"
        )
        planeswalker = next(
            card
            for card in engine.state.cards.values()
            if (
                record := engine.card_record(card)
            ) is not None
            and "planeswalker" in record.type_line.casefold()
        )
        ordinary_creature = next(
            card
            for card in engine.state.cards.values()
            if (
                record := engine.card_record(card)
            ) is not None
            and "creature" in record.type_line.casefold()
            and "planeswalker" not in record.type_line.casefold()
        )
        engine.move_card(
            planeswalker.object_id,
            "battlefield",
            controller="A",
            log=False,
        )
        engine.move_card(
            ordinary_creature.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        program = next(
            candidate
            for candidate in engine.semantics.programs_for_oracle(
                source.oracle_id
            )
            if candidate.event == "resolve"
        )

        public_schema = engine._public_target_schema(
            "A",
            program.target_schema,
            source_ref=source.ref,
        )
        legal_refs = set(public_schema["legal_refs"])
        self.assertTrue({"B", "C", "D"}.issubset(legal_refs))
        self.assertNotIn("A", legal_refs)
        self.assertIn(planeswalker.ref, legal_refs)
        self.assertNotIn(ordinary_creature.ref, legal_refs)


if __name__ == "__main__":
    unittest.main()
