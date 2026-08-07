from __future__ import annotations

import copy
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from common import keep_all, load_assets, make_session, set_fixture_turn
from quorune.aura import (
    AuraControllerRelation,
    AuraEntryChoiceRequired,
    AuraEntryContinuation,
    SimpleEnchantSpec,
    legal_aura_target_refs,
    parse_simple_enchant_line,
    simple_enchant_spec_from_oracle,
)
from quorune.ability_fragments import (
    ProtectionQualityKind,
    ProtectionSpec,
    ability_fragment_to_dict,
)
from quorune.carddb import CardRecord
from quorune.compiler.program_generation import (
    register_generated_programs,
)
from quorune.model import CardInstance
from quorune.oracle_ir import compile_oracle_card
from quorune.record import checkpoint_envelope, replay_record
from quorune.rules.capabilities import (
    load_default_capability_registry,
)
from quorune.semantics import SemanticProgram
from quorune.errors import GameRuleError
from quorune.model import StackItem


def aura_record(oracle_id: str, *, restriction: str = "creature") -> CardRecord:
    return CardRecord(
        oracle_id=oracle_id,
        name="Exact Test Aura",
        mana_cost="{U}",
        mana_value=1,
        type_line="Enchantment — Aura",
        oracle_text=(
            f"Enchant {restriction}\n"
            "Enchanted creature gets +1/+1."
        ),
        power=None,
        toughness=None,
        loyalty=None,
        defense=None,
        colors=("U",),
        color_identity=("U",),
        keywords=("Enchant",),
        produced_mana=(),
        layout="normal",
        released_at="2026-01-01",
        legalities={"commander": "legal"},
        faces=(),
        raw={},
    )


class SimpleEnchantModelTests(unittest.TestCase):
    def test_model_is_canonical_immutable_and_fingerprinted(self):
        spec = SimpleEnchantSpec(
            " Creature ", AuraControllerRelation.YOU
        )
        self.assertEqual("creature", spec.object_kind)
        self.assertEqual(
            {
                "zones": ["battlefield"],
                "categories": ["permanent"],
                "controller": "you",
                "count": 1,
                "source_exclusion": True,
                "types_all": ["creature"],
            },
            spec.target_schema(),
        )
        restored = SimpleEnchantSpec.from_dict(spec.to_dict())
        self.assertEqual(spec, restored)
        self.assertEqual(spec.fingerprint, restored.fingerprint)
        with self.assertRaisesRegex(ValueError, "unknown"):
            SimpleEnchantSpec.from_dict(
                {**spec.to_dict(), "unexpected": True}
            )
        for malformed in (1, True, {}, None):
            with self.subTest(malformed=malformed):
                with self.assertRaisesRegex(ValueError, "object kind"):
                    SimpleEnchantSpec(malformed)  # type: ignore[arg-type]
        for field, malformed in (
            ("schema_version", True),
            ("object_kind", 1),
            ("controller_relation", False),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    SimpleEnchantSpec.from_dict(
                        {**spec.to_dict(), field: malformed}
                    )

    def test_closed_grammar_accepts_only_reviewed_object_and_relation_shapes(self):
        accepted = {
            "Enchant creature": ("creature", "any"),
            "Enchant land you control": ("land", "you"),
            "Enchant artifact an opponent controls.": (
                "artifact",
                "opponent",
            ),
            "Enchant nonland permanent": (
                "nonland permanent",
                "any",
            ),
            (
                "Enchant creature (Target a creature as you cast this. "
                "This card enters attached to that creature.)"
            ): ("creature", "any"),
        }
        for line, expected in accepted.items():
            with self.subTest(line=line):
                spec = parse_simple_enchant_line(line)
                self.assertIsNotNone(spec)
                assert spec is not None
                self.assertEqual(expected[0], spec.object_kind)
                self.assertEqual(
                    expected[1], spec.controller_relation.value
                )
        for line in (
            "Enchant player",
            "Enchant creature card in a graveyard",
            "Enchant creature with flying",
            "Enchant artifact or creature",
            "Enchant basic land you control",
            "Enchant creature you own",
        ):
            with self.subTest(line=line):
                self.assertIsNone(parse_simple_enchant_line(line))
        self.assertIsNone(
            simple_enchant_spec_from_oracle(
                "Enchant creature\nEnchant land"
            )
        )

    def test_continuation_rejects_malformed_entries(self):
        effect = {"op": "move", "nested": {"values": [1]}}
        value = {
            "schema_version": 1,
            "stack_ref": "S1",
            "source_object_id": "O1",
            "source_logical_object_id": "O1@0",
            "controller": "A",
            "effect": effect,
            "remaining": [],
            "destination": None,
            "note": "",
            "instruction_pointer": 0,
            "semantic_frame": {},
            "spec": SimpleEnchantSpec("creature").to_dict(),
            "advertised_targets": ["C1"],
        }
        restored = AuraEntryContinuation.from_dict(value)
        self.assertEqual(("C1",), restored.advertised_targets)
        effect["nested"]["values"].append(2)
        self.assertEqual(
            (1,), restored.effect["nested"]["values"]
        )
        with self.assertRaisesRegex(ValueError, "remaining"):
            AuraEntryContinuation.from_dict(
                {**value, "remaining": ["not-an-object"]}
            )
        with self.assertRaisesRegex(ValueError, "missing or unknown"):
            AuraEntryContinuation.from_dict(
                {**value, "unknown": True}
            )
        for field, malformed in (
            ("schema_version", True),
            ("destination", 1),
            ("note", {}),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    AuraEntryContinuation.from_dict(
                        {**value, field: malformed}
                    )

    def test_compiler_lowers_only_closed_enchant_grammar_to_trusted_capability(self):
        registry = load_default_capability_registry()
        exact = compile_oracle_card(
            aura_record("fixture:simple-aura"),
            capability_registry=registry,
            capability_profile="commander_review",
        )
        keyword = exact.faces[0].nodes[0]
        self.assertTrue(keyword.exact)
        self.assertEqual(
            ("attachment.aura.simple_object",),
            keyword.capability_dependencies,
        )
        self.assertEqual(
            ["creature"], keyword.target_schema["types_all"]
        )
        self.assertFalse(exact.faces[0].residuals)

        unsupported = compile_oracle_card(
            aura_record(
                "fixture:unsupported-aura",
                restriction="creature with flying",
            ),
            capability_registry=registry,
            capability_profile="commander_review",
        )
        unsupported_keyword = unsupported.faces[0].nodes[0]
        self.assertFalse(unsupported_keyword.exact)
        self.assertIn(
            "mechanic:enchant",
            unsupported.faces[0].residuals[0].blockers,
        )


class AuraTargetingEntryEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.mishra, cls.zimone = load_assets()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def make_session(self, seed: int = 3034):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=2,
            seed=seed,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        engine.state.stack.clear()
        set_fixture_turn(engine, 3)
        engine.state.active_player = "A"
        engine.state.phase = "precombat_main"
        engine.state.step = "main"
        engine.state.priority_player = "A"
        return session

    @staticmethod
    def card(engine, seat: str, name: str):
        return next(
            card
            for card in engine.state.cards.values()
            if card.owner == seat and card.printed_name == name
        )

    def fixture(self, *, restriction: str = "creature"):
        session = self.make_session()
        engine = session.engine
        aura = self.card(engine, "A", "Island")
        target = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and engine.card_record(card) is not None
            and "creature"
            in engine.card_record(card).type_line.casefold()
        )
        engine.move_card(aura.object_id, "hand", log=False)
        engine.move_card(
            target.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        record = aura_record(aura.oracle_id, restriction=restriction)
        original = engine.card_record

        def record_for(value):
            instance = (
                value
                if hasattr(value, "object_id")
                else engine.state.cards[value]
            )
            return (
                record
                if instance.object_id == aura.object_id
                else original(value)
            )

        @contextmanager
        def compiled_record():
            engine_type = type(engine)
            original_trust = engine_type.semantic_program_is_current_trusted

            def trust_fixture_program(host, program):
                return bool(
                    program is not None
                    and program.oracle_id == record.oracle_id
                    and program.trust_level == "trusted"
                ) or original_trust(host, program)

            with patch.object(
                engine, "card_record", side_effect=record_for
            ), patch.object(
                engine_type,
                "semantic_program_is_current_trusted",
                new=trust_fixture_program,
            ):
                register_generated_programs(
                    engine.card_db,
                    engine.semantics,
                    (record,),
                    capability_registry=load_default_capability_registry(),
                    capability_profile=engine.state.config.review_profile,
                    promote_exact_runtime_handlers=True,
                )
                yield

        return session, aura, target, compiled_record()

    def add_fixture_aura(self, engine, seat: str, zone: str):
        record = aura_record("fixture:simple-aura")
        card = CardInstance(
            object_id=uuid.uuid4().hex,
            ref=f"AURA-{len(engine.state.cards) + 1}",
            oracle_id=record.oracle_id,
            printed_name=record.name,
            owner=seat,
            controller=seat,
            zone=zone,
            known_to=(
                [seat]
                if zone in {"hand", "library"}
                else list(engine.seats)
            ),
            revealed_to=(
                []
                if zone in {"hand", "library"}
                else list(engine.seats)
            ),
        )
        engine.state.cards[card.object_id] = card
        engine.state.players[seat].zones[zone].append(card.object_id)
        return card

    @staticmethod
    def fixture_aura_records(engine):
        engine_type = type(engine)
        original = engine_type.card_record

        def record_for(host, value):
            instance = (
                value
                if hasattr(value, "object_id")
                else host.state.cards[value]
            )
            if instance.oracle_id == "fixture:simple-aura":
                return aura_record(instance.oracle_id)
            return original(host, value)

        @contextmanager
        def compiled_record():
            record = aura_record("fixture:simple-aura")
            original_trust = (
                engine_type.semantic_program_is_current_trusted
            )

            def trust_fixture_program(host, program):
                return bool(
                    program is not None
                    and program.oracle_id == record.oracle_id
                    and program.trust_level == "trusted"
                ) or original_trust(host, program)

            with patch.object(
                engine_type, "card_record", new=record_for
            ), patch.object(
                engine_type,
                "semantic_program_is_current_trusted",
                new=trust_fixture_program,
            ):
                register_generated_programs(
                    engine.card_db,
                    engine.semantics,
                    (record,),
                    capability_registry=load_default_capability_registry(),
                    capability_profile=engine.state.config.review_profile,
                    promote_exact_runtime_handlers=True,
                )
                yield

        return compiled_record()

    def test_aura_offer_requires_and_projects_one_legal_spell_target(self):
        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.state.players["A"].mana_pool["U"] = 1
        with records:
            hints = engine._priority_action_hints("A")
            action = next(
                action
                for action in hints["actions"]
                if action.get("card") == aura.ref
            )
            self.assertEqual([target.ref], action["target_schema"]["legal_refs"])
            before = copy.deepcopy(engine.state.to_dict())
            with self.assertRaisesRegex(GameRuleError, "requires between"):
                with engine.transaction():
                    engine._cast(
                        "A",
                        {
                            "card": aura.ref,
                            "pay": "manual",
                            "payment": {"U": 1},
                        },
                    )
            self.assertEqual(before, engine.state.to_dict())

    def test_spell_resolution_attaches_and_illegal_target_counters_by_rule(self):
        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.state.players["A"].mana_pool["U"] = 1
        with records:
            engine._cast(
                "A",
                {
                    "card": aura.ref,
                    "targets": [target.ref],
                    "pay": "manual",
                    "payment": {"U": 1},
                },
            )
            item = engine.state.stack[-1]
            self.assertTrue(item.context["aura_spell"])
            engine.permissions.invalidate_current()
            engine.state.pending_decision = None
            engine.state.priority_player = None
            engine._prepare_stack_resolution()
            self.assertEqual("battlefield", aura.zone)
            self.assertEqual(target.object_id, aura.attached_to)
            self.assertIn(aura.object_id, target.attachments)

        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.state.players["A"].mana_pool["U"] = 1
        with records:
            engine._cast(
                "A",
                {
                    "card": aura.ref,
                    "targets": [target.ref],
                    "pay": "manual",
                    "payment": {"U": 1},
                },
            )
            engine.move_card(
                target.object_id,
                "graveyard",
                reason="remove Aura target",
                log=False,
            )
            engine.permissions.invalidate_current()
            engine.state.pending_decision = None
            engine.state.priority_player = None
            engine._prepare_stack_resolution()
            self.assertEqual("graveyard", aura.zone)
            self.assertFalse(engine.state.stack)

    def test_live_aura_paths_never_recompile_oracle_text(self):
        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.state.players["A"].mana_pool["U"] = 1
        with records, patch(
            "quorune.aura.grammar.simple_enchant_spec_from_oracle",
            side_effect=AssertionError("runtime Oracle compiler invoked"),
        ):
            hints = engine._priority_action_hints("A")
            self.assertIn(
                aura.ref,
                {
                    action.get("card")
                    for action in hints["actions"]
                },
            )
            engine._cast(
                "A",
                {
                    "card": aura.ref,
                    "targets": [target.ref],
                    "pay": "manual",
                    "payment": {"U": 1},
                },
            )
            engine.permissions.invalidate_current()
            engine.state.pending_decision = None
            engine.state.priority_player = None
            engine._prepare_stack_resolution()
            self.assertEqual(target.object_id, aura.attached_to)

    def test_nonspell_entry_pauses_for_choice_and_resumes_exact_effect(self):
        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.move_card(aura.object_id, "graveyard", log=False)
        item = StackItem(
            stack_id="test-aura-entry",
            ref="S-aura-entry",
            kind="spell",
            controller="A",
            label="Return an Aura",
            semantic_key="test:aura-entry",
            visibility=["A", "B"],
        )
        engine.state.stack.append(item)
        with records:
            engine._continue_resolution(
                stack_ref=item.ref,
                effects=[
                    {
                        "op": "move",
                        "card": aura.ref,
                        "destination": "battlefield",
                        "controller": "A",
                    }
                ],
                destination=None,
                note="Aura nonspell entry",
            )
            self.assertEqual("aura.entry", engine.state.pending_decision.kind)
            self.assertEqual("graveyard", aura.zone)
            capability = engine.permissions.capability_for("pilot:A")
            self.assertIsNotNone(capability)
            result = engine.submit(
                token=capability.token,
                principal="pilot:A",
                action="choose",
                payload={"aura_target": target.ref},
            )
            self.assertTrue(result.ok)
            self.assertEqual("battlefield", aura.zone)
            self.assertEqual(target.object_id, aura.attached_to)
            self.assertNotIn(item, engine.state.stack)

    def test_nonspell_entry_with_no_legal_object_stays_in_origin_zone(self):
        session, aura, target, records = self.fixture()
        engine = session.engine
        engine.move_card(target.object_id, "graveyard", log=False)
        engine.move_card(aura.object_id, "graveyard", log=False)
        with records:
            moved = engine.move_card(
                aura.object_id,
                "battlefield",
                controller="A",
                semantic_events=True,
            )
        self.assertIs(moved, aura)
        self.assertEqual("graveyard", aura.zone)
        self.assertIsNone(aura.attached_to)

    def test_aura_tokens_preflight_attachment_and_no_legal_object_is_not_created(self):
        session, _aura, target, records = self.fixture()
        engine = session.engine
        characteristics = {
            "type_line": "Token Enchantment — Aura",
            "oracle_text": "Enchant creature",
            "colors": ["U"],
            "ability_fragments": [
                ability_fragment_to_dict(
                    SimpleEnchantSpec("creature")
                )
            ],
        }
        with records:
            before = copy.deepcopy(engine.state.to_dict())
            with self.assertRaisesRegex(
                GameRuleError, "requires a legal attachment choice"
            ):
                engine.create_token(
                    "A",
                    name="Test Aura",
                    characteristics=characteristics,
                )
            self.assertEqual(before, engine.state.to_dict())

            created = engine.create_token(
                "A",
                name="Test Aura",
                characteristics=characteristics,
                aura_target_ref=target.ref,
            )
            self.assertEqual(1, len(created))
            token = engine._resolve_object(
                "A", created[0], zones={"battlefield"}
            )
            self.assertEqual(target.object_id, token.attached_to)

            engine.move_card(token.object_id, "graveyard", log=False)
            engine.move_card(target.object_id, "graveyard", log=False)
            self.assertEqual(
                [],
                engine.create_token(
                    "A",
                    name="Test Aura",
                    characteristics=characteristics,
                ),
            )
            self.assertFalse(
                any(
                    card.is_token and card.zone == "battlefield"
                    for card in engine.state.cards.values()
                )
            )

    def test_unsupported_enchant_grammar_fails_before_mutation(self):
        session, aura, target, records = self.fixture(
            restriction="creature with flying"
        )
        engine = session.engine
        before = copy.deepcopy(engine.state.to_dict())
        with records, self.assertRaisesRegex(
            GameRuleError, "compiled Enchant descriptor"
        ):
            engine.move_card(
                aura.object_id,
                "battlefield",
                controller="A",
                aura_target_ref=target.ref,
            )
        self.assertEqual(before, engine.state.to_dict())

    def test_control_relation_and_protection_are_live_attachment_legality(self):
        session, aura, target, records = self.fixture(
            restriction="creature you control"
        )
        engine = session.engine
        engine.change_control(target.object_id, "A")
        with records:
            engine.move_card(
                aura.object_id,
                "battlefield",
                controller="A",
                aura_target_ref=target.ref,
            )
            self.assertTrue(
                engine._attachment_is_legal(aura, subtypes={"aura"})
            )
            engine.change_control(target.object_id, "B")
            self.assertFalse(
                engine._attachment_is_legal(aura, subtypes={"aura"})
            )
            engine.change_control(target.object_id, "A")
            target.annotations["copy_overrides"] = {
                "keywords": ["Protection"],
                "ability_fragments": [
                    ability_fragment_to_dict(
                        ProtectionSpec(
                            ProtectionQualityKind.COLOR,
                            "U",
                        )
                    )
                ],
            }
            self.assertFalse(
                engine._attachment_is_legal(aura, subtypes={"aura"})
            )
            self.assertFalse(engine._stabilize())
            self.assertEqual("graveyard", aura.zone)

    def test_four_player_aura_targets_and_relations_are_seat_correct(self):
        session = make_session(
            self.db,
            self.mishra,
            self.zimone,
            players=4,
            seed=303404,
            auto_pass_empty=False,
        )
        keep_all(session)
        engine = session.engine
        engine.permissions.invalidate_current()
        engine.state.pending_decision = None
        targets = []
        for seat in engine.seats:
            creature = next(
                card
                for card in engine.state.cards.values()
                if card.owner == seat
                and engine.card_record(card) is not None
                and "creature"
                in engine.card_record(card).type_line.casefold()
            )
            engine.move_card(
                creature.object_id,
                "battlefield",
                controller=seat,
                log=False,
            )
            targets.append(creature)
        aura = self.add_fixture_aura(engine, "A", "hand")
        with self.fixture_aura_records(engine):
            any_targets = legal_aura_target_refs(
                engine,
                aura,
                SimpleEnchantSpec("creature"),
                controller="A",
                as_target=True,
            )
        self.assertEqual(
            {card.ref for card in targets}, set(any_targets)
        )
        with self.fixture_aura_records(engine):
            own_targets = legal_aura_target_refs(
                engine,
                aura,
                SimpleEnchantSpec(
                    "creature", AuraControllerRelation.YOU
                ),
                controller="A",
                as_target=True,
            )
        self.assertEqual(
            {card.ref for card in targets if card.controller == "A"},
            set(own_targets),
        )

    def test_aura_entry_choice_projection_and_replay_are_exact(self):
        session = self.make_session(seed=303405)
        engine = session.engine
        target = next(
            card
            for card in engine.state.cards.values()
            if card.owner == "B"
            and engine.card_record(card) is not None
            and "creature"
            in engine.card_record(card).type_line.casefold()
        )
        engine.move_card(
            target.object_id,
            "battlefield",
            controller="B",
            log=False,
        )
        protected_ref = engine.create_token(
            "B",
            name="Protection Replay Witness",
            characteristics={
                "type_line": "Token Creature — Test",
                "oracle_text": "Protection from blue",
                "keywords": ["Protection"],
                "power": "2",
                "toughness": "2",
                "ability_fragments": [
                    ability_fragment_to_dict(
                        ProtectionSpec(
                            ProtectionQualityKind.COLOR,
                            "U",
                        )
                    )
                ],
            },
        )[0]
        aura = self.add_fixture_aura(engine, "A", "graveyard")
        engine.semantics.put(
            SemanticProgram(
                key="test:aura-replay",
                label="Return Aura replay witness",
                effects=[
                    {
                        "op": "move",
                        "card": aura.ref,
                        "destination": "battlefield",
                        "controller": "A",
                    }
                ],
                trust_level="provisional",
            )
        )
        item = StackItem(
            stack_id="aura-replay-stack",
            ref="S-aura-replay",
            kind="spell",
            controller="A",
            label="Return Aura replay witness",
            semantic_key="test:aura-replay",
            visibility=list(engine.seats),
        )
        engine.state.stack.append(item)
        with self.fixture_aura_records(engine):
            engine._continue_resolution(
                stack_ref=item.ref,
                effects=[
                    {
                        "op": "move",
                        "card": aura.ref,
                        "destination": "battlefield",
                        "controller": "A",
                    }
                ],
                destination=None,
                note="Aura replay witness",
            )
            self.assertEqual(
                "aura.entry", engine.state.pending_decision.kind
            )
            packet = session.packet("pilot:A", full=True)
            rendered = json.dumps(packet, sort_keys=True)
            self.assertIn(target.ref, rendered)
            legal_refs = packet["decision"]["ctx"]["target_schema"][
                "legal_refs"
            ]
            self.assertIn(target.ref, legal_refs)
            self.assertNotIn(protected_ref, legal_refs)
            self.assertNotIn(target.object_id, rendered)
            self.assertNotIn(aura.object_id, rendered)

            session.initial_checkpoint = checkpoint_envelope(engine.state)
            session.commands.clear()
            session.decisions.clear()
            result = session.act(
                "pilot:A",
                {"action_id": "choose", "aura_target": target.ref},
            )
            self.assertTrue(result.ok, result.summary)
            self.assertEqual(target.object_id, aura.attached_to)
            with tempfile.TemporaryDirectory() as temporary:
                record_dir = Path(temporary) / "aura-replay"
                session.save(record_dir)
                replay = replay_record(
                    record_dir, self.db, verify=True
                )
        self.assertTrue(replay["ok"], replay)
        self.assertEqual(1, replay["commands"])


if __name__ == "__main__":
    unittest.main()
